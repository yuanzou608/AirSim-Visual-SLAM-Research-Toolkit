# Convert 4x4 homogeneous poses (16 floats per line) into KITTI 3x4 format (12 floats per line)
# Input: /mnt/data/camera_poses.txt
# Output: /mnt/data/camera_poses_kitti.txt

in_path = "traj.txt"
out_path = "traj_kitti.txt"

def convert_to_kitti(in_file, out_file):
    kitti_lines = []
    with open(in_file, "r") as f:
        for ln, line in enumerate(f, 1):
            parts = line.strip().split()
            if not parts:
                continue
            try:
                vals = [float(x) for x in parts]
            except ValueError:
                # skip malformed lines
                continue
            if len(vals) == 16:
                # 4x4 row-major
                # Take first 3 rows (each 4 elems) -> 12 values
                m00,m01,m02,m03, m10,m11,m12,m13, m20,m21,m22,m23, m30,m31,m32,m33 = vals
                kitti = [m00,m01,m02,m03, m10,m11,m12,m13, m20,m21,m22,m23]
                kitti_lines.append(" ".join(f"{v:.10f}" for v in kitti))
            elif len(vals) == 12:
                # Already KITTI-style
                kitti_lines.append(" ".join(f"{v:.10f}" for v in vals))
            else:
                # Ignore other lengths
                continue
    with open(out_file, "w") as f:
        f.write("\n".join(kitti_lines))
    return len(kitti_lines)

count = convert_to_kitti(in_path, out_path)
count, out_path
