#!/usr/bin/env python3
import argparse, os, shlex, signal, subprocess, time
from dataclasses import dataclass
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image

@dataclass
class Cfg:
    codec: str
    mode: str
    bitrate: str|None
    crf: int|None
    preset: str
    tune: str
    out: str
    fps_hint: float|None
    duration: float
    gop: int
    pkt_size: int
    resend_headers: bool

class DepthStreamer(Node):
    def __init__(self, topic: str, cfg: Cfg):
        super().__init__("depth_streamer")
        self.topic = topic
        self.cfg = cfg
        self.width = None
        self.height = None
        self.ffmpeg = None
        self.first_ts = None
        self.last_ts = None
        self.frames = 0
        self.end_time = time.time() + cfg.duration if cfg.duration>0 else None
        self.create_subscription(Image, topic, self.cb, 10)
        if self.end_time: self.create_timer(0.1, self._tick)
        self.get_logger().info(f"{topic} -> {cfg.codec.upper()} (UDP mpegts) to {cfg.out} (GOP={cfg.gop})")

    def _start_ffmpeg(self):
        vcodec = "libx265" if self.cfg.codec=="h265" else "libx264"
        enc = ["-c:v", vcodec, "-preset", self.cfg.preset, "-tune", self.cfg.tune, "-g", str(self.cfg.gop)]
        # repeat headers on keyframes
        xparams = f"keyint={self.cfg.gop}:min-keyint={self.cfg.gop}:scenecut=0:repeat-headers=1"
        if vcodec == "libx264":
            enc += ["-x264-params", xparams]
        else:
            enc += ["-x265-params", xparams]

        if self.cfg.mode=="cbr":
            if not self.cfg.bitrate: raise RuntimeError("CBR requires --bitrate like 4M")
            enc += ["-b:v", self.cfg.bitrate, "-maxrate", self.cfg.bitrate, "-bufsize", self.cfg.bitrate]
        else:
            enc += ["-crf", str(self.cfg.crf if self.cfg.crf is not None else 23)]

        fps = self.cfg.fps_hint if self.cfg.fps_hint else 30.0
        # Convert 16-bit gray -> 8-bit gray with zscale, then to yuv420p for encoder
        vf = "zscale=rin=16:r=8,format=gray,format=yuv420p"
        input_args = [
            "-f","rawvideo","-pix_fmt","gray16le",
            "-s", f"{self.width}x{self.height}",
            "-r", f"{fps}",
            "-i","pipe:0",
            "-vf", vf
        ]
        # MPEG-TS over UDP
        out_url = self.cfg.out
        if out_url.startswith("udp://"):
            if "?" in out_url:
                out_url += f"&pkt_size={self.cfg.pkt_size}&reuse=1&fifo_size=1000000"
            else:
                out_url += f"?pkt_size={self.cfg.pkt_size}&reuse=1&fifo_size=1000000"
        out_args = ["-f","mpegts","-muxdelay","0","-muxpreload","0"]
        if self.cfg.resend_headers:
            out_args += ["-mpegts_flags","+resend_headers"]
        out_args += [out_url]

        cmd = ["ffmpeg","-hide_banner","-loglevel","error"] + input_args + enc + out_args
        self.get_logger().info("FFmpeg: " + " ".join(shlex.quote(c) for c in cmd))
        self.ffmpeg = subprocess.Popen(cmd, stdin=subprocess.PIPE)

    def _stop(self):
        if self.ffmpeg:
            try: self.ffmpeg.stdin.close()
            except Exception: pass
            try: self.ffmpeg.wait(timeout=3)
            except Exception: self.ffmpeg.kill()
        span = (self.last_ts - self.first_ts) if (self.first_ts and self.last_ts and self.last_ts>self.first_ts) else 0.0
        self.get_logger().info(f"Frames={self.frames}, span={span:.3f}s -> {self.cfg.out}")

    def _tick(self):
        if time.time() >= self.end_time:
            self.get_logger().info("Duration reached; stopping."); self._stop(); rclpy.shutdown()

    def cb(self, msg: Image):
        # Expect depth encoding like "16UC1" (little endian)
        if msg.encoding not in ("16UC1","mono16","16SC1"):
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
    ap = argparse.ArgumentParser(description="Stream 16-bit depth as H.264/H.265 over UDP (for bandwidth testing).")
    ap.add_argument("--topic", default="/camera/camera/depth/image_rect_raw")
    ap.add_argument("--codec", choices=["h264","h265"], default="h264")
    ap.add_argument("--mode", choices=["cbr","crf"], default="crf")
    ap.add_argument("--bitrate")
    ap.add_argument("--crf", type=int, default=23)
    ap.add_argument("--preset", default="veryfast")
    ap.add_argument("--tune", default="zerolatency")
    ap.add_argument("--out", default="udp://127.0.0.1:5602")
    ap.add_argument("--fps-hint", type=float, default=None)
    ap.add_argument("--duration", type=float, default=0.0)
    ap.add_argument("--gop", type=int, default=60)
    ap.add_argument("--pkt-size", type=int, default=1316)
    ap.add_argument("--no-resend-headers", action="store_true")
    args = ap.parse_args()

    cfg = Cfg(args.codec, args.mode, args.bitrate, args.crf, args.preset, args.tune,
              args.out, args.fps_hint, args.duration, args.gop, args.pkt_size, not args.no_resend_headers)

    rclpy.init()
    node = DepthStreamer(args.topic, cfg)
    def sigint(sig,frm):
        node._stop(); rclpy.shutdown()
    signal.signal(signal.SIGINT, sigint)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node._stop(); rclpy.shutdown()

if __name__ == "__main__":
    main()
