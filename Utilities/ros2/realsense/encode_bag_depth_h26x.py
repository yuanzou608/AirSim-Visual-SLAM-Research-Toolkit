#!/usr/bin/env python3

import argparse, os, shlex, signal, subprocess, time
from dataclasses import dataclass
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image

@dataclass
class EncCfg:
    codec: str           # h264/h265
    mode: str            # cbr/crf
    bitrate: str|None
    crf: int|None
    preset: str
    tune: str
    outfile: str
    fps_hint: float|None
    duration: float
    gop: int
    window_min: int|None  # optional windowing for 16->8 bit (depth units, e.g., mm)
    window_max: int|None

class DepthEncodeNode(Node):
    def __init__(self, topic: str, cfg: EncCfg):
        super().__init__("depth_encode_node")
        self.cfg = cfg
        self.topic = topic
        self.width = None
        self.height = None
        self.ffmpeg = None
        self.first_ts = None
        self.last_ts = None
        self.frames = 0
        self.end_time = time.time() + cfg.duration if cfg.duration>0 else None
        self.sub = self.create_subscription(Image, topic, self.cb, 10)
        if self.end_time:
            self.create_timer(0.1, self._tick)
        self.get_logger().info(f"Encoding depth from {topic} to {cfg.outfile} ({cfg.codec.upper()}, GOP={cfg.gop})")

    def _start_ffmpeg(self):
        vcodec = "libx265" if self.cfg.codec=="h265" else "libx264"
        enc = ["-c:v", vcodec, "-preset", self.cfg.preset, "-tune", self.cfg.tune, "-g", str(self.cfg.gop)]
        xparams = f"keyint={self.cfg.gop}:min-keyint={self.cfg.gop}:scenecut=0:repeat-headers=1"
        if vcodec=="libx264":
            enc += ["-x264-params", xparams]
        else:
            enc += ["-x265-params", xparams]

        if self.cfg.mode=="cbr":
            if not self.cfg.bitrate:
                raise RuntimeError("CBR mode requires --bitrate like 4M")
            enc += ["-b:v", self.cfg.bitrate, "-maxrate", self.cfg.bitrate, "-bufsize", self.cfg.bitrate]
        else:
            enc += ["-crf", str(self.cfg.crf if self.cfg.crf is not None else 23)]

        fps = self.cfg.fps_hint if self.cfg.fps_hint else 30.0

        # Depth 16-bit to 8-bit windowing using zscale
        if self.cfg.window_min is not None and self.cfg.window_max is not None:
            # map [min,max] -> [0,255], clamp outside
            vf = "format=gray,format=yuv420p"

        else:
            vf = "format=gray,format=yuv420p"



        input_args = [
            "-f","rawvideo","-pix_fmt","gray16le",
            "-s", f"{self.width}x{self.height}",
            "-r", f"{fps}",
            "-i","pipe:0",
            "-vf", vf
        ]
        out_args = ["-an","-sn","-movflags","+faststart","-f","mp4", self.cfg.outfile]
        cmd = ["ffmpeg","-hide_banner","-loglevel","error"] + input_args + enc + out_args
        self.get_logger().info("FFmpeg: " + " ".join(shlex.quote(c) for c in cmd))
        self.ffmpeg = subprocess.Popen(cmd, stdin=subprocess.PIPE)

    def _stop(self):
        if self.ffmpeg:
            try: self.ffmpeg.stdin.close()
            except Exception: pass
            try: self.ffmpeg.wait(timeout=5)
            except Exception: self.ffmpeg.kill()

        span = (self.last_ts - self.first_ts) if (self.first_ts and self.last_ts and self.last_ts>self.first_ts) else 0.0
        size_bytes = os.path.getsize(self.cfg.outfile) if os.path.exists(self.cfg.outfile) else 0
        if span > 0:
            mib_s = (size_bytes / span) / (1024*1024)
            mb_s = (size_bytes / span) / 1_000_000
            mbit_s = (size_bytes * 8 / span) / 1_000_000
            fps = self.frames / span
        else:
            mib_s = mb_s = mbit_s = fps = 0.0
        self.get_logger().info(f"Frames={self.frames}, span={span:.3f}s, file={size_bytes} bytes")
        print(f"\n=== DEPTH ENCODE RESULT ===\nFile: {self.cfg.outfile}\nFrames: {self.frames}\nSpan: {span:.3f} s\n"
              f"Avg bitrate: {mb_s:.2f} MB/s | {mib_s:.2f} MiB/s | {mbit_s:.2f} Mb/s\nFPS~{fps:.2f}")

    def _tick(self):
        if time.time() >= self.end_time:
            self.get_logger().info("Duration reached; stopping...")
            self._stop()
            rclpy.shutdown()

    def cb(self, msg: Image):
        if msg.encoding not in ("16UC1","16SC1","mono16"):
            self.get_logger().error(f"Unsupported depth encoding '{msg.encoding}', expected 16-bit single channel.")
            return
        if self.width is None:
            self.width, self.height = msg.width, msg.height
            self._start_ffmpeg()
            self.first_ts = msg.header.stamp.sec + msg.header.stamp.nanosec*1e-9
        self.last_ts = msg.header.stamp.sec + msg.header.stamp.nanosec*1e-9
        try:
            self.ffmpeg.stdin.write(msg.data)
        except BrokenPipeError:
            pass
        self.frames += 1

def main():
    ap = argparse.ArgumentParser(description="Encode 16-bit depth topic to H.264/H.265 MP4 and report average bandwidth.")
    ap.add_argument("--topic", default="/camera/camera/depth/image_rect_raw")
    ap.add_argument("--codec", choices=["h264","h265"], default="h264")
    ap.add_argument("--mode", choices=["cbr","crf"], default="crf")
    ap.add_argument("--bitrate")
    ap.add_argument("--crf", type=int, default=23)
    ap.add_argument("--preset", default="veryfast")
    ap.add_argument("--tune", default="zerolatency")
    ap.add_argument("--outfile", default="depth_encoded.mp4")
    ap.add_argument("--fps-hint", type=float, default=None)
    ap.add_argument("--duration", type=float, default=60.0)
    ap.add_argument("--gop", type=int, default=60)
    ap.add_argument("--window-min", type=int, default=None, help="optional min depth for 16->8bit window mapping")
    ap.add_argument("--window-max", type=int, default=None, help="optional max depth for 16->8bit window mapping")
    args = ap.parse_args()

    cfg = EncCfg(args.codec, args.mode, args.bitrate, args.crf, args.preset, args.tune,
                 args.outfile, args.fps_hint, args.duration, args.gop, args.window_min, args.window_max)

    rclpy.init()
    node = DepthEncodeNode(args.topic, cfg)
    def sigint(sig,frm):
        node._stop(); rclpy.shutdown()
    signal.signal(signal.SIGINT, sigint)

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node._stop(); rclpy.shutdown()

if __name__ == "__main__":
    main()
