import os
def add_timestamp(
    input_path="airsim_tartanvo_1914.txt",
    output_path="airsim_tartanvo_1914_tum.txt",
    start_ts=1.0,
    delta=0.1,
):
    with open(input_path, "r") as fin, open(output_path, "w") as fout:
        idx = 0
        for line in fin:
            line = line.strip()
            if not line:
                continue

            ts = start_ts + idx * delta
            fout.write(f"{ts:.6f} {line}\n")
            idx += 1

    print(f"Done! {idx} frames written to {output_path}")


if __name__ == "__main__":
    dataset_list = [
        "building25fps",
        "cross_building_high_high",
        "cross_building_high_low",
        "cross_building_high_medium",
        "cross_building_low_high",
        "cross_building_low_low",
        "cross_building_low_medium",
        "cross_building_medium_high",
        "cross_building_medium_low",
        "cross_building_medium_medium",
        "houses_high_high",
        "houses_high_low",
        "houses_high_medium",
        "houses_low_high",
        "houses_low_low",
        "houses_low_medium",
        "houses_medium_high",
        "houses_medium_low",
        "houses_medium_medium",
        "pool_high_high",
        "pool_high_low",
        "pool_high_medium",
        "pool_low_high",
        "pool_low_low",
        "pool_low_medium",
        "pool_medium_high",
        "pool_medium_low",
        "pool_medium_medium",
        "road25fps",
        "road2_high_high",
        "road2_high_low",
        "road2_high_medium",
        "road2_low_high",
        "road2_low_low",
        "road2_low_medium",
        "road2_medium_high",
        "road2_medium_low",
        "road2_medium_medium",
        "roundabout25fps",
        "roundabout2_high_high",
        "roundabout2_high_low",
        "roundabout2_high_medium",
        "roundabout2_low_high",
        "roundabout2_low_low",
        "roundabout2_low_medium",
        "roundabout2_medium_high",
        "roundabout2_medium_low",
        "roundabout_square25fps",
        # "testdata"
    ]

    root = "/home/yuan/data2tb/experiments/SVO/experiments/airsim/mono"
    for dataset in dataset_list:
        for i in ["1", "2", "3"]:
            source = os.path.join(root, dataset, f"{i}","groundtruth_no_ts.txt")
            target = os.path.join(root, dataset, f"{i}","groundtruth.txt")

            add_timestamp(input_path=source, output_path=target, start_ts=0.0, delta=0.04)
