import airsim
import math
import time

# Connect to the AirSim simulator
client = airsim.MultirotorClient()
client.confirmConnection()
client.enableApiControl(True)
client.armDisarm(True)

<<<<<<< HEAD
velocity = 1.0
=======
velocity = 1.5
>>>>>>> origin/main
# Takeoff to a small default height
print("Taking off...")
client.takeoffAsync().join()

# Climb to the target altitude (-25 m means 25 m above ground, since NED uses negative up)
target_altitude = -30  # 25 meters above ground
radius = 25.0 # 25 radius
client.moveToPositionAsync(radius, 0, target_altitude, velocity).join()  # move vertically to altitude
print(f"Reached altitude {abs(target_altitude)} meters.")

# Define circle parameters
center_x, center_y, center_z = 0, 0, target_altitude  # center of circle at (0,0) horizontal, and at current altitude

num_points = 72  # number of waypoints around the circle (the more points, the smoother the circle)

# Generate waypoints around the circle
waypoints = []
for i in range(num_points + 1):  # +1 to bring it back to start point
    theta = 2 * math.pi * i / num_points
    # Circle parametric equations for clockwise direction (NED: X=north, Y=east)
    x = center_x + radius * math.cos(theta)
    y = center_y + radius * math.sin(theta)
    z = center_z
    waypoints.append(airsim.Vector3r(x, y, z))

# Move to the first waypoint (start of circle) to avoid a sudden lateral jump from current position
start = waypoints[0]
print("Moving to start of circle...")
client.moveToPositionAsync(start.x_val, start.y_val, start.z_val, velocity=velocity).join()

# Fly along the circular path
print("Flying in a circle...")
# Use ForwardOnly so drone points forward along the path, and default yaw_mode (no continuous spin)
client.moveOnPathAsync(waypoints, velocity=velocity,
                       drivetrain=airsim.DrivetrainType.ForwardOnly,
                       yaw_mode=airsim.YawMode(False, 0)).join()
# (yaw_mode set to False with 0 means hold a specific yaw orientation; with ForwardOnly,
# the drone will yaw to face the path direction&#8203;:contentReference[oaicite:5]{index=5}.)
print("back to origin...")
client.moveToPositionAsync(0, 0, -30, velocity=velocity).join()
print("Landing...")
client.hoverAsync().join()
time.sleep(5)
client.moveToZAsync(-5, velocity=velocity).join() # move to z = -3m, 1m/s

# After path complete, command landing
client.landAsync().join()
client.armDisarm(False)
client.enableApiControl(False)
print("Flight complete. Drone has landed.")
