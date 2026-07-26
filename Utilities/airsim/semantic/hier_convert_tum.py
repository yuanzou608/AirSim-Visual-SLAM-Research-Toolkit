import numpy as np
from scipy.spatial.transform import Rotation as R

def load_hierslam_poses(filepath):
    poses = []
    current_pose = []
    with open(filepath, 'r') as f:
        for line in f:
            values = list(map(float, line.strip().split()))
            current_pose.append(values)
            poses.append(np.array(current_pose).reshape(4, 4))
            current_pose = []
    return poses


def save_as_tum_format(pose_matrices, output_path, timestep=1.0, start_time=0.0, inverse=True):
    with open(output_path, 'w') as f:
        for i, pose in enumerate(pose_matrices):
            timestamp = start_time + i * timestep
            c2w = np.linalg.inv(pose) if inverse else pose
            trans = c2w[:3, 3]
            quat = R.from_matrix(c2w[:3, :3]).as_quat()  # [x, y, z, w]
            f.write(f"{timestamp:.6f} {trans[0]:.6f} {trans[1]:.6f} {trans[2]:.6f} "
                    f"{quat[0]:.6f} {quat[1]:.6f} {quat[2]:.6f} {quat[3]:.6f}\n")

if __name__ == "__main__":
    # File paths
    est_file = 'estimate.txt'               # 'estimate.txt'
    gt_file = 'groundtruth.txt'                    # 'traj.txt'
    est_out = 'KeyFrameTrajectory.txt'      # 'KeyFrameTrajectory.txt'
    gt_out = 'GroundTruthTrajectory.txt'    # 'GroundTruthTrajectory.txt'

    # Load poses
    est_poses = load_hierslam_poses(est_file)
    gt_poses = load_hierslam_poses(gt_file)

    # Ensure matching lengths
    n = min(len(est_poses), len(gt_poses))
    est_poses = est_poses[:n]
    gt_poses = gt_poses[:n]

    # Save both as TUM format with same timestamps
    save_as_tum_format(est_poses, est_out, timestep=1.0, start_time=0.0, inverse=True)
    save_as_tum_format(gt_poses, gt_out, timestep=1.0, start_time=0.0, inverse=False)  # assume GT is already c2w

    print(f"Converted {n} estimated and ground truth poses to TUM format.")
