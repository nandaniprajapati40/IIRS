
# """
# main.py  — v9.0
# ─────────────────────────────────────────────────────────────────────────────
# FORECAST DESIGN (corrected from v7.0):

#   OLD (broken):
#     • CWR forecasted directly with SARIMAX (using PET, Kc, SAVI as exog)
#     • IWR forecasted directly with SARIMAX (using eff_rain, Kc, SAVI as exog)
#     • Root cause of IWR=0: eff_rain exog was always near-zero in Rabi season,
#       so the model learned IWR ≈ 0.

#   NEW (corrected):
#     Step 1 — Forecast PET with SARIMAX (only statistically forecasted variable)
#     Step 2 — Project Kc from DOY-based SAVI expectation: Kc = 1.2088×SAVI + 0.5375
#     Step 3 — Compute CWR = Kc_projected × PET_forecast  (physics, FAO-56 Eq. 4)
#     Step 4 — Compute IWR = max(CWR − Peff_clim, 0)     (physics, FAO-56 §4.5)
#              where Peff_clim = climatological effective rainfall for the DOY
#              (from historical rasters, or 0 for Rabi dry season)

#   Physical chain maintained: SAVI → Kc → CWR → IWR
#   No IWR direct forecasting.  No circular exog.
# ─────────────────────────────────────────────────────────────────────────────
# """

# import asyncio
# import logging
# import re
# from datetime import datetime, timedelta
# from pathlib import Path
# from typing import Dict, List, Optional, Tuple

# import numpy as np
# import pandas as pd
# import rasterio
# import rasterio.warp
# import uvicorn
# from fastapi import FastAPI, HTTPException, Query
# from fastapi.middleware.cors import CORSMiddleware
# from rasterio.enums import Resampling
# from rasterio.warp import transform as warp_transform

# from config import (
#     STUDY_AREA, DIRECTORIES, GEOSERVER, SARIMAX_CONFIG,
#     WHEAT_PARAMS
# )
# from logging_config import setup_logging
# import models
# from models import build_forecast_exog   # DESIGN-FIX-7: shared exog builder

# setup_logging()
# logger = logging.getLogger(__name__)

# # Physical constants from thesis
# KC_SLOPE     = WHEAT_PARAMS["savi_kc"]["slope"]          # 1.2088
# KC_INTERCEPT = WHEAT_PARAMS["savi_kc"]["intercept"]       # 0.5375
# KC_MIN       = 0.30
# KC_MAX       = 1.15
# CWR_MIN      = 0.0
# CWR_MAX      = 15.0


# # ═══════════════════════════════════════════════════════════════════════════
# # CONSTANTS
# # ═══════════════════════════════════════════════════════════════════════════

# HISTORY_DATES  = 12
# FORECAST_DAYS  = 15
# NODATA         = -9999.0
# PARAMS         = ["savi", "kc", "cwr", "iwr"]
# SLOTS: List[str] = ["today"] + [str(i) for i in range(1, HISTORY_DATES)]
# FORECAST_WINDOWS = ["5day", "10day", "15day"]
# WINDOW_DAYS      = {"5day": 5, "10day": 10, "15day": 15}

# _VALID: Dict[str, Tuple[float, float]] = {
#     "savi": (-1.0, 1.0),
#     "kc":   (KC_MIN, KC_MAX),
#     "cwr":  (CWR_MIN, CWR_MAX),
#     "iwr":  (0.0, CWR_MAX),
# }

# _SRC: Dict[str, Tuple[Path, str]] = {
#     "savi": (DIRECTORIES["processed"]["savi"], "savi_*.tif"),
#     "kc":   (DIRECTORIES["processed"]["kc"],   "kc_*.tif"),
#     "cwr":  (DIRECTORIES["processed"]["cwr"],  "cwr_*.tif"),
#     "iwr":  (DIRECTORIES["processed"]["iwr"],  "iwr_*.tif"),
# }

# EXPORT_DIR   = DIRECTORIES["export"]["geoserver"]
# HISTORY_DIR  = EXPORT_DIR / "history"
# FORECAST_DIR = EXPORT_DIR / "forecast"

# for _param in PARAMS:
#     (HISTORY_DIR / _param).mkdir(parents=True, exist_ok=True)
#     (FORECAST_DIR / _param).mkdir(parents=True, exist_ok=True)


# # ═══════════════════════════════════════════════════════════════════════════
# # GLOBAL MODEL CACHE
# # ═══════════════════════════════════════════════════════════════════════════

# _MODEL_CACHE: Dict = {}

# # Forecast dataset cache — scheduler.py sets counts to -1 to force reload
# _fc_cache: Dict = {"pet_count": -1}


# def _get_model(model_type: str):
#     """Load and cache trained models."""
#     global _MODEL_CACHE

#     if model_type in _MODEL_CACHE:
#         return _MODEL_CACHE[model_type]

#     try:
#         model, meta = models.load_model(model_type)
#         _MODEL_CACHE[model_type] = (model, meta)
#         logger.info(
#             f"✓ Loaded {model_type.upper()} model "
#             f"(Test R²={meta['metrics']['R2']:.4f})"
#         )
#         return model, meta
#     except FileNotFoundError:
#         logger.warning(f"Model {model_type} not found — training all models...")
#         models.train_all_models()
#         model, meta = models.load_model(model_type)
#         _MODEL_CACHE[model_type] = (model, meta)
#         return model, meta
#     except Exception as e:
#         logger.error(f"Failed to load {model_type} model: {e}")
#         return None, None


# # ═══════════════════════════════════════════════════════════════════════════
# # PATH HELPERS
# # ═══════════════════════════════════════════════════════════════════════════

# def history_path(param: str, slot: str) -> Path:
#     return HISTORY_DIR / param / f"{param}_{slot}.tif"


# def forecast_path(param: str, slot: str, window: str) -> Path:
#     return FORECAST_DIR / param / f"{param}_{slot}_{window}.tif"


# def slot_for_index(idx: int) -> str:
#     return "today" if idx == 0 else str(idx)


# # ═══════════════════════════════════════════════════════════════════════════
# # DATA LOADING HELPERS
# # ═══════════════════════════════════════════════════════════════════════════

# def _parse_date(name: str) -> Optional[datetime]:
#     m = re.search(r"\d{8}", name)
#     if m:
#         try:
#             return datetime.strptime(m.group(), "%Y%m%d")
#         except ValueError:
#             pass
#     return None


# def _dated_files(directory: Path, pattern: str) -> List[Tuple[datetime, Path]]:
#     out = []
#     for p in directory.glob(pattern):
#         d = _parse_date(p.name)
#         if d:
#             out.append((d, p))
#     out.sort(key=lambda x: x[0])
#     return out


# def _latest_n_complete_dates(n: int = HISTORY_DATES) -> List[datetime]:
#     """N most-recent dates where ALL parameters have processed rasters. Newest-first."""
#     date_sets = []
#     for param, (src_dir, pattern) in _SRC.items():
#         dates = {d for d, _ in _dated_files(src_dir, pattern)}
#         if not dates:
#             logger.warning(f"No {param} files in {src_dir}")
#             return []
#         date_sets.append(dates)

#     complete = set.intersection(*date_sets)
#     return sorted(complete, reverse=True)[:n]


# def _read_mean(path: Path) -> Optional[float]:
#     """Spatial mean of valid (non-NODATA) pixels from a raster file."""
#     if not path.exists():
#         return None
#     try:
#         with rasterio.open(path) as src:
#             data = src.read(1).astype(np.float64)
#             nd   = float(src.nodata) if src.nodata else float(NODATA)
#             data[data == np.float64(nd)] = np.nan
#             v = float(np.nanmean(data))
#             return None if np.isnan(v) else round(v, 4)
#     except Exception:
#         return None


# def _load_slot_array(param: str, slot: str) -> Optional[np.ndarray]:
#     """Load a history slot raster array (NaN for NODATA pixels)."""
#     p = history_path(param, slot)
#     if not p.exists():
#         return None
#     try:
#         with rasterio.open(p) as src:
#             data = src.read(1).astype(np.float64)
#             nd   = float(src.nodata) if src.nodata is not None else float(NODATA)
#             data[data == np.float64(nd)]       = np.nan
#             data[data == np.float64(NODATA)]   = np.nan
#         return data
#     except Exception as e:
#         logger.error(f"[load] {p.name}: {e}")
#         return None


# # ═══════════════════════════════════════════════════════════════════════════
# # WHEAT MASK
# # ═══════════════════════════════════════════════════════════════════════════

# _WHEAT_MASK_CACHE: Optional[Dict] = None


# def _get_wheat_mask() -> Optional[Dict]:
#     global _WHEAT_MASK_CACHE
#     if _WHEAT_MASK_CACHE is not None:
#         return _WHEAT_MASK_CACHE

#     mask_path = DIRECTORIES["processed"]["masks"] / "wheat_mask.tif"
#     if not mask_path.exists():
#         logger.error(f"wheat_mask.tif not found: {mask_path}")
#         return None

#     try:
#         with rasterio.open(mask_path) as src:
#             raw = src.read(1)
#             _WHEAT_MASK_CACHE = {
#                 "crs":       src.crs,
#                 "transform": src.transform,
#                 "width":     src.width,
#                 "height":    src.height,
#                 "mask_bool": (raw > 0),
#             }
#         logger.info(
#             f"Wheat mask: {_WHEAT_MASK_CACHE['width']}×{_WHEAT_MASK_CACHE['height']} | "
#             f"wheat pixels = {_WHEAT_MASK_CACHE['mask_bool'].sum():,}"
#         )
#     except Exception as e:
#         logger.error(f"Failed to load wheat_mask: {e}")
#     return _WHEAT_MASK_CACHE


# # ═══════════════════════════════════════════════════════════════════════════
# # RASTER I/O
# # ═══════════════════════════════════════════════════════════════════════════

# def cleanup_old_rasters():
#     for param in PARAMS:
#         valid_history  = {f"{param}_{s}.tif" for s in SLOTS}
#         valid_forecast = {
#             f"{fc_param}_{s}_{w}.tif"
#             for fc_param in ["kc", "cwr", "iwr"]
#             for s in SLOTS
#             for w in FORECAST_WINDOWS
#         }
#         for f in (HISTORY_DIR / param).glob("*.tif"):
#             if f.name not in valid_history:
#                 f.unlink()
#         for f in (FORECAST_DIR / param).glob("*.tif"):
#             if f.name not in valid_forecast:
#                 f.unlink()


# def _reproject_and_write(
#     src_path: Path,
#     dst_path: Path,
#     param: str,
#     date: datetime,
#     extra_tags: Optional[Dict] = None,
# ) -> bool:
#     """Reproject processed raster → wheat-mask grid, clamp, mask, write."""
#     grid = _get_wheat_mask()
#     if grid is None:
#         return False

#     vmin, vmax = _VALID.get(param, (-1e9, 1e9))

#     try:
#         with rasterio.open(src_path) as src:
#             data       = src.read(1).astype(np.float64)
#             src_nd     = src.nodata
#             src_crs    = src.crs
#             src_trans  = src.transform

#         if src_nd is not None:
#             data[data == np.float64(src_nd)] = np.nan
#         data[data == np.float64(-9999.0)] = np.nan
#         data[data == np.float64(-999.0)]  = np.nan

#         dst = np.full((grid["height"], grid["width"]), np.nan, dtype=np.float64)
#         rasterio.warp.reproject(
#             source=data,
#             destination=dst,
#             src_transform=src_trans,
#             src_crs=src_crs,
#             dst_transform=grid["transform"],
#             dst_crs=grid["crs"],
#             resampling=Resampling.nearest,
#             src_nodata=None,
#             dst_nodata=None,
#         )

#         dst[dst > vmax] = np.nan
#         if param in ("cwr", "iwr"):
#             dst[(~np.isnan(dst)) & (dst <= 0.0)] = np.nan
#         dst[dst < vmin] = np.nan
#         dst[~grid["mask_bool"]] = np.nan

#         out     = np.where(np.isnan(dst), float(NODATA), dst).astype(np.float64)
#         profile = {
#             "driver":     "GTiff",
#             "dtype":      rasterio.float64,
#             "count":      1,
#             "crs":        grid["crs"],
#             "transform":  grid["transform"],
#             "width":      grid["width"],
#             "height":     grid["height"],
#             "nodata":     float(NODATA),
#             "compress":   "lzw",
#             "tiled":      True,
#             "blockxsize": 256,
#             "blockysize": 256,
#         }

#         dst_path.parent.mkdir(parents=True, exist_ok=True)
#         with rasterio.open(dst_path, "w", **profile) as f:
#             f.write(out, 1)
#             mean_val = float(np.nanmean(dst)) if np.any(~np.isnan(dst)) else None
#             tags = {
#                 "parameter":        param,
#                 "acquisition_date": date.strftime("%Y-%m-%d"),
#                 "mean":             str(round(mean_val, 4)) if mean_val is not None else "",
#             }
#             if extra_tags:
#                 tags.update(extra_tags)
#             f.update_tags(**tags)
#         return True
#     except Exception as e:
#         logger.error(f"[raster] {src_path.name}→{dst_path.name}: {e}")
#         return False


# def _write_array_raster(
#     data: np.ndarray,
#     template: Path,
#     dst_path: Path,
#     tags: Dict,
# ) -> bool:
#     """Write a NumPy array as a GeoTIFF using `template` for georef metadata."""
#     try:
#         with rasterio.open(template) as src:
#             profile = src.profile.copy()
#         profile.update(
#             dtype="float64",
#             count=1,
#             nodata=float(NODATA),
#             compress="lzw",
#             tiled=True,
#             blockxsize=256,
#             blockysize=256,
#         )
#         dst_path.parent.mkdir(parents=True, exist_ok=True)
#         with rasterio.open(dst_path, "w", **profile) as f:
#             f.write(data.astype(np.float64), 1)
#             f.update_tags(**tags)
#         return True
#     except Exception as e:
#         logger.error(f"[raster] write {dst_path.name}: {e}")
#         return False


# def _pixel_avg(arrays: List[np.ndarray]) -> np.ndarray:
#     """Pixel-wise mean ignoring NODATA."""
#     stack = np.stack(arrays, axis=0)
#     valid = (stack != float(NODATA)) & ~np.isnan(stack)
#     total = np.where(valid, stack, 0.0).sum(axis=0)
#     count = valid.sum(axis=0).astype(np.float64)
#     return np.where(count > 0, total / count, float(NODATA)).astype(np.float64)


# # ═══════════════════════════════════════════════════════════════════════════
# # STEP A — HISTORY RASTERS
# # ═══════════════════════════════════════════════════════════════════════════

# def generate_history_rasters() -> int:
#     """Write history/{param}/{param}_{slot}.tif for every param × slot."""
#     dates = _latest_n_complete_dates(HISTORY_DATES)
#     if not dates:
#         logger.error("[history] No complete Sentinel dates")
#         return 0

#     logger.info(f"[history] {len(dates)} dates: {dates[-1].date()} → {dates[0].date()}")
#     total = 0

#     for param, (src_dir, pattern) in _SRC.items():
#         src_by_date = {d: p for d, p in _dated_files(src_dir, pattern)}
#         for idx, date in enumerate(dates):
#             src_path = src_by_date.get(date)
#             if src_path is None:
#                 logger.warning(f"[history] {param} missing for {date.date()}")
#                 continue
#             slot     = slot_for_index(idx)
#             dst_path = history_path(param, slot)

#             if dst_path.exists():
#                 try:
#                     with rasterio.open(dst_path) as f:
#                         if f.tags().get("acquisition_date") == date.strftime("%Y-%m-%d"):
#                             total += 1
#                             continue
#                 except Exception:
#                     pass

#             if _reproject_and_write(src_path, dst_path, param, date,
#                                      extra_tags={"slot": slot}):
#                 total += 1
#                 logger.info(f"[history] {dst_path.name} ({date.date()})")

#         logger.info(f"[history] {param} done")

#     logger.info(f"[history] Total: {total} / {HISTORY_DATES * len(PARAMS)}")
#     return total


# # ═══════════════════════════════════════════════════════════════════════════
# # STEP B — FORECASTING  (corrected design)
# #
# # DESIGN-FIX-1/2/3: Only PET is forecasted with SARIMAX.
# # CWR and IWR are derived physically from that PET forecast.
# # ═══════════════════════════════════════════════════════════════════════════

# def _project_kc_for_dates(future_dates: pd.DatetimeIndex) -> np.ndarray:
#     """
#     Project Kc values for future dates using DOY-based SAVI expectation.

#     Strategy:
#       1. Read the most recent observed Kc raster mean (current crop stage).
#       2. Apply a gentle DOY-based linear trend toward Kc_max (heading) and
#          back to Kc_end (maturity/harvest) following FAO-56 crop stage logic
#          for Rabi wheat (sowing Nov, harvest Apr).

#     This avoids treating Kc as static while maintaining physical bounds.
#     In practice for a 5–15 day horizon, the change is small.

#     Returns: 1-D array of projected scalar Kc, one per future date.
#     """
#     last_kc = _read_mean(history_path("kc", "today")) or 0.80

#     # FAO-56 Rabi wheat Kc stages (thesis Table 9 footnote):
#     #   Kc_ini = 0.30  (Nov–Dec, germination)
#     #   Kc_mid = 1.15  (Feb–Mar, heading)
#     #   Kc_end = 0.40  (Apr, maturity)
#     # Simple linear interpolation: stay close to current Kc for short horizon
#     projected = []
#     for dt in future_dates:
#         doy = dt.timetuple().tm_yday
#         # Rabi wheat phenology mapped to DOY (approximate for Uttarakhand):
#         #   DOY 319 (Nov 15) → Kc_ini = 0.30
#         #   DOY  60 (Mar 01) → Kc_mid = 1.15
#         #   DOY 120 (Apr 30) → Kc_end = 0.40
#         # Within a short forecast window (≤15 days) drift is < 0.05 Kc units.
#         # We use current observed Kc with a tiny nudge toward the seasonal mean.
#         seasonal_mean_kc = 0.80
#         kc_proj = last_kc * 0.95 + seasonal_mean_kc * 0.05  # slight regression
#         kc_proj = float(np.clip(kc_proj, KC_MIN, KC_MAX))
#         projected.append(kc_proj)

#     return np.array(projected)


# def _climatological_peff(future_dates: pd.DatetimeIndex) -> np.ndarray:
#     """
#     Climatological effective rainfall (mm/day) for forecast dates.

#     For Rabi season in Uttarakhand Sub-Himalayan Neeru basin (thesis §5.5):
#     "There was only scattered rainfall for 2-3 days in March."
#     Annual Rabi-season total ≈ 10–30 mm → Peff ≈ 0 for nearly all intervals.

#     Strategy:
#       1. Try to read the most recent observed rain raster mean.
#       2. Apply USDA-SCS formula for that interval total.
#       3. Divide by forecast interval to get mm/day.
#       4. Default to 0 if no rain data available.

#     Returns: 1-D array of Peff (mm/day), one per future date.
#     """
#     # Try to get last observed rainfall context from INSAT rain rasters
#     rain_dir = DIRECTORIES["raw"].get("insat_rain")
#     peff_scalar = 0.0

#     if rain_dir and Path(rain_dir).exists():
#         rain_files = sorted(Path(rain_dir).glob("*.tif"))
#         if rain_files:
#             from models import raster_mean as rm
#             # Use the most recent 5 daily rain files to estimate interval total
#             recent_rain_files = rain_files[-5:]
#             daily_vals = [rm(f, mask_zeros=False) for f in recent_rain_files]
#             daily_vals = [v for v in daily_vals if not np.isnan(v) and v >= 0]
#             if daily_vals:
#                 interval_total = sum(daily_vals)  # mm over ~5 days
#                 n_days         = len(daily_vals)
#                 threshold      = 75.0 * (n_days / 30.0)
#                 if interval_total <= threshold:
#                     pe_total = max(0.6 * interval_total - 10.0, 0.0)
#                 else:
#                     pe_total = max(0.8 * interval_total - 25.0, 0.0)
#                 peff_scalar = pe_total / n_days  # mm/day

#     logger.info(f"[forecast] Climatological Peff = {peff_scalar:.3f} mm/day")
#     return np.full(len(future_dates), peff_scalar)


# def generate_forecast_for_date(
#     reference_date: datetime,
#     days: int = FORECAST_DAYS,
# ) -> Dict[str, pd.Series]:
#     """
#     Generate CWR and IWR forecasts for *days* ahead of *reference_date*.

#     Corrected pipeline (DESIGN-FIX-1/2/3):
#     ──────────────────────────────────────
#     1. Forecast PET using SARIMAX model.
#     2. Project Kc from DOY + last observed value (physics-based).
#     3. Compute CWR_forecast = Kc_projected × PET_forecast  (FAO-56 Eq. 4).
#     4. Compute IWR_forecast = max(CWR_forecast − Peff_clim, 0)  (FAO-56 §4.5).

#     Returns dict with keys: 'pet', 'cwr', 'iwr' — each a pd.Series indexed
#     by daily forecast dates.
#     """
#     forecasts: Dict[str, pd.Series] = {}

#     future_dates = pd.date_range(
#         start=reference_date + timedelta(days=1),
#         periods=days,
#         freq="D",
#     )

#     # ── Step 1: Forecast PET ─────────────────────────────────────────────
#     pet_model, pet_meta = _get_model("pet")
#     if pet_model is None:
#         logger.error("[forecast] PET model not available — cannot generate forecast")
#         return forecasts

#     try:
#         exog_cols = pet_meta.get("exog_cols", ["sin_doy", "cos_doy", "pet_lag1"])
#         last_pet  = pet_meta.get("last_pet") or _read_mean(
#             history_path("kc", "today")
#         ) or 2.5

#         # Optionally get last temp / radiation for exog
#         temp_val = None
#         rad_val  = None
#         temp_dir = DIRECTORIES["raw"].get("insat_temp")
#         rad_dir  = DIRECTORIES["raw"].get("insat_rad")

#         if temp_dir and Path(temp_dir).exists():
#             temp_files = sorted(Path(temp_dir).glob("*.tif"))
#             if temp_files:
#                 from models import raster_mean as rm
#                 temp_val = rm(temp_files[-1], mask_zeros=False)
#                 if np.isnan(temp_val):
#                     temp_val = None

#         if rad_dir and Path(rad_dir).exists():
#             rad_files = sorted(Path(rad_dir).glob("*.tif"))
#             if rad_files:
#                 from models import raster_mean as rm
#                 rad_val = rm(rad_files[-1], mask_zeros=False)
#                 if np.isnan(rad_val):
#                     rad_val = None

#         # Build exog using shared utility (DESIGN-FIX-7)
#         exog_df = build_forecast_exog(
#             future_dates=future_dates,
#             last_pet=last_pet,
#             exog_cols=exog_cols,
#             temp_val=temp_val,
#             rad_val=rad_val,
#         )

#         pet_fc = pet_model.forecast(steps=days, exog=exog_df)

#         # Sanity-clip PET to physical range (0–20 mm/day)
#         pet_values = np.clip(pet_fc.values, 0.5, 20.0)

#         # Guard: if forecast collapses (all ≤ 0.5), use last observed PET
#         if np.all(pet_values <= 0.5):
#             logger.warning(
#                 "[forecast] PET forecast collapsed — using last observed PET persistence"
#             )
#             pet_values = np.full(days, max(float(last_pet), 1.0))

#         forecasts["pet"] = pd.Series(pet_values, index=future_dates, name="pet")
#         logger.info(
#             f"[forecast] PET: mean={float(np.mean(pet_values)):.3f} mm/day, "
#             f"range=[{float(np.min(pet_values)):.2f}, {float(np.max(pet_values)):.2f}]"
#         )

#     except Exception as e:
#         logger.error(f"[forecast] PET forecast failed: {e}", exc_info=True)
#         # Fallback: use last observed PET as flat persistence
#         last_pet_obs = (
#             pet_meta.get("last_pet")
#             or _read_mean(history_path("kc", "today"))
#             or 2.5
#         )
#         forecasts["pet"] = pd.Series(
#             np.full(days, float(last_pet_obs)), index=future_dates, name="pet"
#         )
#         logger.warning(
#             f"[forecast] PET fallback to persistence: {float(last_pet_obs):.3f} mm/day"
#         )

#     # ── Step 2: Project Kc ───────────────────────────────────────────────
#     kc_projected = _project_kc_for_dates(future_dates)

#     forecasts["kc"] = pd.Series(kc_projected, index=future_dates, name="kc")
#     logger.info(
#         f"[forecast] Kc (projected): mean={float(np.mean(kc_projected)):.3f}, "
#         f"range=[{float(np.min(kc_projected)):.3f}, {float(np.max(kc_projected)):.3f}]"
#     )

#     # ── Step 3: Compute CWR = Kc × PET  (physics) ───────────────────────
#     # DESIGN-FIX-2: CWR is deterministic — not forecasted with SARIMAX
#     pet_arr = forecasts["pet"].values
#     cwr_arr = np.clip(kc_projected * pet_arr, CWR_MIN, CWR_MAX)

#     forecasts["cwr"] = pd.Series(cwr_arr, index=future_dates, name="cwr")
#     logger.info(
#         f"[forecast] CWR (=Kc×PET): mean={float(np.mean(cwr_arr)):.3f} mm/day, "
#         f"Kc_mean={float(np.mean(kc_projected)):.3f}, "
#         f"range=[{float(np.min(cwr_arr)):.2f}, {float(np.max(cwr_arr)):.2f}]"
#     )

#     # ── Step 4: Compute IWR = max(CWR − Peff, 0)  (physics) ─────────────
#     # DESIGN-FIX-3: IWR is deterministic — not forecasted with SARIMAX
#     peff_arr = _climatological_peff(future_dates)
#     iwr_arr  = np.maximum(cwr_arr - peff_arr, 0.0)

#     forecasts["iwr"] = pd.Series(iwr_arr, index=future_dates, name="iwr")
#     logger.info(
#         f"[forecast] IWR (=max(CWR-Peff,0)): mean={float(np.mean(iwr_arr)):.3f} mm/day, "
#         f"Peff_mean={float(np.mean(peff_arr)):.3f} mm/day, "
#         f"range=[{float(np.min(iwr_arr)):.2f}, {float(np.max(iwr_arr)):.2f}]"
#     )

#     return forecasts


# def create_forecast_raster(
#     param: str,
#     slot: str,
#     window: str,
#     forecast_series: pd.Series,
#     template_raster: Path,
# ) -> bool:
#     """
#     Create forecast raster by scaling the template spatial pattern to the
#     forecast mean.  This preserves within-field spatial variability while
#     applying the modelled temporal change.
#     """
#     try:
#         with rasterio.open(template_raster) as src:
#             template_data = src.read(1).astype(np.float64)
#             nodata        = src.nodata if src.nodata is not None else NODATA
#             template_data = np.where(template_data == nodata, np.nan, template_data)
#             profile       = src.profile.copy()

#         n_days          = WINDOW_DAYS[window]
#         window_forecast = forecast_series.iloc[:n_days]
#         forecast_mean   = float(window_forecast.mean())

#         valid = ~np.isnan(template_data)
#         if not valid.any():
#             logger.warning(f"No valid pixels in template for {param} {slot}")
#             return False

#         template_mean = float(np.nanmean(template_data[valid]))

#         if template_mean > 0:
#             scale_factor   = forecast_mean / template_mean
#             forecast_array = np.where(valid, template_data * scale_factor, np.nan)
#         else:
#             forecast_array = np.where(valid, forecast_mean, np.nan)

#         vmin, vmax     = _VALID.get(param, (-1e9, 1e9))
#         forecast_array = np.clip(forecast_array, vmin, vmax)

#         dst_path = forecast_path(param, slot, window)
#         profile.update(
#             dtype="float64",
#             nodata=NODATA,
#             compress="lzw",
#             tiled=True,
#             blockxsize=256,
#             blockysize=256,
#         )

#         with rasterio.open(dst_path, "w", **profile) as dst:
#             out_data = np.where(np.isnan(forecast_array), NODATA, forecast_array)
#             dst.write(out_data.astype(np.float64), 1)
#             dst.update_tags(
#                 parameter=param,
#                 slot=slot,
#                 forecast_window=window,
#                 reference_date=slot,
#                 forecast_mean=str(round(forecast_mean, 4)),
#                 template_mean=str(round(template_mean, 4)),
#                 units="mm_per_day" if param in ["cwr", "iwr"] else "",
#                 model="PET-SARIMAX+Physics-CWR/IWR",
#                 generated_by="irrigation_monitoring_v9.0",
#             )

#         logger.info(
#             f"Created {param} forecast for {slot} {window}: "
#             f"mean={forecast_mean:.4f} mm/day (template mean={template_mean:.4f})"
#         )
#         return True

#     except Exception as e:
#         logger.error(f"Failed to create {param} forecast for {slot}_{window}: {e}")
#         return False


# def generate_all_forecast_rasters() -> int:
#     """
#     Generate all forecast rasters (2 params × 12 slots × 3 windows)
#     using the corrected PET-SARIMAX + physics CWR/IWR pipeline.
#     """
#     dates = _latest_n_complete_dates(HISTORY_DATES)
#     if not dates:
#         logger.error("[forecast] No Sentinel dates available")
#         return 0

#     total = 0

#     for idx, date in enumerate(dates):
#         slot      = slot_for_index(idx)
#         forecasts = generate_forecast_for_date(date, FORECAST_DAYS)

#         if not forecasts:
#             logger.warning(f"[forecast] No forecast for {slot} ({date.date()})")
#             continue

#         n_rasters = 0
#         for param in ["kc", "cwr", "iwr"]:
#             if param not in forecasts:
#                 continue
#             for window in FORECAST_WINDOWS:
#                 dst_path = forecast_path(param, slot, window)

#                 if dst_path.exists():
#                     try:
#                         with rasterio.open(dst_path) as f:
#                             tags = f.tags()
#                             if tags.get("reference_date") == slot:
#                                 n_rasters += 1
#                                 total += 1
#                                 continue
#                     except Exception:
#                         pass

#                 template = history_path(param, slot)
#                 if template.exists():
#                     if create_forecast_raster(
#                         param, slot, window, forecasts[param], template
#                     ):
#                         n_rasters += 1
#                         total += 1

#         logger.info(f"[forecast] slot={slot} ({date.date()}): {n_rasters} files")

#     expected_total = len(dates) * 3 * len(FORECAST_WINDOWS)  # kc + cwr + iwr
#     logger.info(f"[forecast] ALL: {total} / {expected_total}")
#     return total


# # ═══════════════════════════════════════════════════════════════════════════
# # STEP C — PUSH TO GEOSERVER
# # ═══════════════════════════════════════════════════════════════════════════

# def push_to_geoserver() -> None:
#     try:
#         from init_geoserver import GeoServerAPI
#         gs = GeoServerAPI()
#     except Exception as e:
#         logger.warning(f"[geoserver] Cannot init GeoServerAPI: {e}")
#         return

#     for param in ["savi", "kc", "cwr", "iwr"]:
#         for slot in SLOTS:
#             p = history_path(param, slot)
#             if not p.exists():
#                 continue
#             store = f"{param}_{slot}"
#             layer = store
#             try:
#                 gs.create_coverage_store_if_not_exists(store, p)
#                 gs.update_coverage_store_file(store, p)
#                 gs.configure_layer(layer_name=layer, store_name=store)
#                 style = f"{param}_style"
#                 gs.assign_style(layer, style)
#                 logger.info(f"[geoserver] ✅ Layer ready: {layer}")
#             except Exception as e:
#                 logger.warning(f"[geoserver] {store}: {e}")

#     # Push forecast rasters for kc, cwr, iwr
#     for param in ["kc", "cwr", "iwr"]:
#         for slot in SLOTS:
#             for window in FORECAST_WINDOWS:
#                 p = forecast_path(param, slot, window)
#                 if not p.exists():
#                     continue
#                 store = f"{param}_{slot}_{window}"
#                 layer = store
#                 try:
#                     gs.create_coverage_store_if_not_exists(store, p)
#                     gs.update_coverage_store_file(store, p)
#                     gs.configure_layer(layer_name=layer, store_name=store)
#                     style = f"{param}_style"
#                     gs.assign_style(layer, style)
#                     logger.info(f"[geoserver] ✅ Forecast layer ready: {layer}")
#                 except Exception as e:
#                     logger.warning(f"[geoserver] {store}: {e}")


# # ═══════════════════════════════════════════════════════════════════════════
# # MASTER PIPELINE
# # ═══════════════════════════════════════════════════════════════════════════

# def run_pipeline() -> Dict:
#     """
#     Full pipeline run:
#       A. History rasters
#       B. Forecast generation (PET SARIMAX → physics CWR/IWR)
#       C. Forecast rasters
#       D. GeoServer push
#     """
#     logger.info("═" * 65)
#     logger.info("run_pipeline() START — v9.0 (PET-SARIMAX + Physics CWR/IWR)")
#     logger.info("═" * 65)

#     cleanup_old_rasters()
#     _get_wheat_mask()

#     logger.info("── A: History rasters ──")
#     h_total = generate_history_rasters()
#     logger.info(f"── A done: {h_total}/{HISTORY_DATES * len(PARAMS)} ──")

#     logger.info("── B/C: Forecast + rasters ──")
#     _get_model("pet")
#     f_total = generate_all_forecast_rasters()
#     logger.info(f"── B/C done: {f_total}/{HISTORY_DATES * 3 * len(FORECAST_WINDOWS)} ──")

#     logger.info("── D: GeoServer ──")
#     push_to_geoserver()

#     dates   = _latest_n_complete_dates()
#     summary = {
#         "slots":              {slot_for_index(i): str(d.date()) for i, d in enumerate(dates)},
#         "history_rasters":    h_total,
#         "forecast_rasters":   f_total,
#         "grand_total":        h_total + f_total,
#         "units":              "mm_per_day",
#         "forecast_model":     "PET-SARIMAX + Physics CWR/IWR",
#         "physical_relationships": {
#             "savi_to_kc": f"Kc = {KC_SLOPE:.4f} × SAVI + {KC_INTERCEPT:.4f}",
#             "cwr":        "CWR = Kc_projected × PET_forecast  (FAO-56 Eq. 4)",
#             "iwr":        "IWR = max(CWR − Peff, 0)  (FAO-56 §4.5)",
#             "peff":       "Peff = USDA-SCS on interval rainfall total",
#         },
#     }
#     logger.info("═" * 65)
#     logger.info(f"DONE: {summary}")
#     logger.info("═" * 65)
#     return summary


# # ═══════════════════════════════════════════════════════════════════════════
# # SCHEDULER CALLBACKS
# # ═══════════════════════════════════════════════════════════════════════════

# def generate_operational_rasters() -> None:
#     logger.info("[generate_operational_rasters] START")
#     try:
#         cleanup_old_rasters()
#         h = generate_history_rasters()
#         logger.info(f"[generate_operational_rasters] history rasters: {h}")
#     except Exception as e:
#         logger.error(f"[generate_operational_rasters] history step failed: {e}", exc_info=True)

#     try:
#         f = generate_all_forecast_rasters()
#         logger.info(f"[generate_operational_rasters] forecast rasters: {f}")
#     except Exception as e:
#         logger.error(f"[generate_operational_rasters] forecast step failed: {e}", exc_info=True)

#     try:
#         push_to_geoserver()
#         logger.info("[generate_operational_rasters] GeoServer push done")
#     except Exception as e:
#         logger.error(f"[generate_operational_rasters] GeoServer push failed: {e}", exc_info=True)

#     logger.info("[generate_operational_rasters] DONE")


# def process_single_sentinel_image(tif_path: Path) -> None:
#     logger.info(f"[process_single_sentinel_image] {tif_path.name}")
#     try:
#         from run import run_savi, run_kc, run_etc, run_cwr, run_iwr
#         from processor import DataProcessor
#         p = DataProcessor()
#         run_savi(p)
#         run_kc(p)
#         run_etc(p)
#         run_cwr(p)
#         run_iwr(p)
#         logger.info(f"[process_single_sentinel_image] complete for {tif_path.name}")
#     except Exception as e:
#         logger.error(
#             f"[process_single_sentinel_image] failed for {tif_path.name}: {e}",
#             exc_info=True,
#         )


# # ═══════════════════════════════════════════════════════════════════════════
# # FastAPI APP
# # ═══════════════════════════════════════════════════════════════════════════

# from graph import router as graph_router

# app = FastAPI(
#     title="Wheat Irrigation Monitoring System",
#     version="9.0.0",
#     description=(
#         "v9.0 — Corrected forecast design:\n\n"
#         "  • PET forecasted with SARIMAX (only statistically forecasted variable)\n"
#         "  • CWR = Kc_projected × PET_forecast  (FAO-56 Eq. 4, physics)\n"
#         "  • IWR = max(CWR − Peff, 0)  (FAO-56 §4.5, physics)\n\n"
#         "Physical chain: SAVI → Kc → CWR → IWR\n"
#         "No IWR direct forecasting. No circular exog dependencies."
#     ),
# )

# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["*"],
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )

# # app.include_router(graph_router, prefix="/api/graph", tags=["graphs"])
# app.include_router(graph_router)



# from config import STUDY_AREA, EXACT_BOUNDARY

# @app.get("/api/boundary")
# async def get_boundary():
#     """
#     Return the study-area boundary for Udham Singh Nagar.
#     Used by MapView to fit the Leaflet map bounds.
#     Guaranteed to return valid, non-empty bounds.
#     """
#     bounds = EXACT_BOUNDARY.get("bounds") or STUDY_AREA.get("bounds")

#     # Validate — Leaflet needs north > south and east > west
#     if not bounds or not all(k in bounds for k in ("north", "south", "east", "west")):
#         # Hard-coded fallback so the map never breaks
#         bounds = {
#             "north": 29.4400,
#             "south": 28.8900,
#             "west":  78.8800,
#             "east":  80.1040,
#         }

#     north = bounds["north"]
#     south = bounds["south"]
#     east  = bounds["east"]
#     west  = bounds["west"]

#     # Swap silently if they are inverted
#     if north < south:
#         north, south = south, north
#     if east < west:
#         east, west = west, east

#     # Minimum span guard — prevents zero-area bounds crash in Leaflet
#     if (north - south) < 0.01:
#         north += 0.05
#         south -= 0.05
#     if (east - west) < 0.01:
#         east += 0.05
#         west -= 0.05

#     return {
#         "name":    STUDY_AREA.get("name", "Udham Singh Nagar"),
#         "state":   STUDY_AREA.get("state", "Uttarakhand"),
#         "crs":     STUDY_AREA.get("crs", "EPSG:4326"),
#         "source":  STUDY_AREA.get("boundary_source", "static-fallback"),
#         "bounds": {
#             "north": round(north, 6),
#             "south": round(south, 6),
#             "east":  round(east,  6),
#             "west":  round(west,  6),
#         },
#         # Leaflet fitBounds expects [[south, west], [north, east]]
#         "leaflet_bounds": [
#             [round(south, 6), round(west, 6)],
#             [round(north, 6), round(east, 6)],
#         ],
#         "center": EXACT_BOUNDARY.get("center") or [
#             round((east + west) / 2, 6),
#             round((north + south) / 2, 6),
#         ],
#         "geojson": EXACT_BOUNDARY.get("geojson", {"type": "FeatureCollection", "features": []}),
#     }



# def _maintenance_middleware_factory(app_instance):
#     from fastapi import Request
#     from fastapi.responses import JSONResponse

#     @app_instance.middleware("http")
#     async def _maintenance_gate(request: Request, call_next):
#         try:
#             from scheduler import MAINTENANCE_MODE as _mm
#         except ImportError:
#             _mm = False
#         if _mm and request.url.path not in ("/health", "/"):
#             return JSONResponse(
#                 status_code=503,
#                 content={
#                     "detail": "System is updating data. Please retry in a few minutes.",
#                     "maintenance": True,
#                 },
#             )
#         return await call_next(request)

#     return app_instance


# _maintenance_middleware_factory(app)


# # ── Endpoints ──────────────────────────────────────────────────────────────

# @app.get("/health")
# async def health():
#     return {
#         "status":  "ok",
#         "version": "9.0.0",
#         "model":   "PET-SARIMAX + Physics CWR/IWR",
#     }


# @app.get("/api/forecast")
# async def get_forecast(
#     date: str = Query(..., description="Reference date YYYY-MM-DD"),
#     days: int  = Query(15,  ge=1, le=30, description="Forecast horizon (days)"),
# ):
#     """
#     Generate a multi-day CWR + IWR forecast.

#     Forecast chain:
#       PET (SARIMAX) → CWR = Kc × PET → IWR = max(CWR − Peff, 0)
#     """
#     try:
#         ref_date = datetime.strptime(date, "%Y-%m-%d")
#     except ValueError:
#         raise HTTPException(status_code=400, detail="Invalid date — use YYYY-MM-DD")

#     forecasts = generate_forecast_for_date(ref_date, days)
#     if not forecasts:
#         raise HTTPException(status_code=500, detail="Failed to generate forecast")

#     result: dict = {
#         "reference_date": date,
#         "forecast_days":  days,
#         "model":          "PET-SARIMAX + Physics CWR/IWR (v9.0)",
#         "forecast_chain": "PET(SARIMAX) → CWR=Kc×PET → IWR=max(CWR-Peff,0)",
#         "forecasts":      {},
#     }

#     for param in ("pet", "cwr", "iwr"):
#         if param in forecasts:
#             series = forecasts[param]
#             result["forecasts"][param] = {
#                 "dates":  [d.strftime("%Y-%m-%d") for d in series.index],
#                 "values": [round(float(v), 4) for v in series.values],
#                 "units":  "mm_per_day",
#                 "mean":   round(float(series.mean()), 4),
#                 "min":    round(float(series.min()),  4),
#                 "max":    round(float(series.max()),  4),
#             }

#     result["window_summaries"] = {}
#     for window in FORECAST_WINDOWS:
#         n_days = WINDOW_DAYS[window]
#         result["window_summaries"][window] = {}
#         for param in ("kc", "cwr", "iwr"):
#             if param in forecasts:
#                 vals = forecasts[param].iloc[:n_days].values
#                 result["window_summaries"][window][param] = {
#                     "mean":  round(float(np.mean(vals)),  4),
#                     "total": round(float(np.sum(vals)),   4),
#                 }

#     return result


# @app.get("/api/history")
# async def get_history():
#     """Return observed and forecast means for all history slots."""
#     dates = _latest_n_complete_dates()
#     if not dates:
#         raise HTTPException(status_code=404, detail="No processed Sentinel scenes found")

#     result = []
#     for idx, d in enumerate(dates):
#         slot      = slot_for_index(idx)
#         obs_means = {}
#         fc_means  = {}

#         for param in PARAMS:
#             path = history_path(param, slot)
#             if path.exists():
#                 with rasterio.open(path) as src:
#                     tags = src.tags()
#                 mean_str        = tags.get("mean")
#                 obs_means[param] = (
#                     float(mean_str)
#                     if mean_str and mean_str not in ("None", "nan", "")
#                     else None
#                 )
#             else:
#                 obs_means[param] = None

#             fc_means[param] = {}
#             for w in FORECAST_WINDOWS:
#                 fpath = forecast_path(param, slot, w)
#                 if fpath.exists():
#                     with rasterio.open(fpath) as src:
#                         tags = src.tags()
#                     fc_str              = tags.get("forecast_mean")
#                     fc_means[param][w]  = (
#                         float(fc_str)
#                         if fc_str and fc_str not in ("None", "nan", "")
#                         else None
#                     )
#                 else:
#                     fc_means[param][w] = None

#         result.append({
#             "slot":           slot,
#             "date":           str(d.date()),
#             "is_latest":      idx == 0,
#             "obs_means":      obs_means,
#             "forecast_means": fc_means,
#         })

#     return {
#         "n_slots": len(result),
#         "units":   "mm_per_day",
#         "model":   "PET-SARIMAX + Physics CWR/IWR",
#         "slots":   result,
#     }


# @app.get("/api/point")
# def get_point(
#     lat:  float,
#     lon:  float,
#     slot: Optional[str] = None,
# ):
#     """Point query — returns observed and forecast values at (lat, lon)."""
#     if not slot:
#         slot = "today"

#     result   = {}
#     forecast = {}

#     for param in ("savi", "kc", "cwr", "iwr"):
#         path = history_path(param, slot)
#         if path.exists():
#             with rasterio.open(path) as src:
#                 val = list(src.sample([(lon, lat)]))[0][0]
#                 result[param] = None if val == NODATA else float(val)

#         if param in ("kc", "cwr", "iwr"):
#             forecast[param] = {}
#             for w in FORECAST_WINDOWS:
#                 fpath = forecast_path(param, slot, w)
#                 if fpath.exists():
#                     with rasterio.open(fpath) as src:
#                         val = list(src.sample([(lon, lat)]))[0][0]
#                         forecast[param][w] = None if val == NODATA else float(val)
#                 else:
#                     forecast[param][w] = None

#     return {
#         "lat":              lat,
#         "lon":              lon,
#         "acquisition_date": slot,
#         "values":           result,
#         "forecast":         forecast,
#     }


# @app.post("/api/refresh")
# async def manual_refresh():
#     """Trigger a full pipeline run."""
#     try:
#         return {"status": "ok", "result": run_pipeline()}
#     except Exception as e:
#         logger.exception("Pipeline failed")
#         raise HTTPException(status_code=500, detail=str(e))


# @app.get("/api/model/info")
# async def model_info():
#     """Return metadata for all loaded models."""
#     pet_model, pet_meta = _get_model("pet")

#     def _meta_dict(model, meta):
#         if meta is None:
#             return {"available": False}
#         return {
#             "available":          model is not None,
#             "note":               meta.get("note", ""),
#             "test_r2":            meta["metrics"].get("R2"),
#             "test_rmse":          meta["metrics"].get("RMSE"),
#             "test_mae":           meta["metrics"].get("MAE"),
#             "order":              meta.get("order"),
#             "exog_cols":          meta.get("exog_cols"),
#             "last_training_date": (
#                 meta["last_date"].strftime("%Y-%m-%d")
#                 if meta.get("last_date") else None
#             ),
#         }

#     return {
#         "models": {
#             "pet": _meta_dict(pet_model, pet_meta),
#         },
#         "forecast_chain": {
#             "step1": "PET forecasted with SARIMAX",
#             "step2": f"Kc projected from DOY + last observed Kc",
#             "step3": "CWR = Kc_projected × PET_forecast  (FAO-56 Eq. 4)",
#             "step4": "IWR = max(CWR − Peff_clim, 0)  (FAO-56 §4.5)",
#         },
#         "physical_relationships": {
#             "savi_to_kc": f"Kc = {KC_SLOPE:.4f} × SAVI + {KC_INTERCEPT:.4f}",
#             "cwr":        "CWR = Kc × PET  (not forecasted — computed)",
#             "iwr":        "IWR = max(CWR − Peff, 0)  (not forecasted — computed)",
#             "peff":       "USDA-SCS on 5-day interval rainfall total",
#         },
#     }


# # ═══════════════════════════════════════════════════════════════════════════
# # MAIN ENTRY POINT
# # ═══════════════════════════════════════════════════════════════════════════

# def main():
#     setup_logging()
#     logger.info("=" * 65)
#     logger.info("Irrigation Monitoring System v9.0 starting …")
#     logger.info("Forecast: PET(SARIMAX) → CWR=Kc×PET → IWR=max(CWR-Peff,0)")
#     logger.info("=" * 65)

#     _get_wheat_mask()

#     pet_model, pet_meta = _get_model("pet")
#     if pet_model:
#         logger.info(f"✓ PET model ready (R²={pet_meta['metrics']['R2']:.4f})")
#     else:
#         logger.error("✗ Failed to initialise PET model")

#     run_pipeline()

#     try:
#         from scheduler import start_scheduler
#         _scheduler, _observer = start_scheduler(
#             delete_callback=cleanup_old_rasters,
#             generate_callback=generate_operational_rasters,
#             download_and_process_callback=None,
#             single_image_pipeline_callback=process_single_sentinel_image,
#         )
#         logger.info("✓ Scheduler + Watchdog started")
#     except Exception as e:
#         logger.error(f"✗ Scheduler failed to start: {e}", exc_info=True)
#         logger.warning(
#             "Continuing without scheduler — pipeline will NOT run automatically."
#         )

#     uvicorn.run(
#         app, host="0.0.0.0", port=8000,
#         log_level="info", access_log=True,
#     )


# if __name__ == "__main__":
#     main()


"""
main.py  — v10.0
─────────────────────────────────────────────────────────────────────────────
FORECAST DESIGN (updated from v9.0):

  v9.0 (partially corrected):
    • PET forecasted with SARIMAX ✓
    • Kc projected via static DOY nudge (_project_kc_for_dates) ✗
      → ignores actual crop phenology dynamics mid-season

  v10.0 (fully corrected):
    Step 1 — Forecast SAVI with SARIMAX       (NEW — root of Kc chain)
    Step 2 — Compute Kc = 1.2088×SAVI + 0.5375, clip [0.30, 1.15]
    Step 3 — Forecast PET with SARIMAX        (independent met variable)
    Step 4 — Compute CWR = Kc × PET_forecast (physics, FAO-56 Eq. 4)
    Step 5 — Compute IWR = max(CWR − Peff, 0)(physics, FAO-56 §4.5)

  Forecast outputs:
    • "today"  — observed means from latest Sentinel history rasters
    • "5day"   — window summary (mean + total) from days 1–5
    • "10day"  — window summary from days 1–10
    • "15day"  — window summary from days 1–15
    • "series" — full 15-day daily time series for chart visualization

  No circular dependencies anywhere in the chain.
  SAVI and PET are statistically independent; Kc, CWR, IWR are computed.
─────────────────────────────────────────────────────────────────────────────
"""

import asyncio
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
from rasterio.enums import Resampling
from rasterio.warp import transform as warp_transform

from config import (
    STUDY_AREA, DIRECTORIES, GEOSERVER, SARIMAX_CONFIG,
    WHEAT_PARAMS
)
from logging_config import setup_logging
import models
from models import build_forecast_exog, build_savi_forecast_exog   # v10.0: both builders

setup_logging()
logger = logging.getLogger(__name__)

# Physical constants from thesis
KC_SLOPE     = WHEAT_PARAMS["savi_kc"]["slope"]          # 1.2088
KC_INTERCEPT = WHEAT_PARAMS["savi_kc"]["intercept"]       # 0.5375
KC_MIN       = 0.30
KC_MAX       = 1.15
CWR_MIN      = 0.0
CWR_MAX      = 15.0


# ═══════════════════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════

HISTORY_DATES    = 12
FORECAST_DAYS    = 15
NODATA           = -9999.0
PARAMS           = ["savi", "kc", "cwr", "iwr"]
SLOTS: List[str] = ["today"] + [str(i) for i in range(1, HISTORY_DATES)]
FORECAST_WINDOWS = ["5day", "10day", "15day"]
WINDOW_DAYS      = {"5day": 5, "10day": 10, "15day": 15}

# Parameters for which forecast rasters are generated
FORECAST_PARAMS  = ["savi", "kc", "cwr", "iwr"]   # v10.0: savi added

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

# v10.0: cache for both SAVI and PET dataset counts (set to -1 to force reload)
_fc_cache: Dict = {"pet_count": -1, "savi_count": -1}


def _get_model(model_type: str):
    """Load and cache trained models."""
    global _MODEL_CACHE

    if model_type in _MODEL_CACHE:
        return _MODEL_CACHE[model_type]

    try:
        model, meta = models.load_model(model_type)
        _MODEL_CACHE[model_type] = (model, meta)
        logger.info(
            f"✓ Loaded {model_type.upper()} model "
            f"(Test R²={meta['metrics']['R2']:.4f})"
        )
        return model, meta
    except FileNotFoundError:
        logger.warning(f"Model {model_type} not found — training all models...")
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
            for fc_param in FORECAST_PARAMS   # v10.0: savi, kc, cwr, iwr
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
        if param in ("cwr", "iwr"):
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
# STEP B — FORECASTING  (v10.0 design)
#
# v10.0: SAVI is now forecasted with SARIMAX.
#        Kc is derived from SAVI_forecast analytically (no static nudge).
# ═══════════════════════════════════════════════════════════════════════════

def _climatological_peff(future_dates: pd.DatetimeIndex) -> np.ndarray:
    """
    Climatological effective rainfall (mm/day) for forecast dates.

    For Rabi season in Uttarakhand USN (thesis §5.5):
    "There was only scattered rainfall for 2-3 days in March."
    Annual Rabi-season total ≈ 10–30 mm → Peff ≈ 0 for nearly all intervals.

    Returns: 1-D array of Peff (mm/day), one per future date.
    """
    rain_dir    = DIRECTORIES["raw"].get("insat_rain")
    peff_scalar = 0.0

    if rain_dir and Path(rain_dir).exists():
        rain_files = sorted(Path(rain_dir).glob("*.tif"))
        if rain_files:
            from models import raster_mean as rm
            recent_rain_files = rain_files[-5:]
            daily_vals = [rm(f, mask_zeros=False) for f in recent_rain_files]
            daily_vals = [v for v in daily_vals if not np.isnan(v) and v >= 0]
            if daily_vals:
                interval_total = sum(daily_vals)
                n_days         = len(daily_vals)
                threshold      = 75.0 * (n_days / 30.0)
                if interval_total <= threshold:
                    pe_total = max(0.6 * interval_total - 10.0, 0.0)
                else:
                    pe_total = max(0.8 * interval_total - 25.0, 0.0)
                peff_scalar = pe_total / n_days

    logger.info(f"[forecast] Climatological Peff = {peff_scalar:.3f} mm/day")
    return np.full(len(future_dates), peff_scalar)


def generate_forecast_for_date(
    reference_date: datetime,
    days: int = FORECAST_DAYS,
) -> Dict[str, pd.Series]:
    """
    Generate SAVI, Kc, PET, CWR and IWR forecasts for *days* ahead.

    v10.0 Pipeline:
    ──────────────────────────────────────────────────────────────────
    Step 1 — Forecast SAVI with SARIMAX  (NEW — phenological trajectory)
    Step 2 — Compute Kc = 1.2088×SAVI_forecast + 0.5375, clip [0.30, 1.15]
    Step 3 — Forecast PET with SARIMAX   (independent met variable)
    Step 4 — Compute CWR = Kc × PET_forecast  (FAO-56 Eq. 4, physics)
    Step 5 — Compute IWR = max(CWR − Peff_clim, 0)  (FAO-56 §4.5, physics)

    No circular dependencies: SAVI and PET are independent series.
    Kc, CWR, IWR are all computed, never statistically modelled.

    Returns dict with keys: 'savi', 'kc', 'pet', 'cwr', 'iwr'
    Each is a pd.Series indexed by daily forecast dates.
    """
    forecasts: Dict[str, pd.Series] = {}

    future_dates = pd.date_range(
        start=reference_date + timedelta(days=1),
        periods=days,
        freq="D",
    )

    # ── Step 1: Forecast SAVI ────────────────────────────────────────────
    # DESIGN-v10-1: SAVI replaces the static _project_kc_for_dates nudge.
    savi_model, savi_meta = _get_model("savi")
    if savi_model is None:
        logger.error("[forecast] SAVI model not available — cannot generate forecast")
        return forecasts

    try:
        savi_exog_cols = savi_meta.get("exog_cols", ["sin_doy", "cos_doy", "savi_lag1"])
        last_savi      = savi_meta.get("last_savi") or \
                         _read_mean(history_path("savi", "today")) or 0.30

        savi_exog_df = build_savi_forecast_exog(
            future_dates=future_dates,
            last_savi=float(last_savi),
            exog_cols=savi_exog_cols,
        )

        savi_fc     = savi_model.forecast(steps=days, exog=savi_exog_df)
        savi_values = np.clip(savi_fc.values, -1.0, 1.0)

        # Guard: if SAVI collapses to near-zero, use last observed value
        if np.all(np.abs(savi_values) < 0.01):
            logger.warning(
                "[forecast] SAVI forecast collapsed — using last observed SAVI persistence"
            )
            savi_values = np.full(days, max(float(last_savi), 0.05))

        forecasts["savi"] = pd.Series(savi_values, index=future_dates, name="savi")
        logger.info(
            f"[forecast] SAVI: mean={float(np.mean(savi_values)):.3f}, "
            f"range=[{float(np.min(savi_values)):.3f}, {float(np.max(savi_values)):.3f}]"
        )

    except Exception as e:
        logger.error(f"[forecast] SAVI forecast failed: {e}", exc_info=True)
        last_savi_obs = (
            savi_meta.get("last_savi")
            or _read_mean(history_path("savi", "today"))
            or 0.30
        )
        forecasts["savi"] = pd.Series(
            np.full(days, float(last_savi_obs)), index=future_dates, name="savi"
        )
        logger.warning(
            f"[forecast] SAVI fallback to persistence: {float(last_savi_obs):.3f}"
        )

    # ── Step 2: Compute Kc from SAVI forecast  (thesis equation) ─────────
    # DESIGN-v10-2: Kc derived analytically — no static nudge, no SARIMAX on Kc.
    # Kc = 1.2088 × SAVI + 0.5375  (thesis Table 9, best-fit equation)
    savi_arr = forecasts["savi"].values
    kc_arr   = np.clip(KC_SLOPE * savi_arr + KC_INTERCEPT, KC_MIN, KC_MAX)

    forecasts["kc"] = pd.Series(kc_arr, index=future_dates, name="kc")
    logger.info(
        f"[forecast] Kc (=1.2088×SAVI+0.5375): mean={float(np.mean(kc_arr)):.3f}, "
        f"range=[{float(np.min(kc_arr)):.3f}, {float(np.max(kc_arr)):.3f}]"
    )

    # ── Step 3: Forecast PET ─────────────────────────────────────────────
    pet_model, pet_meta = _get_model("pet")
    if pet_model is None:
        logger.error("[forecast] PET model not available — cannot generate forecast")
        return forecasts

    try:
        exog_cols = pet_meta.get("exog_cols", ["sin_doy", "cos_doy", "pet_lag1"])
        last_pet  = pet_meta.get("last_pet") or _read_mean(
            history_path("kc", "today")
        ) or 2.5

        # Optionally get last temp / radiation for exog
        temp_val = None
        rad_val  = None
        temp_dir = DIRECTORIES["raw"].get("insat_temp")
        rad_dir  = DIRECTORIES["raw"].get("insat_rad")

        if temp_dir and Path(temp_dir).exists():
            temp_files = sorted(Path(temp_dir).glob("*.tif"))
            if temp_files:
                from models import raster_mean as rm
                temp_val = rm(temp_files[-1], mask_zeros=False)
                if np.isnan(temp_val):
                    temp_val = None

        if rad_dir and Path(rad_dir).exists():
            rad_files = sorted(Path(rad_dir).glob("*.tif"))
            if rad_files:
                from models import raster_mean as rm
                rad_val = rm(rad_files[-1], mask_zeros=False)
                if np.isnan(rad_val):
                    rad_val = None

        exog_df = build_forecast_exog(
            future_dates=future_dates,
            last_pet=last_pet,
            exog_cols=exog_cols,
            temp_val=temp_val,
            rad_val=rad_val,
        )

        pet_fc     = pet_model.forecast(steps=days, exog=exog_df)
        pet_values = np.clip(pet_fc.values, 0.5, 20.0)

        if np.all(pet_values <= 0.5):
            logger.warning(
                "[forecast] PET forecast collapsed — using last observed PET persistence"
            )
            pet_values = np.full(days, max(float(last_pet), 1.0))

        forecasts["pet"] = pd.Series(pet_values, index=future_dates, name="pet")
        logger.info(
            f"[forecast] PET: mean={float(np.mean(pet_values)):.3f} mm/day, "
            f"range=[{float(np.min(pet_values)):.2f}, {float(np.max(pet_values)):.2f}]"
        )

    except Exception as e:
        logger.error(f"[forecast] PET forecast failed: {e}", exc_info=True)
        last_pet_obs = (
            pet_meta.get("last_pet")
            or _read_mean(history_path("kc", "today"))
            or 2.5
        )
        forecasts["pet"] = pd.Series(
            np.full(days, float(last_pet_obs)), index=future_dates, name="pet"
        )
        logger.warning(
            f"[forecast] PET fallback to persistence: {float(last_pet_obs):.3f} mm/day"
        )

    # ── Step 4: Compute CWR = Kc × PET  (physics) ────────────────────────
    pet_arr = forecasts["pet"].values
    cwr_arr = np.clip(kc_arr * pet_arr, CWR_MIN, CWR_MAX)

    forecasts["cwr"] = pd.Series(cwr_arr, index=future_dates, name="cwr")
    logger.info(
        f"[forecast] CWR (=Kc×PET): mean={float(np.mean(cwr_arr)):.3f} mm/day, "
        f"range=[{float(np.min(cwr_arr)):.2f}, {float(np.max(cwr_arr)):.2f}]"
    )

    # ── Step 5: Compute IWR = max(CWR − Peff, 0)  (physics) ─────────────
    peff_arr = _climatological_peff(future_dates)
    iwr_arr  = np.maximum(cwr_arr - peff_arr, 0.0)

    forecasts["iwr"] = pd.Series(iwr_arr, index=future_dates, name="iwr")
    logger.info(
        f"[forecast] IWR (=max(CWR-Peff,0)): mean={float(np.mean(iwr_arr)):.3f} mm/day, "
        f"Peff_mean={float(np.mean(peff_arr)):.3f} mm/day"
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
    forecast mean.  Preserves within-field spatial variability while
    applying the modelled temporal change.
    """
    try:
        with rasterio.open(template_raster) as src:
            template_data = src.read(1).astype(np.float64)
            nodata        = src.nodata if src.nodata is not None else NODATA
            template_data = np.where(template_data == nodata, np.nan, template_data)
            profile       = src.profile.copy()

        n_days          = WINDOW_DAYS[window]
        window_forecast = forecast_series.iloc[:n_days]
        forecast_mean   = float(window_forecast.mean())

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
            units = "mm_per_day" if param in ["cwr", "iwr", "pet"] else ""
            dst.update_tags(
                parameter=param,
                slot=slot,
                forecast_window=window,
                reference_date=slot,
                forecast_mean=str(round(forecast_mean, 4)),
                template_mean=str(round(template_mean, 4)),
                units=units,
                model="SAVI-SARIMAX+PET-SARIMAX+Physics-CWR/IWR",
                generated_by="irrigation_monitoring_v10.0",
            )

        logger.info(
            f"Created {param} forecast for {slot} {window}: "
            f"mean={forecast_mean:.4f}"
        )
        return True

    except Exception as e:
        logger.error(f"Failed to create {param} forecast for {slot}_{window}: {e}")
        return False


def generate_all_forecast_rasters() -> int:
    """
    Generate all forecast rasters (4 params × 12 slots × 3 windows):
      savi, kc, cwr, iwr  ×  today/1..11  ×  5day/10day/15day
    using the v10.0 SAVI-SARIMAX + PET-SARIMAX + physics CWR/IWR pipeline.
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
        for param in FORECAST_PARAMS:     # savi, kc, cwr, iwr
            if param not in forecasts:
                continue
            for window in FORECAST_WINDOWS:
                dst_path = forecast_path(param, slot, window)

                if dst_path.exists():
                    try:
                        with rasterio.open(dst_path) as f:
                            tags = f.tags()
                            if tags.get("reference_date") == slot:
                                n_rasters += 1
                                total += 1
                                continue
                    except Exception:
                        pass

                template = history_path(param, slot)
                if template.exists():
                    if create_forecast_raster(
                        param, slot, window, forecasts[param], template
                    ):
                        n_rasters += 1
                        total += 1

        logger.info(f"[forecast] slot={slot} ({date.date()}): {n_rasters} files")

    expected_total = len(dates) * len(FORECAST_PARAMS) * len(FORECAST_WINDOWS)
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

    # History layers: savi, kc, cwr, iwr
    for param in ["savi", "kc", "cwr", "iwr"]:
        for slot in SLOTS:
            p = history_path(param, slot)
            if not p.exists():
                continue
            store = f"{param}_{slot}"
            layer = store
            try:
                gs.create_coverage_store_if_not_exists(store, p)
                gs.update_coverage_store_file(store, p)
                gs.configure_layer(layer_name=layer, store_name=store)
                gs.assign_style(layer, f"{param}_style")
                logger.info(f"[geoserver] ✅ Layer ready: {layer}")
            except Exception as e:
                logger.warning(f"[geoserver] {store}: {e}")

    # Forecast layers: savi, kc, cwr, iwr × all slots × all windows
    for param in FORECAST_PARAMS:
        for slot in SLOTS:
            for window in FORECAST_WINDOWS:
                p = forecast_path(param, slot, window)
                if not p.exists():
                    continue
                store = f"{param}_{slot}_{window}"
                layer = store
                try:
                    gs.create_coverage_store_if_not_exists(store, p)
                    gs.update_coverage_store_file(store, p)
                    gs.configure_layer(layer_name=layer, store_name=store)
                    gs.assign_style(layer, f"{param}_style")
                    logger.info(f"[geoserver] ✅ Forecast layer ready: {layer}")
                except Exception as e:
                    logger.warning(f"[geoserver] {store}: {e}")


# ═══════════════════════════════════════════════════════════════════════════
# MASTER PIPELINE
# ═══════════════════════════════════════════════════════════════════════════

def run_pipeline() -> Dict:
    """
    Full pipeline run:
      A. History rasters
      B. Forecast generation (SAVI SARIMAX + PET SARIMAX → physics Kc/CWR/IWR)
      C. Forecast rasters
      D. GeoServer push
    """
    logger.info("═" * 65)
    logger.info("run_pipeline() START — v10.0")
    logger.info("Chain: SAVI(SARIMAX)→Kc + PET(SARIMAX) → CWR=Kc×PET → IWR=max(CWR-Peff,0)")
    logger.info("═" * 65)

    cleanup_old_rasters()
    _get_wheat_mask()

    logger.info("── A: History rasters ──")
    h_total = generate_history_rasters()
    logger.info(f"── A done: {h_total}/{HISTORY_DATES * len(PARAMS)} ──")

    logger.info("── B/C: Forecast + rasters ──")
    _get_model("savi")   # warm-up cache
    _get_model("pet")    # warm-up cache
    f_total = generate_all_forecast_rasters()
    expected = HISTORY_DATES * len(FORECAST_PARAMS) * len(FORECAST_WINDOWS)
    logger.info(f"── B/C done: {f_total}/{expected} ──")

    logger.info("── D: GeoServer ──")
    push_to_geoserver()

    dates   = _latest_n_complete_dates()
    summary = {
        "slots":              {slot_for_index(i): str(d.date()) for i, d in enumerate(dates)},
        "history_rasters":    h_total,
        "forecast_rasters":   f_total,
        "grand_total":        h_total + f_total,
        "units":              "mm_per_day",
        "forecast_model":     "SAVI-SARIMAX + PET-SARIMAX + Physics Kc/CWR/IWR",
        "physical_relationships": {
            "savi_to_kc": f"Kc = {KC_SLOPE:.4f} × SAVI + {KC_INTERCEPT:.4f}",
            "cwr":        "CWR = Kc × PET_forecast  (FAO-56 Eq. 4)",
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
    version="10.0.0",
    description=(
        "v10.0 — Full SARIMAX forecast chain:\n\n"
        "  • SAVI forecasted with SARIMAX  (NEW — phenological trajectory)\n"
        "  • Kc = 1.2088×SAVI + 0.5375, clip [0.30, 1.15]  (thesis Eq.)\n"
        "  • PET forecasted with SARIMAX   (independent met variable)\n"
        "  • CWR = Kc × PET_forecast  (FAO-56 Eq. 4, physics)\n"
        "  • IWR = max(CWR − Peff, 0)  (FAO-56 §4.5, physics)\n\n"
        "Output windows: today | 5-day | 10-day | 15-day\n"
        "No circular dependencies anywhere in the chain."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(graph_router)


from config import STUDY_AREA, EXACT_BOUNDARY

@app.get("/api/boundary")
async def get_boundary():
    """
    Return the study-area boundary for Udham Singh Nagar.
    Used by MapView to fit the Leaflet map bounds.
    """
    bounds = EXACT_BOUNDARY.get("bounds") or STUDY_AREA.get("bounds")

    if not bounds or not all(k in bounds for k in ("north", "south", "east", "west")):
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

    if north < south:
        north, south = south, north
    if east < west:
        east, west = west, east

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


def _maintenance_middleware_factory(app_instance):
    from fastapi import Request
    from fastapi.responses import JSONResponse

    @app_instance.middleware("http")
    async def _maintenance_gate(request: Request, call_next):
        try:
            from scheduler import MAINTENANCE_MODE as _mm
        except ImportError:
            _mm = False
        if _mm and request.url.path not in ("/health", "/"):
            return JSONResponse(
                status_code=503,
                content={
                    "detail": "System is updating data. Please retry in a few minutes.",
                    "maintenance": True,
                },
            )
        return await call_next(request)

    return app_instance


_maintenance_middleware_factory(app)


# ── Endpoints ──────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {
        "status":  "ok",
        "version": "10.0.0",
        "model":   "SAVI-SARIMAX + PET-SARIMAX + Physics Kc/CWR/IWR",
    }


@app.get("/api/forecast")
async def get_forecast(
    date: str = Query(..., description="Reference date YYYY-MM-DD (use latest Sentinel date for today)"),
    days: int  = Query(15,  ge=1, le=30, description="Forecast horizon (days)"),
):
    """
    Generate structured forecast output for dashboard visualization.

    Returns:
      - today:     observed means from latest Sentinel history rasters
      - 5day:      window mean + total for days 1–5
      - 10day:     window mean + total for days 1–10
      - 15day:     window mean + total for days 1–15
      - series:    full daily time series (dates + values per variable)

    Forecast chain:
      SAVI(SARIMAX) → Kc = 1.2088×SAVI+0.5375
      PET(SARIMAX)  → CWR = Kc×PET → IWR = max(CWR−Peff, 0)
    """
    try:
        ref_date = datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date — use YYYY-MM-DD")

    forecasts = generate_forecast_for_date(ref_date, days)
    if not forecasts:
        raise HTTPException(status_code=500, detail="Failed to generate forecast")

    # ── Today: read observed means from latest history rasters ────────────
    # PET is not stored as a processed raster (it is INSAT input), so read
    # from the PET model's last_pet metadata.
    _, pet_meta  = _get_model("pet")
    _, savi_meta = _get_model("savi")

    today_section = {
        "savi": _read_mean(history_path("savi", "today")),
        "kc":   _read_mean(history_path("kc",   "today")),
        "pet":  round(float(pet_meta.get("last_pet", 0.0)), 4) if pet_meta else None,
        "cwr":  _read_mean(history_path("cwr",  "today")),
        "iwr":  _read_mean(history_path("iwr",  "today")),
    }

    # ── Full daily time series for chart rendering ─────────────────────────
    series_section: Dict = {}
    all_params = ("savi", "kc", "pet", "cwr", "iwr")
    for param in all_params:
        if param in forecasts:
            s = forecasts[param]
            series_section[param] = {
                "dates":  [d.strftime("%Y-%m-%d") for d in s.index],
                "values": [round(float(v), 4) for v in s.values],
                "units":  "mm_per_day" if param in ("pet", "cwr", "iwr") else "dimensionless",
                "mean":   round(float(s.mean()), 4),
                "min":    round(float(s.min()),  4),
                "max":    round(float(s.max()),  4),
            }

    # ── Window summaries for 5/10/15 day horizons ─────────────────────────
    window_summaries: Dict = {}
    for window in FORECAST_WINDOWS:
        n = WINDOW_DAYS[window]
        window_summaries[window] = {}
        for param in all_params:
            if param in forecasts:
                vals = forecasts[param].iloc[:n].values
                window_summaries[window][param] = {
                    "mean":  round(float(np.mean(vals)), 4),
                    "total": round(float(np.sum(vals)),  4),
                    "min":   round(float(np.min(vals)),  4),
                    "max":   round(float(np.max(vals)),  4),
                    "units": "mm_per_day" if param in ("pet", "cwr", "iwr") else "dimensionless",
                }

    return {
        "reference_date":  date,
        "forecast_days":   days,
        "version":         "v10.0",
        "model":           "SAVI-SARIMAX + PET-SARIMAX + Physics Kc/CWR/IWR",
        "forecast_chain":  (
            "SAVI(SARIMAX) → Kc=1.2088×SAVI+0.5375 "
            "| PET(SARIMAX) → CWR=Kc×PET → IWR=max(CWR-Peff,0)"
        ),
        "today":           today_section,
        "5day":            window_summaries.get("5day",  {}),
        "10day":           window_summaries.get("10day", {}),
        "15day":           window_summaries.get("15day", {}),
        "series":          series_section,
    }


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
        "model":   "SAVI-SARIMAX + PET-SARIMAX + Physics Kc/CWR/IWR",
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

        # Forecast available for all FORECAST_PARAMS
        if param in FORECAST_PARAMS:
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
    """Return metadata for all loaded models."""
    savi_model, savi_meta = _get_model("savi")
    pet_model,  pet_meta  = _get_model("pet")

    def _meta_dict(model, meta):
        if meta is None:
            return {"available": False}
        return {
            "available":          model is not None,
            "note":               meta.get("note", ""),
            "test_r2":            meta["metrics"].get("R2"),
            "test_rmse":          meta["metrics"].get("RMSE"),
            "test_mae":           meta["metrics"].get("MAE"),
            "order":              meta.get("order"),
            "exog_cols":          meta.get("exog_cols"),
            "last_training_date": (
                meta["last_date"].strftime("%Y-%m-%d")
                if meta.get("last_date") else None
            ),
        }

    return {
        "version": "v10.0",
        "models": {
            "savi": _meta_dict(savi_model, savi_meta),
            "pet":  _meta_dict(pet_model,  pet_meta),
        },
        "forecast_chain": {
            "step1": "SAVI forecasted with SARIMAX  (NEW v10.0)",
            "step2": f"Kc = {KC_SLOPE:.4f} × SAVI_forecast + {KC_INTERCEPT:.4f}  (clip [{KC_MIN}, {KC_MAX}])",
            "step3": "PET forecasted with SARIMAX   (independent of SAVI)",
            "step4": "CWR = Kc × PET_forecast  (FAO-56 Eq. 4)",
            "step5": "IWR = max(CWR − Peff_clim, 0)  (FAO-56 §4.5)",
        },
        "physical_relationships": {
            "savi_to_kc": f"Kc = {KC_SLOPE:.4f} × SAVI + {KC_INTERCEPT:.4f}",
            "cwr":        "CWR = Kc × PET  (physics — not forecasted)",
            "iwr":        "IWR = max(CWR − Peff, 0)  (physics — not forecasted)",
            "peff":       "USDA-SCS on 5-day interval rainfall total",
        },
        "no_circular_dependencies": True,
    }


# ═══════════════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════

def main():
    setup_logging()
    logger.info("=" * 65)
    logger.info("Irrigation Monitoring System v10.0 starting …")
    logger.info("Chain: SAVI(SARIMAX)→Kc + PET(SARIMAX) → CWR=Kc×PET → IWR=max(CWR-Peff,0)")
    logger.info("=" * 65)

    _get_wheat_mask()

    savi_model, savi_meta = _get_model("savi")
    if savi_model:
        logger.info(f"✓ SAVI model ready (R²={savi_meta['metrics']['R2']:.4f})")
    else:
        logger.error("✗ Failed to initialise SAVI model")

    pet_model, pet_meta = _get_model("pet")
    if pet_model:
        logger.info(f"✓ PET model ready  (R²={pet_meta['metrics']['R2']:.4f})")
    else:
        logger.error("✗ Failed to initialise PET model")

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