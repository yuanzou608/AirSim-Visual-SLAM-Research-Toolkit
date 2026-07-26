import airsim
import time

# tf command
# ros2 run tf2_ros tf2_echo SimpleFlight/front_center_custom_body SimpleFlight/odom_local_ned
client = airsim.MultirotorClient() # create drone object
client.enableApiControl(True) # disable this, manual(keyboard/controller) control active
client.armDisarm(True) # prepare for flight
imu_info = client.getImuData()
front_center_custom_info = client.simGetCameraInfo('front_center_custom')
front_center_distortion = client.simGetDistortionParams('front_center_custom')

front_left_custom_info = client.simGetCameraInfo('front_left_custom')
front_left_distortion = client.simGetDistortionParams('front_left_custom')

front_right_custom_info = client.simGetCameraInfo('front_right_custom')
front_right_distortion = client.simGetDistortionParams('front_right_custom')

pose = client.getMultirotorState('SimpleFlight')
print(pose)


with open('sensor_info.txt', 'w') as sensor_info_file:
    sensor_info_file.write('IMU INFO\n')
    sensor_info_file.write(str(imu_info) + '\n\n')

    sensor_info_file.write('Front Center Custom Info\n')
    sensor_info_file.write(str(front_center_custom_info) + '\n\n')
    sensor_info_file.write('Front Center distortion\n')
    sensor_info_file.write(str(front_center_distortion) + '\n\n')

    sensor_info_file.write('Front Left Custom Info\n')
    sensor_info_file.write(str(front_left_custom_info) + '\n\n')
    sensor_info_file.write('Front Left Distortion\n')
    sensor_info_file.write(str(front_left_distortion) + '\n\n')

    sensor_info_file.write('Front Right Custom Info\n')
    sensor_info_file.write(str(front_right_custom_info) + '\n\n')
    sensor_info_file.write('Front Right Distortion\n')
    sensor_info_file.write(str(front_right_distortion) + '\n\n')


print('all sensor info done')
client.armDisarm(False) # disable motors
client.enableApiControl(False)