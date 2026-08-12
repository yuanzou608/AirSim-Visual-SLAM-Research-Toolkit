import os
import shutil



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

    root_source = "/home/yuan/data2tb/dataset/my_data"
    root_target = "/home/yuan/data2tb/experiments/MongGS/results/airsim/"

    for dataset in dataset_list:
        print(f'copying {dataset} from {root_source} to {root_target}')
        source = os.path.join(root_source, dataset, "groundtruth_no_ts.txt")
        for i in ["1", "2", "3"]:
            target = os.path.join(root_target, dataset, "mono", str(i))
            print(f'copying {dataset} from {source} to {target}')
            shutil.copy2(source, target)

    print("Done!")
