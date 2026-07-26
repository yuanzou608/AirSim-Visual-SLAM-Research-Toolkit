#!/usr/bin/env python3
import airsim
import time
import numpy as np
from scipy.spatial.transform import Rotation as R

# Connect to AirSim
client = airsim.MultirotorClient()
client.confirmConnection()
client.enableApiControl(True)
client.armDisarm(True)
client.takeoffAsync().join()

# Initial velocities
vx, vy, vz = 0, 0, 0

# Constant acceleration
ax = 1.0  # m/s^2
dt = 0.1  # time step (s)
duration = 5  # total duration (s)

steps = int(duration / dt)
gravity = 9.8

print(f"\nStarting constant acceleration test in +X direction...")

for i in range(steps):
    vx += ax * dt  # update velocity
    client.moveByVelocityAsync(vx, vy, vz, dt).join()

    imu = client.getImuData()
    kinematics = client.simGetGroundTruthKinematics()

    # --- Transform Ground Truth Acceleration (World → Body Frame) ---
    acc_world = np.array([
        kinematics.linear_acceleration.x_val,
        kinematics.linear_acceleration.y_val,
        kinematics.linear_acceleration.z_val
    ])

    acc_world_nogravity = acc_world - np.array([0, 0, gravity])  # subtract gravity (NED: Z-down)

    q = kinematics.orientation
    r = R.from_quat([q.x_val, q.y_val, q.z_val, q.w_val])
    acc_body = r.inv().apply(acc_world_nogravity)  # rotate into body frame

    # --- Output for Comparison ---
    print(f"\nTime: {i*dt:.1f}s")
    print(f"GT Acc Body X: {acc_body[0]: .4f} | IMU X: {imu.linear_acceleration.x_val: .4f}")
    print(f"GT Acc Body Y: {acc_body[1]: .4f} | IMU Y: {imu.linear_acceleration.y_val: .4f}")
    print(f"GT Acc Body Z: {acc_body[2]: .4f} | IMU Z: {imu.linear_acceleration.z_val: .4f}")

# Stop drone
client.hoverAsync().join()
client.landAsync().join()
client.armDisarm(False)
client.enableApiControl(False)

print("\nTest complete.")
