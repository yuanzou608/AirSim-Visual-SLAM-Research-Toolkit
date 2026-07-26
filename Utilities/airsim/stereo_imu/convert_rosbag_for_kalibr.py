import rospy
import rosbag
from sensor_msgs.msg import Imu
import csv

bag = rosbag.Bag('imu_noise.bag', 'w')
frame_id = 'imu_link'

with open('imu_only_data.csv') as csvfile:
    reader = csv.DictReader(csvfile)
    for row in reader:
        imu_msg = Imu()
        imu_msg.header.stamp = rospy.Time.from_sec(float(row['timestamp']))
        imu_msg.header.frame_id = frame_id

        imu_msg.linear_acceleration.x = float(row['ax'])
        imu_msg.linear_acceleration.y = float(row['ay'])
        imu_msg.linear_acceleration.z = float(row['az'])

        imu_msg.angular_velocity.x = float(row['gx'])
        imu_msg.angular_velocity.y = float(row['gy'])
        imu_msg.angular_velocity.z = float(row['gz'])

        bag.write('/imu0', imu_msg, imu_msg.header.stamp)

bag.close()
