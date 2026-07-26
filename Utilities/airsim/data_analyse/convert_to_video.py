import cv2
import os
from natsort import natsorted  # 自动按数字排序：img1, img2, ..., img10
from glob import glob

def images_to_video(image_folder, output_path, fps=20):
    # 获取所有 PNG 图片路径并排序
    image_files = natsorted(glob(os.path.join(image_folder, "*.png")))

    if not image_files:
        print("❌ 没有找到图片")
        return

    # 从第一张图片读取尺寸
    frame = cv2.imread(image_files[0])
    height, width, _ = frame.shape

    # 初始化视频写入器
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")  # 或者 'XVID'
    out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))
    count = 0
    for filename in image_files:
        img = cv2.imread(filename)
        if img.shape[0] != height or img.shape[1] != width:
            img = cv2.resize(img, (width, height))  # 保证尺寸一致
        out.write(img)
        count += 1

    out.release()
    print(f"✅ 视频已保存: {output_path}")
    print('total frames:', count)


# 示例用法
if __name__ == "__main__":
    images_to_video(
        image_folder="./photo_slam_frames",  # 图片目录
        output_path="photo_slam_mapping_semantic_final.mp4",   # 输出视频名
        fps=20                                 # 设置帧率
    )
