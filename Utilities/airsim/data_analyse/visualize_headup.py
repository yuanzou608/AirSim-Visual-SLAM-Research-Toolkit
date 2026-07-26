import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

# Load and prepare the data
df = pd.read_csv('data.csv')

# Transpose so methods become rows
df = df.set_index('Metric').transpose()

# Extract values
methods = df.index.tolist()
mean_errors = df['mean']
std_errors = df['std']
rmse_errors = df['rmse']

# X positions
x = np.arange(len(methods))

# Plot
plt.figure(figsize=(14, 6))

# Mean error bars
bars = plt.bar(x, mean_errors, yerr=std_errors, capsize=8, alpha=0.8, color='cornflowerblue', label='Mean ± Std')

# RMSE as dashed line
plt.plot(x, rmse_errors, marker='o', linestyle='--', color='darkorange', label='RMSE')

# Labels and ticks
plt.xticks(x, methods, rotation=30, ha='right')
plt.ylabel("Error")
plt.title("Mean ± Std and RMSE for All Configurations")
plt.grid(axis='y', linestyle='--', alpha=0.6)
plt.legend()

# Annotate bars with mean values
for i, bar in enumerate(bars):
    yval = bar.get_height()
    plt.text(bar.get_x() + bar.get_width()/2, yval + 0.05, f"{mean_errors[i]:.2f}", ha='center', va='bottom', fontsize=8)

# Annotate RMSE points
for i, y in enumerate(rmse_errors):
    plt.text(x[i], y + 0.05, f"{y:.2f}", ha='center', va='bottom', fontsize=8, color='darkorange')

plt.tight_layout()
plt.show()


# headup
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

# Load CSV and transpose
df = pd.read_csv('data.csv')
df = df.set_index('Metric').transpose()

# Filter only 'headup' configurations
headup_df = df[df.index.str.contains('headup', case=False)]

# Extract data
methods = headup_df.index.tolist()
mean_errors = headup_df['mean']
std_errors = headup_df['std']
rmse_errors = headup_df['rmse']

# X positions
x = np.arange(len(methods))

# Plot
plt.figure(figsize=(10, 6))

# Mean ± Std bars
bars = plt.bar(x, mean_errors, yerr=std_errors, capsize=8, alpha=0.8, color='steelblue', label='Mean ± Std')

# RMSE line
plt.plot(x, rmse_errors, marker='o', linestyle='--', color='darkorange', label='RMSE')

# Labels and ticks
plt.xticks(x, methods, rotation=20, ha='right')
plt.ylabel("Error")
plt.title("Headup Configurations: Mean ± Std and RMSE")
plt.grid(axis='y', linestyle='--', alpha=0.6)
plt.legend()

# Annotate mean values
for i, bar in enumerate(bars):
    yval = bar.get_height()
    plt.text(bar.get_x() + bar.get_width()/2, yval + 0.05, f"{mean_errors[i]:.2f}", ha='center', va='bottom', fontsize=8)

# Annotate RMSE values
for i, y in enumerate(rmse_errors):
    plt.text(x[i], y + 0.05, f"{y:.2f}", ha='center', va='bottom', fontsize=8, color='darkorange')

plt.tight_layout()
plt.show()

# birdeye
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

# Load CSV and transpose it
df = pd.read_csv('data.csv')
df = df.set_index('Metric').transpose()

# Filter only 'birdeye' configurations
birdeye_df = df[df.index.str.contains('birdeye', case=False)]

# Extract method names, mean, std, and rmse
methods = birdeye_df.index.tolist()
mean_errors = birdeye_df['mean']
std_errors = birdeye_df['std']
rmse_errors = birdeye_df['rmse']

# X positions
x = np.arange(len(methods))

# Plot
plt.figure(figsize=(10, 6))

# Bar chart for mean ± std
bars = plt.bar(x, mean_errors, yerr=std_errors, capsize=8, alpha=0.85, color='salmon', label='Mean ± Std')

# Plot RMSE as a dashed line
plt.plot(x, rmse_errors, marker='o', linestyle='--', color='darkorange', label='RMSE')

# Labeling
plt.xticks(x, methods, rotation=20, ha='right')
plt.ylabel("Error")
plt.title("Birdeye Configurations: Mean ± Std and RMSE")
plt.grid(axis='y', linestyle='--', alpha=0.6)
plt.legend()

# Annotate mean values
for i, bar in enumerate(bars):
    yval = bar.get_height()
    plt.text(bar.get_x() + bar.get_width()/2, yval + 0.05, f"{mean_errors[i]:.2f}", ha='center', va='bottom', fontsize=8)

# Annotate RMSE values
for i, y in enumerate(rmse_errors):
    plt.text(x[i], y + 0.05, f"{y:.2f}", ha='center', va='bottom', fontsize=8, color='darkorange')

plt.tight_layout()
plt.show()


import pandas as pd
import matplotlib.pyplot as plt

# Load the CSV and transpose
df = pd.read_csv('data.csv')
df = df.set_index('Metric').transpose()

# Extract data for box-like plot
methods = df.index.tolist()
mins = df['min']
medians = df['median']
maxs = df['max']
means = df['mean']
stds = df['std']

# Build simulated boxplot data (whiskers: min to max, center: median, overlay mean)
plt.figure(figsize=(12, 6))

# Plot each method
for i, method in enumerate(methods):
    # Whiskers: min to max
    plt.plot([i, i], [mins[i], maxs[i]], color='gray', linestyle='-', linewidth=1)
    # Median as a bold line
    plt.plot(i, medians[i], 's', color='blue', label='Median' if i == 0 else "")
    # Mean as a circle
    plt.plot(i, means[i], 'o', color='red', label='Mean' if i == 0 else "")
    # Error bar for ±1 std (not part of traditional boxplot, but informative)
    plt.errorbar(i, means[i], yerr=stds[i], fmt='none', ecolor='orange', elinewidth=1.5, capsize=5,
                 label='±1 Std' if i == 0 else "")

plt.xticks(range(len(methods)), methods, rotation=30, ha='right')
plt.ylabel("Error Value")
plt.title("Simulated Boxplot (Min–Max, Median, Mean ± Std) for All Configurations")
plt.grid(axis='y', linestyle='--', alpha=0.6)
plt.legend()
plt.tight_layout()
plt.show()
