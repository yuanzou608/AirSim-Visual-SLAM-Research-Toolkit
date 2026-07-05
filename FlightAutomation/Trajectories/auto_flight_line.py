import airsim
import time

client = airsim.MultirotorClient() # create drone object
client.enableApiControl(True) # disable this, manual(keyboard/controller) control active
client.armDisarm(True) # prepare for flight
client.takeoffAsync().join() # takeoff, join ensure takeoff completed to next step

duration = 60
client.moveByVelocityAsync(0.0, 0, -1, 6).join()
print("Hovering at target altitude...")
client.hoverAsync().join()
time.sleep(5)
print("start moving flight...")
client.moveByVelocityAsync(1, 0, 0, duration).join()

client.landAsync().join()
client.armDisarm(False) # disable motors
client.enableApiControl(False)
