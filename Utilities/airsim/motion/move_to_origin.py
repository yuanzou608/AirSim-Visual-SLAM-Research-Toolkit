import airsim
import time

client = airsim.MultirotorClient() # create drone object
client.enableApiControl(True) # disable this, manual(keyboard/controller) control active
client.armDisarm(True) # prepare for flight
client.takeoffAsync().join() # takeoff, join ensure takeoff completed to next step
# client.landAsync().join()

client.moveToZAsync(-5, 1).join() # move to z = -3m, 1m/s
client.moveToPositionAsync(0, 0, -10, 1).join()
yaw_angle = 0 # 90 right, 180 backward, -90 left, 0 forward
client.rotateToYawAsync(yaw_angle).join()
client.moveToZAsync(-3, 1).join()
client.landAsync().join()
client.armDisarm(False) # disable motors
client.enableApiControl(False)
