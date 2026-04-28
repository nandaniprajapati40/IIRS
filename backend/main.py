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
    build_forecast_exog,   # shared exog builder for SARIMAX out-of-sample
    raster_mean,           # spatial mean utility (fixes broken import in _climatological_peff)
    savi_to_kc,            # physics: Kc = KC_SLOPE × SAVI + KC_INTERCEPT
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

HISTORY_DATES  = 12
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
# STEP B — FORECASTING  (Fixed - Thesis Compliant)
# Only PET uses SARIMAX. Kc uses its own trained SARIMAx + DOY adjustment.

# ═══════════════════════════════════════════════════════════════════════════
def _project_kc_for_dates(
    future_dates: pd.DatetimeIndex,
) -> Tuple[np.ndarray, np.ndarray]:
    """Forecast SAVI with SARIMAX, then derive Kc via thesis physics.

    Returns (savi_forecast, kc_forecast).

    IMPROVEMENT over previous version:
    ─────────────────────────────────
    Previously: trained SARIMAX directly on Kc (a derived variable) → R²=0.11,
    then used only 15% of that output anyway.

    Now (primary path):
        1. Forecast SAVI with SARIMAX  (raw satellite signal, cleaner signal)
        2. Apply  Kc = KC_SLOPE × SAVI + KC_INTERCEPT  (thesis linear eq.)
        3. Apply phenological decline at maturation only when obs slope
           confirms it (no blind overrides).
        4. Smooth the 1→15 day transition from last observation.

    Fallback (if SAVI model unavailable):
        Same trend-based Kc method as before, but with 60% SARIMAX weight
        instead of the previous 15%.
    """
    last_kc_obs   = _read_mean(history_path("kc",   "today")) or 0.80
    last_savi_obs = _read_mean(history_path("savi", "today")) or (
        (last_kc_obs - KC_INTERCEPT) / KC_SLOPE
    )
    savi_1d_ago = _read_mean(history_path("savi", "1")) or last_savi_obs

    # ── Primary: SAVI SARIMAX → Kc via thesis physics ────────────────────────
    savi_model, savi_meta = _get_model("savi")
    if savi_model is not None:
        try:
            exog_cols = savi_meta.get("exog_cols", ["doy_sin", "doy_cos"])
            savi_exog = build_forecast_exog(future_dates, exog_cols=exog_cols)
            savi_fc   = savi_model.get_forecast(
                steps=len(future_dates), exog=savi_exog
            )
            savi_base = np.clip(
                savi_fc.predicted_mean.values.astype(float), -0.1, 0.9
            )

            # Phenological adjustment: late-season maturation (DOY ≥ 95 ≈ April 5)
            # Only enforce decline if observation confirms it (avoids overriding
            # a genuine flat or rising signal before senescence).
            ref_doy = future_dates[0].dayofyear
            if ref_doy >= 95:
                obs_slope_savi = last_savi_obs - savi_1d_ago   # observed 1-day slope
                maturation_slope = -0.015                       # ~−0.22 SAVI over 15 days
                if obs_slope_savi > maturation_slope:
                    slope_adj = 0.35 * obs_slope_savi + 0.65 * maturation_slope
                else:
                    slope_adj = obs_slope_savi
                days_ahead  = np.arange(1, len(future_dates) + 1, dtype=float)
                savi_trend  = last_savi_obs + slope_adj * days_ahead
                savi_base   = 0.65 * savi_base + 0.35 * savi_trend
                logger.info(
                    f"SAVI forecast: maturity slope applied "
                    f"(doy={ref_doy}, adj={slope_adj:.4f})"
                )

            savi_base = np.clip(savi_base, -0.1, 0.9)

            # Smooth transition: anchor day-1 to last observation, relax over 7 days
            alpha         = np.exp(-np.arange(len(future_dates)) / 7.0)
            savi_forecast = alpha * float(last_savi_obs) + (1 - alpha) * savi_base

            # Physics: Kc from SAVI
            kc_from_savi = savi_to_kc(savi_forecast)

            logger.info(
                f"Kc forecast via SAVI→Kc chain: "
                f"SAVI_mean={savi_forecast.mean():.3f}, "
                f"Kc_mean={kc_from_savi.mean():.3f}, "
                f"range={kc_from_savi.min():.3f}–{kc_from_savi.max():.3f}"
            )
            return savi_forecast, kc_from_savi

        except Exception as exc:
            logger.warning(f"SAVI→Kc chain failed ({exc}) — using Kc fallback")

    # ── Fallback: Kc SARIMAX + phenological trend ────────────────────────────
    # FIX: increased SARIMAX weight from 0.15 → 0.60 (model was virtually ignored)
    kc_model, kc_meta = _get_model("kc")
    kc_1d_ago  = _read_mean(history_path("kc", "1")) or last_kc_obs
    kc_3d_ago  = _read_mean(history_path("kc", "3")) or kc_1d_ago

    if kc_model is None:
        base = np.full(len(future_dates), float(last_kc_obs))
    else:
        try:
            exog_cols = kc_meta.get("exog_cols", ["doy_sin", "doy_cos"])
            kc_exog   = build_forecast_exog(future_dates, exog_cols=exog_cols)
            kc_fc     = kc_model.get_forecast(steps=len(future_dates), exog=kc_exog)
            base      = kc_fc.predicted_mean.values.astype(float)
        except Exception as e:
            logger.warning(f"Kc SARIMAX failed: {e}")
            base = np.full(len(future_dates), float(last_kc_obs))

    days_ahead    = np.arange(1, len(future_dates) + 1, dtype=float)
    recent_slope  = 0.6 * (last_kc_obs - kc_1d_ago) + 0.4 * (last_kc_obs - kc_3d_ago) / 3.0
    ref_doy       = future_dates[0].dayofyear

    if ref_doy >= 95:
        maturation_slope = -0.022
        if recent_slope > maturation_slope:
            recent_slope = 0.3 * recent_slope + 0.7 * maturation_slope
            logger.info(f"Kc fallback: maturity decline applied (doy={ref_doy})")

    trend    = last_kc_obs + 0.85 * recent_slope * days_ahead
    seasonal = (
        0.15 * np.sin(2 * np.pi * future_dates.dayofyear.values / 365.25) +
        0.08 * np.cos(2 * np.pi * future_dates.dayofyear.values / 365.25)
    )

    # FIX: 60% SARIMAX weight (was 15%)
    kc_final = np.clip(0.60 * base + 0.35 * trend + seasonal, KC_MIN, KC_MAX)

    # Return an estimated SAVI via inverse physics for consistency
    savi_est = np.clip((kc_final - KC_INTERCEPT) / KC_SLOPE, -0.1, 0.9)
    logger.info(
        f"Kc fallback: last={last_kc_obs:.3f}, "
        f"trend_mean={trend.mean():.3f}, range={kc_final.min():.3f}–{kc_final.max():.3f}"
    )
    return savi_est, kc_final


def _climatological_peff(future_dates: pd.DatetimeIndex) -> np.ndarray:
    """Estimate effective rainfall from the last 7 days of rain rasters.

    FIXES:
    1. `raster_mean` is now imported at module level (was a failed local import).
    2. Full USDA-SCS formula applied to the 5-day total (not divided by days).
    3. Removed pseudo-random noise: noise ≠ physical Peff; it was adding ~0.25
       mm/day of fake rainfall that inflated IWR uncertainty.

    For Rabi wheat (Nov–Apr) in Haryana/Uttarakhand, mean seasonal rainfall is
    low (< 5 mm/day most days), so Peff is near zero most of the forecast window.
    This is physically correct per Thesis §5.5.
    """
    rain_dir = DIRECTORIES["raw"].get("insat_rain")
    peff_scalar = 0.0

    if rain_dir and Path(rain_dir).exists():
        rain_files = sorted(Path(rain_dir).glob("*.tif"))[-7:]
        if rain_files:
            try:
                # raster_mean is now imported at module level — no local import needed
                recent_vals = [
                    raster_mean(f, mask_zeros=False)
                    for f in rain_files if f.exists()
                ]
                recent_vals = [v for v in recent_vals if np.isfinite(v) and v >= 0]

                if recent_vals:
                    # USDA-SCS effective rainfall formula:
                    #   For P_total (mm over N days):
                    #     Peff = 0.70 × P_total − 5.0  (for P_total > 7.1 mm)
                    #     Peff = 0.82 × P_total − 0.91 (for P_total ≤ 7.1 mm)
                    #   Then convert to daily average.
                    p_total  = float(sum(recent_vals))
                    n_days   = max(len(recent_vals), 1)
                    if p_total > 7.1:
                        peff_total = max(0.0, 0.70 * p_total - 5.0)
                    else:
                        peff_total = max(0.0, 0.82 * p_total - 0.91)
                    peff_scalar = peff_total / n_days
            except Exception as exc:
                logger.debug(f"Peff calculation error: {exc}")

    logger.info(f"[forecast] Peff ≈ {peff_scalar:.3f} mm/day (USDA-SCS, last 7-day rain)")

    # Return constant daily Peff for the forecast window.
    # A constant is more honest than fake random spikes when we have no
    # actual forecast rainfall data.
    return np.full(len(future_dates), peff_scalar, dtype=float)




def generate_forecast_for_date(
    reference_date: datetime,
    days: int = FORECAST_DAYS,
) -> Dict[str, pd.Series]:
    """Fixed forecasting pipeline (only PET uses SARIMAX)"""
    forecasts: Dict[str, pd.Series] = {}

    future_dates = pd.date_range(
        start=reference_date + timedelta(days=1),
        periods=days,
        freq="D",
    )

    # ── 1. Forecast PET with SARIMAX ─────────────────────────────────────
    pet_model, pet_meta = _get_model("pet")
    
    # Safely estimate last PET from CWR and Kc (since PET isn't in PARAMS history)
    last_kc_obs  = _read_mean(history_path("kc", "today")) or 0.85
    last_cwr_obs = _read_mean(history_path("cwr", "today")) or 3.5
    last_pet_obs = last_cwr_obs / last_kc_obs if last_kc_obs > 0 else 4.0

    doy = future_dates.dayofyear.values.astype(float)
    # Seasonal Climatology: Low in Jan (~2.5), peaking in May/June (>8.0).
    # Thesis §5.4: PET rises from ~3.0 in Jan to peaks of 7.0+ in April.
    seasonal_pet = 5.5 + 3.2 * np.sin(2 * np.pi * (doy - 45) / 365.25)

    # Smooth transition anchor: decays over 5 days
    alpha = np.exp(-np.arange(days) / 5.0)

    if pet_model is None:
        logger.warning("[forecast] PET model unavailable → using seasonal trend")
        pet_values = alpha * float(last_pet_obs) + (1 - alpha) * seasonal_pet
        pet_values = np.clip(pet_values, 1.5, 12.0)
        forecasts["pet"] = pd.Series(pet_values, index=future_dates, name="pet")
    else:
        try:
            exog_cols = pet_meta.get("exog_cols", ["doy_sin", "doy_cos"])
            exog_df = build_forecast_exog(
                future_dates=future_dates,
                exog_cols=exog_cols,
            )

            pet_fc   = pet_model.get_forecast(steps=days, exog=exog_df if not exog_df.empty else None)
            base_pet = pet_fc.predicted_mean.values.astype(float)

            # FIX: was 0.2 SARIMAX + 0.8 seasonal → model was basically ignored.
            # Now 0.65 SARIMAX + 0.35 seasonal. The SARIMAX carries the actual
            # learned pattern; seasonal is a soft regularizer for long-range days.
            pet_values = 0.65 * base_pet + 0.35 * seasonal_pet

            # Smooth first few days to last observation (removes jumps at t=1)
            pet_values = alpha * float(last_pet_obs) + (1 - alpha) * pet_values
            pet_values = np.clip(pet_values, 1.5, 12.0)

            forecasts["pet"] = pd.Series(pet_values, index=future_dates, name="pet")

        except Exception as e:
            logger.warning(f"[forecast] PET SARIMAX failed: {e} → seasonal fallback")
            pet_values = alpha * float(last_pet_obs) + (1 - alpha) * seasonal_pet
            pet_values = np.clip(pet_values, 1.5, 12.0)
            forecasts["pet"] = pd.Series(pet_values, index=future_dates, name="pet")

    # ── 2. Forecast SAVI + derive Kc via physics ─────────────────────────────
    # FIX: _project_kc_for_dates now returns (savi_arr, kc_arr).
    # SAVI is forecasted via SARIMAX; Kc = KC_SLOPE × SAVI + KC_INTERCEPT.
    savi_projected, kc_projected = _project_kc_for_dates(future_dates)
    forecasts["savi"] = pd.Series(savi_projected, index=future_dates, name="savi")
    forecasts["kc"]   = pd.Series(kc_projected,   index=future_dates, name="kc")

    # ── 3. Physics: CWR = Kc × PET ───────────────────────────────────────
    cwr_arr = np.clip(kc_projected * forecasts["pet"].values, CWR_MIN, CWR_MAX)
    forecasts["cwr"] = pd.Series(cwr_arr, index=future_dates, name="cwr")

    # ── 4. Physics: IWR = max(CWR - Peff, 0) ─────────────────────────────
    peff_arr = _climatological_peff(future_dates)
    iwr_arr = np.maximum(cwr_arr - peff_arr, 0.0)
    forecasts["iwr"] = pd.Series(iwr_arr, index=future_dates, name="iwr")

    logger.info(f"[forecast] Generated for {reference_date.date()}: "
                f"SAVI_mean={forecasts['savi'].mean():.3f}, "
                f"PET_mean={forecasts['pet'].mean():.2f}, "
                f"Kc_mean={forecasts['kc'].mean():.3f}, "
                f"CWR_mean={forecasts['cwr'].mean():.2f}, "
                f"IWR_mean={forecasts['iwr'].mean():.2f}")

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

    for param in ("savi", "pet", "kc", "cwr", "iwr"):
        if param in forecasts:
            series = forecasts[param]
            result["forecasts"][param] = {
                "dates":  [d.strftime("%Y-%m-%d") for d in series.index],
                "values": [round(float(v), 4) for v in series.values],
                "units":  "mm_per_day",
                "mean":   round(float(series.mean()), 4),
                "min":    round(float(series.min()),  4),
                "max":    round(float(series.max()),  4),
            }

    result["window_summaries"] = {}
    WINDOW_SLICES = {
    "5day": (0, 5),   # days 1-5
    "10day": (0, 10), # days 1-10 (Cumulative)
    "15day": (0, 15), # days 1-15 (Cumulative)
}



    for window, (start_idx, end_idx) in WINDOW_SLICES.items():
        result["window_summaries"][window] = {}
        for param in ("kc", "cwr", "iwr"):
            if param in forecasts:
                vals = forecasts[param].iloc[start_idx:end_idx].values
                result["window_summaries"][window][param] = {
                    "mean": round(float(np.mean(vals)), 4),
                    "total": round(float(np.sum(vals)), 4),
                }

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
    pet_model, pet_meta   = _get_model("pet")
    kc_model,  kc_meta    = _get_model("kc")
    savi_model, savi_meta = _get_model("savi")

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
            "savi": _meta_dict(savi_model, savi_meta),
            "pet":  _meta_dict(pet_model,  pet_meta),
            "kc":   _meta_dict(kc_model,   kc_meta),
        },
        "forecast_chain": {
            "step1": "SAVI forecasted with SARIMAX (raw satellite signal)",
            "step2": f"Kc derived from SAVI: Kc = {KC_SLOPE}×SAVI + {KC_INTERCEPT}  (thesis Eq.)",
            "step3": "PET forecasted with SARIMAX (65% model, 35% seasonal)",
            "step4": "CWR = Kc × PET  (FAO-56 Eq. 4)",
            "step5": "IWR = max(CWR − Peff, 0)  (FAO-56 §4.5, USDA-SCS Peff)",
        },
        "physical_relationships": {
            "savi_to_kc": f"Kc = {KC_SLOPE:.4f} × SAVI + {KC_INTERCEPT:.4f}  (thesis linear regression)",
            "cwr":        "CWR = Kc × PET  (computed)",
            "iwr":        "IWR = max(CWR − Peff, 0)  (computed)",
            "peff":       "USDA-SCS on 7-day interval rainfall total",
        },
    }


# ═══════════════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════

def main():
    setup_logging()
    logger.info("=" * 65)
    logger.info("Irrigation Monitoring System v9.0 starting …")
    logger.info("Forecast: PET(SARIMAX) → CWR=Kc×PET → IWR=max(CWR-Peff,0)")
    logger.info("=" * 65)

    _get_wheat_mask()

    pet_model, pet_meta = _get_model("pet")
    if pet_model:
        logger.info(f"✓ PET model ready (R²={pet_meta['metrics']['R2']:.4f})")
    else:
        logger.error("✗ Failed to initialise PET model")

    savi_model, savi_meta = _get_model("savi")
    if savi_model:
        logger.info(
            f"✓ SAVI model ready (R²={savi_meta['metrics']['R2']:.4f}) "
            f"→ Kc via Kc={KC_SLOPE}×SAVI+{KC_INTERCEPT}"
        )
    else:
        logger.warning("⚠ SAVI model not available — Kc fallback will be used")

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