import airsim
import time

client = airsim.MultirotorClient() # create drone object
client.enableApiControl(True) # disable this, manual(keyboard/controller) control active
client.armDisarm(True) # prepare for flight
client.takeoffAsync().join() # takeoff, join ensure takeoff completed to next step
# client.landAsync().join()

client.moveToZAsync(-3, 1.5).join() # move to z = -3m, 1m/s
client.moveToPositionAsync(25, 0, -30, 1.5).join() # move to (50, 0, -30), 2m/s
client.moveToPositionAsync(25, 25, -30, 1.5).join()
client.moveToPositionAsync(-25, 25, -30, 1.5).join()
client.moveToPositionAsync(-25, -25, -30, 1.5).join()
client.moveToPositionAsync(25, -25, -30, 1.5).join()
client.moveToPositionAsync(0, 0, -10, 1.5).join()
client.moveToPositionAsync(0, 0, -3, 1.5).join()

client.landAsync().join()
client.armDisarm(False) # disable motors
client.enableApiControl(False)