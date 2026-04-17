
import os
import sys
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Mocking logging and Path to run without full backend infra if needed
import logging
logging.basicConfig(level=logging.INFO)

# Add backend to path
sys.path.append("/home/aman-/aman/irrigation/backend")

from main import generate_forecast_for_date

def test_forecast_dynamics():
    ref_date = datetime.now()
    print(f"Generating forecast from {ref_date.date()}...")
    
    forecasts = generate_forecast_for_date(ref_date, days=15)
    
    if not forecasts:
        print("FAILED: No forecasts generated.")
        return

    for param in ["pet", "kc", "cwr", "iwr"]:
        if param not in forecasts:
            print(f"FAILED: {param} missing from forecasts.")
            continue
        
        series = forecasts[param]
        std = series.std()
        mean = series.mean()
        min_val = series.min()
        max_val = series.max()
        
        print(f"\nParameter: {param.upper()}")
        print(f"  Mean: {mean:.4f}")
        print(f"  Range: {min_val:.4f} - {max_val:.4f}")
        print(f"  StdDev: {std:.4f}")
        
        if std < 0.0001:
            print(f"  [!] WARNING: {param} forecast is FLAT!")
        else:
            print(f"  [OK] {param} forecast is dynamic.")

if __name__ == "__main__":
    test_forecast_dynamics()
