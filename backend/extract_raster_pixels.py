import rasterio
import pandas as pd
import numpy as np
from pathlib import Path
from tqdm import tqdm
import re

from config import DIRECTORIES

# ==========================================
# Raster Directories
# ==========================================

RASTER_GROUPS = {
    "savi": DIRECTORIES["processed"]["savi"],
    "kc": DIRECTORIES["processed"]["kc"],
    "cwr": DIRECTORIES["processed"]["cwr"],
    "iwr": DIRECTORIES["processed"]["iwr"],
    "etc": DIRECTORIES["processed"]["ETc"],
}

# ==========================================
# Output Directories
# ==========================================

PARQUET_OUTPUT_DIR = Path("pixel_parquet")
PARQUET_OUTPUT_DIR.mkdir(exist_ok=True)

# Master pixel table
PIXEL_MASTER_FILE = PARQUET_OUTPUT_DIR / "pixel_master.parquet"

# ==========================================
# Batch Size
# ==========================================

BATCH_SIZE = 50000

# ==========================================
# Create Pixel Master Only Once
# ==========================================

pixel_master_created = PIXEL_MASTER_FILE.exists()

# ==========================================
# Process Each Raster Type
# ==========================================

for raster_type, folder in RASTER_GROUPS.items():

    print("\n===================================")
    print(f"Processing: {raster_type.upper()}")
    print("===================================")

    tif_files = sorted(Path(folder).glob("*.tif"))

    for tif_path in tif_files:

        print(f"\nReading Raster: {tif_path.name}")

        # ==========================================
        # Extract Date From Filename
        # Example:
        # savi_20211102.tif
        # ==========================================

        date_match = re.search(r"(\d{8})", tif_path.stem)

        raster_date = None

        if date_match:
            raster_date = pd.to_datetime(
                date_match.group(1),
                format="%Y%m%d"
            ).strftime("%Y-%m-%d")

        # ==========================================
        # Output File
        # ==========================================

        parquet_file = (
            PARQUET_OUTPUT_DIR /
            f"{tif_path.stem}.parquet"
        )

        parquet_batches = []

        # Pixel master batches
        pixel_master_batches = []

        with rasterio.open(tif_path) as src:

            nodata = src.nodata

            height = src.height
            width = src.width

            # ======================================
            # Read Full Band
            # ======================================

            band = src.read(1)

            # ======================================
            # Valid Mask
            # ======================================

            valid_mask = np.ones_like(
                band,
                dtype=bool
            )

            if nodata is not None:
                valid_mask &= (band != nodata)

            valid_mask &= ~np.isnan(band)
            valid_mask &= (band > 0)

            # ======================================
            # Get Valid Pixel Indices
            # ======================================

            rows, cols = np.where(valid_mask)

            values = band[rows, cols]

            print(f"Valid Pixels: {len(values)}")

            batch_records = []
            pixel_master_records = []

            # ======================================
            # Process Pixels
            # ======================================

            for idx in tqdm(
                range(len(values)),
                desc=tif_path.name
            ):

                row = int(rows[idx])
                col = int(cols[idx])

                value = float(values[idx])

                # ==================================
                # Pixel ID
                # ==================================

                pixel_id = f"{row}_{col}"

                # ==================================
                # Main Time-Series Record
                # ==================================

                record = {
                    "pixel_id": pixel_id,
                    "row": row,
                    "col": col,
                    "date": raster_date,
                    "value": round(value, 4),
                    "raster_type": raster_type,
                    "raster_file": tif_path.name,
                }

                batch_records.append(record)

                # ==================================
                # Pixel Master Record (only once)
                # ==================================

                if not pixel_master_created:

                    lon, lat = src.xy(row, col)

                    pixel_record = {
                        "pixel_id": pixel_id,
                        "row": row,
                        "col": col,
                        "latitude": round(float(lat), 6),
                        "longitude": round(float(lon), 6),
                    }

                    pixel_master_records.append(pixel_record)

                # ==================================
                # Save Main Batch
                # ==================================

                if len(batch_records) >= BATCH_SIZE:

                    df = pd.DataFrame(batch_records)

                    parquet_batches.append(df)

                    print(
                        f"Saved Batch: "
                        f"{len(batch_records)} records"
                    )

                    batch_records = []

                # ==================================
                # Save Pixel Master Batch
                # ==================================

                if (
                    not pixel_master_created
                    and len(pixel_master_records) >= BATCH_SIZE
                ):

                    master_df = pd.DataFrame(
                        pixel_master_records
                    )

                    pixel_master_batches.append(master_df)

                    pixel_master_records = []

            # ======================================
            # Remaining Main Records
            # ======================================

            if batch_records:

                df = pd.DataFrame(batch_records)

                parquet_batches.append(df)

                print(
                    f"Saved Final Batch: "
                    f"{len(batch_records)} records"
                )

            # ======================================
            # Remaining Pixel Master Records
            # ======================================

            if (
                not pixel_master_created
                and pixel_master_records
            ):

                master_df = pd.DataFrame(
                    pixel_master_records
                )

                pixel_master_batches.append(master_df)

        # ==========================================
        # Save Raster Time-Series Parquet
        # ==========================================

        if parquet_batches:

            final_df = pd.concat(
                parquet_batches,
                ignore_index=True
            )

            final_df.to_parquet(
                parquet_file,
                index=False,
                compression="snappy"
            )

            parquet_size = (
                parquet_file.stat().st_size /
                (1024 ** 2)
            )

            print("\n===================================")
            print(f"Saved: {parquet_file}")
            print(f"Parquet Size: {parquet_size:.2f} MB")
            print("===================================")

        # ==========================================
        # Save Pixel Master Only Once
        # ==========================================

        if (
            not pixel_master_created
            and pixel_master_batches
        ):

            pixel_master_df = pd.concat(
                pixel_master_batches,
                ignore_index=True
            )

            # Remove duplicate pixels
            pixel_master_df = pixel_master_df.drop_duplicates(
                subset=["pixel_id"]
            )

            pixel_master_df.to_parquet(
                PIXEL_MASTER_FILE,
                index=False,
                compression="snappy"
            )

            master_size = (
                PIXEL_MASTER_FILE.stat().st_size /
                (1024 ** 2)
            )

            print("\n===================================")
            print("Pixel Master Saved")
            print(f"File: {PIXEL_MASTER_FILE}")
            print(f"Size: {master_size:.2f} MB")
            print("===================================")

            pixel_master_created = True

print("\nDONE!")