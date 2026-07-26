import airsim

client = airsim.MultirotorClient() # create drone object
client.confirmConnection()
client.enableApiControl(True) # disable this, manual(keyboard/controller) control active
client.armDisarm(True) # prepare for flight



client.takeoffAsync().join() # takeoff, join ensure takeoff completed to next step
camera_info = client.simGetCameraInfo("front_center_custom")  # Camera ID 0 (front camera)
imu_info = client.simGetVehiclePose()

print("Camera Pose:", camera_info.pose)
print("\nImu pose: ", imu_info)

client.moveByVelocityAsync(0.1, 0.0, 0.0, 5).join()

camera_info = client.simGetCameraInfo("front_center_custom")  # Camera ID 0 (front camera)
imu_info = client.simGetVehiclePose()
print("\n\nCamera Pose:", camera_info.pose)
print("\nImu pose: ", imu_info)

client.landAsync().join()
client.armDisarm(False) # disable motors
client.enableApiControl(False)


