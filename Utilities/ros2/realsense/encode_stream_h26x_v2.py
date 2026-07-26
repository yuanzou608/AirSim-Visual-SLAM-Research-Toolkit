#!/usr/bin/env python3
import argparse, os, shlex, signal, subprocess, sys, time
from dataclasses import dataclass
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image

PIXFMT_MAP = {"rgb8":"rgb24","bgr8":"bgr24"}

@dataclass
class Cfg:
    codec: str
    mode: str
    bitrate: str|None
    crf: int|None
    preset: str
    tune: str
    out: str
    container: str
    fps_hint: float|None
    duration: float
    gop: int
    resend_headers: bool
    pkt_size: int

class H26xStreamer(Node):
    def __init__(self, topic: str, cfg: Cfg):
        super().__init__("h26x_streamer_v2")
        self.topic = topic
        self.cfg = cfg
        self.width = None
        self.height = None
        self.pixfmt = None
        self.ffmpeg = None
        self.first_ts = None
        self.last_ts = None
        self.frames = 0
        self.end_time = time.time() + cfg.duration if cfg.duration>0 else None
        self.create_subscription(Image, topic, self.cb, 10)
        if self.end_time: self.create_timer(0.1, self._tick)
        self.get_logger().info(f"{topic} -> {cfg.codec.upper()} {cfg.container} to {cfg.out} (gop={cfg.gop}, resend_headers={cfg.resend_headers})")

    def _start_ffmpeg(self):
        vcodec = "libx265" if self.cfg.codec=="h265" else "libx264"
        enc = ["-c:v", vcodec, "-preset", self.cfg.preset, "-tune", self.cfg.tune, "-g", str(self.cfg.gop)]
        # Repeat SPS/PPS at each keyframe
        if vcodec=="libx264":
            xparams = f"keyint={self.cfg.gop}:min-keyint={self.cfg.gop}:scenecut=0:repeat-headers=1"
            enc += ["-x264-params", xparams]
        else:
            xparams = f"keyint={self.cfg.gop}:min-keyint={self.cfg.gop}:scenecut=0:repeat-headers=1"
            enc += ["-x265-params", xparams]

        if self.cfg.mode=="cbr":
            if not self.cfg.bitrate: raise RuntimeError("CBR requires --bitrate like 4M")
            enc += ["-b:v", self.cfg.bitrate, "-maxrate", self.cfg.bitrate, "-bufsize", self.cfg.bitrate]
        else:
            enc += ["-crf", str(self.cfg.crf if self.cfg.crf is not None else 23)]

        fps = self.cfg.fps_hint if self.cfg.fps_hint else 30.0
        input_args = ["-f","rawvideo","-pix_fmt",self.pixfmt,"-s",f"{self.width}x{self.height}","-r",f"{fps}","-i","pipe:0"]

        if self.cfg.container=="mpegts":
            out_url = self.cfg.out
            # add pkt_size etc for udp:// urls
            if out_url.startswith("udp://"):
                # Append query parameters safely
                suffix = f"?pkt_size={self.cfg.pkt_size}&reuse=1&fifo_size=65536"
                if "?" in out_url:
                    out_url += "&pkt_size=" + str(self.cfg.pkt_size)
                else:
                    out_url += suffix
            # out_args = ["-f","mpegts","-muxdelay","0","-muxpreload","0"]
            out_args = ["-f","mpegts","-muxdelay","0","-muxpreload","0","-flush_packets","1"]
            if self.cfg.resend_headers:
                out_args += ["-mpegts_flags","+resend_headers"]
            out_args += [out_url]
        else:
            out_args = ["-an","-sn","-movflags","+faststart","-f","mp4", self.cfg.out]

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
        if self.pixfmt is None:
            if msg.encoding not in PIXFMT_MAP:
                self.get_logger().error(f"Unsupported encoding {msg.encoding}; supported {list(PIXFMT_MAP)}")
                return
            self.pixfmt = PIXFMT_MAP[msg.encoding]
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
    ap = argparse.ArgumentParser(description="ROS2 Image -> H.26x live stream with periodic SPS/PPS and mpegts resend_headers.")
    ap.add_argument("--topic", default="/camera/camera/color/image_raw")
    ap.add_argument("--codec", choices=["h264","h265"], default="h264")
    ap.add_argument("--mode", choices=["cbr","crf"], default="crf")
    ap.add_argument("--bitrate")
    ap.add_argument("--crf", type=int, default=23)
    ap.add_argument("--preset", default="veryfast")
    ap.add_argument("--tune", default="zerolatency")
    ap.add_argument("--out", default="udp://127.0.0.1:5600")
    ap.add_argument("--container", choices=["mpegts","mp4"], default="mpegts")
    ap.add_argument("--fps-hint", type=float)
    ap.add_argument("--duration", type=float, default=0.0)
    ap.add_argument("--gop", type=int, default=60, help="keyframe interval (frames)")
    ap.add_argument("--no-resend-headers", action="store_true", help="disable mpegts resend_headers")
    ap.add_argument("--pkt-size", type=int, default=1316, help="UDP packet payload size (bytes)")
    args = ap.parse_args()

    cfg = Cfg(args.codec, args.mode, args.bitrate, args.crf, args.preset, args.tune, args.out,
              args.container, args.fps_hint, args.duration, args.gop, not args.no_resend_headers, args.pkt_size)

    rclpy.init()
    node = H26xStreamer(args.topic, cfg)
    def sigint(sig,frm):
        node._stop(); rclpy.shutdown()
    signal.signal(signal.SIGINT, sigint)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node._stop(); rclpy.shutdown()

if __name__ == "__main__":
    main()
