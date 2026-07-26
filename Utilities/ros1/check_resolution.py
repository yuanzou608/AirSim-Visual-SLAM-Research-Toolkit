#!/usr/bin/env python
import rospy
from sensor_msgs.msg import Image
import time

frame_count = 0
start_time = None
fps_window = 5.0  # seconds to average FPS over

def callback(msg):
    global frame_count, start_time

    if start_time is None:
        start_time = time.time()
        print("当前 RealSense 分辨率：{} x {}".format(msg.width, msg.height))

    frame_count += 1
    elapsed_time = time.time() - start_time

    if elapsed_time >= fps_window:
        fps = frame_count / elapsed_time
        print("当前 RealSense FPS：{:.2f}".format(fps))
        rospy.signal_shutdown("Got resolution and FPS")

def main():
    rospy.init_node('realsense_resolution_fps_checker', anonymous=True)
    rospy.Subscriber("/camera/color/image_raw", Image, callback)
    rospy.spin()

if __name__ == "__main__":
    main()
