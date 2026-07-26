#!/usr/bin/env python3
import argparse, os, shlex, socket, struct, subprocess, time, threading, queue, sys

def telem_reader(port, q):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("", port))
    while True:
        data, _ = sock.recvfrom(1024)
        # payload: seq(uint64), t_ns(uint64), w(uint32), h(uint32)
        if len(data) >= 24:
            # We don't rely on sender timestamp; take LOCAL arrival time for telemetry
            seq, t_ns, w, h = struct.unpack("!QQII", data[:24])
            q.put((time.time_ns(), seq))

def main():
    ap = argparse.ArgumentParser(description="Measure end-to-end latency without clock sync: video arrival - telemetry arrival (same host).")
    ap.add_argument("--url", default="udp://127.0.0.1:5600")
    ap.add_argument("--width", type=int, required=True)
    ap.add_argument("--height", type=int, required=True)
    ap.add_argument("--telem-port", type=int, default=5601)
    ap.add_argument("--codec", choices=["h264","h265"], default="h264")
    args = ap.parse_args()

    telem_q = queue.Queue()
    t = threading.Thread(target=telem_reader, args=(args.telem_port, telem_q), daemon=True)
    t.start()

    # Decode to rawvideo and read frames one by one (low-latency flags)
    cmd = [
        "ffmpeg","-hide_banner","-loglevel","error",
        "-fflags","+nobuffer","-flags","+low_delay",
        "-probesize","32","-analyzeduration","0",
        "-i", args.url,
        "-an","-sn","-pix_fmt","bgr24","-f","rawvideo","pipe:1"
    ]
    print("Running:", " ".join(shlex.quote(c) for c in cmd))
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE)

    frame_size = args.width * args.height * 3
    frames = 0
    lat_list = []
    try:
        while True:
            buf = p.stdout.read(frame_size)
            if not buf or len(buf) < frame_size:
                break
            frames += 1
            video_arrival = time.time_ns()

            # match with latest telemetry arrival (best-effort 1:1)
            try:
                telem_arrival, seq = telem_q.get(timeout=1.0)
            except queue.Empty:
                continue

            latency_ms = (video_arrival - telem_arrival) / 1e6
            lat_list.append(latency_ms)
            if frames % 30 == 0:
                avg_tail = sum(lat_list[-120:]) / max(1, len(lat_list[-120:]))
                print(f"[{frames} frames] latency ~ {latency_ms:.1f} ms (avg(last 120) {avg_tail:.1f} ms)")
    except KeyboardInterrupt:
        pass
    finally:
        try:
            p.kill()
        except Exception:
            pass
        if lat_list:
            overall = sum(lat_list) / len(lat_list)
            print(f"\nOverall avg latency: {overall:.1f} ms over {len(lat_list)} frames")
        else:
            print("No frames measured.")

if __name__ == "__main__":
    main()
