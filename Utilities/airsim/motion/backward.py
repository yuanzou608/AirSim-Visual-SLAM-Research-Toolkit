import airsim
import time

client = airsim.MultirotorClient() # create drone object
client.enableApiControl(True) # disable this, manual(keyboard/controller) control active
client.armDisarm(True) # prepare for flight
client.takeoffAsync().join() # takeoff, join ensure takeoff completed to next step

client.moveByVelocityAsync(-2, 0, 0, 10).join() # move forward 2m/s, duration 10s


client.landAsync().join()
client.armDisarm(False) # disable motors
client.enableApiControl(False)