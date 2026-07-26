import matplotlib
matplotlib.use('TkAgg')  # Force use of TkAgg backend

import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
from matplotlib.animation import FuncAnimation

# Load keyframes
timestamps = []
positions = []

keyframe_path = "/scripts/airsim/visualize/keyframe_latest.txt"

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

# Setup plot
fig = plt.figure()
ax = fig.add_subplot(111, projection='3d')
ax.set_xlim(min(xs), max(xs))
ax.set_ylim(min(ys), max(ys))
ax.set_zlim(min(zs), max(zs))
ax.set_xlabel('X')
ax.set_ylabel('Y')
ax.set_zlabel('Z')
ax.set_title('Dynamic Camera Path Visualization')

# Elements to update
line, = ax.plot([], [], [], color='blue', label='Trajectory')
point, = ax.plot([], [], [], 'ro')  # red point
timestamp_text = ax.text2D(0.05, 0.95, '', transform=ax.transAxes)

# Update function
def update(frame):
    line.set_data(xs[:frame], ys[:frame])
    line.set_3d_properties(zs[:frame])
    point.set_data([xs[frame-1]], [ys[frame-1]])
    point.set_3d_properties([zs[frame-1]])
    timestamp_text.set_text(f'Time: {timestamps[frame-1]:.2f}s')
    return line, point, timestamp_text

# Animate
ani = FuncAnimation(fig, update, frames=len(xs), interval=100, blit=False, repeat=False)

plt.legend()
plt.show()
