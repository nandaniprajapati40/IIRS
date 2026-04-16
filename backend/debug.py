# import rasterio
# import numpy as np
# from pathlib import Path

# # 👉 CHANGE THESE PATHS
# PET_FILE = "data/raw/insat_pet/3RIMG_01APR2022_0015_L3C_PET_DLY_V01R00.tif"
# RAIN_FILE = "data/raw/insat_rain/3RIMG_01APR2022_0015_L3G_IMR_DLY_V01R00.tif"
# KC_FILE = "data/processed/kc/kc_20211102.tif"


# def raster_stats(fp):
#     with rasterio.open(fp) as src:
#         data = src.read(1).astype(float)

#         if src.nodata is not None:
#             data[data == src.nodata] = np.nan

#         data = data[~np.isnan(data)]

#         return {
#             "mean": float(np.mean(data)),
#             "min": float(np.min(data)),
#             "max": float(np.max(data)),
#         }


# print("\n====== DEBUG START ======\n")

# # PET
# pet = raster_stats(PET_FILE)
# print("📌 PET (mm/day)")
# print("Mean:", pet["mean"])
# print("Min :", pet["min"])
# print("Max :", pet["max"])

# # Rain
# rain = raster_stats(RAIN_FILE)
# print("\n📌 Rainfall (mm)")
# print("Mean:", rain["mean"])

# # Kc
# kc = raster_stats(KC_FILE)
# print("\n📌 Kc")
# print("Mean:", kc["mean"])

# # Manual calculation
# print("\n====== CALCULATION ======\n")

# PET = pet["mean"]
# Kc = kc["mean"]
# P = rain["mean"]

# # CWR
# CWR = Kc * PET

# # Effective rainfall (5-day assumption)
# Pe = max(0.6 * P - 10, 0)

# # IWR
# IWR = max(CWR - Pe, 0)

# print(f"Kc = {Kc:.3f}")
# print(f"PET = {PET:.3f} mm/day")
# print(f"CWR = {CWR:.3f} mm/day")
# print(f"Rain = {P:.3f} mm")
# print(f"Pe = {Pe:.3f} mm")
# print(f"IWR = {IWR:.3f} mm/day")

# print("\n====== DEBUG END ======\n")

# import rasterio
# import numpy as np
# from pathlib import Path

# rain_dir = Path("data/raw/insat_rain")

# files = sorted(rain_dir.glob("*.tif"))

# print(f"Total rain files: {len(files)}\n")

# for fp in files:
#     try:
#         with rasterio.open(fp) as src:
#             data = src.read(1).astype(float)

#             if src.nodata is not None:
#                 data[data == src.nodata] = np.nan

#             valid = data[~np.isnan(data)]

#             if len(valid) == 0:
#                 print(f"❌ {fp.name} → ALL NODATA")
#                 continue

#             mean = np.mean(valid)
#             minv = np.min(valid)
#             maxv = np.max(valid)

#             status = "OK"
#             if mean == 0:
#                 status = "⚠️ ZERO DATA"

#             print(f"{fp.name} | mean={mean:.3f} | min={minv:.3f} | max={maxv:.3f} | {status}")

#     except Exception as e:
#         print(f"❌ {fp.name} → ERROR: {e}")


import rasterio
import numpy as np
from pathlib import Path

pet_dir = Path("data/raw/insat_pet")

files = sorted(pet_dir.glob("*.tif"))

print(f"Total PET files: {len(files)}\n")

for fp in files:
    try:
        with rasterio.open(fp) as src:
            data = src.read(1).astype(float)

            if src.nodata is not None:
                data[data == src.nodata] = np.nan

            valid = data[~np.isnan(data)]

            if len(valid) == 0:
                print(f"❌ {fp.name} → ALL NODATA")
                continue

            mean = np.mean(valid)
            minv = np.min(valid)
            maxv = np.max(valid)

            # status check
            status = "OK"

            if mean == 0:
                status = "⚠️ ZERO DATA"

            elif mean < 1:
                status = "⚠️ VERY LOW PET"

            elif mean > 10:
                status = "⚠️ VERY HIGH PET"

            print(f"{fp.name} | mean={mean:.3f} | min={minv:.3f} | max={maxv:.3f} | {status}")

    except Exception as e:
        print(f"❌ {fp.name} → ERROR: {e}")