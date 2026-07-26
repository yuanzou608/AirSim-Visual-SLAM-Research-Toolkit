#!/usr/bin/env python3
import argparse, os, shlex, socket, struct, subprocess, time, threading, queue, sys

def telem_reader(port, q):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("", port))
    while True:
        data, _ = sock.recvfrom(1024)
        if len(data) >= 24:
            seq, t_ns, w, h = struct.unpack("!QQII", data[:24])
            q.put((seq, t_ns, w, h))

def main():
    ap = argparse.ArgumentParser(description="Measure end-to-end latency by matching frame order with telemetry timestamps.")
    ap.add_argument("--url", default="udp://127.0.0.1:5600")
    ap.add_argument("--width", type=int, required=True)
    ap.add_argument("--height", type=int, required=True)
    ap.add_argument("--telem-port", type=int, default=5601)
    ap.add_argument("--codec", choices=["h264","h265"], default="h264")
    args = ap.parse_args()

    telem_q = queue.Queue()
    t = threading.Thread(target=telem_reader, args=(args.telem_port, telem_q), daemon=True)
    t.start()

    # Decode to rawvideo and read frames one by one
    parse = "h264parse" if args.codec=="h264" else "hevcparse"
    cmd = ["ffmpeg","-hide_banner","-loglevel","error","-fflags","+nobuffer","-flags","+low_delay",
           "-i", args.url, "-an", "-sn", "-pix_fmt", "bgr24", "-f", "rawvideo", "pipe:1"]
    print("Running:", " ".join(shlex.quote(c) for c in cmd))
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE)

    frame_size = args.width*args.height*3
    seq = 0
    lat_list = []
    t0 = time.time()
    try:
        while True:
            buf = p.stdout.read(frame_size)
            if not buf:
                break
            seq += 1
            now_ns = time.time_ns()
            # pop a telemetry packet (assumes no drop & roughly in order)
            try:
                s, send_ns, w, h = telem_q.get(timeout=1.0)
            except queue.Empty:
                print("No telemetry; skipping frame")
                continue
            latency_ms = (now_ns - send_ns)/1e6
            lat_list.append(latency_ms)
            if len(lat_list) % 30 == 0:
                avg = sum(lat_list[-120:])/max(1,len(lat_list[-120:]))
                print(f"[{len(lat_list)} frames] latency ~ {latency_ms:.1f} ms (avg(last 120) {avg:.1f} ms)")
    except KeyboardInterrupt:
        pass
    finally:
        p.kill()
        if lat_list:
            overall = sum(lat_list)/len(lat_list)
            print(f"\nOverall avg latency: {overall:.1f} ms over {len(lat_list)} frames")
        else:
            print("No frames measured.")

if __name__ == "__main__":
    main()
