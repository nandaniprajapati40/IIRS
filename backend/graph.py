
# graph.py

from fastapi import APIRouter, HTTPException, Query
from pymongo import MongoClient
from datetime import datetime
from typing import Dict
import logging
from config import MONGODB  
import math

router = APIRouter(
    prefix="/api/graph",
    tags=["Graph"]
)

logger = logging.getLogger(__name__)

MONGODB_URI = MONGODB["uri"]
DB_NAME = MONGODB["database"]
LAYER_CONFIGS = {
    "savi": {"full_name": "Soil Adjusted Vegetation Index", "unit": "index"},
    "kc": {"full_name": "Crop Coefficient", "unit": "coefficient"},
    "cwr": {"full_name": "Crop Water Requirement", "unit": "mm"},
    "etc": {"full_name": "Actual Evapotranspiration", "unit": "mm/day"},
    "iwr": {"full_name": "Irrigation Water Requirement", "unit": "mm"}
}

MONTH_NAMES = {
    1: "January", 2: "February", 3: "March", 4: "April",
    5: "May", 6: "June", 7: "July", 8: "August",
    9: "September", 10: "October",
    11: "November", 12: "December"
}

def get_collection():
    client = MongoClient(MONGODB_URI)
    db = client[DB_NAME]
    return db["processed_data"] 


@router.get("/seasonal-chart")
async def seasonal_chart(
    layer: str = Query(...),
    mode: str = Query("monthly")
):

    import math

    layer = layer.lower()

    if layer not in LAYER_CONFIGS:
        raise HTTPException(status_code=400, detail="Invalid layer")

    collection = get_collection()

    pipeline = [
        {"$match": {"parameter": layer}},
        {
            "$group": {
                "_id": {
                    "year": {"$year": "$date"},
                    "month": {"$month": "$date"}
                },
                "monthly_avg": {"$avg": "$value"}
            }
        },
        {"$sort": {"_id.year": 1, "_id.month": 1}}
    ]

    results = list(collection.aggregate(pipeline))

    if not results:
        raise HTTPException(status_code=404, detail="No data found")

    years = sorted(set(r["_id"]["year"] for r in results))
    months = sorted(set(r["_id"]["month"] for r in results))

    year_map = {}

    for r in results:
        y = r["_id"]["year"]
        m = r["_id"]["month"]
        val = r["monthly_avg"]

        if val is None or (isinstance(val, float) and math.isnan(val)):
            val = None

        year_map.setdefault(y, {})
        year_map[y][m] = val

    chart_data = []

    for y in years:
        monthly_vals = []
        cumulative_vals = []
        running = 0

        for m in months:
            val = year_map.get(y, {}).get(m)

            if val is not None:
                monthly_vals.append(round(val, 6))
                running += val
                cumulative_vals.append(round(running, 6))
            else:
                monthly_vals.append(None)
                cumulative_vals.append(None)

        entry = {"year": y}
        if mode == "monthly":
            entry["monthly"] = monthly_vals
        elif mode == "cumulative":
            entry["cumulative"] = cumulative_vals
        else:
            entry["monthly"] = monthly_vals
            entry["cumulative"] = cumulative_vals

        chart_data.append(entry)

    response = {
        "layer": layer,
        "layer_config": LAYER_CONFIGS[layer],
        "mode": mode,
        "years": years,
        "months": months,
        "month_names": [MONTH_NAMES[m] for m in months],
        "data": chart_data
    }

    # Final JSON safety
    def clean_nan(obj):
        if isinstance(obj, float) and math.isnan(obj):
            return None
        if isinstance(obj, list):
            return [clean_nan(x) for x in obj]
        if isinstance(obj, dict):
            return {k: clean_nan(v) for k, v in obj.items()}
        return obj

    return clean_nan(response)