import airsim
import csv
import time

client = airsim.MultirotorClient()
client.confirmConnection()
client.armDisarm(False)
client.enableApiControl(False)

with open('imu_only_data.csv', 'w', newline='') as csvfile:
    writer = csv.writer(csvfile)
    writer.writerow(['timestamp', 'ax', 'ay', 'az', 'gx', 'gy', 'gz', 'ox', 'oy', 'oz', 'ow'])

    duration = 14400  # record 60s
    start_time = time.time()

    while time.time() - start_time < duration:
        imu = client.getImuData()
        t = imu.time_stamp / 1e9  # nanoseconds -> seconds
        ax, ay, az = imu.linear_acceleration.x_val, imu.linear_acceleration.y_val, imu.linear_acceleration.z_val
        gx, gy, gz = imu.angular_velocity.x_val, imu.angular_velocity.y_val, imu.angular_velocity.z_val
        ox, oy, oz, ow = imu.orientation.x_val, imu.orientation.y_val, imu.orientation.z_val, imu.orientation.w_val
        writer.writerow([t, ax, ay, az, gx, gy, gz, ox, oy, oz, ow])
        time.sleep(0.005)