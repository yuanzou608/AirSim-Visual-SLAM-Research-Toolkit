import airsim
import time
import numpy as np

client = airsim.MultirotorClient() # create drone object
client.enableApiControl(True) # disable this, manual(keyboard/controller) control active
client.armDisarm(True) # prepare for flight
client.takeoffAsync().join() # takeoff, join ensure takeoff completed to next step

client.moveToPositionAsync(0, 0, 0, 5).join() # move to (130, 0, -2), velocity 2m/s

client.hoverAsync().join()