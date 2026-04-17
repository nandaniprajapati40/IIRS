
import rasterio
import numpy as np
from pathlib import Path
import pandas as pd
from datetime import datetime
import re

PET_DIR = Path("/home/aman-/aman/irrigation/backend/data/raw/insat_pet")

def extract_date(filename):
    m = re.search(r"\d{8}", filename)
    if m:
        return datetime.strptime(m.group(), "%Y%m%d")
    m = re.search(r"\d{2}[A-Z]{3}\d{4}", filename.upper())
    if m:
        return datetime.strptime(m.group(), "%d%b%Y")
    return None

files = sorted(PET_DIR.glob("*.tif"))
data = []
for f in files[-30:]: # last 30 files
    date = extract_date(f.name)
    if not date: continue
    with rasterio.open(f) as src:
        arr = src.read(1).astype(float)
        if src.nodata:
            arr[arr == src.nodata] = np.nan
        mean_val = np.nanmean(arr)
        data.append({"date": date, "mean": mean_val})

df = pd.DataFrame(data).sort_values("date")
print(df.to_string())
