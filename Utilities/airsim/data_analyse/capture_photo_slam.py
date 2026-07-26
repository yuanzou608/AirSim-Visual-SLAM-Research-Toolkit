import subprocess
import pyautogui
import time
import numpy as np
import os
from datetime import datetime


class PhotoSLAMCaptureLinux:
    def __init__(self, window_name="Photo-SLAM", output_dir="./photo_slam_captures"):
        self.window_name = window_name
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    def get_window_geometry(self):
        try:
            # 获取窗口ID
            window_id = subprocess.check_output([
                "xdotool", "search", "--name", self.window_name
            ]).decode().strip().split("\n")[0]

            # 获取窗口几何信息
            output = subprocess.check_output([
                "xwininfo", "-id", window_id
            ]).decode()

            x = int(self._extract_field(output, "Absolute upper-left X"))
            y = int(self._extract_field(output, "Absolute upper-left Y"))
            width = int(self._extract_field(output, "Width"))
            height = int(self._extract_field(output, "Height"))
            # print(x, y, width, height)
            x, y = 122, 64
            width, height = 1400, 1050
            return (x, y, width, height)
        except Exception as e:
            print(f"[Error] Failed to get window geometry: {e}")
            return None

    def _extract_field(self, text, field):
        for line in text.splitlines():
            if field in line:
                return line.split(":")[1].strip()
        raise ValueError(f"Field '{field}' not found")

    def capture_window(self):
        region = self.get_window_geometry()
        if region is None:
            return None

        screenshot = pyautogui.screenshot(region=region)

        now = datetime.now()
        timestamp = now.strftime("%Y%m%d_%H%M%S_%f")  # %f 表示微秒（百万分之一秒）
        filename = f"{self.output_dir}/capture_{timestamp}.png"

        screenshot.save(filename)
        print(f"📸 Saved: {filename}")

        return np.array(screenshot)

    def continuous_capture(self, interval=0.05):
        print("开始连续截图，按 Ctrl+C 停止...")
        try:
            while True:
                self.capture_window()
                time.sleep(interval)
        except KeyboardInterrupt:
            print("\n截图停止。")


if __name__ == "__main__":
    capture = PhotoSLAMCaptureLinux()

    # print("Photo-SLAM 截图工具（Linux）")
    # print("1. 单次截图")
    # print("2. 连续截图")
    #
    # choice = input("选择操作 (1/2): ")
    #
    # if choice == "1":
    #     capture.capture_window()
    # elif choice == "2":
    #     interval = float(input("截图间隔（秒）: ") or "1.0")
    #     capture.continuous_capture(interval)
    capture.continuous_capture()
