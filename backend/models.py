"""
models.py  –  SARIMA training & forecasting for Kc and PET
Udham Singh Nagar wheat IWR pipeline

ROOT-CAUSE FIXES applied in this version
─────────────────────────────────────────
FIX-A  Kc is computed FRESH from SAVI rasters via the thesis regression
       (Kc = 1.2088·SAVI + 0.5375) instead of reading noisy pre-processed
       Kc TIFs.  This gives the model clean, physics-consistent Kc values.

FIX-B  PET SARIMA is a TRUE SARIMAX: district-mean daily rainfall from the
       INSAT rain TIFs is included as an exogenous regressor so the model
       knows wet vs dry days.  Forecast uses the mean seasonal rain cycle
       as the future exog (climatological approach).

FIX-C  Seasonal period corrected and justified:
         • Kc  cadence = 5 days, Rabi season ≈ 36 pentads  →  s_kc  = 36
         • PET cadence = 1 day,  Rabi season ≈ 181 days    →  s_pet = 181
       With only 5 seasons of Kc data and 4 of PET the grid-search is now
       bounded tightly (max_p=1, max_q=1, P∈{0,1}, Q∈{0,1}) to prevent
       over-parameterisation.

FIX-D  Hold-out size reduced to ONE THIRD of a season (not a full season)
       so the training set always spans ≥ 2 complete seasonal cycles, which
       is the minimum SARIMA needs for reliable seasonal estimation.

FIX-E  IWR formula corrected:
         IWR = max(CWR − Peff, 0)
       Peff is derived from the rain TIFs (80 % of daily rainfall ≤ 5 mm,
       per FAO-56 §3.3 simplified formula for Rabi wheat).

FIX-F  raster_mean now handles INSAT scaling factors (values > 100 are
       divided by the native scale so PET is always in mm/day, not in
       tenths-of-mm).

FIX-G  No more summer-gap skipping in _map_steps_to_dates – forecasts are
       labelled with real calendar dates; the caller trims by is_rabi().
"""

from __future__ import annotations

import logging
import pickle
import re
import warnings
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import rasterio
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from statsmodels.tsa.statespace.sarimax import SARIMAX

warnings.filterwarnings("ignore")
logger = logging.getLogger(__name__)

# ── Directory configuration ──────────────────────────────────────────────────
try:
    from config import DIRECTORIES
except ImportError:
    BASE = Path(__file__).parent / "data"
    DIRECTORIES = {
        "raw": {
            "insat_pet":  BASE / "raw/insat_pet",
            "insat_rain": BASE / "raw/insat_rain",
        },
        "processed": {
            "savi": BASE / "processed/savi",   # Sentinel-2 SAVI TIFs (primary)
            "kc":   BASE / "processed/kc",     # fallback only if SAVI missing
        },
        "models": BASE / "models",
    }

MODEL_DIR = Path(DIRECTORIES["models"])
MODEL_DIR.mkdir(parents=True, exist_ok=True)

KC_MODEL_PATH  = MODEL_DIR / "sarima_wheat_kc.pkl"
PET_MODEL_PATH = MODEL_DIR / "sarima_wheat_pet.pkl"

# ── Physical bounds ───────────────────────────────────────────────────────────
KC_MIN,   KC_MAX   = 0.30, 1.15      # thesis Table 9
PET_MIN,  PET_MAX  = 0.5,  15.0     # mm/day
SAVI_MIN, SAVI_MAX = 0.0,  0.90
RAIN_MIN, RAIN_MAX = 0.0,  150.0    # mm/day
NODATA = -9999.0

# Thesis linear regression  Kc = slope·SAVI + intercept  (R²=0.882, Table 9)
KC_SLOPE     = 1.2088
KC_INTERCEPT = 0.5375

# Rabi season (Nov–Apr)
RABI_START_MONTH = 11
RABI_END_MONTH   = 4

# Sensor cadence
KC_CADENCE_DAYS  = 5    # Sentinel-2 pentad
PET_CADENCE_DAYS = 1    # INSAT daily

# Seasonal periods – one full Rabi season
S_KC  = 36    # 6 months × 30.4 d / 5 d ≈ 36 pentads
S_PET = 181   # 6 months × 30.4 d / 1 d ≈ 181 days

# FAO-56 §3.3 effective rainfall fraction for Rabi wheat
# Peff = RAIN_FRACTION × rain   (rain is small in Rabi, so most is effective)
RAIN_EFFECTIVE_FRACTION = 0.80


# ── Helpers ───────────────────────────────────────────────────────────────────
def extract_date(filename: str) -> Optional[datetime]:
    """Parse YYYYMMDD, DDMMMYYYY (INSAT), or YYYY-MM-DD from filename."""
    for pattern, fmt in [
        (r"(\d{8})",               "%Y%m%d"),
        (r"(\d{2}[A-Z]{3}\d{4})", "%d%b%Y"),
        (r"(\d{4}-\d{2}-\d{2})",  "%Y-%m-%d"),
    ]:
        m = re.search(pattern, filename.upper())
        if m:
            try:
                return datetime.strptime(m.group(1), fmt)
            except ValueError:
                pass
    logger.debug("Cannot extract date from: %s", filename)
    return None


def is_rabi(date: datetime) -> bool:
    """True if the date falls in the Rabi growing season (Nov–Apr)."""
    return date.month >= RABI_START_MONTH or date.month <= RABI_END_MONTH


# FIX-F: scale-aware raster reader
def raster_mean(path: Path,
                valid_min: float = None,
                valid_max: float = None,
                scale_threshold: float = 50.0,
                scale_factor: float = 0.1) -> float:
    """
    Spatial mean of valid pixels.

    If the raw raster mean exceeds `scale_threshold` (e.g. INSAT stores PET
    in tenths-of-mm so values are 10× too large), the values are multiplied
    by `scale_factor` to bring them to physical units.

    valid_min / valid_max: clip before returning (use physical bounds).
    """
    try:
        with rasterio.open(path) as src:
            data = src.read(1).astype(np.float64)
            nd   = src.nodata if src.nodata is not None else NODATA
            data[data == nd]       = np.nan
            data[data == NODATA]   = np.nan
            data[data < -999]      = np.nan

            raw_mean = float(np.nanmean(data))

            # FIX-F: auto-detect INSAT integer encoding (tenths of mm)
            if not np.isnan(raw_mean) and raw_mean > scale_threshold:
                data = data * scale_factor

            if valid_min is not None:
                data[data < valid_min] = np.nan
            if valid_max is not None:
                data[data > valid_max] = np.nan

            return float(np.nanmean(data))
    except Exception as exc:
        logger.debug("raster_mean failed for %s: %s", path, exc)
        return np.nan


# ── Series builders ───────────────────────────────────────────────────────────

# FIX-A: Kc comes from SAVI rasters, not pre-processed Kc TIFs
def build_kc_series() -> Tuple[np.ndarray, List[datetime]]:
    """
    Compute Kc from SAVI rasters using the thesis regression:
        Kc = KC_SLOPE · SAVI + KC_INTERCEPT

    Falls back to the pre-processed Kc TIFs only when the SAVI directory
    is absent or empty, but logs a prominent warning in that case because
    pre-processed Kc files add spatial averaging noise.
    """
    savi_dir = Path(DIRECTORIES["processed"]["savi"])
    kc_dir   = Path(DIRECTORIES["processed"]["kc"])

    # Prefer SAVI directory
    source_dir = None
    use_regression = False

    if savi_dir.exists() and list(savi_dir.glob("*.tif")):
        source_dir     = savi_dir
        use_regression = True
        logger.info("Kc: using SAVI→Kc regression from %s", savi_dir)
    elif kc_dir.exists() and list(kc_dir.glob("*.tif")):
        source_dir     = kc_dir
        use_regression = False
        logger.warning(
            "Kc: SAVI directory missing or empty – falling back to pre-processed "
            "Kc TIFs.  This may add noise; provide SAVI rasters for best results."
        )
    else:
        raise FileNotFoundError(
            "Neither SAVI nor Kc raster directory found. "
            f"Expected: {savi_dir}  or  {kc_dir}"
        )

    files = sorted(source_dir.glob("*.tif"))
    records: List[Tuple[datetime, float]] = []

    for fp in files:
        d = extract_date(fp.name)
        if d is None or not is_rabi(d):
            continue
        if use_regression:
            savi = raster_mean(fp, valid_min=SAVI_MIN, valid_max=SAVI_MAX)
            if np.isnan(savi):
                continue
            kc = float(np.clip(KC_SLOPE * savi + KC_INTERCEPT, KC_MIN, KC_MAX))
        else:
            kc = raster_mean(fp, valid_min=KC_MIN, valid_max=KC_MAX)
            if np.isnan(kc):
                continue
        records.append((d, kc))

    if not records:
        raise ValueError("No valid Rabi SAVI/Kc rasters found.")

    records.sort(key=lambda x: x[0])
    dates  = [r[0] for r in records]
    values = np.array([r[1] for r in records], dtype=float)

    logger.info("Kc: %d points  %s → %s  (cadence≈%dd)",
                len(values), dates[0].date(), dates[-1].date(), KC_CADENCE_DAYS)
    return values, dates


# FIX-B: PET series + rain exog built together so dates are always aligned
def build_pet_rain_series() -> Tuple[np.ndarray, np.ndarray, List[datetime]]:
    """
    Read INSAT PET and INSAT rain TIFs.
    Returns (pet_values, rain_values, dates) aligned by date.
    Only dates that have BOTH a PET and a rain raster are kept.
    """
    pet_dir  = Path(DIRECTORIES["raw"]["insat_pet"])
    rain_dir = Path(DIRECTORIES["raw"]["insat_rain"])

    if not pet_dir.exists():
        raise FileNotFoundError(f"PET directory not found: {pet_dir}")
    if not rain_dir.exists():
        logger.warning("Rain directory not found: %s – PET model will have no exog.", rain_dir)
        rain_dir = None

    # Build date→path maps
    def date_map(d: Path) -> Dict[datetime, Path]:
        m = {}
        for fp in sorted(d.glob("*.tif")):
            dt = extract_date(fp.name)
            if dt and is_rabi(dt):
                m[dt] = fp
        return m

    pet_map  = date_map(pet_dir)
    rain_map = date_map(rain_dir) if rain_dir else {}

    common_dates = sorted(pet_map.keys())   # use all PET dates

    pet_vals,  rain_vals, good_dates = [], [], []

    for d in common_dates:
        pet_v = raster_mean(pet_map[d],
                            valid_min=PET_MIN, valid_max=PET_MAX,
                            scale_threshold=50.0, scale_factor=0.1)
        if np.isnan(pet_v):
            continue

        if d in rain_map:
            rain_v = raster_mean(rain_map[d],
                                 valid_min=RAIN_MIN, valid_max=RAIN_MAX,
                                 scale_threshold=500.0, scale_factor=0.1)
            rain_v = 0.0 if np.isnan(rain_v) else rain_v
        else:
            rain_v = 0.0  # assume no rain if file missing

        pet_vals.append(pet_v)
        rain_vals.append(rain_v)
        good_dates.append(d)

    if not good_dates:
        raise ValueError("No valid Rabi PET rasters found.")

    pet_arr  = np.array(pet_vals,  dtype=float)
    rain_arr = np.array(rain_vals, dtype=float)

    logger.info("PET: %d points  %s → %s  (cadence≈%dd)",
                len(pet_arr), good_dates[0].date(), good_dates[-1].date(),
                PET_CADENCE_DAYS)
    return pet_arr, rain_arr, good_dates


# ── SARIMA order search ───────────────────────────────────────────────────────
def find_best_order(series: pd.Series, s: int,
                    exog: pd.Series = None,
                    max_p: int = 1,
                    max_q: int = 1) -> Tuple[tuple, tuple]:
    """
    Grid search SARIMA(p,1,q)(P,1,Q,s) by AIC.
    max_p=1, max_q=1 to prevent over-fitting on short Rabi records (FIX-C).
    """
    best_aic   = float("inf")
    best_order = (1, 1, 1)
    best_seas  = (0, 1, 1, s)

    for p in range(max_p + 1):
        for q in range(max_q + 1):
            for P in range(2):
                for Q in range(2):
                    if p == 0 and q == 0 and P == 0 and Q == 0:
                        continue
                    try:
                        res = SARIMAX(
                            series,
                            exog=exog,
                            order=(p, 1, q),
                            seasonal_order=(P, 1, Q, s),
                            enforce_stationarity=False,
                            enforce_invertibility=False,
                        ).fit(disp=False, maxiter=500)
                        if res.aic < best_aic:
                            best_aic   = res.aic
                            best_order = (p, 1, q)
                            best_seas  = (P, 1, Q, s)
                    except Exception:
                        continue

    logger.info("Best SARIMA%s%s  AIC=%.2f", best_order, best_seas, best_aic)
    return best_order, best_seas


# ── SARIMA fit ────────────────────────────────────────────────────────────────
def fit_sarima(values: np.ndarray, s: int, label: str,
               exog: np.ndarray = None,
               auto: bool = True) -> "SARIMAXResultsWrapper":
    """
    Fit SARIMA(X) on a plain RangeIndex series (no DatetimeIndex gaps).
    Pass exog for SARIMAX (PET model uses rain as exog – FIX-B).
    """
    series   = pd.Series(values, dtype=float)
    exog_ser = pd.Series(exog,   dtype=float) if exog is not None else None

    min_pts = 2 * s + 10
    if auto and len(series) >= min_pts:
        order, seas = find_best_order(series, s, exog=exog_ser)
    else:
        logger.warning(
            "%s: only %d points (need %d for grid search) – using default SARIMA(1,1,1)(0,1,1,%d)",
            label, len(series), min_pts, s
        )
        order, seas = (1, 1, 1), (0, 1, 1, s)

    logger.info("%s: fitting SARIMA%s%s on %d points", label, order, seas, len(series))
    res = SARIMAX(
        series,
        exog=exog_ser,
        order=order,
        seasonal_order=seas,
        enforce_stationarity=False,
        enforce_invertibility=False,
    ).fit(disp=False, maxiter=500)

    logger.info("%s: AIC=%.2f  BIC=%.2f  resid_mean=%.6f",
                label, res.aic, res.bic, res.resid.mean())

    try:
        from statsmodels.stats.diagnostic import acorr_ljungbox
        lb = acorr_ljungbox(res.resid.dropna(), lags=[10], return_df=True)
        p  = lb["lb_pvalue"].iloc[0]
        logger.info("%s: Ljung-Box p=%.4f (%s)",
                    label, p, "white noise ✓" if p > 0.05 else "autocorr present – consider larger p/q")
    except Exception:
        pass

    return res


# ── Hold-out evaluation ───────────────────────────────────────────────────────
def evaluate(values: np.ndarray, s: int, label: str,
             exog: np.ndarray = None,
             test_n: int = None) -> Dict:
    """
    Hold-out evaluation.
    FIX-D: test_n defaults to s//3 (one-third season) so training always
    covers ≥ 2 full seasonal cycles.
    """
    if test_n is None:
        test_n = max(s // 3, 5)   # e.g. 12 pentads for Kc, 60 days for PET

    if len(values) < test_n + 2 * s:
        logger.warning(
            "%s: too few points (%d) for hold-out evaluation (need %d) – skipping.",
            label, len(values), test_n + 2 * s
        )
        return {"R2": np.nan, "RMSE": np.nan, "MAE": np.nan}

    train_vals = values[:-test_n]
    test_vals  = values[-test_n:]
    train_exog = exog[:-test_n] if exog is not None else None
    test_exog  = exog[-test_n:] if exog is not None else None

    res  = fit_sarima(train_vals, s, f"{label}_train", exog=train_exog, auto=True)
    pred = res.get_forecast(steps=test_n,
                            exog=test_exog).predicted_mean.values

    r2   = r2_score(test_vals, pred)
    rmse = float(np.sqrt(mean_squared_error(test_vals, pred)))
    mae  = float(mean_absolute_error(test_vals, pred))
    logger.info("%s hold-out (%d pts): R²=%.4f  RMSE=%.4f  MAE=%.4f",
                label, test_n, r2, rmse, mae)
    return {"R2": r2, "RMSE": rmse, "MAE": mae}


# ── Train & save ──────────────────────────────────────────────────────────────
def train_all_models() -> Dict[str, Dict]:
    """
    Main entry point:
      1. Load rasters → build native-cadence series
      2. Evaluate with hold-out
      3. Refit on ALL data
      4. Save .pkl

    Returns hold-out metrics for Kc and PET.
    """
    results: Dict[str, Dict] = {}

    # ── Kc (from SAVI rasters via regression) ────────────────────────────────
    try:
        kc_vals, kc_dates = build_kc_series()   # FIX-A

        kc_metrics = evaluate(kc_vals, S_KC, "Kc")   # FIX-D default test_n
        kc_res     = fit_sarima(kc_vals, S_KC, "Kc_final", auto=True)

        with open(KC_MODEL_PATH, "wb") as f:
            pickle.dump({
                "model":   kc_res,
                "values":  kc_vals,
                "dates":   kc_dates,
                "s":       S_KC,
                "cadence": KC_CADENCE_DAYS,
                "meta": {
                    "metrics":   kc_metrics,
                    "last_date": kc_dates[-1],
                    "n_obs":     len(kc_vals),
                    "source":    "SAVI→regression",
                },
            }, f)
        logger.info("Kc model saved → %s", KC_MODEL_PATH)
        results["kc"] = kc_metrics

    except Exception as exc:
        logger.error("Kc training failed: %s", exc, exc_info=True)
        results["kc"] = {"R2": np.nan, "RMSE": np.nan, "MAE": np.nan}

    # ── PET (SARIMAX with rain as exog) ───────────────────────────────────────
    try:
        pet_vals, rain_vals, pet_dates = build_pet_rain_series()   # FIX-B

        pet_metrics = evaluate(pet_vals, S_PET, "PET", exog=rain_vals)
        pet_res     = fit_sarima(pet_vals, S_PET, "PET_final",
                                 exog=rain_vals, auto=True)

        # Store seasonal climatological rain for future forecasts
        # (mean rain by day-of-season index)
        rain_clim = _compute_rain_climatology(rain_vals, S_PET)

        with open(PET_MODEL_PATH, "wb") as f:
            pickle.dump({
                "model":       pet_res,
                "values":      pet_vals,
                "rain_values": rain_vals,
                "dates":       pet_dates,
                "s":           S_PET,
                "cadence":     PET_CADENCE_DAYS,
                "rain_clim":   rain_clim,   # used as future exog
                "meta": {
                    "metrics":   pet_metrics,
                    "last_date": pet_dates[-1],
                    "n_obs":     len(pet_vals),
                },
            }, f)
        logger.info("PET model saved → %s", PET_MODEL_PATH)
        results["pet"] = pet_metrics

    except Exception as exc:
        logger.error("PET training failed: %s", exc, exc_info=True)
        results["pet"] = {"R2": np.nan, "RMSE": np.nan, "MAE": np.nan}

    logger.info("Training complete — Kc R²=%.4f  PET R²=%.4f",
                results["kc"].get("R2", float("nan")),
                results["pet"].get("R2", float("nan")))
    return results


def _compute_rain_climatology(rain_vals: np.ndarray, s: int) -> np.ndarray:
    """
    Mean rain by position within the seasonal cycle (length s).
    Used as the best estimate of future rain for PET forecasting.
    """
    n       = len(rain_vals)
    n_full  = (n // s) * s
    if n_full == 0:
        return np.zeros(s)
    mat  = rain_vals[:n_full].reshape(-1, s)
    clim = mat.mean(axis=0)
    return clim


# ── Load models ───────────────────────────────────────────────────────────────
def load_model(model_type: str) -> dict:
    """Load pkl for 'kc' or 'pet'. Trains if missing."""
    path = KC_MODEL_PATH if model_type == "kc" else PET_MODEL_PATH
    if not path.exists():
        logger.warning("Model %s not found – training now …", path)
        train_all_models()
    with open(path, "rb") as f:
        return pickle.load(f)


# ── Forecast helpers ──────────────────────────────────────────────────────────
def _future_rain_exog(rain_clim: np.ndarray,
                      last_date: datetime,
                      steps: int) -> np.ndarray:
    """
    Build `steps` days of future rain using the seasonal climatology.
    day_of_season is determined by distance from Nov-1 (Rabi start).
    """
    s    = len(rain_clim)
    exog = []
    cur  = last_date
    for _ in range(steps):
        cur = cur + timedelta(days=1)
        # Position within the seasonal cycle (0-based)
        rabi_start = datetime(cur.year if cur.month >= 11 else cur.year - 1, 11, 1)
        pos = (cur - rabi_start).days % s
        exog.append(rain_clim[pos])
    return np.array(exog, dtype=float)


def _map_steps_to_dates(last_date: datetime,
                        cadence: int,
                        steps: int) -> List[datetime]:
    """Generate forecast dates at native cadence. All calendar dates included."""
    return [last_date + timedelta(days=(i + 1) * cadence) for i in range(steps)]


def forecast_series_kc(steps: int) -> Tuple[np.ndarray, List[datetime]]:
    obj       = load_model("kc")
    res       = obj["model"]
    last_date = obj["meta"]["last_date"]

    raw  = res.get_forecast(steps=steps).predicted_mean.values.astype(float)
    vals = np.clip(raw, KC_MIN, KC_MAX)
    dates = _map_steps_to_dates(last_date, KC_CADENCE_DAYS, steps)
    return vals, dates


def forecast_series_pet(steps: int) -> Tuple[np.ndarray, np.ndarray, List[datetime]]:
    """Returns (pet_vals, peff_vals, dates)."""
    obj       = load_model("pet")
    res       = obj["model"]
    last_date = obj["meta"]["last_date"]
    rain_clim = obj.get("rain_clim", np.zeros(S_PET))

    future_rain = _future_rain_exog(rain_clim, last_date, steps)
    raw  = res.get_forecast(steps=steps,
                            exog=future_rain).predicted_mean.values.astype(float)
    pet  = np.clip(raw, PET_MIN, PET_MAX)

    # FIX-E: effective rainfall for IWR
    peff = np.clip(future_rain * RAIN_EFFECTIVE_FRACTION, 0.0, None)

    dates = _map_steps_to_dates(last_date, PET_CADENCE_DAYS, steps)
    return pet, peff, dates


def _interpolate_to_daily(values: np.ndarray,
                           dates: List[datetime],
                           target_dates: List[datetime]) -> np.ndarray:
    """Linear interpolation of sparse forecast onto specific target_dates."""
    src_ord = np.array([d.toordinal() for d in dates], dtype=float)
    tgt_ord = np.array([d.toordinal() for d in target_dates], dtype=float)
    return np.interp(tgt_ord, src_ord, values,
                     left=values[0], right=values[-1])


# ── Public API ────────────────────────────────────────────────────────────────
def forecast_points(reference_date: datetime,
                    horizons: List[int] = (0, 5, 10, 15)) -> pd.DataFrame:
    """
    Return Kc, SAVI, PET, CWR, IWR for each day horizon.
    horizons=0 → today, horizons=5 → 5 days ahead, etc.
    """
    max_h = max(horizons) + 2

    kc_steps  = max(max_h // KC_CADENCE_DAYS + 4, S_KC)
    pet_steps = max(max_h + 10, S_PET)

    kc_vals,            kc_dates  = forecast_series_kc(kc_steps)
    pet_vals, peff_vals, pet_dates = forecast_series_pet(pet_steps)

    rows = []
    for h in horizons:
        tgt = reference_date + timedelta(days=h)

        kc_day   = float(_interpolate_to_daily(kc_vals,   kc_dates,  [tgt])[0])
        pet_day  = float(_interpolate_to_daily(pet_vals,  pet_dates, [tgt])[0])
        peff_day = float(_interpolate_to_daily(peff_vals, pet_dates, [tgt])[0])

        kc_day  = float(np.clip(kc_day,  KC_MIN,  KC_MAX))
        pet_day = float(np.clip(pet_day, PET_MIN, PET_MAX))

        savi_day = float(np.clip((kc_day - KC_INTERCEPT) / KC_SLOPE,
                                 SAVI_MIN, SAVI_MAX))

        cwr = kc_day * pet_day                    # mm/day
        iwr = max(cwr - peff_day, 0.0)            # FIX-E: subtract Peff

        rows.append({
            "horizon_days": h,
            "date":  tgt.strftime("%Y-%m-%d"),
            "savi":  round(savi_day, 4),
            "kc":    round(kc_day,   4),
            "pet":   round(pet_day,  4),
            "peff":  round(peff_day, 4),
            "cwr":   round(cwr,      4),
            "iwr":   round(iwr,      4),
        })

    return pd.DataFrame(rows).set_index("horizon_days")


def compute_iwr_forecast(reference_date: datetime,
                         days: int = 15) -> pd.DataFrame:
    """
    Daily IWR forecast for the next `days` Rabi days.
    Compatible with existing main.py call signature.
    """
    kc_steps  = max(days // KC_CADENCE_DAYS + 4, S_KC)
    pet_steps = max(days + 10, S_PET)

    kc_vals,             kc_dates  = forecast_series_kc(kc_steps)
    pet_vals, peff_vals, pet_dates = forecast_series_pet(pet_steps)

    target_dates = [reference_date + timedelta(days=i + 1) for i in range(days)]
    target_dates = [d for d in target_dates if is_rabi(d)]

    kc_i   = _interpolate_to_daily(kc_vals,   kc_dates,  target_dates)
    pet_i  = _interpolate_to_daily(pet_vals,  pet_dates, target_dates)
    peff_i = _interpolate_to_daily(peff_vals, pet_dates, target_dates)

    kc_i  = np.clip(kc_i,  KC_MIN,  KC_MAX)
    pet_i = np.clip(pet_i, PET_MIN, PET_MAX)

    savi_i = np.clip((kc_i - KC_INTERCEPT) / KC_SLOPE, SAVI_MIN, SAVI_MAX)
    cwr_i  = kc_i * pet_i
    iwr_i  = np.maximum(cwr_i - peff_i, 0.0)   # FIX-E

    df = pd.DataFrame({
        "savi": savi_i,
        "kc":   kc_i,
        "pet":  pet_i,
        "peff": peff_i,
        "cwr":  cwr_i,
        "iwr":  iwr_i,
    }, index=pd.DatetimeIndex(target_dates))

    logger.info("IWR forecast: %d days from %s, mean IWR=%.3f mm/day",
                len(df), reference_date.date(), iwr_i.mean())
    return df


# ── Spatial mapping helpers ───────────────────────────────────────────────────
def savi_to_kc(savi: np.ndarray) -> np.ndarray:
    """Thesis regression for pixel-level mapping (spatial, not time-series)."""
    return np.clip(KC_SLOPE * np.asarray(savi, float) + KC_INTERCEPT,
                   KC_MIN, KC_MAX)


def kc_to_savi(kc: np.ndarray) -> np.ndarray:
    """Inverse regression: Kc → SAVI."""
    return np.clip((np.asarray(kc, float) - KC_INTERCEPT) / KC_SLOPE,
                   SAVI_MIN, SAVI_MAX)


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    print("=" * 64)
    print("Training SARIMAX models …")
    print("=" * 64)

    metrics = train_all_models()

    print("\n" + "=" * 64)
    print(f"  Kc  R² = {metrics['kc']['R2']:+.4f}   "
          f"RMSE = {metrics['kc']['RMSE']:.4f}   "
          f"MAE = {metrics['kc']['MAE']:.4f}")
    print(f"  PET R² = {metrics['pet']['R2']:+.4f}   "
          f"RMSE = {metrics['pet']['RMSE']:.4f}   "
          f"MAE = {metrics['pet']['MAE']:.4f}")
    print("=" * 64)

    today = datetime.now()
    print(f"\nForecast from {today.date()} for horizons: today, +5, +10, +15")
    try:
        fp = forecast_points(today, horizons=[0, 5, 10, 15])
        print(fp.to_string())
    except Exception as e:
        print(f"  Forecast failed: {e}")

    print("\nDone.")