# """
# models.py  — v9.0
# ═══════════════════════════════════════════════════════════════════════════
# ROOT-CAUSE FIXES from v8.1 analysis:

#   DESIGN-FIX-1  Forecasting strategy corrected per FAO-56 physics:
#                 ─ ONLY PET is forecasted with SARIMAX (it is the sole
#                   exogenous driver that changes day-to-day).
#                 ─ CWR is COMPUTED, not forecasted: CWR = Kc × PET_forecast
#                   where Kc is projected from DOY-based SAVI expectation.
#                 ─ IWR is COMPUTED, not forecasted: IWR = max(CWR − Peff, 0)
#                   where Peff is derived from a seasonal climatological
#                   rainfall expectation (not a direct forecast).

#   DESIGN-FIX-2  CWR was forecasted directly with PET, Kc, SAVI as exog,
#                 creating circular dependency.  CWR SARIMAX removed.
#                 CWR is now deterministic from PET forecast.

#   DESIGN-FIX-3  IWR = 0 root cause: in processor.py the USDA-SCS formula
#                 with P_interval ≈ 2–5 mm always yields Pe = 0 (correct for
#                 Rabi season).  But in the old SARIMAX IWR model, eff_rain
#                 exog was a constant near-zero scalar → model learned IWR ≈ 0.
#                 Fix: stop forecasting IWR; compute it physics-only.

#   DESIGN-FIX-4  PET exog: DOY sin/cos is a good base. When INSAT temp/rad
#                 rasters are present they are included.  Added: lagged PET
#                 (PET_lag1) as a strong auto-regressive exog since PET is
#                 highly persistent (r > 0.85 at lag-1 in Rabi season).

#   DESIGN-FIX-5  SARIMAX seasonal_period was 26 (bi-weekly Sentinel cadence).
#                 PET data is daily; Sentinel data is ~5-day. The PET SARIMAX
#                 model uses PET rasters aligned to Sentinel dates (so it IS
#                 5-day cadence), making seasonal_period=26 correct for the
#                 within-season cycle. Documented clearly.

#   DESIGN-FIX-6  train_sarimax_model: added d=0 to search space alongside d=1.
#                 PET is usually stationary within a season → over-differencing
#                 (always d=1) was collapsing forecasts toward zero.

#   DESIGN-FIX-7  Forecast exog builder (build_forecast_exog) is now a public
#                 utility function used by both models.py and main.py, ensuring
#                 consistent exog construction at train-time and forecast-time.

# Physics chain (thesis FAO-56):
#     SAVI  →  Kc = 1.2088×SAVI + 0.5375  (clip 0.30–1.15)
#     Kc + PET_forecast  →  CWR_forecast = Kc_projected × PET_forecast
#     CWR_forecast − Peff_climatology  →  IWR_forecast = max(CWR − Peff, 0)
# ═══════════════════════════════════════════════════════════════════════════
# """

# from __future__ import annotations

# import logging
# import os
# import pickle
# import re
# import warnings
# from datetime import datetime, timedelta
# from pathlib import Path
# from typing import Dict, List, Optional, Tuple

# import numpy as np
# import pandas as pd
# import rasterio
# from sklearn.linear_model import Ridge
# from sklearn.metrics import mean_absolute_error, mean_squared_error
# from sklearn.pipeline import Pipeline
# from sklearn.preprocessing import PolynomialFeatures
# from statsmodels.tsa.statespace.sarimax import SARIMAX

# warnings.filterwarnings("ignore")
# logger = logging.getLogger(__name__)

# from config import DIRECTORIES

# # ── Directory paths ──────────────────────────────────────────────────────────
# CWR_DIR  = DIRECTORIES["processed"]["cwr"]
# IWR_DIR  = DIRECTORIES["processed"]["iwr"]
# PET_DIR  = DIRECTORIES["raw"]["insat_pet"]
# KC_DIR   = DIRECTORIES["processed"]["kc"]
# SAVI_DIR = DIRECTORIES["processed"]["savi"]
# RAIN_DIR = DIRECTORIES["raw"]["insat_rain"]

# TEMP_DIR: Optional[Path] = DIRECTORIES["raw"].get("insat_temp")
# RAD_DIR:  Optional[Path] = DIRECTORIES["raw"].get("insat_rad")

# if TEMP_DIR is None:
#     logger.info(
#         "DIRECTORIES['raw']['insat_temp'] not configured — "
#         "PET model will use DOY + lag exog only"
#     )
# if RAD_DIR is None:
#     logger.info(
#         "DIRECTORIES['raw']['insat_rad'] not configured — "
#         "PET model will use DOY + lag exog only"
#     )

# MODEL_DIR = DIRECTORIES["models"]
# os.makedirs(MODEL_DIR, exist_ok=True)

# # ── Model file paths ─────────────────────────────────────────────────────────
# PET_MODEL_PATH = MODEL_DIR / "sarimax_wheat_pet.pkl"
# KC_MODEL_PATH  = MODEL_DIR / "poly_wheat_kc.pkl"
# IWR_MODEL_PATH = MODEL_DIR / "physics_wheat_iwr.pkl"
# # CWR model path kept for backward-compat (saved as physics wrapper)
# MODEL_PATH     = MODEL_DIR / "physics_wheat_cwr.pkl"

# # ── Physical constants (thesis Table 9) ──────────────────────────────────────
# KC_SLOPE     = 1.2088
# KC_INTERCEPT = 0.5375
# KC_MIN       = 0.30
# KC_MAX       = 1.15
# CWR_MIN      = 1.0
# CWR_MAX      = 15.0


# # ═══════════════════════════════════════════════════════════════════════════
# # Fallback / physics model wrappers  (module-level for pickle compatibility)
# # ═══════════════════════════════════════════════════════════════════════════

# class _ClimModel:
#     """
#     Ridge regression on sin_doy/cos_doy — picklable climatological fallback.
#     Implements .forecast(steps, exog) so it is a drop-in for SARIMAX results.
#     """
#     def __init__(self, reg, exog_cols_):
#         self._reg   = reg
#         self._ecols = list(exog_cols_)

#     def forecast(self, steps: int, exog=None) -> pd.Series:
#         if exog is not None and self._ecols:
#             available = [c for c in self._ecols if c in exog.columns]
#             if available:
#                 X = exog[available].values
#             else:
#                 X = np.zeros((steps, len(self._ecols)))
#         else:
#             X = np.zeros((steps, len(self._ecols)))
#         return pd.Series(self._reg.predict(X))


# class _NaiveModel:
#     """
#     Seasonal-naive fallback: predicts the training-set mean.
#     Implements .forecast(steps, exog) so it is a drop-in for SARIMAX results.
#     """
#     def __init__(self, mu: float):
#         self._mu = float(mu)

#     def forecast(self, steps: int, exog=None) -> pd.Series:
#         return pd.Series([self._mu] * steps)


# class _PhysicsIWR:
#     """
#     Physics-based IWR — NOT a statistical model.

#         IWR = max(CWR − Peff, 0)   [FAO-56 water balance, thesis §4.5]

#     Usage:
#         iwr_array = model.predict(cwr_array, peff_array)
#     """
#     def predict(self, cwr: np.ndarray, peff: np.ndarray) -> np.ndarray:
#         return np.maximum(np.asarray(cwr) - np.asarray(peff), 0.0)


# class _PhysicsCWR:
#     """
#     Physics-based CWR wrapper.

#         CWR = Kc × PET   [FAO-56, thesis Eq. 4]

#     Usage:
#         cwr_array = model.predict(kc_array, pet_array)
#     """
#     def predict(self, kc: np.ndarray, pet: np.ndarray) -> np.ndarray:
#         cwr = np.asarray(kc) * np.asarray(pet)
#         return np.clip(cwr, 0.0, CWR_MAX)


# class _KcPolyModel:
#     """
#     SAVI→Kc polynomial model wrapping a fitted sklearn Pipeline.
#     predict() accepts a 1-D SAVI array and returns clipped Kc values.
#     """
#     def __init__(self, pipeline: Pipeline):
#         self._pipe = pipeline

#     def predict(self, savi: np.ndarray) -> np.ndarray:
#         X   = np.asarray(savi).reshape(-1, 1)
#         raw = self._pipe.predict(X)
#         return np.clip(raw, KC_MIN, KC_MAX)


# # ═══════════════════════════════════════════════════════════════════════════
# # Raster utilities
# # ═══════════════════════════════════════════════════════════════════════════

# def extract_date(filename: str) -> datetime:
#     """Parse YYYYMMDD or DDMMMYYYY date from a filename."""
#     m = re.search(r"\d{8}", filename)
#     if m:
#         return datetime.strptime(m.group(), "%Y%m%d")
#     m = re.search(r"\d{2}[A-Z]{3}\d{4}", filename.upper())
#     if m:
#         return datetime.strptime(m.group(), "%d%b%Y")
#     raise ValueError(f"No valid date in: {filename}")


# def build_date_file_map(directory: Optional[Path]) -> Dict[datetime, Path]:
#     """Return {datetime: Path} for every .tif in *directory* (None-safe)."""
#     fm: Dict[datetime, Path] = {}
#     if directory is None or not directory.exists():
#         return fm
#     for fp in directory.glob("*"):
#         if fp.suffix.lower() in {".tif", ".tiff"}:
#             try:
#                 fm[extract_date(fp.name)] = fp
#             except Exception:
#                 pass
#     return fm


# def is_rabi(date: datetime) -> bool:
#     """Rabi wheat season: 15-Nov through 30-Apr."""
#     return (date.month == 11 and date.day >= 15) or date.month in [12, 1, 2, 3, 4]


# def raster_mean(fp: Path, mask_zeros: bool = True) -> float:
#     """Spatial mean of valid (non-nodata, non-nan) pixels."""
#     try:
#         with rasterio.open(fp) as src:
#             arr = src.read(1).astype(np.float64)
#             if src.nodata is not None:
#                 arr[arr == src.nodata] = np.nan
#             arr[arr < -900] = np.nan
#             if mask_zeros:
#                 arr[arr == 0] = np.nan
#             arr = arr[~np.isnan(arr)]
#             return float(np.mean(arr)) if len(arr) > 0 else np.nan
#     except Exception:
#         return np.nan


# def _interval_mean_raster(
#     start: datetime,
#     end: datetime,
#     raster_map: Dict[datetime, Path],
#     mask_zeros: bool = True,
# ) -> Optional[float]:
#     """
#     Mean raster value over the interval (start, end].
#     Falls back to the nearest past raster when no files fall inside the window.
#     Returns None only when no past file exists at all.
#     """
#     files = [(d, fp) for d, fp in raster_map.items() if start < d <= end]
#     if not files:
#         past = [(d, fp) for d, fp in raster_map.items() if d <= end]
#         if not past:
#             return None
#         _, best_fp = max(past, key=lambda x: x[0])
#         val = raster_mean(best_fp, mask_zeros=mask_zeros)
#         return None if np.isnan(val) else val
#     vals = [raster_mean(fp, mask_zeros=mask_zeros) for _, fp in files]
#     vals = [v for v in vals if not np.isnan(v)]
#     return float(np.mean(vals)) if vals else None


# # deprecated alias kept for backward compatibility
# _interval_mean_pet = _interval_mean_raster


# def _interval_sum(
#     start: datetime,
#     end: datetime,
#     rain_map: Dict[datetime, Path],
# ):
#     """
#     Sum raster values (e.g. rainfall) over (start, end].
#     Returns (total: float, n_files: int) or None.
#     """
#     files = [fp for d, fp in sorted(rain_map.items()) if start < d <= end]
#     if not files:
#         past = [(d, fp) for d, fp in rain_map.items() if d <= end]
#         if not past:
#             return None
#         files = [max(past, key=lambda x: x[0])[1]]
#     total = float(sum(raster_mean(fp, mask_zeros=False) for fp in files))
#     return total, len(files)


# def _doy_sin_cos(doy_series):
#     """Cyclic day-of-year encoding."""
#     angle = 2.0 * np.pi * np.asarray(doy_series, dtype=float) / 365.0
#     return np.sin(angle), np.cos(angle)


# def _effective_rainfall(rain_sum: float, interval_days: int) -> float:
#     """FAO-56 effective rainfall (Doorenbos & Pruitt, USDA-SCS)."""
#     pe_threshold = 75.0 * (interval_days / 30.0)
#     if rain_sum <= pe_threshold:
#         return max(0.6 * rain_sum - 10.0, 0.0)
#     return max(0.8 * rain_sum - 25.0, 0.0)


# # ═══════════════════════════════════════════════════════════════════════════
# # Validation metrics
# # ═══════════════════════════════════════════════════════════════════════════

# def compute_validation_metrics(observed, predicted) -> dict:
#     """R², NSE, RMSE, MAE, MAPE on the overlap of non-NaN values."""
#     obs  = np.asarray(observed,  dtype=float)
#     pred = np.asarray(predicted, dtype=float)
#     valid = ~(np.isnan(obs) | np.isnan(pred))
#     obs, pred = obs[valid], pred[valid]

#     if len(obs) < 2:
#         return {k: np.nan for k in ("R2", "NSE", "RMSE", "MAE", "MAPE")}

#     ss_res = np.sum((obs - pred) ** 2)
#     ss_tot = np.sum((obs - np.mean(obs)) ** 2)
#     r2   = 1.0 - ss_res / ss_tot if ss_tot > 0 else np.nan
#     nse  = r2
#     rmse = float(np.sqrt(mean_squared_error(obs, pred)))
#     mae  = float(mean_absolute_error(obs, pred))
#     nz   = np.abs(obs) > 1e-9
#     mape = float(np.mean(np.abs((obs[nz] - pred[nz]) / obs[nz])) * 100) if nz.any() else np.nan

#     return {
#         "R2":   round(r2,   4),
#         "NSE":  round(nse,  4),
#         "RMSE": round(rmse, 4),
#         "MAE":  round(mae,  4),
#         "MAPE": round(mape, 2),
#     }


# # ═══════════════════════════════════════════════════════════════════════════
# # Forecast exog builder — PUBLIC UTILITY (used by models.py + main.py)
# # DESIGN-FIX-7: single source of truth for exog construction
# # ═══════════════════════════════════════════════════════════════════════════

# def build_forecast_exog(
#     future_dates: pd.DatetimeIndex,
#     last_pet: float,
#     exog_cols: List[str],
#     temp_val: Optional[float] = None,
#     rad_val:  Optional[float] = None,
# ) -> pd.DataFrame:
#     """
#     Build the exogenous variable DataFrame for forecast horizon.

#     Strategy per variable:
#       sin_doy / cos_doy  — computed exactly from future calendar dates
#       pet_lag1           — carry-forward of last observed PET (persistence)
#       temp               — carry-forward of last observed temperature
#       radiation          — carry-forward of last observed radiation

#     Args:
#         future_dates : DatetimeIndex of forecast dates
#         last_pet     : last observed PET value (mm/day) for lag feature
#         exog_cols    : list of column names expected by the trained model
#         temp_val     : last observed temperature (°C), if in exog_cols
#         rad_val      : last observed radiation (MJ/m²), if in exog_cols

#     Returns:
#         DataFrame with exactly the columns in exog_cols.
#     """
#     records = []
#     for dt in future_dates:
#         doy = dt.timetuple().tm_yday
#         s, c = _doy_sin_cos([doy])
#         rec: Dict = {
#             "sin_doy":  float(s[0]),
#             "cos_doy":  float(c[0]),
#             "pet_lag1": float(last_pet),
#         }
#         if temp_val is not None:
#             rec["temp"] = float(temp_val)
#         if rad_val is not None:
#             rec["radiation"] = float(rad_val)
#         records.append(rec)

#     df = pd.DataFrame(records, index=future_dates)

#     # Keep only columns the model was trained on; fill any missing with 0
#     for col in exog_cols:
#         if col not in df.columns:
#             logger.warning(
#                 f"build_forecast_exog: column '{col}' not built — filling with 0. "
#                 "Check exog_cols in the saved model meta."
#             )
#             df[col] = 0.0

#     return df[exog_cols]


# # ═══════════════════════════════════════════════════════════════════════════
# # Dataset loaders
# # ═══════════════════════════════════════════════════════════════════════════

# def load_wheat_kc_dataset() -> pd.DataFrame:
#     """
#     Load (SAVI, Kc) pairs for Rabi dates.
#     Kc is the target; SAVI is the predictor.
#     """
#     logger.info("Loading Kc dataset...")
#     kc_map   = build_date_file_map(KC_DIR)
#     savi_map = build_date_file_map(SAVI_DIR)

#     records = []
#     for date, kc_fp in sorted(kc_map.items()):
#         if not is_rabi(date) or date not in savi_map:
#             continue
#         kc_val   = raster_mean(kc_fp,          mask_zeros=True)
#         savi_val = raster_mean(savi_map[date],  mask_zeros=True)
#         if np.isnan(kc_val) or np.isnan(savi_val):
#             continue
#         doy = date.timetuple().tm_yday
#         s, c = _doy_sin_cos([doy])
#         records.append({"date": date, "kc": kc_val, "savi": savi_val,
#                          "sin_doy": s[0], "cos_doy": c[0]})

#     if not records:
#         raise RuntimeError("No Kc/SAVI data found — check KC_DIR and SAVI_DIR")
#     df = pd.DataFrame(records).sort_values("date").set_index("date")
#     logger.info(f"Kc dataset: {len(df)} records")
#     return df


# def load_wheat_pet_dataset() -> pd.DataFrame:
#     """
#     Load PET dataset aligned to Sentinel-2 acquisition dates.

#     DESIGN-FIX-4: Adds pet_lag1 (one-step lagged PET) as an exogenous variable.
#     PET is highly autocorrelated within the Rabi season (r > 0.85 at lag-1),
#     making the lag a much stronger predictor than DOY alone.

#     Optional temperature and solar radiation rasters are included when their
#     directories are configured (INSAT_TEMP / INSAT_RAD).
#     """
#     logger.info("Loading PET dataset...")
#     pet_map  = build_date_file_map(PET_DIR)
#     kc_map   = build_date_file_map(KC_DIR)
#     temp_map = build_date_file_map(TEMP_DIR)
#     rad_map  = build_date_file_map(RAD_DIR)

#     sentinel_dates = sorted(d for d in kc_map if is_rabi(d))
#     records = []

#     for i, date in enumerate(sentinel_dates):
#         prev_date = sentinel_dates[i - 1] if i > 0 else date - timedelta(days=5)
#         pet_val = _interval_mean_raster(prev_date, date, pet_map, mask_zeros=True)
#         if pet_val is None:
#             continue

#         doy = date.timetuple().tm_yday
#         s, c = _doy_sin_cos([doy])
#         rec = {"date": date, "pet": pet_val, "sin_doy": s[0], "cos_doy": c[0]}

#         # DESIGN-FIX-4: lagged PET
#         if records:
#             rec["pet_lag1"] = records[-1]["pet"]
#         else:
#             rec["pet_lag1"] = pet_val  # first row: use same value

#         if temp_map:
#             t = _interval_mean_raster(prev_date, date, temp_map, mask_zeros=False)
#             rec["temp"] = t if t is not None else np.nan

#         if rad_map:
#             r = _interval_mean_raster(prev_date, date, rad_map, mask_zeros=False)
#             rec["radiation"] = r if r is not None else np.nan

#         records.append(rec)

#     if not records:
#         raise RuntimeError("No PET data found — check PET_DIR")

#     df = pd.DataFrame(records).sort_values("date").set_index("date")

#     for col in ("temp", "radiation"):
#         if col in df.columns:
#             n_miss = df[col].isna().sum()
#             if n_miss > 0:
#                 logger.warning(
#                     f"PET dataset: {n_miss} missing '{col}' values — interpolating"
#                 )
#                 df[col] = df[col].interpolate(method="time").bfill().ffill()

#     logger.info(f"PET dataset: {len(df)} records, columns: {list(df.columns)}")
#     return df


# def load_wheat_cwr_dataset() -> pd.DataFrame:
#     """
#     Load CWR + PET + Kc dataset for validation purposes only.
#     NOTE: CWR is no longer modelled with SARIMAX; this loader is used only
#     for computing physics validation metrics (CWR_computed vs CWR_observed).
#     """
#     logger.info("Loading CWR dataset (for validation)...")
#     pet_map  = build_date_file_map(PET_DIR)
#     kc_map   = build_date_file_map(KC_DIR)
#     savi_map = build_date_file_map(SAVI_DIR)

#     cwr_files = []
#     for fp in sorted(CWR_DIR.glob("cwr_*.tif")):
#         try:
#             d = extract_date(fp.name)
#             if is_rabi(d):
#                 cwr_files.append((d, fp))
#         except Exception:
#             pass

#     records = []
#     for i, (date, cwr_fp) in enumerate(cwr_files):
#         prev_date = cwr_files[i - 1][0] if i > 0 else date - timedelta(days=5)
#         pet_val = _interval_mean_raster(prev_date, date, pet_map, mask_zeros=True)
#         if pet_val is None or date not in kc_map or date not in savi_map:
#             continue
#         cwr_val  = raster_mean(cwr_fp,           mask_zeros=True)
#         kc_val   = raster_mean(kc_map[date],      mask_zeros=True)
#         savi_val = raster_mean(savi_map[date],     mask_zeros=True)
#         if any(np.isnan(v) for v in [cwr_val, kc_val, savi_val]):
#             continue
#         doy = date.timetuple().tm_yday
#         s, c = _doy_sin_cos([doy])
#         records.append({
#             "date": date, "cwr": cwr_val, "pet": pet_val,
#             "kc": kc_val, "savi": savi_val,
#             "sin_doy": s[0], "cos_doy": c[0],
#         })

#     if not records:
#         raise RuntimeError("No CWR data found — check CWR_DIR, PET_DIR, KC_DIR, SAVI_DIR")
#     df = pd.DataFrame(records).sort_values("date").set_index("date")
#     logger.info(f"CWR dataset: {len(df)} records")
#     return df


# def load_wheat_iwr_dataset() -> pd.DataFrame:
#     """Load IWR + CWR + rainfall dataset for physics validation."""
#     logger.info("Loading IWR dataset...")
#     rain_map = build_date_file_map(RAIN_DIR)
#     kc_map   = build_date_file_map(KC_DIR)
#     savi_map = build_date_file_map(SAVI_DIR)

#     cwr_map: Dict[datetime, Path] = {}
#     for fp in CWR_DIR.glob("cwr_*.tif"):
#         try:
#             cwr_map[extract_date(fp.name)] = fp
#         except Exception:
#             pass

#     iwr_files = sorted(IWR_DIR.glob("iwr_*.tif"))
#     if not iwr_files:
#         raise RuntimeError(f"No IWR files found in {IWR_DIR}")

#     records = []
#     for i, iwr_fp in enumerate(iwr_files):
#         date = extract_date(iwr_fp.name)
#         if not is_rabi(date):
#             continue
#         prev_date = (extract_date(iwr_files[i - 1].name) if i > 0
#                      else date - timedelta(days=5))

#         rain_result = _interval_sum(prev_date, date, rain_map)
#         if rain_result is None:
#             continue
#         rain_sum, _ = rain_result

#         if np.isnan(rain_sum):
#             logger.debug(f"[iwr_dataset] rain_sum=nan for {date.date()} — skipping")
#             continue

#         if date not in kc_map or date not in savi_map:
#             continue

#         kc_val   = raster_mean(kc_map[date],  mask_zeros=True)
#         savi_val = raster_mean(savi_map[date], mask_zeros=True)
#         iwr_val  = raster_mean(iwr_fp,         mask_zeros=True)
#         cwr_val  = raster_mean(cwr_map[date],  mask_zeros=True) if date in cwr_map else np.nan

#         if any(np.isnan(v) for v in [kc_val, savi_val, iwr_val]):
#             continue

#         interval_days = max((date - prev_date).days, 1)
#         eff_rain      = _effective_rainfall(rain_sum, interval_days)
#         doy           = date.timetuple().tm_yday
#         s, c          = _doy_sin_cos([doy])

#         records.append({
#             "date":     date,
#             "iwr":      iwr_val,
#             "cwr":      cwr_val,
#             "rain":     rain_sum,
#             "eff_rain": eff_rain,
#             "kc":       kc_val,
#             "savi":     savi_val,
#             "sin_doy":  s[0],
#             "cos_doy":  c[0],
#         })

#     if not records:
#         raise RuntimeError("No IWR data found — check IWR_DIR, RAIN_DIR, KC_DIR")
#     df = pd.DataFrame(records).sort_values("date").set_index("date")
#     logger.info(f"IWR dataset: {len(df)} records")
#     return df


# # ═══════════════════════════════════════════════════════════════════════════
# # SARIMAX training  (used for PET only)
# # ═══════════════════════════════════════════════════════════════════════════

# def _climatological_regression(y_train, y_test, exog_train, exog_test):
#     """Ridge regression on sin/cos DOY — used as a SARIMAX fallback."""
#     if exog_train is None or "sin_doy" not in exog_train.columns:
#         return np.full(len(y_test), y_train.mean()), None
#     X_tr = exog_train[["sin_doy", "cos_doy"]].values
#     X_te = exog_test[["sin_doy",  "cos_doy"]].values
#     reg  = Ridge(alpha=1.0).fit(X_tr, y_train.values)
#     return reg.predict(X_te), reg


# def train_sarimax_model(
#     y: pd.Series,
#     exog: pd.DataFrame,
#     target_name: str,
#     seasonal_period: int = 26,
# ):
#     """
#     Train SARIMAX with AIC-guided grid search.

#     DESIGN-FIX-6: d=0 is now searched alongside d=1.
#     PET within a Rabi season is typically stationary (no unit root); forcing
#     d=1 over-differences the signal and collapses forecasts toward the mean.

#     Raises TypeError if y is not a pd.Series.
#     """
#     logger.info(f"\n{'='*65}")
#     logger.info(f"Training SARIMAX for {target_name.upper()}")
#     logger.info(f"{'='*65}")

#     if not isinstance(y, pd.Series):
#         raise TypeError(
#             f"'y' must be a pd.Series, got {type(y).__name__}. "
#             f"Pass df['{target_name}'] explicitly."
#         )

#     common_idx = y.index.intersection(exog.index)
#     if len(common_idx) == 0:
#         raise ValueError(
#             "No common dates between y and exog — check dataset loaders."
#         )
#     y    = y.loc[common_idx]
#     exog = exog.loc[common_idx]

#     valid_rows = ~exog.isnull().any(axis=1)
#     y    = y[valid_rows]
#     exog = exog[valid_rows]

#     logger.info(f"Total samples after cleaning: {len(y)}")
#     logger.info(f"Exogenous variables: {list(exog.columns)}")

#     split_idx = int(len(y) * 0.8)
#     if split_idx < 20:
#         raise ValueError(
#             f"Too few samples ({len(y)}) — need ≥ 25 total so that the "
#             "80 % training split contains ≥ 20 samples."
#         )

#     y_train, y_test       = y.iloc[:split_idx],    y.iloc[split_idx:]
#     exog_train, exog_test = exog.iloc[:split_idx], exog.iloc[split_idx:]

#     logger.info(
#         f"Train: {len(y_train)} ({y_train.index[0].date()} → {y_train.index[-1].date()})"
#     )
#     logger.info(
#         f"Test:  {len(y_test)}  ({y_test.index[0].date()}  → {y_test.index[-1].date()})"
#     )

#     # ── Grid search — DESIGN-FIX-6: include d=0 ──────────────────────────
#     best_aic = np.inf
#     best_result = best_order = best_seasonal = None

#     for p in [0, 1, 2]:
#         for d in [0, 1]:           # ← FIX: was hardcoded d=1
#             for q in [0, 1]:
#                 for P in [0, 1]:
#                     for D in [0, 1]:
#                         for Q in [0, 1]:
#                             try:
#                                 res = SARIMAX(
#                                     y_train, exog=exog_train,
#                                     order=(p, d, q),
#                                     seasonal_order=(P, D, Q, seasonal_period),
#                                     trend="c",
#                                     enforce_stationarity=False,
#                                     enforce_invertibility=False,
#                                 ).fit(disp=False, method="lbfgs", maxiter=500)
#                                 if res.aic < best_aic:
#                                     best_aic      = res.aic
#                                     best_result   = res
#                                     best_order    = (p, d, q)
#                                     best_seasonal = (P, D, Q, seasonal_period)
#                             except Exception:
#                                 continue

#     # ── Evaluate on test set ─────────────────────────────────────────────
#     metrics = None
#     if best_result is not None:
#         try:
#             fc      = best_result.forecast(steps=len(y_test), exog=exog_test)
#             metrics = compute_validation_metrics(y_test.values, fc.values)
#             logger.info(
#                 f"Best SARIMAX {best_order} × {best_seasonal}: "
#                 f"R²={metrics['R2']:.4f}, RMSE={metrics['RMSE']:.4f}"
#             )
#         except Exception as e:
#             logger.warning(f"SARIMAX test forecast failed: {e}")
#             best_result = None

#     # ── Climatological fallback ───────────────────────────────────────────
#     clim_pred, clim_reg = _climatological_regression(
#         y_train, y_test, exog_train, exog_test
#     )
#     clim_m = compute_validation_metrics(y_test.values, clim_pred)
#     logger.info(
#         f"Climatological baseline: R²={clim_m['R2']:.4f}, "
#         f"RMSE={clim_m['RMSE']:.4f}"
#     )

#     r2_best: float
#     if metrics is None or metrics.get("R2") is None or np.isnan(metrics["R2"]):
#         r2_best = -np.inf
#     else:
#         r2_best = float(metrics["R2"])

#     use_clim = (not np.isnan(clim_m["R2"])) and (clim_m["R2"] > r2_best)

#     if use_clim and clim_reg is not None:
#         logger.info("Climatological regression outperforms SARIMAX — using it")
#         X_full   = exog[["sin_doy", "cos_doy"]].values
#         full_reg = Ridge(alpha=1.0).fit(X_full, y.values)
#         return (
#             _ClimModel(full_reg, ["sin_doy", "cos_doy"]),
#             clim_m,
#             (0, 0, 0),
#         )

#     if best_result is None:
#         logger.warning("All SARIMAX fits failed — falling back to seasonal naive")
#         return _NaiveModel(float(y_train.mean())), clim_m, (0, 0, 0)

#     # ── Retrain winner on full data ───────────────────────────────────────
#     try:
#         final_model = SARIMAX(
#             y, exog=exog,
#             order=best_order,
#             seasonal_order=best_seasonal,
#             trend="c",
#         ).fit(disp=False, method="lbfgs", maxiter=500)
#     except Exception:
#         final_model = best_result

#     return final_model, metrics, best_order


# # ═══════════════════════════════════════════════════════════════════════════
# # Kc: SAVI→Kc polynomial regression
# # ═══════════════════════════════════════════════════════════════════════════

# def train_kc_model():
#     """
#     Fit a polynomial regression  Kc = f(SAVI)  (degree 1 or 2).
#     Thesis-constant fallback builds a properly fitted degree-1 Pipeline
#     with overridden Ridge coefficients.
#     """
#     df = load_wheat_kc_dataset()

#     X = df[["savi"]].values
#     y = df["kc"].values

#     split_idx = int(len(df) * 0.8)
#     if split_idx < 10:
#         raise ValueError(f"Too few Kc/SAVI pairs: {len(df)} — need ≥ 13")

#     X_train, X_test = X[:split_idx], X[split_idx:]
#     y_train, y_test = y[:split_idx], y[split_idx:]

#     best_pipe, best_metrics, best_degree = None, None, None

#     for degree in [1, 2]:
#         pipe = Pipeline([
#             ("poly",  PolynomialFeatures(degree=degree, include_bias=True)),
#             ("ridge", Ridge(alpha=0.5)),
#         ])
#         pipe.fit(X_train, y_train)
#         pred    = np.clip(pipe.predict(X_test), KC_MIN, KC_MAX)
#         metrics = compute_validation_metrics(y_test, pred)
#         logger.info(
#             f"Kc poly degree={degree}: R²={metrics['R2']:.4f}, "
#             f"RMSE={metrics['RMSE']:.4f}, MAE={metrics['MAE']:.4f}"
#         )
#         if best_metrics is None or metrics["R2"] > best_metrics["R2"]:
#             best_pipe, best_metrics, best_degree = pipe, metrics, degree

#     thesis_pred = np.clip(
#         KC_SLOPE * X_test[:, 0] + KC_INTERCEPT, KC_MIN, KC_MAX
#     )
#     thesis_m = compute_validation_metrics(y_test, thesis_pred)
#     logger.info(
#         f"Kc thesis constants (linear): R²={thesis_m['R2']:.4f}, "
#         f"RMSE={thesis_m['RMSE']:.4f}"
#     )

#     r2_poly = best_metrics["R2"] if best_metrics else -np.inf

#     if thesis_m["R2"] > r2_poly:
#         logger.info(
#             "Thesis constants outperform polynomial fit — "
#             "building degree-1 pipeline with enforced coefficients"
#         )
#         thesis_pipe = Pipeline([
#             ("poly",  PolynomialFeatures(degree=1, include_bias=True)),
#             ("ridge", Ridge(alpha=0.0, fit_intercept=False)),
#         ])
#         thesis_pipe.fit(X, y)
#         thesis_pipe.named_steps["ridge"].coef_ = np.array(
#             [KC_INTERCEPT, KC_SLOPE]
#         )
#         kc_model     = _KcPolyModel(thesis_pipe)
#         best_metrics = thesis_m
#         best_degree  = 1
#     else:
#         best_pipe.fit(X, y)
#         kc_model = _KcPolyModel(best_pipe)

#     meta = {
#         "model":       kc_model,
#         "metrics":     best_metrics,
#         "degree":      best_degree,
#         "last_date":   df.index[-1],
#         "target_name": "kc",
#         "note":        f"SAVI→Kc poly degree={best_degree} (v9.0)",
#     }

#     with open(KC_MODEL_PATH, "wb") as f:
#         pickle.dump(meta, f)

#     logger.info(
#         f"✓ Kc model saved  "
#         f"(Test R²={best_metrics['R2']:.4f}, RMSE={best_metrics['RMSE']:.4f})"
#     )
#     return kc_model, best_metrics


# # ═══════════════════════════════════════════════════════════════════════════
# # PET: SARIMAX  — the ONLY variable we forecast statistically
# # DESIGN-FIX-1/4: PET forecast is the root of the entire forecast chain
# # ═══════════════════════════════════════════════════════════════════════════

# def train_pet_model():
#     """
#     SARIMAX for PET (the only statistically forecasted variable).

#     DESIGN-FIX-4: pet_lag1 is now the primary exogenous variable.
#     PET is highly persistent within a season; the lag feature dramatically
#     improves SARIMAX R² and prevents the flat-forecast issue.

#     Exog priority:
#       1. sin_doy, cos_doy  — always included (seasonal cycle)
#       2. pet_lag1          — always included (persistence)
#       3. temp, radiation   — included if raster directories are configured

#     DESIGN-FIX-5 note: seasonal_period=26 is correct because the PET dataset
#     is aligned to Sentinel acquisition dates (~5-day cadence), giving
#     26 observations per ~4-month Rabi season.
#     """
#     df = load_wheat_pet_dataset()

#     base_exog  = ["sin_doy", "cos_doy", "pet_lag1"]
#     extra_exog = [
#         c for c in ("temp", "radiation")
#         if c in df.columns and not df[c].isna().all()
#     ]
#     if not extra_exog:
#         logger.warning(
#             "PET model: temperature/radiation rasters not found. "
#             "Using DOY + lag exog — configure insat_temp/insat_rad to improve R²."
#         )
#     else:
#         logger.info(f"PET model: using extra exog: {extra_exog}")

#     exog_cols = base_exog + extra_exog
#     model, metrics, order = train_sarimax_model(
#         df["pet"], df[exog_cols], "pet", seasonal_period=26
#     )

#     meta = {
#         "model":       model,
#         "metrics":     metrics,
#         "exog_cols":   exog_cols,
#         "order":       order,
#         "last_date":   df.index[-1],
#         "last_pet":    float(df["pet"].iloc[-1]),   # needed for lag at forecast time
#         "target_name": "pet",
#         "note":        f"SARIMAX PET exog={exog_cols} (v9.0)",
#     }

#     with open(PET_MODEL_PATH, "wb") as f:
#         pickle.dump(meta, f)

#     logger.info(
#         f"✓ PET model saved  "
#         f"(Test R²={metrics['R2']:.4f}, RMSE={metrics['RMSE']:.4f})"
#     )
#     return model, metrics


# # ═══════════════════════════════════════════════════════════════════════════
# # CWR: Physics wrapper  CWR = Kc × PET
# # DESIGN-FIX-2: CWR is no longer forecasted with SARIMAX.
# # A physics wrapper is saved so load_model('cwr') returns a consistent
# # interface and existing code that calls _get_model('cwr') does not break.
# # ═══════════════════════════════════════════════════════════════════════════

# def train_cwr_model():
#     """
#     Validate CWR physics relationship and save _PhysicsCWR wrapper.

#     CWR = Kc × PET   (FAO-56, thesis Eq. 4)

#     This validates how well the physics formula reconstructs observed CWR
#     rasters.  The _PhysicsCWR wrapper is what main.py uses at forecast time.
#     """
#     df = load_wheat_cwr_dataset()

#     cwr_physics = np.clip(df["kc"].values * df["pet"].values, 0.0, CWR_MAX)
#     valid_mask  = ~np.isnan(df["cwr"].values)
#     metrics     = compute_validation_metrics(
#         df["cwr"].values[valid_mask], cwr_physics[valid_mask]
#     )

#     logger.info("Physics CWR = Kc × PET:")
#     logger.info(f"  R²  : {metrics['R2']:.4f}")
#     logger.info(f"  RMSE: {metrics['RMSE']:.4f} mm/day")
#     logger.info(f"  MAE : {metrics['MAE']:.4f} mm/day")
#     logger.info(f"  Mean CWR (raster)  : {float(np.nanmean(df['cwr'].values)):.3f} mm/day")
#     logger.info(f"  Mean CWR (physics) : {float(np.mean(cwr_physics)):.3f} mm/day")

#     physics_model = _PhysicsCWR()

#     meta = {
#         "model":       physics_model,
#         "metrics":     metrics,
#         "last_date":   df.index[-1],
#         "target_name": "cwr",
#         "note":        "Physics: CWR = Kc × PET (v9.0)",
#         "exog_cols":   [],   # no exog needed — deterministic from Kc + PET
#     }

#     with open(MODEL_PATH, "wb") as f:
#         pickle.dump(meta, f)

#     logger.info(
#         f"✓ CWR model saved  "
#         f"(Test R²={metrics['R2']:.4f}, RMSE={metrics['RMSE']:.4f} mm/day)"
#     )
#     return physics_model, metrics


# # ═══════════════════════════════════════════════════════════════════════════
# # IWR: physics-based  IWR = max(CWR − Peff, 0)
# # ═══════════════════════════════════════════════════════════════════════════

# def train_iwr_model():
#     """
#     IWR is computed deterministically from CWR and effective rainfall.

#         IWR = max(CWR − Peff, 0)   [FAO-56, thesis §4.5]

#     A _PhysicsIWR wrapper is saved for load_model('iwr').
#     """
#     df = load_wheat_iwr_dataset()

#     iwr_physics = np.maximum(df["cwr"].values - df["eff_rain"].values, 0.0)
#     valid_mask  = ~np.isnan(df["cwr"].values)
#     metrics     = compute_validation_metrics(
#         df["iwr"].values[valid_mask], iwr_physics[valid_mask]
#     )

#     logger.info("Physics IWR = max(CWR − Peff, 0):")
#     logger.info(f"  R²  : {metrics['R2']:.4f}")
#     logger.info(f"  RMSE: {metrics['RMSE']:.4f} mm/day")
#     logger.info(f"  MAE : {metrics['MAE']:.4f} mm/day")
#     logger.info(f"  Mean CWR (raster)  : {float(np.nanmean(df['cwr'].values)):.3f} mm/day")
#     logger.info(f"  Mean Peff          : {float(np.nanmean(df['eff_rain'].values)):.3f} mm/day")
#     logger.info(f"  Mean IWR (physics) : {float(np.mean(iwr_physics)):.3f} mm/day")
#     logger.info(f"  Mean IWR (observed): {float(np.nanmean(df['iwr'].values)):.3f} mm/day")

#     physics_model = _PhysicsIWR()

#     meta = {
#         "model":       physics_model,
#         "metrics":     metrics,
#         "last_date":   df.index[-1],
#         "target_name": "iwr",
#         "note":        "Physics: IWR = max(CWR − Peff, 0) (v9.0)",
#         "mean_cwr":    float(np.nanmean(df["cwr"].values)),
#         "mean_peff":   float(np.nanmean(df["eff_rain"].values)),
#     }

#     with open(IWR_MODEL_PATH, "wb") as f:
#         pickle.dump(meta, f)

#     logger.info(
#         f"✓ IWR model saved  "
#         f"(Test R²={metrics['R2']:.4f}, RMSE={metrics['RMSE']:.4f} mm/day)"
#     )
#     return physics_model, metrics


# # ═══════════════════════════════════════════════════════════════════════════
# # Train all
# # ═══════════════════════════════════════════════════════════════════════════

# def train_all_models() -> dict:
#     """
#     Train all models in dependency order:
#       1. Kc  (polynomial SAVI→Kc)
#       2. PET (SARIMAX — the only statistically forecasted variable)
#       3. CWR (physics wrapper for validation)
#       4. IWR (physics wrapper for validation)
#     """
#     logger.info("=" * 80)
#     logger.info("Training All Models — v9.0")
#     logger.info("Forecast chain: PET(SARIMAX) → CWR=Kc×PET → IWR=max(CWR-Peff,0)")
#     logger.info("=" * 80)

#     results = {}
#     for name, fn in [
#         ("kc",  train_kc_model),
#         ("pet", train_pet_model),
#         ("cwr", train_cwr_model),
#         ("iwr", train_iwr_model),
#     ]:
#         try:
#             model, metrics = fn()
#             results[name]  = {"model": model, "metrics": metrics}
#         except Exception as e:
#             logger.error(f"{name.upper()} model failed: {e}")
#             import traceback
#             traceback.print_exc()
#             results[name] = None

#     logger.info("\n" + "=" * 80)
#     logger.info("Training Summary")
#     logger.info("=" * 80)
#     for name, result in results.items():
#         if result:
#             m = result["metrics"]
#             logger.info(f"\n{name.upper()}:")
#             for k in ("R2", "NSE", "RMSE", "MAE", "MAPE"):
#                 v = m.get(k)
#                 if v is not None and not (isinstance(v, float) and np.isnan(v)):
#                     logger.info(f"  {k:6s}: {v}")

#     return results


# # ═══════════════════════════════════════════════════════════════════════════
# # Model loading
# # ═══════════════════════════════════════════════════════════════════════════

# def load_model(model_type: str):
#     """
#     Load a trained model pickle.
#     Returns (model, meta) — same interface for all model types.
#     """
#     path_map = {
#         "kc":  KC_MODEL_PATH,
#         "pet": PET_MODEL_PATH,
#         "cwr": MODEL_PATH,
#         "iwr": IWR_MODEL_PATH,
#     }
#     path = path_map.get(model_type)
#     if not path or not path.exists():
#         raise FileNotFoundError(f"Model not found: {path}")
#     with open(path, "rb") as f:
#         meta = pickle.load(f)
#     logger.info(
#         f"Loaded {model_type.upper()} model — {meta.get('note', '')} "
#         f"(Test R²={meta['metrics']['R2']:.4f})"
#     )
#     return meta["model"], meta


# # ═══════════════════════════════════════════════════════════════════════════
# # Quick smoke-test
# # ═══════════════════════════════════════════════════════════════════════════

# if __name__ == "__main__":
#     logging.basicConfig(level=logging.INFO)
#     results = train_all_models()

#     if results.get("kc"):
#         kc_model  = results["kc"]["model"]
#         test_savi = np.array([0.2, 0.4, 0.6, 0.8])
#         kc_pred   = kc_model.predict(test_savi)
#         print("\nKc predictions for SAVI = [0.2, 0.4, 0.6, 0.8]:")
#         for s, k in zip(test_savi, kc_pred):
#             print(f"  SAVI={s:.1f}  →  Kc={k:.4f}")

#     if results.get("iwr"):
#         iwr_model = results["iwr"]["model"]
#         cwr_vals  = np.array([3.0, 5.0, 7.0])
#         peff_vals = np.array([1.5, 4.0, 8.0])
#         iwr_pred  = iwr_model.predict(cwr_vals, peff_vals)
#         print("\nIWR predictions (CWR − Peff):")
#         for cwr, peff, iwr in zip(cwr_vals, peff_vals, iwr_pred):
#             print(f"  CWR={cwr:.1f}, Peff={peff:.1f}  →  IWR={iwr:.2f}")



"""
models.py  — v10.0
═══════════════════════════════════════════════════════════════════════════
CHANGES from v9.0:

  DESIGN-v10-1  SAVI is now forecasted with SARIMAX (NEW).
                Previous design projected Kc using a static DOY nudge
                (_project_kc_for_dates).  That approach ignored actual
                crop phenology dynamics mid-season.
                Kc is now derived from the SAVI forecast:
                    Kc_forecast = 1.2088 × SAVI_forecast + 0.5375

  DESIGN-v10-2  Forecast chain is now fully explicit:
                    SAVI (SARIMAX) ──► Kc  (= 1.2088×SAVI + 0.5375)
                    PET  (SARIMAX) ──┐
                                     ├──► CWR = Kc × PET
                                     └──► IWR = max(CWR − Peff, 0)

  DESIGN-v10-3  No circular dependencies anywhere in the chain.
                SAVI and PET are independent time series — both driven only
                by DOY cyclic exog + lag.  Kc, CWR, IWR are all computed,
                never statistically modelled.

  DESIGN-v10-4  build_savi_forecast_exog() added as public utility
                (symmetric to build_forecast_exog for PET).

Physics chain (thesis FAO-56):
    SAVI (SARIMAX)  →  Kc = 1.2088×SAVI + 0.5375  (clip 0.30–1.15)
    PET  (SARIMAX)  →  CWR = Kc × PET_forecast
    CWR − Peff      →  IWR = max(CWR − Peff, 0)
═══════════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import logging
import os
import pickle
import re
import warnings
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import rasterio
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import PolynomialFeatures
from statsmodels.tsa.statespace.sarimax import SARIMAX

warnings.filterwarnings("ignore")
logger = logging.getLogger(__name__)

from config import DIRECTORIES

# ── Directory paths ──────────────────────────────────────────────────────────
CWR_DIR  = DIRECTORIES["processed"]["cwr"]
IWR_DIR  = DIRECTORIES["processed"]["iwr"]
PET_DIR  = DIRECTORIES["raw"]["insat_pet"]
KC_DIR   = DIRECTORIES["processed"]["kc"]
SAVI_DIR = DIRECTORIES["processed"]["savi"]
RAIN_DIR = DIRECTORIES["raw"]["insat_rain"]

TEMP_DIR: Optional[Path] = DIRECTORIES["raw"].get("insat_temp")
RAD_DIR:  Optional[Path] = DIRECTORIES["raw"].get("insat_rad")

if TEMP_DIR is None:
    logger.info(
        "DIRECTORIES['raw']['insat_temp'] not configured — "
        "PET model will use DOY + lag exog only"
    )
if RAD_DIR is None:
    logger.info(
        "DIRECTORIES['raw']['insat_rad'] not configured — "
        "PET model will use DOY + lag exog only"
    )

MODEL_DIR = DIRECTORIES["models"]
os.makedirs(MODEL_DIR, exist_ok=True)

# ── Model file paths ─────────────────────────────────────────────────────────
PET_MODEL_PATH  = MODEL_DIR / "sarimax_wheat_pet.pkl"
SAVI_MODEL_PATH = MODEL_DIR / "sarimax_wheat_savi.pkl"   # NEW v10.0
KC_MODEL_PATH   = MODEL_DIR / "poly_wheat_kc.pkl"
IWR_MODEL_PATH  = MODEL_DIR / "physics_wheat_iwr.pkl"
MODEL_PATH      = MODEL_DIR / "physics_wheat_cwr.pkl"    # backward-compat alias

# ── Physical constants (thesis Table 9) ──────────────────────────────────────
KC_SLOPE     = 1.2088
KC_INTERCEPT = 0.5375
KC_MIN       = 0.30
KC_MAX       = 1.15
CWR_MIN      = 1.0
CWR_MAX      = 15.0


# ═══════════════════════════════════════════════════════════════════════════
# Fallback / physics model wrappers  (module-level for pickle compatibility)
# ═══════════════════════════════════════════════════════════════════════════

class _ClimModel:
    """
    Ridge regression on sin_doy/cos_doy — picklable climatological fallback.
    Implements .forecast(steps, exog) so it is a drop-in for SARIMAX results.
    """
    def __init__(self, reg, exog_cols_):
        self._reg   = reg
        self._ecols = list(exog_cols_)

    def forecast(self, steps: int, exog=None) -> pd.Series:
        if exog is not None and self._ecols:
            available = [c for c in self._ecols if c in exog.columns]
            if available:
                X = exog[available].values
            else:
                X = np.zeros((steps, len(self._ecols)))
        else:
            X = np.zeros((steps, len(self._ecols)))
        return pd.Series(self._reg.predict(X))


class _NaiveModel:
    """
    Seasonal-naive fallback: predicts the training-set mean.
    Implements .forecast(steps, exog) so it is a drop-in for SARIMAX results.
    """
    def __init__(self, mu: float):
        self._mu = float(mu)

    def forecast(self, steps: int, exog=None) -> pd.Series:
        return pd.Series([self._mu] * steps)


class _PhysicsIWR:
    """
    Physics-based IWR — NOT a statistical model.

        IWR = max(CWR − Peff, 0)   [FAO-56 water balance, thesis §4.5]

    Usage:
        iwr_array = model.predict(cwr_array, peff_array)
    """
    def predict(self, cwr: np.ndarray, peff: np.ndarray) -> np.ndarray:
        return np.maximum(np.asarray(cwr) - np.asarray(peff), 0.0)


class _PhysicsCWR:
    """
    Physics-based CWR wrapper.

        CWR = Kc × PET   [FAO-56, thesis Eq. 4]

    Usage:
        cwr_array = model.predict(kc_array, pet_array)
    """
    def predict(self, kc: np.ndarray, pet: np.ndarray) -> np.ndarray:
        cwr = np.asarray(kc) * np.asarray(pet)
        return np.clip(cwr, 0.0, CWR_MAX)


class _KcPolyModel:
    """
    SAVI→Kc polynomial model wrapping a fitted sklearn Pipeline.
    predict() accepts a 1-D SAVI array and returns clipped Kc values.
    """
    def __init__(self, pipeline: Pipeline):
        self._pipe = pipeline

    def predict(self, savi: np.ndarray) -> np.ndarray:
        X   = np.asarray(savi).reshape(-1, 1)
        raw = self._pipe.predict(X)
        return np.clip(raw, KC_MIN, KC_MAX)


# ═══════════════════════════════════════════════════════════════════════════
# Raster utilities
# ═══════════════════════════════════════════════════════════════════════════

def extract_date(filename: str) -> datetime:
    """Parse YYYYMMDD or DDMMMYYYY date from a filename."""
    m = re.search(r"\d{8}", filename)
    if m:
        return datetime.strptime(m.group(), "%Y%m%d")
    m = re.search(r"\d{2}[A-Z]{3}\d{4}", filename.upper())
    if m:
        return datetime.strptime(m.group(), "%d%b%Y")
    raise ValueError(f"No valid date in: {filename}")


def build_date_file_map(directory: Optional[Path]) -> Dict[datetime, Path]:
    """Return {datetime: Path} for every .tif in *directory* (None-safe)."""
    fm: Dict[datetime, Path] = {}
    if directory is None or not directory.exists():
        return fm
    for fp in directory.glob("*"):
        if fp.suffix.lower() in {".tif", ".tiff"}:
            try:
                fm[extract_date(fp.name)] = fp
            except Exception:
                pass
    return fm


def is_rabi(date: datetime) -> bool:
    """Rabi wheat season: 15-Nov through 30-Apr."""
    return (date.month == 11 and date.day >= 15) or date.month in [12, 1, 2, 3, 4]


def raster_mean(fp: Path, mask_zeros: bool = True) -> float:
    """Spatial mean of valid (non-nodata, non-nan) pixels."""
    try:
        with rasterio.open(fp) as src:
            arr = src.read(1).astype(np.float64)
            if src.nodata is not None:
                arr[arr == src.nodata] = np.nan
            arr[arr < -900] = np.nan
            if mask_zeros:
                arr[arr == 0] = np.nan
            arr = arr[~np.isnan(arr)]
            return float(np.mean(arr)) if len(arr) > 0 else np.nan
    except Exception:
        return np.nan


def _interval_mean_raster(
    start: datetime,
    end: datetime,
    raster_map: Dict[datetime, Path],
    mask_zeros: bool = True,
) -> Optional[float]:
    """
    Mean raster value over the interval (start, end].
    Falls back to the nearest past raster when no files fall inside the window.
    Returns None only when no past file exists at all.
    """
    files = [(d, fp) for d, fp in raster_map.items() if start < d <= end]
    if not files:
        past = [(d, fp) for d, fp in raster_map.items() if d <= end]
        if not past:
            return None
        _, best_fp = max(past, key=lambda x: x[0])
        val = raster_mean(best_fp, mask_zeros=mask_zeros)
        return None if np.isnan(val) else val
    vals = [raster_mean(fp, mask_zeros=mask_zeros) for _, fp in files]
    vals = [v for v in vals if not np.isnan(v)]
    return float(np.mean(vals)) if vals else None


# deprecated alias kept for backward compatibility
_interval_mean_pet = _interval_mean_raster


def _interval_sum(
    start: datetime,
    end: datetime,
    rain_map: Dict[datetime, Path],
):
    """
    Sum raster values (e.g. rainfall) over (start, end].
    Returns (total: float, n_files: int) or None.
    """
    files = [fp for d, fp in sorted(rain_map.items()) if start < d <= end]
    if not files:
        past = [(d, fp) for d, fp in rain_map.items() if d <= end]
        if not past:
            return None
        files = [max(past, key=lambda x: x[0])[1]]
    total = float(sum(raster_mean(fp, mask_zeros=False) for fp in files))
    return total, len(files)


def _doy_sin_cos(doy_series):
    """Cyclic day-of-year encoding."""
    angle = 2.0 * np.pi * np.asarray(doy_series, dtype=float) / 365.0
    return np.sin(angle), np.cos(angle)


def _effective_rainfall(rain_sum: float, interval_days: int) -> float:
    """FAO-56 effective rainfall (Doorenbos & Pruitt, USDA-SCS)."""
    pe_threshold = 75.0 * (interval_days / 30.0)
    if rain_sum <= pe_threshold:
        return max(0.6 * rain_sum - 10.0, 0.0)
    return max(0.8 * rain_sum - 25.0, 0.0)


# ═══════════════════════════════════════════════════════════════════════════
# Validation metrics
# ═══════════════════════════════════════════════════════════════════════════

def compute_validation_metrics(observed, predicted) -> dict:
    """R², NSE, RMSE, MAE, MAPE on the overlap of non-NaN values."""
    obs  = np.asarray(observed,  dtype=float)
    pred = np.asarray(predicted, dtype=float)
    valid = ~(np.isnan(obs) | np.isnan(pred))
    obs, pred = obs[valid], pred[valid]

    if len(obs) < 2:
        return {k: np.nan for k in ("R2", "NSE", "RMSE", "MAE", "MAPE")}

    ss_res = np.sum((obs - pred) ** 2)
    ss_tot = np.sum((obs - np.mean(obs)) ** 2)
    r2   = 1.0 - ss_res / ss_tot if ss_tot > 0 else np.nan
    nse  = r2
    rmse = float(np.sqrt(mean_squared_error(obs, pred)))
    mae  = float(mean_absolute_error(obs, pred))
    nz   = np.abs(obs) > 1e-9
    mape = float(np.mean(np.abs((obs[nz] - pred[nz]) / obs[nz])) * 100) if nz.any() else np.nan

    return {
        "R2":   round(r2,   4),
        "NSE":  round(nse,  4),
        "RMSE": round(rmse, 4),
        "MAE":  round(mae,  4),
        "MAPE": round(mape, 2),
    }


# ═══════════════════════════════════════════════════════════════════════════
# Forecast exog builders — PUBLIC UTILITIES
# ═══════════════════════════════════════════════════════════════════════════

def build_forecast_exog(
    future_dates: pd.DatetimeIndex,
    last_pet: float,
    exog_cols: List[str],
    temp_val: Optional[float] = None,
    rad_val:  Optional[float] = None,
) -> pd.DataFrame:
    """
    Build the exogenous variable DataFrame for PET forecast horizon.

    Strategy per variable:
      sin_doy / cos_doy  — computed exactly from future calendar dates
      pet_lag1           — carry-forward of last observed PET (persistence)
      temp               — carry-forward of last observed temperature
      radiation          — carry-forward of last observed radiation

    Args:
        future_dates : DatetimeIndex of forecast dates
        last_pet     : last observed PET value (mm/day) for lag feature
        exog_cols    : list of column names expected by the trained model
        temp_val     : last observed temperature (°C), if in exog_cols
        rad_val      : last observed radiation (MJ/m²), if in exog_cols

    Returns:
        DataFrame with exactly the columns in exog_cols.
    """
    records = []
    for dt in future_dates:
        doy = dt.timetuple().tm_yday
        s, c = _doy_sin_cos([doy])
        rec: Dict = {
            "sin_doy":  float(s[0]),
            "cos_doy":  float(c[0]),
            "pet_lag1": float(last_pet),
        }
        if temp_val is not None:
            rec["temp"] = float(temp_val)
        if rad_val is not None:
            rec["radiation"] = float(rad_val)
        records.append(rec)

    df = pd.DataFrame(records, index=future_dates)

    for col in exog_cols:
        if col not in df.columns:
            logger.warning(
                f"build_forecast_exog: column '{col}' not built — filling with 0. "
                "Check exog_cols in the saved model meta."
            )
            df[col] = 0.0

    return df[exog_cols]


def build_savi_forecast_exog(
    future_dates: pd.DatetimeIndex,
    last_savi: float,
    exog_cols: List[str],
) -> pd.DataFrame:
    """
    Build the exogenous variable DataFrame for SAVI forecast horizon.

    DESIGN-v10-4: Symmetric counterpart to build_forecast_exog for PET.

    Strategy per variable:
      sin_doy / cos_doy  — computed exactly from future calendar dates
                           (captures the Rabi phenological curve well)
      savi_lag1          — carry-forward of last observed SAVI (strong
                           autocorrelation r > 0.90 at lag-1 within season)

    Args:
        future_dates : DatetimeIndex of forecast dates
        last_savi    : last observed SAVI value (dimensionless, ~0.05–0.60)
        exog_cols    : list of column names expected by the trained model

    Returns:
        DataFrame with exactly the columns in exog_cols.
    """
    records = []
    for dt in future_dates:
        doy = dt.timetuple().tm_yday
        s, c = _doy_sin_cos([doy])
        rec: Dict = {
            "sin_doy":   float(s[0]),
            "cos_doy":   float(c[0]),
            "savi_lag1": float(last_savi),
        }
        records.append(rec)

    df = pd.DataFrame(records, index=future_dates)

    for col in exog_cols:
        if col not in df.columns:
            logger.warning(
                f"build_savi_forecast_exog: column '{col}' not built — filling with 0. "
                "Check exog_cols in the saved SAVI model meta."
            )
            df[col] = 0.0

    return df[exog_cols]


# ═══════════════════════════════════════════════════════════════════════════
# Dataset loaders
# ═══════════════════════════════════════════════════════════════════════════

def load_wheat_savi_dataset() -> pd.DataFrame:
    """
    Load SAVI time series aligned to Sentinel-2 acquisition dates.

    DESIGN-v10-1: SAVI is now the root of the statistical forecast chain.
    SARIMAX on SAVI captures the phenological growth curve of Rabi wheat:
        Nov–Dec: ~0.05–0.15  (germination / sparse canopy)
        Jan:     ~0.25–0.35  (tillering)
        Feb–Mar: ~0.45–0.55  (heading / flowering peak)
        Apr:     ~0.20–0.30  (maturity / senescence)

    Adds savi_lag1 (one-step lagged SAVI) as an exogenous variable.
    SAVI is highly autocorrelated within a season (r > 0.90 at lag-1).
    """
    logger.info("Loading SAVI dataset...")
    savi_map = build_date_file_map(SAVI_DIR)

    sentinel_dates = sorted(d for d in savi_map if is_rabi(d))
    records = []

    for i, date in enumerate(sentinel_dates):
        savi_val = raster_mean(savi_map[date], mask_zeros=True)
        if np.isnan(savi_val):
            continue

        doy = date.timetuple().tm_yday
        s, c = _doy_sin_cos([doy])
        rec = {
            "date":     date,
            "savi":     savi_val,
            "sin_doy":  s[0],
            "cos_doy":  c[0],
        }

        # DESIGN-v10-4: lagged SAVI — persistence carries strong phenological signal
        if records:
            rec["savi_lag1"] = records[-1]["savi"]
        else:
            rec["savi_lag1"] = savi_val  # first row: self-lag

        records.append(rec)

    if not records:
        raise RuntimeError("No SAVI data found — check SAVI_DIR")

    df = pd.DataFrame(records).sort_values("date").set_index("date")
    logger.info(f"SAVI dataset: {len(df)} records, columns: {list(df.columns)}")
    return df


def load_wheat_kc_dataset() -> pd.DataFrame:
    """
    Load (SAVI, Kc) pairs for Rabi dates.
    Kc is the target; SAVI is the predictor.
    """
    logger.info("Loading Kc dataset...")
    kc_map   = build_date_file_map(KC_DIR)
    savi_map = build_date_file_map(SAVI_DIR)

    records = []
    for date, kc_fp in sorted(kc_map.items()):
        if not is_rabi(date) or date not in savi_map:
            continue
        kc_val   = raster_mean(kc_fp,          mask_zeros=True)
        savi_val = raster_mean(savi_map[date],  mask_zeros=True)
        if np.isnan(kc_val) or np.isnan(savi_val):
            continue
        doy = date.timetuple().tm_yday
        s, c = _doy_sin_cos([doy])
        records.append({"date": date, "kc": kc_val, "savi": savi_val,
                         "sin_doy": s[0], "cos_doy": c[0]})

    if not records:
        raise RuntimeError("No Kc/SAVI data found — check KC_DIR and SAVI_DIR")
    df = pd.DataFrame(records).sort_values("date").set_index("date")
    logger.info(f"Kc dataset: {len(df)} records")
    return df


def load_wheat_pet_dataset() -> pd.DataFrame:
    """
    Load PET dataset aligned to Sentinel-2 acquisition dates.

    Adds pet_lag1 (one-step lagged PET) as an exogenous variable.
    PET is highly autocorrelated within the Rabi season (r > 0.85 at lag-1).
    Optional temperature and solar radiation rasters are included when
    their directories are configured (INSAT_TEMP / INSAT_RAD).
    """
    logger.info("Loading PET dataset...")
    pet_map  = build_date_file_map(PET_DIR)
    kc_map   = build_date_file_map(KC_DIR)
    temp_map = build_date_file_map(TEMP_DIR)
    rad_map  = build_date_file_map(RAD_DIR)

    sentinel_dates = sorted(d for d in kc_map if is_rabi(d))
    records = []

    for i, date in enumerate(sentinel_dates):
        prev_date = sentinel_dates[i - 1] if i > 0 else date - timedelta(days=5)
        pet_val = _interval_mean_raster(prev_date, date, pet_map, mask_zeros=True)
        if pet_val is None:
            continue

        doy = date.timetuple().tm_yday
        s, c = _doy_sin_cos([doy])
        rec = {"date": date, "pet": pet_val, "sin_doy": s[0], "cos_doy": c[0]}

        if records:
            rec["pet_lag1"] = records[-1]["pet"]
        else:
            rec["pet_lag1"] = pet_val

        if temp_map:
            t = _interval_mean_raster(prev_date, date, temp_map, mask_zeros=False)
            rec["temp"] = t if t is not None else np.nan

        if rad_map:
            r = _interval_mean_raster(prev_date, date, rad_map, mask_zeros=False)
            rec["radiation"] = r if r is not None else np.nan

        records.append(rec)

    if not records:
        raise RuntimeError("No PET data found — check PET_DIR")

    df = pd.DataFrame(records).sort_values("date").set_index("date")

    for col in ("temp", "radiation"):
        if col in df.columns:
            n_miss = df[col].isna().sum()
            if n_miss > 0:
                logger.warning(
                    f"PET dataset: {n_miss} missing '{col}' values — interpolating"
                )
                df[col] = df[col].interpolate(method="time").bfill().ffill()

    logger.info(f"PET dataset: {len(df)} records, columns: {list(df.columns)}")
    return df


def load_wheat_cwr_dataset() -> pd.DataFrame:
    """
    Load CWR + PET + Kc dataset for validation purposes only.
    CWR is no longer modelled with SARIMAX; used only for physics validation.
    """
    logger.info("Loading CWR dataset (for validation)...")
    pet_map  = build_date_file_map(PET_DIR)
    kc_map   = build_date_file_map(KC_DIR)
    savi_map = build_date_file_map(SAVI_DIR)

    cwr_files = []
    for fp in sorted(CWR_DIR.glob("cwr_*.tif")):
        try:
            d = extract_date(fp.name)
            if is_rabi(d):
                cwr_files.append((d, fp))
        except Exception:
            pass

    records = []
    for i, (date, cwr_fp) in enumerate(cwr_files):
        prev_date = cwr_files[i - 1][0] if i > 0 else date - timedelta(days=5)
        pet_val = _interval_mean_raster(prev_date, date, pet_map, mask_zeros=True)
        if pet_val is None or date not in kc_map or date not in savi_map:
            continue
        cwr_val  = raster_mean(cwr_fp,           mask_zeros=True)
        kc_val   = raster_mean(kc_map[date],      mask_zeros=True)
        savi_val = raster_mean(savi_map[date],     mask_zeros=True)
        if any(np.isnan(v) for v in [cwr_val, kc_val, savi_val]):
            continue
        doy = date.timetuple().tm_yday
        s, c = _doy_sin_cos([doy])
        records.append({
            "date": date, "cwr": cwr_val, "pet": pet_val,
            "kc": kc_val, "savi": savi_val,
            "sin_doy": s[0], "cos_doy": c[0],
        })

    if not records:
        raise RuntimeError("No CWR data found — check CWR_DIR, PET_DIR, KC_DIR, SAVI_DIR")
    df = pd.DataFrame(records).sort_values("date").set_index("date")
    logger.info(f"CWR dataset: {len(df)} records")
    return df


def load_wheat_iwr_dataset() -> pd.DataFrame:
    """Load IWR + CWR + rainfall dataset for physics validation."""
    logger.info("Loading IWR dataset...")
    rain_map = build_date_file_map(RAIN_DIR)
    kc_map   = build_date_file_map(KC_DIR)
    savi_map = build_date_file_map(SAVI_DIR)

    cwr_map: Dict[datetime, Path] = {}
    for fp in CWR_DIR.glob("cwr_*.tif"):
        try:
            cwr_map[extract_date(fp.name)] = fp
        except Exception:
            pass

    iwr_files = sorted(IWR_DIR.glob("iwr_*.tif"))
    if not iwr_files:
        raise RuntimeError(f"No IWR files found in {IWR_DIR}")

    records = []
    for i, iwr_fp in enumerate(iwr_files):
        date = extract_date(iwr_fp.name)
        if not is_rabi(date):
            continue
        prev_date = (extract_date(iwr_files[i - 1].name) if i > 0
                     else date - timedelta(days=5))

        rain_result = _interval_sum(prev_date, date, rain_map)
        if rain_result is None:
            continue
        rain_sum, _ = rain_result

        if np.isnan(rain_sum):
            logger.debug(f"[iwr_dataset] rain_sum=nan for {date.date()} — skipping")
            continue

        if date not in kc_map or date not in savi_map:
            continue

        kc_val   = raster_mean(kc_map[date],  mask_zeros=True)
        savi_val = raster_mean(savi_map[date], mask_zeros=True)
        iwr_val  = raster_mean(iwr_fp,         mask_zeros=True)
        cwr_val  = raster_mean(cwr_map[date],  mask_zeros=True) if date in cwr_map else np.nan

        if any(np.isnan(v) for v in [kc_val, savi_val, iwr_val]):
            continue

        interval_days = max((date - prev_date).days, 1)
        eff_rain      = _effective_rainfall(rain_sum, interval_days)
        doy           = date.timetuple().tm_yday
        s, c          = _doy_sin_cos([doy])

        records.append({
            "date":     date,
            "iwr":      iwr_val,
            "cwr":      cwr_val,
            "rain":     rain_sum,
            "eff_rain": eff_rain,
            "kc":       kc_val,
            "savi":     savi_val,
            "sin_doy":  s[0],
            "cos_doy":  c[0],
        })

    if not records:
        raise RuntimeError("No IWR data found — check IWR_DIR, RAIN_DIR, KC_DIR")
    df = pd.DataFrame(records).sort_values("date").set_index("date")
    logger.info(f"IWR dataset: {len(df)} records")
    return df


# ═══════════════════════════════════════════════════════════════════════════
# SARIMAX training  (used for SAVI and PET)
# ═══════════════════════════════════════════════════════════════════════════

def _climatological_regression(y_train, y_test, exog_train, exog_test):
    """Ridge regression on sin/cos DOY — used as a SARIMAX fallback."""
    if exog_train is None or "sin_doy" not in exog_train.columns:
        return np.full(len(y_test), y_train.mean()), None
    X_tr = exog_train[["sin_doy", "cos_doy"]].values
    X_te = exog_test[["sin_doy",  "cos_doy"]].values
    reg  = Ridge(alpha=1.0).fit(X_tr, y_train.values)
    return reg.predict(X_te), reg


def train_sarimax_model(
    y: pd.Series,
    exog: pd.DataFrame,
    target_name: str,
    seasonal_period: int = 26,
):
    """
    Train SARIMAX with AIC-guided grid search.

    d=0 is searched alongside d=1 (SAVI and PET within a Rabi season are
    typically stationary; over-differencing collapses forecasts to the mean).

    Raises TypeError if y is not a pd.Series.
    """
    logger.info(f"\n{'='*65}")
    logger.info(f"Training SARIMAX for {target_name.upper()}")
    logger.info(f"{'='*65}")

    if not isinstance(y, pd.Series):
        raise TypeError(
            f"'y' must be a pd.Series, got {type(y).__name__}. "
            f"Pass df['{target_name}'] explicitly."
        )

    common_idx = y.index.intersection(exog.index)
    if len(common_idx) == 0:
        raise ValueError(
            "No common dates between y and exog — check dataset loaders."
        )
    y    = y.loc[common_idx]
    exog = exog.loc[common_idx]

    valid_rows = ~exog.isnull().any(axis=1)
    y    = y[valid_rows]
    exog = exog[valid_rows]

    logger.info(f"Total samples after cleaning: {len(y)}")
    logger.info(f"Exogenous variables: {list(exog.columns)}")

    split_idx = int(len(y) * 0.8)
    if split_idx < 20:
        raise ValueError(
            f"Too few samples ({len(y)}) — need ≥ 25 total so that the "
            "80 % training split contains ≥ 20 samples."
        )

    y_train, y_test       = y.iloc[:split_idx],    y.iloc[split_idx:]
    exog_train, exog_test = exog.iloc[:split_idx], exog.iloc[split_idx:]

    logger.info(
        f"Train: {len(y_train)} ({y_train.index[0].date()} → {y_train.index[-1].date()})"
    )
    logger.info(
        f"Test:  {len(y_test)}  ({y_test.index[0].date()}  → {y_test.index[-1].date()})"
    )

    # ── Grid search — d=0 included (stationarity within season) ──────────
    best_aic = np.inf
    best_result = best_order = best_seasonal = None

    for p in [0, 1, 2]:
        for d in [0, 1]:
            for q in [0, 1]:
                for P in [0, 1]:
                    for D in [0, 1]:
                        for Q in [0, 1]:
                            try:
                                res = SARIMAX(
                                    y_train, exog=exog_train,
                                    order=(p, d, q),
                                    seasonal_order=(P, D, Q, seasonal_period),
                                    trend="c",
                                    enforce_stationarity=False,
                                    enforce_invertibility=False,
                                ).fit(disp=False, method="lbfgs", maxiter=500)
                                if res.aic < best_aic:
                                    best_aic      = res.aic
                                    best_result   = res
                                    best_order    = (p, d, q)
                                    best_seasonal = (P, D, Q, seasonal_period)
                            except Exception:
                                continue

    # ── Evaluate on test set ─────────────────────────────────────────────
    metrics = None
    if best_result is not None:
        try:
            fc      = best_result.forecast(steps=len(y_test), exog=exog_test)
            metrics = compute_validation_metrics(y_test.values, fc.values)
            logger.info(
                f"Best SARIMAX {best_order} × {best_seasonal}: "
                f"R²={metrics['R2']:.4f}, RMSE={metrics['RMSE']:.4f}"
            )
        except Exception as e:
            logger.warning(f"SARIMAX test forecast failed: {e}")
            best_result = None

    # ── Climatological fallback ───────────────────────────────────────────
    clim_pred, clim_reg = _climatological_regression(
        y_train, y_test, exog_train, exog_test
    )
    clim_m = compute_validation_metrics(y_test.values, clim_pred)
    logger.info(
        f"Climatological baseline: R²={clim_m['R2']:.4f}, "
        f"RMSE={clim_m['RMSE']:.4f}"
    )

    r2_best: float
    if metrics is None or metrics.get("R2") is None or np.isnan(metrics["R2"]):
        r2_best = -np.inf
    else:
        r2_best = float(metrics["R2"])

    use_clim = (not np.isnan(clim_m["R2"])) and (clim_m["R2"] > r2_best)

    if use_clim and clim_reg is not None:
        logger.info("Climatological regression outperforms SARIMAX — using it")
        X_full   = exog[["sin_doy", "cos_doy"]].values
        full_reg = Ridge(alpha=1.0).fit(X_full, y.values)
        return (
            _ClimModel(full_reg, ["sin_doy", "cos_doy"]),
            clim_m,
            (0, 0, 0),
        )

    if best_result is None:
        logger.warning("All SARIMAX fits failed — falling back to seasonal naive")
        return _NaiveModel(float(y_train.mean())), clim_m, (0, 0, 0)

    # ── Retrain winner on full data ───────────────────────────────────────
    try:
        final_model = SARIMAX(
            y, exog=exog,
            order=best_order,
            seasonal_order=best_seasonal,
            trend="c",
        ).fit(disp=False, method="lbfgs", maxiter=500)
    except Exception:
        final_model = best_result

    return final_model, metrics, best_order


# ═══════════════════════════════════════════════════════════════════════════
# SAVI: SARIMAX — NEW in v10.0
# DESIGN-v10-1: SAVI forecast is the root of the Kc forecast chain.
# ═══════════════════════════════════════════════════════════════════════════

def train_savi_model():
    """
    SARIMAX for SAVI (NEW in v10.0 — the root of the Kc forecast chain).

    DESIGN-v10-1: Previously Kc was projected using a static DOY nudge
    (_project_kc_for_dates).  By forecasting SAVI directly and computing
    Kc = 1.2088×SAVI + 0.5375, we get a physically grounded, seasonally
    aware Kc trajectory for the forecast window.

    Exog:
      1. sin_doy, cos_doy  — always included (phenological seasonal cycle)
      2. savi_lag1         — always included (strong persistence r > 0.90)

    seasonal_period=26: correct because the SAVI dataset is aligned to
    Sentinel acquisition dates (~5-day cadence × ~26 scenes per Rabi season).
    """
    df = load_wheat_savi_dataset()

    exog_cols = ["sin_doy", "cos_doy", "savi_lag1"]
    model, metrics, order = train_sarimax_model(
        df["savi"], df[exog_cols], "savi", seasonal_period=26
    )

    meta = {
        "model":       model,
        "metrics":     metrics,
        "exog_cols":   exog_cols,
        "order":       order,
        "last_date":   df.index[-1],
        "last_savi":   float(df["savi"].iloc[-1]),  # needed for lag at forecast time
        "target_name": "savi",
        "note":        f"SARIMAX SAVI exog={exog_cols} (v10.0)",
    }

    with open(SAVI_MODEL_PATH, "wb") as f:
        pickle.dump(meta, f)

    logger.info(
        f"✓ SAVI model saved  "
        f"(Test R²={metrics['R2']:.4f}, RMSE={metrics['RMSE']:.4f})"
    )
    return model, metrics


# ═══════════════════════════════════════════════════════════════════════════
# Kc: SAVI→Kc polynomial regression (retained for physics validation)
# ═══════════════════════════════════════════════════════════════════════════

def train_kc_model():
    """
    Fit a polynomial regression  Kc = f(SAVI)  (degree 1 or 2).
    Used for validating the thesis equation Kc = 1.2088×SAVI + 0.5375.
    At forecast time Kc is computed analytically from SAVI_forecast, not
    loaded from this model.
    """
    df = load_wheat_kc_dataset()

    X = df[["savi"]].values
    y = df["kc"].values

    split_idx = int(len(df) * 0.8)
    if split_idx < 10:
        raise ValueError(f"Too few Kc/SAVI pairs: {len(df)} — need ≥ 13")

    X_train, X_test = X[:split_idx], X[split_idx:]
    y_train, y_test = y[:split_idx], y[split_idx:]

    best_pipe, best_metrics, best_degree = None, None, None

    for degree in [1, 2]:
        pipe = Pipeline([
            ("poly",  PolynomialFeatures(degree=degree, include_bias=True)),
            ("ridge", Ridge(alpha=0.5)),
        ])
        pipe.fit(X_train, y_train)
        pred    = np.clip(pipe.predict(X_test), KC_MIN, KC_MAX)
        metrics = compute_validation_metrics(y_test, pred)
        logger.info(
            f"Kc poly degree={degree}: R²={metrics['R2']:.4f}, "
            f"RMSE={metrics['RMSE']:.4f}, MAE={metrics['MAE']:.4f}"
        )
        if best_metrics is None or metrics["R2"] > best_metrics["R2"]:
            best_pipe, best_metrics, best_degree = pipe, metrics, degree

    thesis_pred = np.clip(
        KC_SLOPE * X_test[:, 0] + KC_INTERCEPT, KC_MIN, KC_MAX
    )
    thesis_m = compute_validation_metrics(y_test, thesis_pred)
    logger.info(
        f"Kc thesis constants (linear): R²={thesis_m['R2']:.4f}, "
        f"RMSE={thesis_m['RMSE']:.4f}"
    )

    r2_poly = best_metrics["R2"] if best_metrics else -np.inf

    if thesis_m["R2"] > r2_poly:
        logger.info(
            "Thesis constants outperform polynomial fit — "
            "building degree-1 pipeline with enforced coefficients"
        )
        thesis_pipe = Pipeline([
            ("poly",  PolynomialFeatures(degree=1, include_bias=True)),
            ("ridge", Ridge(alpha=0.0, fit_intercept=False)),
        ])
        thesis_pipe.fit(X, y)
        thesis_pipe.named_steps["ridge"].coef_ = np.array(
            [KC_INTERCEPT, KC_SLOPE]
        )
        kc_model     = _KcPolyModel(thesis_pipe)
        best_metrics = thesis_m
        best_degree  = 1
    else:
        best_pipe.fit(X, y)
        kc_model = _KcPolyModel(best_pipe)

    meta = {
        "model":       kc_model,
        "metrics":     best_metrics,
        "degree":      best_degree,
        "last_date":   df.index[-1],
        "target_name": "kc",
        "note":        f"SAVI→Kc poly degree={best_degree} (v10.0)",
    }

    with open(KC_MODEL_PATH, "wb") as f:
        pickle.dump(meta, f)

    logger.info(
        f"✓ Kc model saved  "
        f"(Test R²={best_metrics['R2']:.4f}, RMSE={best_metrics['RMSE']:.4f})"
    )
    return kc_model, best_metrics


# ═══════════════════════════════════════════════════════════════════════════
# PET: SARIMAX  — statistically forecasted alongside SAVI
# ═══════════════════════════════════════════════════════════════════════════

def train_pet_model():
    """
    SARIMAX for PET.

    Exog priority:
      1. sin_doy, cos_doy  — always included (seasonal cycle)
      2. pet_lag1          — always included (persistence)
      3. temp, radiation   — included if raster directories are configured

    seasonal_period=26: PET dataset is aligned to Sentinel acquisition
    dates (~5-day cadence), giving 26 observations per ~4-month Rabi season.
    """
    df = load_wheat_pet_dataset()

    base_exog  = ["sin_doy", "cos_doy", "pet_lag1"]
    extra_exog = [
        c for c in ("temp", "radiation")
        if c in df.columns and not df[c].isna().all()
    ]
    if not extra_exog:
        logger.warning(
            "PET model: temperature/radiation rasters not found. "
            "Using DOY + lag exog — configure insat_temp/insat_rad to improve R²."
        )
    else:
        logger.info(f"PET model: using extra exog: {extra_exog}")

    exog_cols = base_exog + extra_exog
    model, metrics, order = train_sarimax_model(
        df["pet"], df[exog_cols], "pet", seasonal_period=26
    )

    meta = {
        "model":       model,
        "metrics":     metrics,
        "exog_cols":   exog_cols,
        "order":       order,
        "last_date":   df.index[-1],
        "last_pet":    float(df["pet"].iloc[-1]),
        "target_name": "pet",
        "note":        f"SARIMAX PET exog={exog_cols} (v10.0)",
    }

    with open(PET_MODEL_PATH, "wb") as f:
        pickle.dump(meta, f)

    logger.info(
        f"✓ PET model saved  "
        f"(Test R²={metrics['R2']:.4f}, RMSE={metrics['RMSE']:.4f})"
    )
    return model, metrics


# ═══════════════════════════════════════════════════════════════════════════
# CWR: Physics wrapper  CWR = Kc × PET
# ═══════════════════════════════════════════════════════════════════════════

def train_cwr_model():
    """
    Validate CWR physics relationship and save _PhysicsCWR wrapper.

        CWR = Kc × PET   (FAO-56, thesis Eq. 4)
    """
    df = load_wheat_cwr_dataset()

    cwr_physics = np.clip(df["kc"].values * df["pet"].values, 0.0, CWR_MAX)
    valid_mask  = ~np.isnan(df["cwr"].values)
    metrics     = compute_validation_metrics(
        df["cwr"].values[valid_mask], cwr_physics[valid_mask]
    )

    logger.info("Physics CWR = Kc × PET:")
    logger.info(f"  R²  : {metrics['R2']:.4f}")
    logger.info(f"  RMSE: {metrics['RMSE']:.4f} mm/day")
    logger.info(f"  MAE : {metrics['MAE']:.4f} mm/day")

    physics_model = _PhysicsCWR()

    meta = {
        "model":       physics_model,
        "metrics":     metrics,
        "last_date":   df.index[-1],
        "target_name": "cwr",
        "note":        "Physics: CWR = Kc × PET (v10.0)",
        "exog_cols":   [],
    }

    with open(MODEL_PATH, "wb") as f:
        pickle.dump(meta, f)

    logger.info(
        f"✓ CWR model saved  "
        f"(Test R²={metrics['R2']:.4f}, RMSE={metrics['RMSE']:.4f} mm/day)"
    )
    return physics_model, metrics


# ═══════════════════════════════════════════════════════════════════════════
# IWR: physics-based  IWR = max(CWR − Peff, 0)
# ═══════════════════════════════════════════════════════════════════════════

def train_iwr_model():
    """
    IWR is computed deterministically from CWR and effective rainfall.

        IWR = max(CWR − Peff, 0)   [FAO-56, thesis §4.5]
    """
    df = load_wheat_iwr_dataset()

    iwr_physics = np.maximum(df["cwr"].values - df["eff_rain"].values, 0.0)
    valid_mask  = ~np.isnan(df["cwr"].values)
    metrics     = compute_validation_metrics(
        df["iwr"].values[valid_mask], iwr_physics[valid_mask]
    )

    logger.info("Physics IWR = max(CWR − Peff, 0):")
    logger.info(f"  R²  : {metrics['R2']:.4f}")
    logger.info(f"  RMSE: {metrics['RMSE']:.4f} mm/day")
    logger.info(f"  MAE : {metrics['MAE']:.4f} mm/day")

    physics_model = _PhysicsIWR()

    meta = {
        "model":       physics_model,
        "metrics":     metrics,
        "last_date":   df.index[-1],
        "target_name": "iwr",
        "note":        "Physics: IWR = max(CWR − Peff, 0) (v10.0)",
        "mean_cwr":    float(np.nanmean(df["cwr"].values)),
        "mean_peff":   float(np.nanmean(df["eff_rain"].values)),
    }

    with open(IWR_MODEL_PATH, "wb") as f:
        pickle.dump(meta, f)

    logger.info(
        f"✓ IWR model saved  "
        f"(Test R²={metrics['R2']:.4f}, RMSE={metrics['RMSE']:.4f} mm/day)"
    )
    return physics_model, metrics


# ═══════════════════════════════════════════════════════════════════════════
# Train all
# ═══════════════════════════════════════════════════════════════════════════

def train_all_models() -> dict:
    """
    Train all models in dependency order:
      1. SAVI (SARIMAX — root of Kc forecast chain)
      2. Kc   (polynomial SAVI→Kc — validation only)
      3. PET  (SARIMAX — independent met variable)
      4. CWR  (physics wrapper — validation only)
      5. IWR  (physics wrapper — validation only)

    Forecast chain: SAVI(SARIMAX)→Kc=f(SAVI) + PET(SARIMAX)→CWR=Kc×PET→IWR=max(CWR-Peff,0)
    """
    logger.info("=" * 80)
    logger.info("Training All Models — v10.0")
    logger.info("Chain: SAVI(SARIMAX)→Kc + PET(SARIMAX) → CWR=Kc×PET → IWR=max(CWR-Peff,0)")
    logger.info("=" * 80)

    results = {}
    for name, fn in [
        ("savi", train_savi_model),   # NEW in v10.0
        ("kc",   train_kc_model),
        ("pet",  train_pet_model),
        ("cwr",  train_cwr_model),
        ("iwr",  train_iwr_model),
    ]:
        try:
            model, metrics = fn()
            results[name]  = {"model": model, "metrics": metrics}
        except Exception as e:
            logger.error(f"{name.upper()} model failed: {e}")
            import traceback
            traceback.print_exc()
            results[name] = None

    logger.info("\n" + "=" * 80)
    logger.info("Training Summary")
    logger.info("=" * 80)
    for name, result in results.items():
        if result:
            m = result["metrics"]
            logger.info(f"\n{name.upper()}:")
            for k in ("R2", "NSE", "RMSE", "MAE", "MAPE"):
                v = m.get(k)
                if v is not None and not (isinstance(v, float) and np.isnan(v)):
                    logger.info(f"  {k:6s}: {v}")

    return results


# ═══════════════════════════════════════════════════════════════════════════
# Model loading
# ═══════════════════════════════════════════════════════════════════════════

def load_model(model_type: str):
    """
    Load a trained model pickle.
    Returns (model, meta) — same interface for all model types.
    """
    path_map = {
        "savi": SAVI_MODEL_PATH,   # NEW v10.0
        "kc":   KC_MODEL_PATH,
        "pet":  PET_MODEL_PATH,
        "cwr":  MODEL_PATH,
        "iwr":  IWR_MODEL_PATH,
    }
    path = path_map.get(model_type)
    if not path or not path.exists():
        raise FileNotFoundError(f"Model not found: {path}")
    with open(path, "rb") as f:
        meta = pickle.load(f)
    logger.info(
        f"Loaded {model_type.upper()} model — {meta.get('note', '')} "
        f"(Test R²={meta['metrics']['R2']:.4f})"
    )
    return meta["model"], meta


# ═══════════════════════════════════════════════════════════════════════════
# Quick smoke-test
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    results = train_all_models()

    # Test SAVI → Kc chain
    if results.get("savi") and results["savi"] is not None:
        print("\nSAVI SARIMAX model trained successfully.")
        print(f"  R² = {results['savi']['metrics']['R2']:.4f}")

    # Test Kc from SAVI analytical equation
    test_savi = np.array([0.1, 0.2, 0.35, 0.45, 0.55])
    kc_from_savi = np.clip(KC_SLOPE * test_savi + KC_INTERCEPT, KC_MIN, KC_MAX)
    print("\nKc from SAVI (thesis eq: 1.2088×SAVI + 0.5375, clip [0.30, 1.15]):")
    for s, k in zip(test_savi, kc_from_savi):
        print(f"  SAVI={s:.2f}  →  Kc={k:.4f}")

    if results.get("iwr"):
        iwr_model = results["iwr"]["model"]
        cwr_vals  = np.array([3.0, 5.0, 7.0])
        peff_vals = np.array([1.5, 4.0, 8.0])
        iwr_pred  = iwr_model.predict(cwr_vals, peff_vals)
        print("\nIWR predictions (CWR − Peff):")
        for cwr, peff, iwr in zip(cwr_vals, peff_vals, iwr_pred):
            print(f"  CWR={cwr:.1f}, Peff={peff:.1f}  →  IWR={iwr:.2f}")