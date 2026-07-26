import airsim
import numpy as np
import time
import os

# Connect to AirSim running inside Docker
client = airsim.MultirotorClient(ip="127.0.0.1")  # Change IP if needed
client.confirmConnection()

response = client.simGetGroundTruthKinematics(vehicle_name='SimpleFlight')
response_imu = client.getImuData(vehicle_name='SimpleFlight')

print('ground_truth: ', response)
print('\n\nimu: ', response_imu)