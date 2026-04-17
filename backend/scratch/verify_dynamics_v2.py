
import os
import sys
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging

# Mock problematic imports to allow verify_dynamics to run
import builtins
real_import = builtins.__import__
def mock_import(name, *args, **kwargs):
    if name in ['uvicorn', 'fastapi', 'pymongo', 'rasterio']:
        return type('Mock', (), {'APIRouter': lambda *a, **k: None, 'FastAPI': lambda *a, **k: None})
    return real_import(name, *args, **kwargs)
builtins.__import__ = mock_import

# Add backend to path
sys.path.append("/home/aman-/aman/irrigation/backend")

# Try to import generate_forecast_for_date
try:
    from main import generate_forecast_for_date
except ImportError as e:
    print(f"Import failed: {e}")
    # Fallback: manually define a mock for testing the math if import fails
    def generate_forecast_for_date(*args, **kwargs): return None

def test_forecast_dynamics():
    ref_date = datetime.now()
    print(f"Generating forecast from {ref_date.date()}...")
    
    try:
        forecasts = generate_forecast_for_date(ref_date, days=15)
    except Exception as e:
        print(f"Execution failed: {e}")
        return
    
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
