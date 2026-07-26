import matplotlib
matplotlib.use('TkAgg')

import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
from matplotlib.animation import FuncAnimation

# --- Load Estimated Keyframes ---
timestamps = []
positions = []

keyframe_path = "/home/yuan/dataset/textslam/Seq_01/keyframe.txt"

with open(keyframe_path, 'r') as f:
    for line in f:
        parts = line.strip().split()
        if len(parts) != 8:
            continue
        timestamp = float(parts[0])
        x, y, z = map(float, parts[1:4])
        timestamps.append(timestamp)
        positions.append((x, y, z))

xs = [p[0] for p in positions]
ys = [p[1] for p in positions]
zs = [p[2] for p in positions]

# --- Load Ground Truth Path ---
gt_path = "/home/yuan/dataset/textslam/Seq_01/gt.txt"  # <-- change if needed
gt_positions = []

with open(gt_path, 'r') as f:
    for line in f:
        parts = line.strip().split()
        if len(parts) != 8:
            continue
        x, y, z = map(float, parts[1:4])
        gt_positions.append((x, y, z))

gt_xs = [p[0] for p in gt_positions]
gt_ys = [p[1] for p in gt_positions]
gt_zs = [p[2] for p in gt_positions]

# --- Setup Plot ---
fig = plt.figure()
ax = fig.add_subplot(111, projection='3d')

all_x = xs + gt_xs
all_y = ys + gt_ys
all_z = zs + gt_zs

ax.set_xlim(min(all_x), max(all_x))
ax.set_ylim(min(all_y), max(all_y))
ax.set_zlim(min(all_z), max(all_z))
ax.set_xlabel('X')
ax.set_ylabel('Y')
ax.set_zlabel('Z')
ax.set_title('Estimated (Blue) vs Ground Truth (Red) Trajectory')

# Ground Truth (Static)
ax.plot(gt_xs, gt_ys, gt_zs, color='red', label='Ground Truth')

# Estimated (Animated)
line, = ax.plot([], [], [], color='blue', label='Estimated Trajectory')
point, = ax.plot([], [], [], 'ro')
timestamp_text = ax.text2D(0.05, 0.95, '', transform=ax.transAxes)

def update(frame):
    line.set_data(xs[:frame], ys[:frame])
    line.set_3d_properties(zs[:frame])
    point.set_data([xs[frame-1]], [ys[frame-1]])
    point.set_3d_properties([zs[frame-1]])
    timestamp_text.set_text(f'Time: {timestamps[frame-1]:.2f}s')
    return line, point, timestamp_text

ani = FuncAnimation(fig, update, frames=len(xs), interval=100, blit=False, repeat=False)

plt.legend()
plt.show()
