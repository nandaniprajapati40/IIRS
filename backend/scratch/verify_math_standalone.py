
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

def test_math_logic():
    days = 15
    reference_date = datetime.now()
    future_dates = pd.date_range(start=reference_date + timedelta(days=1), periods=days, freq="D")
    doy = future_dates.dayofyear.values.astype(float)
    
    # Logic for seasonal PET
    seasonal_pet = 5.5 + 3.2 * np.sin(2 * np.pi * (doy - 45) / 365.25)
    
    # Logic for Peff
    peff_scalar = 0.5 # Example
    seed_val = int(future_dates[0].dayofyear)
    state = np.random.RandomState(seed_val)
    noise = state.normal(0, 0.05, days) 
    spikes = state.choice([0, 1], size=days, p=[0.85, 0.15])
    spike_vals = state.uniform(0.5, 2.5, days) * spikes
    peff_values = np.maximum(0.0, peff_scalar + noise + spike_vals)
    
    # Logic for PET
    last_pet_obs = 2.0 # Example
    alpha = np.exp(-np.arange(days) / 5.0)
    pet_noise = state.normal(0, 0.25, days)
    # Case: pet_model is None
    pet_values = alpha * np.full(days, float(last_pet_obs)) + (1 - alpha) * seasonal_pet + pet_noise
    
    # Logic for Kc
    last_kc_obs = 0.8
    blended_slope = -0.01 # Example
    days_ahead = np.arange(1, days + 1, dtype=float)
    trend = last_kc_obs + 0.85 * blended_slope * days_ahead
    seasonal_kc = 0.15 * np.sin(2 * np.pi * doy / 365.25) + 0.08 * np.cos(2 * np.pi * doy / 365.25)
    base_kc = np.full(days, 0.8)
    kc_noise = state.normal(0, 0.015, days)
    kc_final = 0.15 * base_kc + 0.75 * trend + seasonal_kc + kc_noise
    
    # Logic for CWR and IWR
    cwr = np.clip(kc_final * pet_values, 0, 15)
    iwr = np.maximum(cwr - peff_values, 0)
    
    print(f"PET StdDev: {pet_values.std():.4f}")
    print(f"Kc StdDev: {kc_final.std():.4f}")
    print(f"CWR StdDev: {cwr.std():.4f}")
    print(f"IWR StdDev: {iwr.std():.4f}")
    
    print("\nIWR Values (first 10 days):")
    print(iwr[:10])

if __name__ == "__main__":
    test_math_logic()
