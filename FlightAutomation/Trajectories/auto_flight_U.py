import airsim
import math
import time
import sys

client = airsim.MultirotorClient()
client.confirmConnection()
client.enableApiControl(True)
client.armDisarm(True)

velocity = 1.0

print("Taking off...")
client.takeoffAsync().join()

# 上升到 30 m 高度 (NED 坐标 z = -40)
target_altitude = -30
client.moveToZAsync(target_altitude, velocity=velocity).join()
print(f"Reached altitude {abs(target_altitude)} meters.")

print("Hovering at target altitude...")
client.hoverAsync().join()
time.sleep(10)

# ---------- 生成平滑飞行路径 ----------
path = []

# 折线段关键控制点
control_pts_1 = [
    airsim.Vector3r(10,   0, target_altitude),
    airsim.Vector3r(10, 20, target_altitude),
    airsim.Vector3r(20, 20, target_altitude),
    airsim.Vector3r(20, 0, -target_altitude),
    # airsim.Vector3r(50,   0, target_altitude),
    # airsim.Vector3r(60,  0, target_altitude),
    # airsim.Vector3r(60,-30, target_altitude)
]

control_pts_2 = [
    # airsim.Vector3r(10,   0, target_altitude),
    # airsim.Vector3r(10, -30, target_altitude),
    # airsim.Vector3r(50, -30, target_altitude),
    airsim.Vector3r(-20,   0, target_altitude),
    airsim.Vector3r(-20,  20, target_altitude),
    airsim.Vector3r(-10,20, target_altitude),
    airsim.Vector3r(-10,0, target_altitude),
    airsim.Vector3r(0,0, target_altitude),
]
# 直线细分：每 5 m 插入一个点
seg_step = 2
def add_segment(p1, p2):
    dx, dy = p2.x_val - p1.x_val, p2.y_val - p1.y_val
    dist = math.hypot(dx, dy)
    n = max(1, int(dist / seg_step))
    for k in range(1, n + 1):
        t = k / n
        path.append(airsim.Vector3r(p1.x_val + dx * t,
                                    p1.y_val + dy * t,
                                    p1.z_val))

# 折线路段1
for i in range(len(control_pts_1) - 1):
    add_segment(control_pts_1[i], control_pts_1[i + 1])

# 半圆轨迹 (中心 (50,-50), 半径 50 m)
center_x, center_y, radius = 0, 0, 20
num_points = 36
for i in range(num_points + 1):
    theta = -math.pi * i / num_points      # 0 → π，逆时针
    x = center_x + radius * math.cos(theta)
    y = center_y + radius * math.sin(theta)
    path.append(airsim.Vector3r(x, y, target_altitude))

# 折线路段2
for i in range(len(control_pts_2) - 1):
    add_segment(control_pts_2[i], control_pts_2[i + 1])

# # 从 (-50,0) 回到 (0,0)
# add_segment(airsim.Vector3r(-20, 0, target_altitude),
#             airsim.Vector3r(  0, 0, target_altitude))

# ---------- 执行飞行 ----------
print("Moving to start of path...")
client.moveToPositionAsync(0, 0, target_altitude, velocity=velocity).join()

print("Following complex path (smoothed)...")
client.moveOnPathAsync(
    path,
    velocity=velocity,
    drivetrain=airsim.DrivetrainType.MaxDegreeOfFreedom,  # 允许机头自由旋转
    yaw_mode=airsim.YawMode(False, 0),                    # 保持朝向与轨迹一致
    lookahead=5,                                         # 预判 20 m
    adaptive_lookahead=1                                  # 根据速度自适应
).join()

# ✅ 回到原点后悬停 5 秒
print("Hovering at final position...")
client.hoverAsync().join()
time.sleep(5)

# # move to higher for whole map
# client.moveToZAsync(-100, velocity=10).join()
# client.hoverAsync().join()
# time.sleep(100)

# 降落
print("Descending to landing height...")
client.moveToZAsync(-5, velocity=velocity).join()

print("Landing...")
client.landAsync().join()
client.armDisarm(False)
client.enableApiControl(False)
print("Flight complete.")
