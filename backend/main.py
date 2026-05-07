import logging
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import rasterio
import rasterio.warp
import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from rasterio.enums import Resampling
from rasterio.warp import transform as warp_transform
import os
from dotenv import load_dotenv
from config import (
    STUDY_AREA, DIRECTORIES, GEOSERVER, SARIMAX_CONFIG,
    WHEAT_PARAMS
)
from logging_config import setup_logging
import models
from models import (
    build_forecast_exog,      # out-of-sample exog builder for SARIMAX/Ridge
    set_forecast_context,     # injects last observed SAVI/Kc into exog builder
    raster_mean,              # spatial mean utility
    savi_to_kc,               # physics: Kc = KC_SLOPE × SAVI + KC_INTERCEPT
    get_wheat_stage_info,
    get_wheat_stage_kc,
    KC_SLOPE,
    KC_INTERCEPT,
    KC_MIN,
    KC_MAX,
)

setup_logging()
logger = logging.getLogger(__name__)

# Physical constants sourced from models.py (thesis linear regression)
# KC_SLOPE, KC_INTERCEPT, KC_MIN, KC_MAX imported above from models
CWR_MIN      = 0.0
CWR_MAX      = 15.0


# ═══════════════════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════

HISTORY_DATES  = 20   # ← increased from 12 for fuller calendar coverage
FORECAST_DAYS  = 15
NODATA         = -9999.0
PARAMS         = ["savi", "kc", "cwr", "iwr"]
SLOTS: List[str] = ["today"] + [str(i) for i in range(1, HISTORY_DATES)]
FORECAST_WINDOWS = ["5day", "10day", "15day"]
WINDOW_DAYS      = {"5day": 5, "10day": 10, "15day": 15}

_VALID: Dict[str, Tuple[float, float]] = {
    "savi": (-1.0, 1.0),
    "kc":   (KC_MIN, KC_MAX),
    "cwr":  (CWR_MIN, CWR_MAX),
    "iwr":  (0.0, CWR_MAX),
}

_SRC: Dict[str, Tuple[Path, str]] = {
    "savi": (DIRECTORIES["processed"]["savi"], "savi_*.tif"),
    "kc":   (DIRECTORIES["processed"]["kc"],   "kc_*.tif"),
    "cwr":  (DIRECTORIES["processed"]["cwr"],  "cwr_*.tif"),
    "iwr":  (DIRECTORIES["processed"]["iwr"],  "iwr_*.tif"),
}

EXPORT_DIR   = DIRECTORIES["export"]["geoserver"]
HISTORY_DIR  = EXPORT_DIR / "history"
FORECAST_DIR = EXPORT_DIR / "forecast"

for _param in PARAMS:
    (HISTORY_DIR / _param).mkdir(parents=True, exist_ok=True)
    (FORECAST_DIR / _param).mkdir(parents=True, exist_ok=True)


# ═══════════════════════════════════════════════════════════════════════════
# GLOBAL MODEL CACHE
# ═══════════════════════════════════════════════════════════════════════════

_MODEL_CACHE: Dict = {}

# Forecast dataset cache — scheduler.py sets counts to -1 to force reload
_fc_cache: Dict = {"pet_count": -1}


def _get_model(model_type: str):
    """Load and cache trained SARIMAx models.
    Supported types: 'pet', 'kc', 'savi'
    """
    global _MODEL_CACHE

    if model_type in _MODEL_CACHE:
        return _MODEL_CACHE[model_type]

    try:
        model, meta = models.load_model(model_type)
        _MODEL_CACHE[model_type] = (model, meta)
        logger.info(f"✓ Loaded {model_type.upper()} SARIMAx model "
                    f"(R²={meta['metrics']['R2']:.4f})")
        return model, meta
    except FileNotFoundError:
        logger.warning(f"Model {model_type} not found — training now...")
        models.train_all_models()
        model, meta = models.load_model(model_type)
        _MODEL_CACHE[model_type] = (model, meta)
        return model, meta
    except Exception as e:
        logger.error(f"Failed to load {model_type} model: {e}")
        return None, None
# ═══════════════════════════════════════════════════════════════════════════
# PATH HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def history_path(param: str, slot: str) -> Path:
    return HISTORY_DIR / param / f"{param}_{slot}.tif"


def forecast_path(param: str, slot: str, window: str) -> Path:
    return FORECAST_DIR / param / f"{param}_{slot}_{window}.tif"


def slot_for_index(idx: int) -> str:
    return "today" if idx == 0 else str(idx)


# ═══════════════════════════════════════════════════════════════════════════
# DATA LOADING HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def _parse_date(name: str) -> Optional[datetime]:
    m = re.search(r"\d{8}", name)
    if m:
        try:
            return datetime.strptime(m.group(), "%Y%m%d")
        except ValueError:
            pass
    return None


def _dated_files(directory: Path, pattern: str) -> List[Tuple[datetime, Path]]:
    out = []
    for p in directory.glob(pattern):
        d = _parse_date(p.name)
        if d:
            out.append((d, p))
    out.sort(key=lambda x: x[0])
    return out


def _latest_n_complete_dates(n: int = HISTORY_DATES) -> List[datetime]:
    """N most-recent dates where ALL parameters have processed rasters. Newest-first."""
    date_sets = []
    for param, (src_dir, pattern) in _SRC.items():
        dates = {d for d, _ in _dated_files(src_dir, pattern)}
        if not dates:
            logger.warning(f"No {param} files in {src_dir}")
            return []
        date_sets.append(dates)

    complete = set.intersection(*date_sets)
    return sorted(complete, reverse=True)[:n]


def _read_mean(path: Path) -> Optional[float]:
    """Spatial mean of valid (non-NODATA) pixels from a raster file."""
    if not path.exists():
        return None
    try:
        with rasterio.open(path) as src:
            data = src.read(1).astype(np.float64)
            nd   = float(src.nodata) if src.nodata else float(NODATA)
            data[data == np.float64(nd)] = np.nan
            v = float(np.nanmean(data))
            return None if np.isnan(v) else round(v, 4)
    except Exception:
        return None


def _processed_mean_for_date(param: str, date: datetime) -> Optional[float]:
    """Read the processed raster mean for the requested parameter/date."""
    src = _SRC.get(param)
    if src is None:
        return None

    src_dir, pattern = src
    date_key = date.replace(hour=0, minute=0, second=0, microsecond=0)
    for d, path in _dated_files(src_dir, pattern):
        if d == date_key:
            return _read_mean(path)
    return None


def _reference_mean(param: str, reference_date: datetime, fallback: Optional[float] = None) -> Optional[float]:
    """
    Forecasts may be generated for any history slot, not only "today".
    Prefer the raster from the actual reference date, then the matching
    exported history slot, then the supplied fallback.
    """
    value = _processed_mean_for_date(param, reference_date)
    if value is not None:
        return value

    for idx, d in enumerate(_latest_n_complete_dates(HISTORY_DATES)):
        if d.date() == reference_date.date():
            value = _read_mean(history_path(param, slot_for_index(idx)))
            if value is not None:
                return value

    return fallback


def _load_slot_array(param: str, slot: str) -> Optional[np.ndarray]:
    """Load a history slot raster array (NaN for NODATA pixels)."""
    p = history_path(param, slot)
    if not p.exists():
        return None
    try:
        with rasterio.open(p) as src:
            data = src.read(1).astype(np.float64)
            nd   = float(src.nodata) if src.nodata is not None else float(NODATA)
            data[data == np.float64(nd)]       = np.nan
            data[data == np.float64(NODATA)]   = np.nan
        return data
    except Exception as e:
        logger.error(f"[load] {p.name}: {e}")
        return None


# ═══════════════════════════════════════════════════════════════════════════
# WHEAT MASK
# ═══════════════════════════════════════════════════════════════════════════

_WHEAT_MASK_CACHE: Optional[Dict] = None


def _get_wheat_mask() -> Optional[Dict]:
    global _WHEAT_MASK_CACHE
    if _WHEAT_MASK_CACHE is not None:
        return _WHEAT_MASK_CACHE

    mask_path = DIRECTORIES["processed"]["masks"] / "wheat_mask.tif"
    if not mask_path.exists():
        logger.error(f"wheat_mask.tif not found: {mask_path}")
        return None

    try:
        with rasterio.open(mask_path) as src:
            raw = src.read(1)
            _WHEAT_MASK_CACHE = {
                "crs":       src.crs,
                "transform": src.transform,
                "width":     src.width,
                "height":    src.height,
                "mask_bool": (raw > 0),
            }
        logger.info(
            f"Wheat mask: {_WHEAT_MASK_CACHE['width']}×{_WHEAT_MASK_CACHE['height']} | "
            f"wheat pixels = {_WHEAT_MASK_CACHE['mask_bool'].sum():,}"
        )
    except Exception as e:
        logger.error(f"Failed to load wheat_mask: {e}")
    return _WHEAT_MASK_CACHE


# ═══════════════════════════════════════════════════════════════════════════
# RASTER I/O
# ═══════════════════════════════════════════════════════════════════════════

def cleanup_old_rasters():
    for param in PARAMS:
        valid_history  = {f"{param}_{s}.tif" for s in SLOTS}
        valid_forecast = {
            f"{fc_param}_{s}_{w}.tif"
            for fc_param in ["kc", "cwr", "iwr"]
            for s in SLOTS
            for w in FORECAST_WINDOWS
        }
        for f in (HISTORY_DIR / param).glob("*.tif"):
            if f.name not in valid_history:
                f.unlink()
        for f in (FORECAST_DIR / param).glob("*.tif"):
            if f.name not in valid_forecast:
                f.unlink()


def _reproject_and_write(
    src_path: Path,
    dst_path: Path,
    param: str,
    date: datetime,
    extra_tags: Optional[Dict] = None,
) -> bool:
    """Reproject processed raster → wheat-mask grid, clamp, mask, write."""
    grid = _get_wheat_mask()
    if grid is None:
        return False

    vmin, vmax = _VALID.get(param, (-1e9, 1e9))

    try:
        with rasterio.open(src_path) as src:
            data       = src.read(1).astype(np.float64)
            src_nd     = src.nodata
            src_crs    = src.crs
            src_trans  = src.transform

        if src_nd is not None:
            data[data == np.float64(src_nd)] = np.nan
        data[data == np.float64(-9999.0)] = np.nan
        data[data == np.float64(-999.0)]  = np.nan

        dst = np.full((grid["height"], grid["width"]), np.nan, dtype=np.float64)
        rasterio.warp.reproject(
            source=data,
            destination=dst,
            src_transform=src_trans,
            src_crs=src_crs,
            dst_transform=grid["transform"],
            dst_crs=grid["crs"],
            resampling=Resampling.nearest,
            src_nodata=None,
            dst_nodata=None,
        )

        dst[dst > vmax] = np.nan
        if param == "cwr":
            dst[(~np.isnan(dst)) & (dst <= 0.0)] = np.nan
        dst[dst < vmin] = np.nan
        dst[~grid["mask_bool"]] = np.nan

        out     = np.where(np.isnan(dst), float(NODATA), dst).astype(np.float64)
        profile = {
            "driver":     "GTiff",
            "dtype":      rasterio.float64,
            "count":      1,
            "crs":        grid["crs"],
            "transform":  grid["transform"],
            "width":      grid["width"],
            "height":     grid["height"],
            "nodata":     float(NODATA),
            "compress":   "lzw",
            "tiled":      True,
            "blockxsize": 256,
            "blockysize": 256,
        }

        dst_path.parent.mkdir(parents=True, exist_ok=True)
        with rasterio.open(dst_path, "w", **profile) as f:
            f.write(out, 1)
            mean_val = float(np.nanmean(dst)) if np.any(~np.isnan(dst)) else None
            tags = {
                "parameter":        param,
                "acquisition_date": date.strftime("%Y-%m-%d"),
                "mean":             str(round(mean_val, 4)) if mean_val is not None else "",
            }
            if extra_tags:
                tags.update(extra_tags)
            f.update_tags(**tags)
        return True
    except Exception as e:
        logger.error(f"[raster] {src_path.name}→{dst_path.name}: {e}")
        return False


def _write_array_raster(
    data: np.ndarray,
    template: Path,
    dst_path: Path,
    tags: Dict,
) -> bool:
    """Write a NumPy array as a GeoTIFF using `template` for georef metadata."""
    try:
        with rasterio.open(template) as src:
            profile = src.profile.copy()
        profile.update(
            dtype="float64",
            count=1,
            nodata=float(NODATA),
            compress="lzw",
            tiled=True,
            blockxsize=256,
            blockysize=256,
        )
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        with rasterio.open(dst_path, "w", **profile) as f:
            f.write(data.astype(np.float64), 1)
            f.update_tags(**tags)
        return True
    except Exception as e:
        logger.error(f"[raster] write {dst_path.name}: {e}")
        return False


def _pixel_avg(arrays: List[np.ndarray]) -> np.ndarray:
    """Pixel-wise mean ignoring NODATA."""
    stack = np.stack(arrays, axis=0)
    valid = (stack != float(NODATA)) & ~np.isnan(stack)
    total = np.where(valid, stack, 0.0).sum(axis=0)
    count = valid.sum(axis=0).astype(np.float64)
    return np.where(count > 0, total / count, float(NODATA)).astype(np.float64)


# ═══════════════════════════════════════════════════════════════════════════
# STEP A — HISTORY RASTERS
# ═══════════════════════════════════════════════════════════════════════════

def generate_history_rasters() -> int:
    """Write history/{param}/{param}_{slot}.tif for every param × slot."""
    dates = _latest_n_complete_dates(HISTORY_DATES)
    if not dates:
        logger.error("[history] No complete Sentinel dates")
        return 0

    logger.info(f"[history] {len(dates)} dates: {dates[-1].date()} → {dates[0].date()}")
    total = 0

    for param, (src_dir, pattern) in _SRC.items():
        src_by_date = {d: p for d, p in _dated_files(src_dir, pattern)}
        for idx, date in enumerate(dates):
            src_path = src_by_date.get(date)
            if src_path is None:
                logger.warning(f"[history] {param} missing for {date.date()}")
                continue
            slot     = slot_for_index(idx)
            dst_path = history_path(param, slot)

            if dst_path.exists():
                try:
                    with rasterio.open(dst_path) as f:
                        if f.tags().get("acquisition_date") == date.strftime("%Y-%m-%d"):
                            total += 1
                            continue
                except Exception:
                    pass

            if _reproject_and_write(src_path, dst_path, param, date,
                                     extra_tags={"slot": slot}):
                total += 1
                logger.info(f"[history] {dst_path.name} ({date.date()})")

        logger.info(f"[history] {param} done")

    logger.info(f"[history] Total: {total} / {HISTORY_DATES * len(PARAMS)}")
    return total


# ═══════════════════════════════════════════════════════════════════════════
# STEP B — FORECASTING  (Fixed - Thesis Compliant)
# Only PET uses SARIMAX. Kc uses its own trained SARIMAx + DOY adjustment.

# ═══════════════════════════════════════════════════════════════════════════

def _effective_rainfall_daily(rain_mm: float) -> float:
    """Daily effective rainfall using the thesis/FAO monthly formula scaled to 1 day."""
    rain_mm = max(float(rain_mm), 0.0)
    period_factor = 1.0 / 30.0
    threshold = 75.0 * period_factor
    if rain_mm > threshold:
        return max(0.0, 0.8 * rain_mm - 25.0 * period_factor)
    return max(0.0, 0.6 * rain_mm - 10.0 * period_factor)


def _rainfall_mean_for_date(date: datetime, rain_by_date: Dict[datetime, Path]) -> float:
    """Return rainfall for the forecast date; missing future rain is treated as dry."""
    date_key = date.replace(hour=0, minute=0, second=0, microsecond=0)
    rain_path = rain_by_date.get(date_key)
    if rain_path is None:
        return 0.0

    rain_val = raster_mean(rain_path, mask_zeros=False)
    return float(rain_val) if np.isfinite(rain_val) and rain_val >= 0 else 0.0


def _climatological_peff(future_dates: pd.DatetimeIndex) -> np.ndarray:
    """Estimate daily effective rainfall for each forecast date.

    Earlier code reused the latest rain rasters on disk for every reference
    date. That made historical stage forecasts subtract the same Peff and often
    flattened IWR to zero. The thesis chain is date based: IWR = CWR - Peff for
    the forecast period, so rainfall must come from the matching forecast dates.
    """
    rain_dir = DIRECTORIES["raw"].get("insat_rain")
    rain_by_date: Dict[datetime, Path] = {}

    if rain_dir and Path(rain_dir).exists():
        for rain_path in Path(rain_dir).glob("*.tif"):
            try:
                rain_date = models.extract_date(rain_path.name)
                rain_by_date[rain_date.replace(hour=0, minute=0, second=0, microsecond=0)] = rain_path
            except Exception:
                continue

    peff_vals = np.array([
        _effective_rainfall_daily(
            _rainfall_mean_for_date(
                d.to_pydatetime() if hasattr(d, "to_pydatetime") else d,
                rain_by_date,
            )
        )
        for d in future_dates
    ], dtype=float)

    logger.info(
        f"[forecast] Peff mean={peff_vals.mean():.3f} mm/day "
        f"range={peff_vals.min():.3f}–{peff_vals.max():.3f} "
        "(date-matched rain; FAO monthly formula scaled to daily)"
    )
    return peff_vals


def _project_kc_for_dates(
    future_dates: pd.DatetimeIndex,
    reference_date: Optional[datetime] = None,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    THESIS-COMPLIANT Kc forecasting.
    
    Strategy (v13.0 — thesis §4.6, §5.6):
        1. Use trained SARIMA Kc model for Kc forecast.
        2. If model unavailable, use FAO-56 stage Kc as fallback.
        3. SAVI is NOT used to forecast Kc — Kc has its own SARIMA.
    
    Returns (savi_forecast, kc_forecast) — both shape (len(future_dates),).
    """
    # ── Load trained Kc SARIMA model ──────────────────────────────────────
    kc_model, kc_meta = _get_model("kc")
    
    anchor_date = reference_date or (future_dates[0].to_pydatetime() - timedelta(days=1))
    last_kc_obs = _reference_mean("kc", anchor_date, 0.80) or 0.80
    last_savi_obs = _reference_mean("savi", anchor_date, None) or (
        (last_kc_obs - KC_INTERCEPT) / KC_SLOPE
    )
    set_forecast_context(last_savi=last_savi_obs, last_kc=last_kc_obs)
    
    days_ahead = np.arange(1, len(future_dates) + 1, dtype=float)
    
    if kc_model is not None:
        # ── Use trained SARIMA Kc model ───────────────────────────────
        logger.info("Using trained SARIMA Kc model for forecast")
        exog_cols = kc_meta.get("exog_cols", ["sin_doy", "cos_doy", "sin2_doy", "cos2_doy"])
        exog_df = build_forecast_exog(future_dates=future_dates, exog_cols=exog_cols)
        
        if hasattr(kc_model, "get_forecast"):
            kc_fc = kc_model.get_forecast(steps=len(future_dates), exog=exog_df)
            kc_forecast = kc_fc.predicted_mean.values.astype(float)
        else:
            kc_forecast = kc_model.forecast(steps=len(future_dates), exog=exog_df).values.astype(float)
        
        stage_kc = np.array([
            get_wheat_stage_kc(d.to_pydatetime())[1]
            for d in future_dates
        ], dtype=float)
        kc_forecast = 0.65 * kc_forecast + 0.35 * stage_kc

        # Smooth first few days to the selected reference-date observation.
        alpha = np.exp(-days_ahead / 5.0)
        kc_forecast = alpha * float(last_kc_obs) + (1 - alpha) * kc_forecast
        
    else:
        # ── Fallback: FAO-56 stage Kc ──────────────────────────────────
        logger.warning("No Kc SARIMA model — using FAO-56 stage Kc")
        kc_forecast = np.array([
            get_wheat_stage_kc(d.to_pydatetime())[1]
            for d in future_dates
        ], dtype=float)
    
    kc_forecast = np.clip(kc_forecast, KC_MIN, KC_MAX)
    
    # ── Derive SAVI from Kc (inverse of thesis equation) ──────────────
    # Kc = 1.2088 * SAVI + 0.5375  →  SAVI = (Kc - 0.5375) / 1.2088
    savi_forecast = np.clip((kc_forecast - KC_INTERCEPT) / KC_SLOPE, -0.1, 0.9)
    
    # Log crop stage context
    first_stage, first_kc_fao = get_wheat_stage_kc(future_dates[0].to_pydatetime())
    logger.info(
        f"Kc forecast [SARIMA/FAO-56]: "
        f"Kc_mean={kc_forecast.mean():.3f}, "
        f"range={kc_forecast.min():.3f}–{kc_forecast.max():.3f} "
        f"| crop_stage={first_stage} (FAO-56 Kc={first_kc_fao:.3f})"
    )
    return savi_forecast, kc_forecast

def generate_forecast_for_date(
    reference_date: datetime,
    days: int = FORECAST_DAYS,
) -> Dict[str, pd.Series]:
    """
    THESIS-COMPLIANT forecasting pipeline (v13.0).
    
    THESIS §4.6, §5.6 chain:
      1. Forecast Kc with SARIMA(1,1,1)(1,1,1,12) 
      2. Forecast PET with SARIMA(1,1,1)(1,1,1,12) [NO SAVI input]
      3. CWR = Kc × PET  (FAO-56 Eq. 4)
      4. IWR = max(CWR − Peff, 0)  (FAO-56 §4.5)
    
    CRITICAL: NO SAVI in PET model. PET is meteorological.
    """
    forecasts: Dict[str, pd.Series] = {}

    future_dates = pd.date_range(
        start=reference_date + timedelta(days=1),
        periods=days,
        freq="D",
    )

    # ── 1. Forecast Kc with trained SARIMA ──────────────────────────────
    kc_model, kc_meta = _get_model("kc")
    if kc_model is None:
        raise RuntimeError(
            "[forecast] Kc model not available. Run models.train_all_models()."
        )
    
    last_kc_obs = _reference_mean("kc", reference_date, kc_meta.get("last_kc", 0.80)) or 0.80
    last_savi_obs = _reference_mean("savi", reference_date, None) or kc_meta.get(
        "last_savi",
        (last_kc_obs - KC_INTERCEPT) / KC_SLOPE,
    )
    set_forecast_context(last_savi=last_savi_obs, last_kc=last_kc_obs)
    
    exog_cols_kc = kc_meta.get("exog_cols", ["sin_doy", "cos_doy", "sin2_doy", "cos2_doy"])
    exog_kc = build_forecast_exog(future_dates=future_dates, exog_cols=exog_cols_kc)
    
    if hasattr(kc_model, "get_forecast"):
        kc_fc = kc_model.get_forecast(steps=days, exog=exog_kc)
        kc_values = kc_fc.predicted_mean.values.astype(float)
    else:
        kc_values = kc_model.forecast(steps=days, exog=exog_kc).values.astype(float)

    stage_kc = np.array([
        get_wheat_stage_kc(d.to_pydatetime())[1]
        for d in future_dates
    ], dtype=float)
    kc_values = 0.65 * kc_values + 0.35 * stage_kc
    
    # Smooth to the selected reference-date crop state for the first few days.
    alpha_kc = np.exp(-np.arange(1, days + 1, dtype=float) / 5.0)
    kc_values = alpha_kc * float(last_kc_obs) + (1 - alpha_kc) * kc_values
    kc_values = np.clip(kc_values, KC_MIN, KC_MAX)
    
    forecasts["kc"] = pd.Series(kc_values, index=future_dates, name="kc")

    # ── 2. Forecast PET with trained SARIMA — NO SAVI ─────────────────
    pet_model, pet_meta = _get_model("pet")
    if pet_model is None:
        raise RuntimeError(
            "[forecast] PET model not available. Run models.train_all_models()."
        )
    
    # Estimate last PET from CWR/Kc
    last_cwr_obs = _reference_mean("cwr", reference_date, 3.5) or 3.5
    last_pet_obs = pet_meta.get("last_pet")
    if last_pet_obs is None or not np.isfinite(last_pet_obs):
        last_pet_obs = last_cwr_obs / last_kc_obs if last_kc_obs > 0 else 4.0

    # PET may include lag exog; seed it from the selected reference-date context.
    set_forecast_context(
        last_savi=last_savi_obs,
        last_kc=last_kc_obs,
        last_pet=float(last_pet_obs),
    )
    exog_cols_pet = pet_meta.get("exog_cols", ["sin_doy", "cos_doy", "sin2_doy", "cos2_doy", "month"])
    exog_pet = build_forecast_exog(future_dates=future_dates, exog_cols=exog_cols_pet)
    
    if hasattr(pet_model, "get_forecast"):
        pet_fc = pet_model.get_forecast(steps=days, exog=exog_pet)
        base_pet = pet_fc.predicted_mean.values.astype(float)
    else:
        base_pet = pet_model.forecast(steps=days, exog=exog_pet).values.astype(float)
    if pet_meta.get("target_transform") == "log1p":
        base_pet = np.expm1(base_pet)
    
    # Mild seasonal regulariser (keeps long-range realistic)
    doy = future_dates.dayofyear.values.astype(float)
    seasonal_pet = 5.5 + 3.2 * np.sin(2 * np.pi * (doy - 45) / 365.25)
    pet_values = 0.65 * base_pet + 0.35 * seasonal_pet
    
    # Smooth first few days
    alpha_pet = np.exp(-np.arange(days) / 5.0)
    pet_values = alpha_pet * float(last_pet_obs) + (1 - alpha_pet) * pet_values
    pet_values = np.clip(pet_values, 1.5, 12.0)
    
    forecasts["pet"] = pd.Series(pet_values, index=future_dates, name="pet")

    # ── 3. Physics: CWR = Kc × PET ────────────────────────────────────
    cwr_arr = np.clip(kc_values * pet_values, CWR_MIN, CWR_MAX)
    forecasts["cwr"] = pd.Series(cwr_arr, index=future_dates, name="cwr")

    # ── 4. Physics: IWR = max(CWR − Peff, 0) ─────────────────────────
    peff_arr = _climatological_peff(future_dates)
    iwr_arr = np.maximum(cwr_arr - peff_arr, 0.0)
    forecasts["iwr"] = pd.Series(iwr_arr, index=future_dates, name="iwr")
    forecasts["peff"] = pd.Series(peff_arr, index=future_dates, name="peff")
    
    # ── Derive SAVI from Kc for dashboard consistency ─────────────────
    savi_arr = np.clip((kc_values - KC_INTERCEPT) / KC_SLOPE, -0.1, 0.9)
    forecasts["savi"] = pd.Series(savi_arr, index=future_dates, name="savi")

    # ── Crop-stage summary log ────────────────────────────────────────
    stage_info = get_wheat_stage_info(future_dates[0].to_pydatetime())
    logger.info(
        f"[forecast] Generated for {reference_date.date()}: "
        f"stage={stage_info['stage']} (DAS={stage_info['das']}, "
        f"FAO-56 Kc={stage_info['kc_fao56']:.3f}) | "
        f"Kc_mean={forecasts['kc'].mean():.3f}, "
        f"PET_mean={forecasts['pet'].mean():.2f}, "
        f"CWR_mean={forecasts['cwr'].mean():.2f}, "
        f"IWR_mean={forecasts['iwr'].mean():.2f}"
    )

    return forecasts

def create_forecast_raster(
    param: str,
    slot: str,
    window: str,
    forecast_series: pd.Series,
    template_raster: Path,
) -> bool:
    """
    Create forecast raster by scaling the template spatial pattern to the
    forecast mean.  This preserves within-field spatial variability while
    applying the modelled temporal change.
    """
    try:
        with rasterio.open(template_raster) as src:
            template_data = src.read(1).astype(np.float64)
            nodata        = src.nodata if src.nodata is not None else NODATA
            template_data = np.where(template_data == nodata, np.nan, template_data)
            profile       = src.profile.copy()

            WINDOW_SLICES = {
                "5day": (0, 5),
                "10day": (0, 10),
                "15day": (0, 15),
            }

            start_idx, end_idx = WINDOW_SLICES[window]
            window_forecast = forecast_series.iloc[start_idx:end_idx]
            forecast_mean = float(window_forecast.mean())
            stage_info = get_wheat_stage_info(window_forecast.index[0].to_pydatetime())

        valid = ~np.isnan(template_data)
        if not valid.any():
            logger.warning(f"No valid pixels in template for {param} {slot}")
            return False

        template_mean = float(np.nanmean(template_data[valid]))

        if template_mean > 0:
            scale_factor   = forecast_mean / template_mean
            forecast_array = np.where(valid, template_data * scale_factor, np.nan)
        else:
            forecast_array = np.where(valid, forecast_mean, np.nan)

        vmin, vmax     = _VALID.get(param, (-1e9, 1e9))
        forecast_array = np.clip(forecast_array, vmin, vmax)

        dst_path = forecast_path(param, slot, window)
        profile.update(
            dtype="float64",
            nodata=NODATA,
            compress="lzw",
            tiled=True,
            blockxsize=256,
            blockysize=256,
        )

        with rasterio.open(dst_path, "w", **profile) as dst:
            out_data = np.where(np.isnan(forecast_array), NODATA, forecast_array)
            dst.write(out_data.astype(np.float64), 1)
            dst.update_tags(
                parameter=param,
                slot=slot,
                forecast_window=window,
                reference_date=slot,
                forecast_mean=str(round(forecast_mean, 4)),
                template_mean=str(round(template_mean, 4)),
                crop_stage=stage_info["stage"],
                days_after_sowing=str(stage_info["das"]),
                kc_fao56=str(round(stage_info["kc_fao56"], 4)),
                units="mm_per_day" if param in ["cwr", "iwr"] else "",
                model="PET-SARIMAX+Physics-CWR/IWR",
                generated_by="irrigation_monitoring_v9.0",
            )

        logger.info(
            f"Created {param} forecast for {slot} {window}: "
            f"mean={forecast_mean:.4f} mm/day (template mean={template_mean:.4f})"
        )
        return True

    except Exception as e:
        logger.error(f"Failed to create {param} forecast for {slot}_{window}: {e}")
        return False


def generate_all_forecast_rasters() -> int:
    """
    Generate all forecast rasters (2 params × 12 slots × 3 windows)
    using the corrected PET-SARIMAX + physics CWR/IWR pipeline.
    """
    dates = _latest_n_complete_dates(HISTORY_DATES)
    if not dates:
        logger.error("[forecast] No Sentinel dates available")
        return 0

    total = 0

    for idx, date in enumerate(dates):
        slot      = slot_for_index(idx)
        forecasts = generate_forecast_for_date(date, FORECAST_DAYS)

        if not forecasts:
            logger.warning(f"[forecast] No forecast for {slot} ({date.date()})")
            continue

        n_rasters = 0
        for param in ["kc", "cwr", "iwr"]:
            if param not in forecasts:
                continue
            for window in FORECAST_WINDOWS:
                dst_path = forecast_path(param, slot, window)

                # FORCED REGENERATION: Logic changes in main.py must be reflected immediately.
                # Removing the skip check to ensure fresh forecasts whenever the pipeline runs.
                template = history_path(param, slot)
                if template.exists():
                    if create_forecast_raster(
                        param, slot, window, forecasts[param], template
                    ):
                        n_rasters += 1
                        total += 1

        logger.info(f"[forecast] slot={slot} ({date.date()}): {n_rasters} files")

    expected_total = len(dates) * 3 * len(FORECAST_WINDOWS)  # kc + cwr + iwr
    logger.info(f"[forecast] ALL: {total} / {expected_total}")
    return total




# ═══════════════════════════════════════════════════════════════════════════
# STEP C — PUSH TO GEOSERVER
# ═══════════════════════════════════════════════════════════════════════════
 
def push_to_geoserver() -> None:
    try:
        from init_geoserver import GeoServerAPI
        gs = GeoServerAPI()
    except Exception as e:
        logger.warning(f"[geoserver] Cannot init GeoServerAPI: {e}")
        return
 
    for param in ["savi", "kc", "cwr", "iwr"]:
        for slot in SLOTS:
            p = history_path(param, slot)
            if not p.exists():
                continue
            store = f"{param}_{slot}"
            layer = store
            try:
                store_ok     = gs.create_coverage_store_if_not_exists(store, p)
                file_ok      = gs.update_coverage_store_file(store, p)
                # configure_layer now auto-publishes via publish_coverage() on 404
                configure_ok = gs.configure_layer(layer_name=layer, store_name=store)
                style        = f"{param}_style"
                style_ok     = gs.assign_style(layer, style)
                if store_ok and file_ok and configure_ok and style_ok:
                    logger.info(f"[geoserver] ✅ Layer ready: {layer}")
                else:
                    logger.warning(
                        f"[geoserver] ⚠ Layer partially configured: {layer} "
                        f"(store={store_ok} file={file_ok} "
                        f"configure={configure_ok} style={style_ok})"
                    )
            except Exception as e:
                logger.warning(f"[geoserver] {store}: {e}")
 
    # Push forecast rasters for kc, cwr, iwr
    for param in ["kc", "cwr", "iwr"]:
        for slot in SLOTS:
            for window in FORECAST_WINDOWS:
                p = forecast_path(param, slot, window)
                if not p.exists():
                    continue
                store = f"{param}_{slot}_{window}"
                layer = store
                try:
                    store_ok     = gs.create_coverage_store_if_not_exists(store, p)
                    file_ok      = gs.update_coverage_store_file(store, p)
                    # configure_layer now auto-publishes via publish_coverage() on 404
                    configure_ok = gs.configure_layer(layer_name=layer, store_name=store)
                    style        = f"{param}_style"
                    style_ok     = gs.assign_style(layer, style)
                    if store_ok and file_ok and configure_ok and style_ok:
                        logger.info(f"[geoserver] ✅ Forecast layer ready: {layer}")
                    else:
                        logger.warning(
                            f"[geoserver] ⚠ Forecast layer partially configured: {layer} "
                            f"(store={store_ok} file={file_ok} "
                            f"configure={configure_ok} style={style_ok})"
                        )
                except Exception as e:
                    logger.warning(f"[geoserver] {store}: {e}")



# ═══════════════════════════════════════════════════════════════════════════
# MASTER PIPELINE
# ═══════════════════════════════════════════════════════════════════════════

def run_pipeline() -> Dict:
    """
    Full pipeline run:
      A. History rasters
      B. Forecast generation (PET SARIMAX → physics CWR/IWR)
      C. Forecast rasters
      D. GeoServer push
    """
    logger.info("═" * 65)
    logger.info("run_pipeline() START — v9.0 (PET-SARIMAX + Physics CWR/IWR)")
    logger.info("═" * 65)

    cleanup_old_rasters()
    _get_wheat_mask()

    logger.info("── A: History rasters ──")
    h_total = generate_history_rasters()
    logger.info(f"── A done: {h_total}/{HISTORY_DATES * len(PARAMS)} ──")

    logger.info("── B/C: Forecast + rasters ──")
    _get_model("pet")
    f_total = generate_all_forecast_rasters()
    logger.info(f"── B/C done: {f_total}/{HISTORY_DATES * 3 * len(FORECAST_WINDOWS)} ──")

    logger.info("── D: GeoServer ──")
    push_to_geoserver()

    dates   = _latest_n_complete_dates()
    summary = {
        "slots":              {slot_for_index(i): str(d.date()) for i, d in enumerate(dates)},
        "history_rasters":    h_total,
        "forecast_rasters":   f_total,
        "grand_total":        h_total + f_total,
        "units":              "mm_per_day",
        "forecast_model":     "PET-SARIMAX + Physics CWR/IWR",
        "physical_relationships": {
            "savi_to_kc": f"Kc = {KC_SLOPE:.4f} × SAVI + {KC_INTERCEPT:.4f}",
            "cwr":        "CWR = Kc_projected × PET_forecast  (FAO-56 Eq. 4)",
            "iwr":        "IWR = max(CWR − Peff, 0)  (FAO-56 §4.5)",
            "peff":       "Peff = USDA-SCS on interval rainfall total",
        },
    }
    logger.info("═" * 65)
    logger.info(f"DONE: {summary}")
    logger.info("═" * 65)
    return summary


# ═══════════════════════════════════════════════════════════════════════════
# SCHEDULER CALLBACKS
# ═══════════════════════════════════════════════════════════════════════════

def generate_operational_rasters() -> None:
    logger.info("[generate_operational_rasters] START")
    try:
        cleanup_old_rasters()
        h = generate_history_rasters()
        logger.info(f"[generate_operational_rasters] history rasters: {h}")
    except Exception as e:
        logger.error(f"[generate_operational_rasters] history step failed: {e}", exc_info=True)

    try:
        f = generate_all_forecast_rasters()
        logger.info(f"[generate_operational_rasters] forecast rasters: {f}")
    except Exception as e:
        logger.error(f"[generate_operational_rasters] forecast step failed: {e}", exc_info=True)

    try:
        push_to_geoserver()
        logger.info("[generate_operational_rasters] GeoServer push done")
    except Exception as e:
        logger.error(f"[generate_operational_rasters] GeoServer push failed: {e}", exc_info=True)

    logger.info("[generate_operational_rasters] DONE")


def process_single_sentinel_image(tif_path: Path) -> None:
    logger.info(f"[process_single_sentinel_image] {tif_path.name}")
    try:
        from run import run_savi, run_kc, run_etc, run_cwr, run_iwr
        from processor import DataProcessor
        p = DataProcessor()
        run_savi(p)
        run_kc(p)
        run_etc(p)
        run_cwr(p)
        run_iwr(p)
        logger.info(f"[process_single_sentinel_image] complete for {tif_path.name}")
    except Exception as e:
        logger.error(
            f"[process_single_sentinel_image] failed for {tif_path.name}: {e}",
            exc_info=True,
        )


# ═══════════════════════════════════════════════════════════════════════════
# FastAPI APP
# ═══════════════════════════════════════════════════════════════════════════

from graph import router as graph_router

app = FastAPI(
    title="Wheat Irrigation Monitoring System",
    version="9.0.0",
    description=(
        "v9.0 — Corrected forecast design:\n\n"
        "  • PET forecasted with SARIMAX (only statistically forecasted variable)\n"
        "  • CWR = Kc_projected × PET_forecast  (FAO-56 Eq. 4, physics)\n"
        "  • IWR = max(CWR − Peff, 0)  (FAO-56 §4.5, physics)\n\n"
        "Physical chain: SAVI → Kc → CWR → IWR\n"
        "No IWR direct forecasting. No circular exog dependencies."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# app.include_router(graph_router, prefix="/api/graph", tags=["graphs"])
app.include_router(graph_router)



from config import STUDY_AREA, EXACT_BOUNDARY


class ChatRequest(BaseModel):
    query: str
    lat: Optional[float] = None
    lon: Optional[float] = None
    history: Optional[List[Dict]] = None

@app.get("/api/boundary")
async def get_boundary():
    """
    Return the study-area boundary for Udham Singh Nagar.
    Used by MapView to fit the Leaflet map bounds.
    Guaranteed to return valid, non-empty bounds.
    """
    bounds = EXACT_BOUNDARY.get("bounds") or STUDY_AREA.get("bounds")

    # Validate — Leaflet needs north > south and east > west
    if not bounds or not all(k in bounds for k in ("north", "south", "east", "west")):
        # Hard-coded fallback so the map never breaks
        bounds = {
            "north": 29.4400,
            "south": 28.8900,
            "west":  78.8800,
            "east":  80.1040,
        }

    north = bounds["north"]
    south = bounds["south"]
    east  = bounds["east"]
    west  = bounds["west"]

    # Swap silently if they are inverted
    if north < south:
        north, south = south, north
    if east < west:
        east, west = west, east

    # Minimum span guard — prevents zero-area bounds crash in Leaflet
    if (north - south) < 0.01:
        north += 0.05
        south -= 0.05
    if (east - west) < 0.01:
        east += 0.05
        west -= 0.05

    return {
        "name":    STUDY_AREA.get("name", "Udham Singh Nagar"),
        "state":   STUDY_AREA.get("state", "Uttarakhand"),
        "crs":     STUDY_AREA.get("crs", "EPSG:4326"),
        "source":  STUDY_AREA.get("boundary_source", "static-fallback"),
        "bounds": {
            "north": round(north, 6),
            "south": round(south, 6),
            "east":  round(east,  6),
            "west":  round(west,  6),
        },
        # Leaflet fitBounds expects [[south, west], [north, east]]
        "leaflet_bounds": [
            [round(south, 6), round(west, 6)],
            [round(north, 6), round(east, 6)],
        ],
        "center": EXACT_BOUNDARY.get("center") or [
            round((east + west) / 2, 6),
            round((north + south) / 2, 6),
        ],
        "geojson": EXACT_BOUNDARY.get("geojson", {"type": "FeatureCollection", "features": []}),
    }


@app.post("/api/chat")
async def chat(req: ChatRequest):
    """
    RAG-powered chatbot endpoint.
    Retrieves domain knowledge chunks, fetches live irrigation data,
    then generates an answer via Gemini API with fallback behavior.
    """
    query = req.query.strip()
    if not query:
        return {
            "answer": "Please ask a question about irrigation, crop water requirements, or the study region.",
            "sources": [],
            "live_data": {},
        }

    live_data: Dict[str, object] = {}
    try:
        dates = _latest_n_complete_dates(1)
        if dates:
            for param in ("savi", "kc", "cwr", "iwr"):
                val = _read_mean(history_path(param, "today"))
                if val is not None:
                    live_data[param] = round(val, 3)

            if req.lat is not None and req.lon is not None:
                live_data["query_location"] = f"lat={req.lat:.4f}, lon={req.lon:.4f}"
                for param in ("savi", "kc", "cwr", "iwr"):
                    p = history_path(param, "today")
                    if not p.exists():
                        continue
                    try:
                        with rasterio.open(p) as src:
                            val = list(src.sample([(req.lon, req.lat)]))[0][0]
                        if val != NODATA:
                            live_data[f"point_{param}"] = round(float(val), 3)
                    except Exception:
                        logger.debug("[chat] failed point sample for %s", param, exc_info=True)
    except Exception as e:
        logger.warning(f"[chat] live data fetch failed: {e}")

    try:
        from rag_kb import get_chat_answer

        rag_response = get_chat_answer(
            query,
            live_data=live_data or None,
            history=req.history or [],
        )
        answer = rag_response.get("answer") or "I could not generate an answer right now."
        source_ids = rag_response.get("sources", [])
    except Exception as e:
        logger.error(f"[chat] LangChain RAG failed: {e}", exc_info=True)
        from rag_kb import fallback_answer

        answer = fallback_answer(query)
        source_ids = []

    return {
        "answer": answer,
        "sources": source_ids,
        "live_data": live_data,
    }




# ── Endpoints ──────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {
        "status":  "ok",
        "version": "9.0.0",
        "model":   "PET-SARIMAX + Physics CWR/IWR",
    }


@app.get("/api/forecast")
async def get_forecast(
    date: str = Query(..., description="Reference date YYYY-MM-DD"),
    days: int  = Query(15,  ge=1, le=30, description="Forecast horizon (days)"),
):
    """
    Generate a multi-day CWR + IWR forecast.

    Forecast chain:
      PET (SARIMAX) → CWR = Kc × PET → IWR = max(CWR − Peff, 0)
    """
    try:
        ref_date = datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date — use YYYY-MM-DD")

    forecasts = generate_forecast_for_date(ref_date, days)
    if not forecasts:
        raise HTTPException(status_code=500, detail="Failed to generate forecast")

    result: dict = {
        "reference_date": date,
        "forecast_days":  days,
        "model":          "PET-SARIMAX + Physics CWR/IWR (v9.0)",
        "forecast_chain": "PET(SARIMAX) → CWR=Kc×PET → IWR=max(CWR-Peff,0)",
        "forecasts":      {},
    }

    units_by_param = {
        "savi": "unitless",
        "kc": "unitless",
        "pet": "mm_per_day",
        "cwr": "mm_per_day",
        "iwr": "mm_per_day",
        "peff": "mm_per_day",
    }

    for param in ("savi", "pet", "kc", "cwr", "iwr", "peff"):
        if param in forecasts:
            series = forecasts[param]
            result["forecasts"][param] = {
                "dates":  [d.strftime("%Y-%m-%d") for d in series.index],
                "values": [round(float(v), 4) for v in series.values],
                "units":  units_by_param[param],
                "mean":   round(float(series.mean()), 4),
                "min":    round(float(series.min()),  4),
                "max":    round(float(series.max()),  4),
            }

    result["crop_stages"] = [
        {
            "date": d.strftime("%Y-%m-%d"),
            **get_wheat_stage_info(d.to_pydatetime()),
        }
        for d in forecasts["kc"].index
    ]

    result["window_summaries"] = {}
    WINDOW_SLICES = {
        "5day": (0, 5),    # days 1-5
        "10day": (0, 10),  # days 1-10 (cumulative)
        "15day": (0, 15),  # days 1-15 (cumulative)
    }

    for window, (start_idx, end_idx) in WINDOW_SLICES.items():
        result["window_summaries"][window] = {}
        for param in ("kc", "cwr", "iwr", "peff"):
            if param in forecasts:
                vals = forecasts[param].iloc[start_idx:end_idx].values
                result["window_summaries"][window][param] = {
                    "mean": round(float(np.mean(vals)), 4),
                    "total": round(float(np.sum(vals)), 4),
                }
        window_date = forecasts["kc"].index[start_idx].to_pydatetime()
        result["window_summaries"][window]["crop_stage"] = get_wheat_stage_info(window_date)

    return result


@app.get("/api/history")
async def get_history():
    """Return observed and forecast means for all history slots."""
    dates = _latest_n_complete_dates()
    if not dates:
        raise HTTPException(status_code=404, detail="No processed Sentinel scenes found")

    result = []
    for idx, d in enumerate(dates):
        slot      = slot_for_index(idx)
        obs_means = {}
        fc_means  = {}

        for param in PARAMS:
            path = history_path(param, slot)
            if path.exists():
                with rasterio.open(path) as src:
                    tags = src.tags()
                mean_str        = tags.get("mean")
                obs_means[param] = (
                    float(mean_str)
                    if mean_str and mean_str not in ("None", "nan", "")
                    else None
                )
            else:
                obs_means[param] = None

            fc_means[param] = {}
            for w in FORECAST_WINDOWS:
                fpath = forecast_path(param, slot, w)
                if fpath.exists():
                    with rasterio.open(fpath) as src:
                        tags = src.tags()
                    fc_str              = tags.get("forecast_mean")
                    fc_means[param][w]  = (
                        float(fc_str)
                        if fc_str and fc_str not in ("None", "nan", "")
                        else None
                    )
                else:
                    fc_means[param][w] = None

        result.append({
            "slot":           slot,
            "date":           str(d.date()),
            "is_latest":      idx == 0,
            "obs_means":      obs_means,
            "forecast_means": fc_means,
        })

    return {
        "n_slots": len(result),
        "units":   "mm_per_day",
        "model":   "PET-SARIMAX + Physics CWR/IWR",
        "slots":   result,
    }


@app.get("/api/point")
def get_point(
    lat:  float,
    lon:  float,
    slot: Optional[str] = None,
):
    """Point query — returns observed and forecast values at (lat, lon)."""
    if not slot:
        slot = "today"

    result   = {}
    forecast = {}

    for param in ("savi", "kc", "cwr", "iwr"):
        path = history_path(param, slot)
        if path.exists():
            with rasterio.open(path) as src:
                val = list(src.sample([(lon, lat)]))[0][0]
                result[param] = None if val == NODATA else float(val)

        if param in ("kc", "cwr", "iwr"):
            forecast[param] = {}
            for w in FORECAST_WINDOWS:
                fpath = forecast_path(param, slot, w)
                if fpath.exists():
                    with rasterio.open(fpath) as src:
                        val = list(src.sample([(lon, lat)]))[0][0]
                        forecast[param][w] = None if val == NODATA else float(val)
                else:
                    forecast[param][w] = None

    return {
        "lat":              lat,
        "lon":              lon,
        "acquisition_date": slot,
        "values":           result,
        "forecast":         forecast,
    }

# @app.get("/api/point")
# def get_point(
#     lat: float,
#     lon: float,
#     slot: Optional[str] = None,
# ):
#     if not slot:
#         slot = "today"

#     result = {}
#     forecast = {}
#     forecast_daily = {}

#     # observed values
#     for param in ("savi", "kc", "cwr", "iwr"):
#         path = history_path(param, slot)

#         if path.exists():
#             with rasterio.open(path) as src:
#                 val = list(src.sample([(lon, lat)]))[0][0]
#                 result[param] = None if val == NODATA else float(val)

#     # old forecast window values (keep UI safe)
#     for param in ("kc", "cwr", "iwr"):
#         forecast[param] = {}

#         for w in FORECAST_WINDOWS:
#             fpath = forecast_path(param, slot, w)

#             if fpath.exists():
#                 with rasterio.open(fpath) as src:
#                     val = list(src.sample([(lon, lat)]))[0][0]
#                     forecast[param][w] = None if val == NODATA else float(val)
#             else:
#                 forecast[param][w] = None

#     # NEW DAILY FORECAST
#     dates = _latest_n_complete_dates(1)
#     ref_date = dates[0] if dates else datetime.today()

#     fc = generate_forecast_for_date(ref_date, 15)

#     forecast_daily["dates"] = [
#         d.strftime("%Y-%m-%d") for d in fc["kc"].index
#     ]

#     for param in ("kc", "cwr", "iwr"):
#         forecast_daily[param] = [
#             round(float(v), 4)
#             for v in fc[param].values
#         ]

#     return {
#         "lat": lat,
#         "lon": lon,
#         "acquisition_date": slot,
#         "values": result,
#         "forecast": forecast,
#         "forecast_daily": forecast_daily
#     }

@app.post("/api/refresh")
async def manual_refresh():
    """Trigger a full pipeline run."""
    try:
        return {"status": "ok", "result": run_pipeline()}
    except Exception as e:
        logger.exception("Pipeline failed")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/model/info")
async def model_info():
    """Return metadata for all loaded models — THESIS COMPLIANT."""
    pet_model, pet_meta = _get_model("pet")
    kc_model, kc_meta = _get_model("kc")

    def _meta_dict(model, meta):
        if meta is None:
            return {"available": False}
        return {
            "available": model is not None,
            "note": meta.get("note", ""),
            "test_r2": meta["metrics"].get("R2"),
            "test_rmse": meta["metrics"].get("RMSE"),
            "test_mae": meta["metrics"].get("MAE"),
            "order": meta.get("order"),
            "exog_cols": meta.get("exog_cols"),
            "last_training_date": (
                meta["last_date"].strftime("%Y-%m-%d")
                if meta.get("last_date") else None
            ),
        }

    return {
        "models": {
            "kc":  _meta_dict(kc_model,  kc_meta),
            "pet": _meta_dict(pet_model, pet_meta),
        },
        "forecast_chain": {
            "step1": "Kc forecast: SARIMA(1,1,1)(1,1,1,12) on Kc time series",
            "step2": "PET forecast: SARIMA(1,1,1)(1,1,1,12) — NO SAVI (purely meteorological)",
            "step3": "CWR = Kc × PET  (FAO-56 Eq. 4)",
            "step4": "IWR = max(CWR − Peff, 0)  (FAO-56 §4.5)",
        },
        "physical_relationships": {
            "savi_to_kc": f"Kc = {KC_SLOPE:.4f} × SAVI + {KC_INTERCEPT:.4f}  (thesis Table 9)",
            "kc_to_savi": f"SAVI = (Kc − {KC_INTERCEPT:.4f}) / {KC_SLOPE:.4f}  (inverse)",
            "cwr":        "CWR = Kc × PET  (FAO-56)",
            "iwr":        "IWR = max(CWR − Peff, 0)  (FAO-56)",
            "peff":       "Peff from INSAT rainfall via FAO-56 formula",
        },
        "crop_stage_today": get_wheat_stage_info(datetime.utcnow()),
        "history_slots": HISTORY_DATES,
        "thesis_reference": "Satabdi Mandal, 2025, IIRS-ISRO, §4.6, §5.6",
    }

# ═══════════════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════

def main():
    setup_logging()
    logger.info("=" * 65)
    logger.info("Irrigation Monitoring System v10.0 starting …")
    logger.info("Forecast: PET(SARIMAX trained) → CWR=Kc×PET → IWR=max(CWR-Peff,0)")
    logger.info("Stage-aware Kc: SAVI-physics (day-weighted) + FAO-56 crop stage blend")
    logger.info("=" * 65)

    _get_wheat_mask()

    pet_model, pet_meta = _get_model("pet")
    if pet_model:
        logger.info(f"✓ PET model ready (R²={pet_meta['metrics']['R2']:.4f})")
    else:
        logger.error("✗ Failed to initialise PET model")

    logger.info(
        f"SAVI→Kc chain: Kc = {KC_SLOPE}×SAVI + {KC_INTERCEPT} "
        f"(no SAVI SARIMAX — using trend+climatology blend)"
    )

    run_pipeline()

    try:
        from scheduler import start_scheduler
        _scheduler, _observer = start_scheduler(
            delete_callback=cleanup_old_rasters,
            generate_callback=generate_operational_rasters,
            download_and_process_callback=None,
            single_image_pipeline_callback=process_single_sentinel_image,
        )
        logger.info("✓ Scheduler + Watchdog started")
    except Exception as e:
        logger.error(f"✗ Scheduler failed to start: {e}", exc_info=True)
        logger.warning(
            "Continuing without scheduler — pipeline will NOT run automatically."
        )

    uvicorn.run(
        app, host="0.0.0.0", port=8000,
        log_level="info", access_log=True,
    )


if __name__ == "__main__":
    main()
