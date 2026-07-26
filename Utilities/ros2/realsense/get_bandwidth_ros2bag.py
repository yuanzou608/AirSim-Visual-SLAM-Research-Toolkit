#!/usr/bin/env python3
"""
Compute average bandwidth for a ROS 2 bag topic (rosbag2, sqlite3 storage).

- Default topic: /camera/camera/color/image_raw
- Works without ROS installed (uses sqlite3 + glob)
- Handles multi-file split bags (bag_0.db3, bag_1.db3, ...)

Usage:
  python3 rgb_bandwidth.py /path/to/bagdir [-t /your/topic] [--verbose]
"""

import argparse
import glob
import os
import sqlite3
from typing import List, Tuple

def find_db_files(bag_dir: str) -> List[str]:
    # rosbag2 (sqlite3) stores files as *.db3 under the bag directory
    files = sorted(glob.glob(os.path.join(bag_dir, "*.db3")))
    if not files:
        raise FileNotFoundError(f"No .db3 files found in: {bag_dir}")
    return files

def query_topic_id(conn: sqlite3.Connection, topic_name: str):
    cur = conn.execute("SELECT id FROM topics WHERE name = ? LIMIT 1;", (topic_name,))
    row = cur.fetchone()
    return row[0] if row else None

def query_stats_for_topic(conn: sqlite3.Connection, topic_id: int) -> Tuple[int, int, int, int]:
    """
    Returns (count, total_bytes, min_ts, max_ts) for messages of given topic_id.
    - total_bytes is SUM(LENGTH(data)) in bytes
    - timestamps are in nanoseconds
    """
    cur = conn.execute(
        "SELECT COUNT(*), SUM(LENGTH(data)), MIN(timestamp), MAX(timestamp) "
        "FROM messages WHERE topic_id = ?;", (topic_id,)
    )
    count, total_bytes, min_ts, max_ts = cur.fetchone()
    # normalize None to 0
    return (count or 0, total_bytes or 0, min_ts or 0, max_ts or 0)

def human_bytes(b: int) -> str:
    return f"{b/1024/1024:.2f} MiB"

def main():
    parser = argparse.ArgumentParser(description="Compute average bandwidth for a ROS 2 bag topic (sqlite3).")
    parser.add_argument("--bag_dir", help="Path to rosbag2 directory (contains *.db3)", 
                        default="./5fps/rsbag_sel_20250823_150219")
    # # rgb
    # parser.add_argument("-t", "--topic", default="/camera/camera/color/image_raw",
    #                     help="Topic name to analyze (default: /camera/camera/color/image_raw)")
    # # depth
    # parser.add_argument("-t", "--topic", default="/camera/camera/depth/image_rect_raw",
    #                     help="Topic name to analyze (default: /camera/camera/depth/image_rect_raw)")
    # # imu
    parser.add_argument("-t", "--topic", default="/camera/camera/imu",
                        help="Topic name to analyze (default: /camera/camera/imu)")
    
    parser.add_argument("--verbose", action="store_true", help="Print per-file details")
    args = parser.parse_args()

    db_files = find_db_files(args.bag_dir)

    total_msgs = 0
    total_bytes = 0
    global_min_ts = None
    global_max_ts = None
    files_with_topic = 0

    for db in db_files:
        conn = sqlite3.connect(db)
        try:
            topic_id = query_topic_id(conn, args.topic)
            if topic_id is None:
                if args.verbose:
                    print(f"[skip] {os.path.basename(db)}: topic not found")
                continue

            files_with_topic += 1
            count, bytes_sum, min_ts, max_ts = query_stats_for_topic(conn, topic_id)

            if args.verbose:
                dur_s = (max_ts - min_ts) / 1e9 if max_ts and min_ts and max_ts > min_ts else 0.0
                avg_mib_s = (bytes_sum / dur_s / (1024*1024)) if dur_s > 0 else 0.0
                print(f"[file] {os.path.basename(db)} | msgs={count:7d} | bytes={human_bytes(bytes_sum):>10} "
                      f"| span={dur_s:7.3f}s | ~{avg_mib_s:6.2f} MiB/s")

            total_msgs += count
            total_bytes += bytes_sum
            if min_ts and (global_min_ts is None or min_ts < global_min_ts):
                global_min_ts = min_ts
            if max_ts and (global_max_ts is None or max_ts > global_max_ts):
                global_max_ts = max_ts
        finally:
            conn.close()

    if files_with_topic == 0 or total_msgs == 0 or global_min_ts is None or global_max_ts is None or global_max_ts <= global_min_ts:
        print(f"No messages found for topic '{args.topic}' in {args.bag_dir}")
        return

    duration_s = (global_max_ts - global_min_ts) / 1e9
    avg_bps = total_bytes / duration_s              # bytes per second
    avg_mb_s = avg_bps / (1000 * 1000)             # MiB/s
    avg_mbps = (avg_bps * 8) / (1000 * 1000)           # Mbit/s (decimal)
    fps = total_msgs / duration_s

    print("\n=== Bandwidth Summary ===")
    print(f"Bag dir     : {args.bag_dir}")
    print(f"Topic       : {args.topic}")
    print(f"DB files    : {len(db_files)} (with topic in {files_with_topic})")
    print(f"Messages    : {total_msgs}")
    print(f"Span        : {duration_s:.3f} s")
    print(f"Total bytes : {total_bytes} bytes ({human_bytes(total_bytes)})")
    print(f"Avg rate    : {avg_mb_s:.2f} MB/s  |  {avg_mbps:.2f} Mbps")
    print(f"Approx FPS  : {fps:.2f} Hz")

if __name__ == "__main__":
    main()
