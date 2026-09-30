import numpy as np
import allantools
import matplotlib.pyplot as plt


def estimate_imu_noise_params(data,
                              rate,
                              data_type='freq',
                              axis_name="GyroX"):
    """
    Estimates basic IMU noise parameters from stationary data using Allan Deviation:
      - Angle/Velocity Random Walk
      - Approx. Bias Instability
    data: numpy array of IMU readings (e.g., deg/s for gyro if data_type='freq')
    rate: sample period (seconds) -> i.e. dt = 1/frequency
    data_type: passed to allantools.oadev (e.g. 'phase' if data is integrated angle,
               'freq' if data is angular rate)
    axis_name: just a label for plotting

    Returns a dictionary with noise estimates:
      {
        'random_walk': ...,
        'bias_instability': ...,
        'arw_in_deg_rt_hr': ...
        ...
      }
    """
    # 1) Compute overlapping Allan deviation
    taus, adev, _, _ = allantools.oadev(data=data,
                                        rate=rate,
                                        data_type=data_type,
                                        taus='octave')

    # 2) Convert to log space for slope analysis
    log_tau = np.log10(taus)
    log_adev = np.log10(adev)

    # PLOT the Allan Deviation
    plt.loglog(taus, adev)
    plt.title(f"Allan Deviation - {axis_name}")
    plt.xlabel("Tau (s)")
    plt.ylabel("Allan Deviation")
    plt.grid(True)
    plt.show()

    # ~~~ A) Estimate random walk (white noise) from short-tau region ~~~
    # We'll pick the first decade or so of tau to do a linear fit in log-log space
    # (Adjust as needed if your data is short or has different shape)
    n_short = max(3, len(taus) // 10)  # just pick some portion
    tau_short = log_tau[:n_short]
    adev_short = log_adev[:n_short]

    # linear fit y = m*x + b in log10 space
    slope, intercept = np.polyfit(tau_short, adev_short, 1)
    # slope should be about -0.5 if purely white noise
    # intercept = log10(adevn at tau=1s) basically
    # For a perfect -1/2 slope, ARW = sqrt(3)* (value at tau=1)
    # (There's also a direct method using min(sigma * sqrt(tau)).)

    # approximate angle random walk (for gyro):
    # ARW (deg/sqrt(hr)) = (value at tau=1 second) * sqrt(3)
    # where (value at tau=1 second) = 10^intercept if slope ~ -0.5
    noise_at_1s = 10 ** (intercept)
    ARW = noise_at_1s * np.sqrt(3.0)  # in deg/s if your data is deg/s

    # ~~~ B) Estimate bias instability ~~~
    # A common approach is to find the minimum of sigma^2(tau)*tau, or
    # just look for a local "flat" region. We'll do a naive approach:
    sig_tau = adev * np.sqrt(taus)
    idx_min = np.argmin(sig_tau)
    bias_instability_approx = sig_tau[idx_min] / 0.664  # for the standard formula
    tau_for_bias = taus[idx_min]

    results = {
        "all_taus": taus,
        "all_adev": adev,
        "arw_deg_per_sqrt_hr": ARW,  # or some interpretation
        "bias_instability": bias_instability_approx,
        "tau_bias_instability_s": tau_for_bias,
        "fitted_slope_short_tau": slope
    }
    return results


import pandas as pd

# 1) Load your CSV
df = pd.read_csv("imu_only_data.csv")

# 2) Suppose you have a time column in seconds, or you know sampling frequency
time = df["timestamp"].values
dt = np.mean(np.diff(time))  # seconds per sample
fs = 1.0 / dt
print("Sampling freq:", fs, "Hz")

# 3) Extract your gyro X data, e.g. in deg/s (if that’s what you have)
gyro_x = df["gx"].values

# 4) Call the function
res_x = estimate_imu_noise_params(
    data=gyro_x,
    rate=dt,             # sample period
    data_type='freq',    # because we have rate data (deg/s)
    axis_name="Gyro X"
)

print("=== Results Gyro X ===")
print(f"Short-tau slope: {res_x['fitted_slope_short_tau']:.3f} (ideal ~ -0.5 for white noise)")
print(f"Angle Random Walk ~ {res_x['arw_deg_per_sqrt_hr']:.4f} deg / sqrt(hr)")
print(f"Bias Instability ~ {res_x['bias_instability']:.4e} deg/s (approx)")
print(f"Tau at bias instability: {res_x['tau_bias_instability_s']} s")
