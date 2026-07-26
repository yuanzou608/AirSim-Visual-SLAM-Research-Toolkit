#!/usr/bin/env python
import rospy
from sensor_msgs.msg import Image
import time

class StreamMonitor:
    def __init__(self, name):
        self.name = name
        self.total_bytes = 0
        self.instant_bytes = 0
        self.max_bandwidth = 0  # MB/s

    def update(self, msg_size):
        self.total_bytes += msg_size
        self.instant_bytes += msg_size

    def reset_instant(self):
        inst_bw = self.instant_bytes / 1024.0 / 1024.0
        self.max_bandwidth = max(self.max_bandwidth, inst_bw)
        self.instant_bytes = 0
        return inst_bw

    def avg_bandwidth(self, duration):
        return self.total_bytes / 1024.0 / 1024.0 / duration

def monitor_all_streams(sample_time=10):
    rospy.init_node("multi_stream_bandwidth_monitor")

    streams = {
        "/camera/color/image_raw": StreamMonitor("RGB"),
        "/camera/depth/image_rect_raw": StreamMonitor("Depth"),
        "/camera/infra1/image_rect_raw": StreamMonitor("Infra1"),
        "/camera/infra2/image_rect_raw": StreamMonitor("Infra2"),
    }

    start_time = time.time()
    last_second = start_time

    def make_callback(topic):
        def callback(msg):
            streams[topic].update(len(msg.data))
        return callback

    for topic in streams:
        rospy.Subscriber(topic, Image, make_callback(topic))
        rospy.loginfo("订阅话题: {}".format(topic))

    rate = rospy.Rate(10)  # 10Hz 循环检查时间
    print("采样 {} 秒中，请稍候...\n".format(sample_time))
    while not rospy.is_shutdown():
        now = time.time()
        elapsed = now - start_time

        if now - last_second >= 1.0:
            print("⏱️ [瞬时带宽]")
            total_inst_bw = 0
            for topic, monitor in streams.items():
                bw = monitor.reset_instant()
                total_inst_bw += bw
                print("  {:<25} {:.2f} MB/s".format(topic, bw))
            print("  {:<25} {:.2f} MB/s\n".format("TOTAL", total_inst_bw))
            last_second = now

        if elapsed >= sample_time:
            break
        rate.sleep()

    print("✅ 测量完成，结果如下：\n")
    total_avg_bw = 0
    total_max_bw = 0
    for topic, monitor in streams.items():
        avg = monitor.avg_bandwidth(sample_time)
        max_ = monitor.max_bandwidth
        total_avg_bw += avg
        total_max_bw += max_
        print("📦 {:<25} 平均: {:.2f} MB/s   最大: {:.2f} MB/s".format(topic, avg, max_))
    print("\n🚀 总平均带宽: {:.2f} MB/s".format(total_avg_bw))
    print("🚀 总最大带宽: {:.2f} MB/s".format(total_max_bw))

    rospy.signal_shutdown("Sampling complete")

if __name__ == "__main__":
    monitor_all_streams(sample_time=10)
