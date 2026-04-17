
import sys
import os
from datetime import datetime
import pandas as pd
import numpy as np

# Mocking parts of main.py to test the function
sys.path.append('/home/aman-/aman/irrigation/backend')

import main
import config

# Mock _get_model to return None (triggering base = persistence)
def mock_get_model(model_type):
    return None, None

main._get_model = mock_get_model

# Mock _read_mean to return a constant (triggering flat trend in old code)
def mock_read_mean(path):
    return 0.68

main._read_mean = mock_read_mean

# Test for April 15 (DOY 105)
test_date = datetime(2026, 4, 15)
future_dates = pd.date_range(start=test_date + pd.Timedelta(days=1), periods=15, freq='D')

print(f"Testing Kc forecast for {test_date.date()} (DOY {test_date.timetuple().tm_yday})")
kc_forecast = main._project_kc_for_dates(future_dates)

print("\nForecasted Kc values (15 days):")
for i, val in enumerate(kc_forecast):
    print(f"Day {i+1}: {val:.4f}")

# Check if it is declining
if kc_forecast[-1] < kc_forecast[0]:
    print("\n✅ SUCCESS: Kc forecast is declining as expected for April.")
else:
    print("\n❌ FAILURE: Kc forecast is still flat or rising.")

# Check the averages (what the UI shows)
five_day = np.mean(kc_forecast[0:5])
ten_day = np.mean(kc_forecast[0:10])
fifteen_day = np.mean(kc_forecast[0:15])

print(f"\nUI Averages:")
print(f"Today (last obs): 0.680")
print(f"5-day avg:  {five_day:.3f}")
print(f"10-day avg: {ten_day:.3f}")
print(f"15-day avg: {fifteen_day:.3f}")
