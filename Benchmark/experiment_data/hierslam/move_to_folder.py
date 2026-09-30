import os
import shutil
import re

def merge_similar_folders(root):
    """
    root: 所有 *_数字 文件夹所在的目录
    """

    # 匹配形如 xxx_1, xxx_2, xxx_3 的 folder
    # pattern = re.compile(r"^(.*)_(\d+)$")
    pattern = re.compile(r"^(.*)_(4)$")

    # 列出 root 目录下的所有内容
    items = os.listdir(root)

    for item in items:
        item_path = os.path.join(root, item)

        # 只处理文件夹
        if not os.path.isdir(item_path):
            continue

        match = pattern.match(item)
        if match:
            prefix, idx = match.group(1), match.group(2)

            # 目标父目录
            target_dir = os.path.join(root, prefix)
            os.makedirs(target_dir, exist_ok=True)

            # 在父目录下的编号目录
            new_dir = os.path.join(target_dir, idx)

            print(f"Moving: {item_path} --> {new_dir}")
            shutil.move(item_path, new_dir)

    print("Done!")


if __name__ == "__main__":
    merge_similar_folders("/home/yuan/data2tb/experiments/hierslam/experiments/Airsim_semantic")
