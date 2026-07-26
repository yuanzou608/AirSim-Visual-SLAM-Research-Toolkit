#!/usr/bin/env python3
import argparse, shlex, subprocess, time, socket, struct, threading, collections

def telem_reader(port, dq):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("", port))
    while True:
        data, _ = sock.recvfrom(1024)
        if len(data) >= 24:
            now_ns = time.time_ns()  # 本机到达时间（不依赖发送端时钟）
            dq.append(now_ns)

def main():
    ap = argparse.ArgumentParser(
        description="Latency = video_arrival - telemetry_arrival(启动自同步，避免起播错位）。"
    )
    ap.add_argument("--url", default="udp://127.0.0.1:5600?fifo_size=65536&buffer_size=65536&overrun_nonfatal=1")
    ap.add_argument("--width", type=int, required=True)
    ap.add_argument("--height", type=int, required=True)
    ap.add_argument("--telem-port", type=int, default=5601)
    ap.add_argument("--codec", choices=["h264","h265"], default="h264")
    ap.add_argument("--fresh-window-ms", type=int, default=200,
                    help="首次对齐时保留近这个窗口内的遥测（丢弃更旧的）")
    ap.add_argument("--warmup-frames", type=int, default=0,
                    help="可选：忽略前 N 帧的统计")
    args = ap.parse_args()

    telem_dq = collections.deque(maxlen=10000)
    t = threading.Thread(target=telem_reader, args=(args.telem_port, telem_dq), daemon=True)
    t.start()

    cmd = [
        "ffmpeg","-hide_banner","-loglevel","error",
        "-fflags","+nobuffer","-flags","+low_delay",
        "-probesize","32","-analyzeduration","0",
        "-i", args.url,
        "-an","-sn","-pix_fmt","bgr24","-f","rawvideo","pipe:1"
    ]
    print("Running:", " ".join(shlex.quote(c) for c in cmd))
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, bufsize=0)

    frame_size = args.width * args.height * 3
    frames, synced = 0, False
    lat_list = []
    try:
        while True:
            buf = p.stdout.read(frame_size)
            if not buf or len(buf) < frame_size:
                break
            frames += 1
            now_ns = time.time_ns()

            # 启动自同步：把过旧的遥测丢掉，只保留“新鲜”的
            if not synced:
                thr = args.fresh_window_ms * 1_000_000
                dropped = 0
                while len(telem_dq) > 1 and (now_ns - telem_dq[0]) > thr:
                    telem_dq.popleft()
                    dropped += 1
                if len(telem_dq) > 0:
                    synced = True
                    if dropped:
                        print(f"[sync] Dropped {dropped} stale telemetry entries to align queues")

            if len(telem_dq) == 0:
                continue

            telem_arrival = telem_dq.popleft()
            latency_ms = (now_ns - telem_arrival) / 1e6
            if frames > args.warmup_frames:
                lat_list.append(latency_ms)
                if len(lat_list) % 30 == 0:
                    avg_tail = sum(lat_list[-120:]) / max(1, len(lat_list[-120:]))
                    print(f"[{frames} frames] latency ~ {latency_ms:.1f} ms (avg(last 120) {avg_tail:.1f} ms)")
    except KeyboardInterrupt:
        pass
    finally:
        try: p.kill()
        except Exception: pass
        if lat_list:
            overall = sum(lat_list) / len(lat_list)
            print(f"\nOverall avg latency: {overall:.1f} ms over {len(lat_list)} frames")
        else:
            print("No frames measured.")

if __name__ == "__main__":
    main()