# Create a Python script that subscribes to a ROS 2 image topic, encodes frames to H.264/H.265
# using ffmpeg via stdin, and reports the average bandwidth at the end.
# The script doesn't require cv_bridge; it streams raw RGB/BGR bytes to ffmpeg.
# It stops after a user-specified duration.
#!/usr/bin/env python3
import argparse
import os
import shlex
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Optional

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image

# Map ROS encoding -> ffmpeg pix_fmt and byte depth
PIXFMT_MAP = {
    "rgb8": "rgb24",
    "bgr8": "bgr24",
    # You can expand as needed
}

@dataclass
class EncConfig:
    codec: str           # 'h264' or 'h265'
    mode: str            # 'cbr' or 'crf'
    bitrate: Optional[str] = None  # e.g. '4M'
    crf: Optional[int] = None
    preset: str = "veryfast"
    tune: str = "zerolatency"
    outfile: str = "encoded.mp4"
    fps_hint: Optional[float] = None

class H26xEncoder(Node):
    def __init__(self, topic: str, cfg: EncConfig, duration: float):
        super().__init__("rgb_h26x_encoder")
        self.topic = topic
        self.cfg = cfg
        self.duration = duration

        self.width = None
        self.height = None
        self.pixfmt = None
        self.first_ts = None
        self.last_ts = None
        self.frame_count = 0

        self.ffmpeg = None
        self.ffmpeg_bytes_written = 0
        self.shutdown_time = time.time() + duration if duration > 0 else None

        self.sub = self.create_subscription(Image, topic, self.cb, 10)
        if self.shutdown_time is not None:
            self.timer = self.create_timer(0.1, self._check_timeout)
        self.get_logger().info(f"Subscribing to {topic} and writing {cfg.codec.upper()} to {cfg.outfile}")

    def _start_ffmpeg(self):
        assert self.width and self.height and self.pixfmt
        # Build encoder args
        if self.cfg.codec == "h265":
            vcodec = "libx265"
        else:
            vcodec = "libx264"

        if self.cfg.mode == "cbr":
            if not self.cfg.bitrate:
                raise RuntimeError("CBR mode requires --bitrate like 4M")
            enc_args = [
                "-c:v", vcodec,
                "-preset", self.cfg.preset,
                "-tune", self.cfg.tune,
                "-b:v", self.cfg.bitrate,
                "-maxrate", self.cfg.bitrate,
                "-bufsize", str(int(int(self.cfg.bitrate.rstrip('kKmM'))*2)) + self.cfg.bitrate[-1] if self.cfg.bitrate[-1] in "kKmM" else self.cfg.bitrate,
            ]
        else:  # CRF
            if self.cfg.crf is None:
                self.cfg.crf = 23
            enc_args = [
                "-c:v", vcodec,
                "-preset", self.cfg.preset,
                "-tune", self.cfg.tune,
                "-crf", str(self.cfg.crf),
            ]

        fps = self.cfg.fps_hint if self.cfg.fps_hint else 30.0  # best-effort hint; real pacing comes from incoming messages
        input_args = [
            "-f", "rawvideo",
            "-pix_fmt", self.pixfmt,
            "-s", f"{self.width}x{self.height}",
            "-r", f"{fps}",
            "-i", "pipe:0",
        ]
        output_args = [
            "-an", "-sn",
            "-movflags", "+faststart",
            "-f", "mp4", self.cfg.outfile,
        ]
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error"] + input_args + enc_args + output_args
        self.get_logger().info("Starting ffmpeg: " + " ".join(shlex.quote(c) for c in cmd))
        self.ffmpeg = subprocess.Popen(cmd, stdin=subprocess.PIPE)

    def _check_timeout(self):
        if self.shutdown_time and time.time() >= self.shutdown_time:
            self.get_logger().info("Duration reached; stopping encoder...")
            self._stop()
            rclpy.shutdown()

    def _stop(self):
        if self.ffmpeg:
            try:
                self.ffmpeg.stdin.close()
            except Exception:
                pass
            try:
                self.ffmpeg.wait(timeout=5)
            except Exception:
                self.ffmpeg.kill()
        if self.first_ts and self.last_ts and self.last_ts > self.first_ts:
            dur = self.last_ts - self.first_ts
        else:
            dur = 0.0
        size_bytes = os.path.getsize(self.cfg.outfile) if os.path.exists(self.cfg.outfile) else 0
        if dur > 0:
            mib_s = (size_bytes / dur) / (1024*1024)
            mb_s = (size_bytes / dur) / 1_000_000
            mbit_s = (size_bytes * 8 / dur) / 1_000_000
            fps = self.frame_count / dur
        else:
            mib_s = mb_s = mbit_s = fps = 0.0
        self.get_logger().info(f"Frames: {self.frame_count}, span={dur:.3f}s, file={size_bytes} bytes")
        self.get_logger().info(f"Avg bitrate: {mb_s:.2f} MB/s | {mib_s:.2f} MiB/s | {mbit_s:.2f} Mb/s; FPS~{fps:.2f}")
        print(f"\n=== RESULT ===\nFile: {self.cfg.outfile}\nFrames: {self.frame_count}\nSpan: {dur:.3f} s\n"
              f"Avg bitrate: {mb_s:.2f} MB/s | {mib_s:.2f} MiB/s | {mbit_s:.2f} Mb/s\nFPS~{fps:.2f}")

    def cb(self, msg: Image):
        if self.pixfmt is None:
            if msg.encoding not in PIXFMT_MAP:
                self.get_logger().error(f"Unsupported encoding '{msg.encoding}'. Supported: {list(PIXFMT_MAP)}")
                return
            self.pixfmt = PIXFMT_MAP[msg.encoding]
            self.width, self.height = msg.width, msg.height
            self._start_ffmpeg()
            self.first_ts = msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9
        self.last_ts = msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9
        # Write raw bytes to ffmpeg
        try:
            self.ffmpeg.stdin.write(msg.data)
        except BrokenPipeError:
            self.get_logger().warn("ffmpeg stdin closed unexpectedly")
        self.frame_count += 1

def main():
    parser = argparse.ArgumentParser(description="Encode a ROS 2 Image topic to H.264/H.265 with ffmpeg and report average bandwidth.")
    parser.add_argument("--topic", default="/camera/camera/color/image_raw", help="Image topic to subscribe")
    parser.add_argument("--codec", choices=["h264", "h265"], default="h264")
    parser.add_argument("--mode", choices=["cbr", "crf"], default="crf")
    parser.add_argument("--bitrate", help="Target bitrate for CBR (e.g., 4M)")
    parser.add_argument("--crf", type=int, help="CRF value for quality-based mode (default 23)")
    parser.add_argument("--preset", default="veryfast")
    parser.add_argument("--tune", default="zerolatency")
    parser.add_argument("--outfile", default="encoded.mp4")
    parser.add_argument("--duration", type=float, default=60.0, help="Seconds to run (0=run until Ctrl+C)")
    parser.add_argument("--fps-hint", type=float, default=None, help="Input fps hint for ffmpeg (e.g., 30)")
    args = parser.parse_args()

    cfg = EncConfig(codec=args.codec, mode=args.mode, bitrate=args.bitrate, crf=args.crf,
                    preset=args.preset, tune=args.tune, outfile=args.outfile, fps_hint=args.fps_hint)

    rclpy.init()
    node = H26xEncoder(args.topic, cfg, args.duration)

    def handle_sigint(sig, frame):
        node.get_logger().info("Ctrl+C received; stopping...")
        node._stop()
        rclpy.shutdown()
    signal.signal(signal.SIGINT, handle_sigint)

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info("KeyboardInterrupt")
    finally:
        if rclpy.ok():
            node._stop()
            rclpy.shutdown()

if __name__ == "__main__":
    main()


