#!/usr/bin/env python3
import argparse, socket, struct, time
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image

class TelemetryPub(Node):
    def __init__(self, topic, host, port):
        super().__init__("telem_pub")
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.addr = (host, port)
        self.seq = 0
        self.create_subscription(Image, topic, self.cb, 10)
        self.get_logger().info(f"Sending telemetry to {host}:{port} from topic {topic}")

    def cb(self, msg: Image):
        self.seq += 1
        t_ns = time.time_ns()  # sender wallclock
        payload = struct.pack("!QQII", self.seq, t_ns, msg.width, msg.height)
        self.sock.sendto(payload, self.addr)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--topic", default="/camera/camera/color/image_raw")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=5601)
    args = ap.parse_args()
    rclpy.init()
    node = TelemetryPub(args.topic, args.host, args.port)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()
