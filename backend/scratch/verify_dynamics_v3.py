
import os
import sys
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging

# Improved Mock problematic imports
import builtins
real_import = builtins.__import__
def mock_import(name, globals=None, locals=None, fromlist=(), level=0):
    if name in ['uvicorn', 'fastapi', 'pymongo', 'rasterio', 'geemap', 'earthengine-api', 'google-auth-oauthlib', 'playwright', 'anthropic', 'paramiko', 'pysftp', 'h5py', 'watchdog', 'apscheduler']:
        class Mock:
            def __init__(self, *args, **kwargs): pass
            def __getattr__(self, name): 
                if name == 'APIRouter': return lambda *a, **k: Mock()
                if name == 'FastAPI': return lambda *a, **k: Mock()
                return Mock()
        return Mock()
    return real_import(name, globals, locals, fromlist, level)
builtins.__import__ = mock_import

# Add backend to path
sys.path.append("/home/aman-/aman/irrigation/backend")

# Mock the constants that come from config.py if needed, 
# but main.py imports them. Let's hope the mock catches config imports too.

try:
    from main import generate_forecast_for_date
except Exception as e:
    print(f"Import failed: {e}")
    # Fallback to manual check of the logic if import falls through
    generate_forecast_for_date = None

if generate_forecast_for_date:
    def test_forecast_dynamics():
        ref_date = datetime.now()
        print(f"Generating forecast from {ref_date.date()}...")
        
        try:
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
        except Exception as e:
            print(f"Execution failed: {e}")
            import traceback
            traceback.print_exc()

    if __name__ == "__main__":
        test_forecast_dynamics()
else:
    print("Could not test generate_forecast_for_date.")
