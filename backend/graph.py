import logging
import math
from collections import defaultdict
from typing import Dict, List, Tuple

from fastapi import APIRouter, HTTPException, Query

from extract_raster_pixels import (
    get_allowed_season_ids,
    get_season_id,
    history_files_for_param,
    is_in_season,
    raster_mean_value,
)


router = APIRouter(
    prefix="/api/graph",
    tags=["Graph"],
)

logger = logging.getLogger(__name__)

LAYER_CONFIGS = {
    "savi": {"full_name": "Soil Adjusted Vegetation Index", "unit": "index"},
    "kc": {"full_name": "Crop Coefficient", "unit": "coefficient"},
    "cwr": {"full_name": "Crop Water Requirement", "unit": "mm"},
    "etc": {"full_name": "Actual Evapotranspiration", "unit": "mm/day"},
    "iwr": {"full_name": "Irrigation Water Requirement", "unit": "mm"},
}

MONTH_NAMES = {
    1: "January",
    2: "February",
    3: "March",
    4: "April",
    5: "May",
    6: "June",
    7: "July",
    8: "August",
    9: "September",
    10: "October",
    11: "November",
    12: "December",
}


def _history_monthly_means(layer: str) -> List[Dict]:
    grouped: Dict[Tuple[int, int], List[float]] = defaultdict(list)
    allowed_seasons = set(get_allowed_season_ids())

    for date_obj, raster_path in history_files_for_param(layer):
        season_id = get_season_id(date_obj)
        if not is_in_season(date_obj) or season_id not in allowed_seasons:
            continue

        value = raster_mean_value(raster_path)
        if value is None or not math.isfinite(value):
            continue
        grouped[(date_obj.year, date_obj.month)].append(float(value))

    results = []
    for (year, month), values in sorted(grouped.items()):
        if not values:
            continue
        results.append(
            {
                "year": year,
                "month": month,
                "monthly_avg": sum(values) / len(values),
            }
        )
    return results


@router.get("/seasonal-chart")
async def seasonal_chart(
    layer: str = Query(...),
    mode: str = Query("monthly"),
):
    layer = layer.lower()

    if layer not in LAYER_CONFIGS:
        raise HTTPException(status_code=400, detail="Invalid layer")

    results = _history_monthly_means(layer)
    if not results:
        raise HTTPException(status_code=404, detail="No raster history data found")

    years = sorted({r["year"] for r in results})
    months = sorted({r["month"] for r in results})

    year_map: Dict[int, Dict[int, float]] = {}
    for row in results:
        year_map.setdefault(row["year"], {})
        year_map[row["year"]][row["month"]] = row["monthly_avg"]

    chart_data = []
    for year in years:
        monthly_vals = []
        cumulative_vals = []
        running = 0.0

        for month in months:
            value = year_map.get(year, {}).get(month)
            if value is not None and math.isfinite(value):
                monthly_vals.append(round(value, 6))
                running += value
                cumulative_vals.append(round(running, 6))
            else:
                monthly_vals.append(None)
                cumulative_vals.append(None)

        entry = {"year": year}
        if mode == "monthly":
            entry["monthly"] = monthly_vals
        elif mode == "cumulative":
            entry["cumulative"] = cumulative_vals
        else:
            entry["monthly"] = monthly_vals
            entry["cumulative"] = cumulative_vals
        chart_data.append(entry)

    return {
        "layer": layer,
        "layer_config": LAYER_CONFIGS[layer],
        "mode": mode,
        "years": years,
        "months": months,
        "month_names": [MONTH_NAMES[m] for m in months],
        "data": chart_data,
        "source": "history_rasters",
    }