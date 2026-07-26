def calculate_fps(file_path):
    timestamps = []

    # Read timestamps from the file
    with open(file_path, 'r') as f:
        for line in f:
            parts = line.strip().split()
            if parts:
                try:
                    timestamps.append(float(parts[0]))
                except ValueError:
                    continue  # Skip lines with invalid floats

    # Ensure at least 2 timestamps to calculate FPS
    if len(timestamps) < 2:
        print("Not enough data to compute FPS.")
        return

    # Compute frame intervals
    intervals = [t2 - t1 for t1, t2 in zip(timestamps[:-1], timestamps[1:])]
    avg_interval = sum(intervals) / len(intervals)
    fps = 1.0 / avg_interval

    print(f"Total frames: {len(timestamps)}")
    print(f"Average interval: {avg_interval:.6f} seconds")
    print(f"Estimated FPS: {fps:.2f}")

# Example usage
file_path = "associations.txt"
calculate_fps(file_path)
