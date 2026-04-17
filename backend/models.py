

from __future__ import annotations

import logging
import os
import pickle
import re
import warnings
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
import rasterio
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from statsmodels.tsa.statespace.sarimax import SARIMAX

warnings.filterwarnings("ignore")
logger = logging.getLogger(__name__)

from config import DIRECTORIES

# Directory paths
PET_DIR = DIRECTORIES["raw"]["insat_pet"]
KC_DIR  = DIRECTORIES["processed"]["kc"]

MODEL_DIR = DIRECTORIES["models"]
os.makedirs(MODEL_DIR, exist_ok=True)

PET_MODEL_PATH = MODEL_DIR / "sarimax_wheat_pet.pkl"
KC_MODEL_PATH  = MODEL_DIR / "sarimax_wheat_kc.pkl"

CWR_MAX = 15.0


# Physics Wrappers
class _PhysicsIWR:
    def predict(self, cwr: np.ndarray, peff: np.ndarray) -> np.ndarray:
        return np.maximum(np.asarray(cwr) - np.asarray(peff), 0.0)

class _PhysicsCWR:
    def predict(self, kc: np.ndarray, pet: np.ndarray) -> np.ndarray:
        cwr = np.asarray(kc) * np.asarray(pet)
        return np.clip(cwr, 0.0, CWR_MAX)

# At the top of models.py (replace the current extract_date)
def extract_date(filename: str) -> datetime:
    m = re.search(r"\d{8}", filename)
    if m:
        return datetime.strptime(m.group(), "%Y%m%d")
    m = re.search(r"\d{2}[A-Z]{3}\d{4}", filename.upper())
    if m:
        return datetime.strptime(m.group(), "%d%b%Y")
    raise ValueError(f"No valid date in filename: {filename}")

def build_date_file_map(directory: Path) -> Dict[datetime, Path]:
    fm: Dict[datetime, Path] = {}
    if not directory.exists():
        return fm
    for fp in directory.glob("*.tif"):
        try:
            fm[extract_date(fp.name)] = fp
        except Exception:
            pass
    return fm


# Exogenous variables (DOY = Day of Year)
def create_exog(dates: pd.DatetimeIndex) -> pd.DataFrame:
    df = pd.DataFrame(index=dates)
    df["doy"] = dates.dayofyear
    df["doy_sin"] = np.sin(2 * np.pi * df["doy"] / 365.25)
    df["doy_cos"] = np.cos(2 * np.pi * df["doy"] / 365.25)
    return df


def build_forecast_exog(
    future_dates: pd.DatetimeIndex,
    last_pet: float = None,
    exog_cols: List[str] = None,
) -> pd.DataFrame:
    """
    Build the exog DataFrame for out-of-sample SARIMAX forecasting.
    Column names are aligned to what create_exog() produces so they always
    match the structure the model was trained on.

    FIX: This function was referenced in main.py but never existed, causing
    NameError on every call → both PET and Kc fell back to flat persistence.
    """
    # Build the full DOY feature frame (same as training)
    df = create_exog(future_dates)

    if exog_cols:
        # Map alternate spellings used in old meta dicts to actual column names
        alias = {
            "sin_doy": "doy_sin",
            "cos_doy": "doy_cos",
        }
        resolved = [alias.get(c, c) for c in exog_cols]
        available = [c for c in resolved if c in df.columns]
        if available:
            return df[available]

    # Default: return the two DOY harmonic features (what train_all_models uses)
    return df[["doy_sin", "doy_cos"]]


# SARIMAX Training
def train_sarimax(
    ts_data: pd.Series,
    exog: pd.DataFrame = None,
    order: Tuple[int, int, int] = (2, 1, 2),
    seasonal_order: Tuple[int, int, int, int] = (1, 0, 1, 12),
    model_name: str = "unknown"
) -> Tuple[SARIMAX, dict]:
    model = SARIMAX(
        ts_data,
        exog=exog,
        order=order,
        seasonal_order=seasonal_order,
        enforce_stationarity=False,
        enforce_invertibility=False,
    )
    results = model.fit(disp=False, maxiter=500)

    # Metrics
    n_eval = max(1, len(ts_data) // 5)
    mae = mean_absolute_error(ts_data.iloc[-n_eval:], results.fittedvalues.iloc[-n_eval:])
    rmse = float(np.sqrt(mean_squared_error(ts_data.iloc[-n_eval:], results.fittedvalues.iloc[-n_eval:])))
    r2 = r2_score(ts_data.iloc[-n_eval:], results.fittedvalues.iloc[-n_eval:])

    # Store the exog column names so forecasting code can build matching exog
    exog_cols = list(exog.columns) if exog is not None else []
    meta = {
        "metrics": {"MAE": mae, "RMSE": rmse, "R2": r2},
        "order": order,
        "seasonal_order": seasonal_order,
        "last_date": ts_data.index[-1],
        "exog_cols": exog_cols,          # <-- FIX: was missing; caused wrong exog at forecast time
        "note": f"SARIMAX for {model_name}"
    }

    logger.info(f"✓ SARIMAX {model_name} trained → MAE={mae:.4f}, RMSE={rmse:.4f}, R²={r2:.4f}")
    return results, meta


def save_model(model: SARIMAX, meta: dict, path: Path) -> None:
    with open(path, "wb") as f:
        pickle.dump({"model": model, "meta": meta}, f)
    logger.info(f"Model saved: {path}")


def load_model(model_type: str) -> Tuple[SARIMAX, dict]:
    path = PET_MODEL_PATH if model_type == "pet" else KC_MODEL_PATH
    if not path.exists():
        raise FileNotFoundError(f"Model not found: {path}")
    with open(path, "rb") as f:
        obj = pickle.load(f)
    return obj["model"], obj["meta"]


# Forecasting without forcing same value
def forecast_with_sarimax(model_type: str, steps: int = 15) -> np.ndarray:
    """Pure SARIMAX forecast — no anchoring to latest observed value"""
    model, meta = load_model(model_type)

    last_date = meta["last_date"]
    future_dates = pd.date_range(last_date + pd.Timedelta(days=1), periods=steps, freq='D')
    future_exog = create_exog(future_dates)

    forecast = model.get_forecast(steps=steps, exog=future_exog)
    pred = forecast.predicted_mean.values

    # Kc ke liye FAO-56 bounds
    if model_type == "kc":
        pred = np.clip(pred, 0.25, 1.25)

    return pred


# Physics Chain
def compute_iwr_from_forecasts(
    kc_forecast: np.ndarray,
    pet_forecast: np.ndarray,
    peff_clim: np.ndarray = None,
) -> np.ndarray:
    if peff_clim is None:
        peff_clim = np.zeros_like(kc_forecast)

    cwr_model = _PhysicsCWR()
    cwr_forecast = cwr_model.predict(kc_forecast, pet_forecast)

    iwr_model = _PhysicsIWR()
    return iwr_model.predict(cwr_forecast, peff_clim)


# Train both models
def train_all_models() -> Dict[str, dict]:
    results: Dict[str, dict] = {}

    # Kc
    kc_map = build_date_file_map(KC_DIR)
    kc_series = _rasters_to_series(kc_map)
    kc_exog = create_exog(kc_series.index)

    logger.info("Training SARIMAX for Kc...")
    # kc_model, kc_meta = train_sarimax(kc_series, exog=kc_exog, model_name="Kc")
    kc_model, kc_meta = train_sarimax(
    kc_series,
    exog=kc_exog,
    order=(1, 0, 1),
    seasonal_order=(1, 0, 0, 7),
    model_name="Kc"
)
    save_model(kc_model, kc_meta, KC_MODEL_PATH)
    results["kc"] = kc_meta["metrics"]

    # PET
    pet_map = build_date_file_map(PET_DIR)
    pet_series = _rasters_to_series(pet_map)
    pet_exog = create_exog(pet_series.index)

    logger.info("Training SARIMAX for PET...")
    pet_model, pet_meta = train_sarimax(pet_series, exog=pet_exog, model_name="PET")
    save_model(pet_model, pet_meta, PET_MODEL_PATH)
    results["pet"] = pet_meta["metrics"]

    logger.info("✓ Both SARIMAX models trained successfully!")
    return results


def _rasters_to_series(file_map: Dict[datetime, Path]) -> pd.Series:
    """Helper: Convert rasters to time series (spatial mean)"""
    records: List[Tuple[datetime, float]] = []
    for date, path in sorted(file_map.items()):
        try:
            with rasterio.open(path) as src:
                data = src.read(1).astype(np.float64)
                if src.nodata is not None:
                    data[data == src.nodata] = np.nan
                val = float(np.nanmean(data))
                if np.isfinite(val):
                    records.append((date, val))
        except Exception as exc:
            logger.warning(f"Could not read {path.name}: {exc}")

    if not records:
        raise RuntimeError(
            f"No valid raster data found in directory for time series. "
            f"Check that raw/insat_pet/ (for PET) or processed/kc/ (for Kc) "
            f"contains valid .tif files with readable mean values."
        )

    dates, vals = zip(*records)
    series = pd.Series(list(vals), index=pd.DatetimeIndex(list(dates)), dtype=np.float64)
    return series.sort_index().drop_duplicates(keep="last")