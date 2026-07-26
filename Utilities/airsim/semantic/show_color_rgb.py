#!/usr/bin/env python3
import argparse, math
import numpy as np
from PIL import Image  # 读图为 RGB
import cv2

def luminance(r, g, b):
    return 0.2126*r + 0.7152*g + 0.0722*b

def make_grid(colors, counts, total, cols=6, tile_w=240, tile_h=100):
    """colors: [(R,G,B), ...] 按频次排序的前 N 个颜色"""
    n = len(colors)
    rows = math.ceil(n / cols)
    canvas = np.full((rows*tile_h, cols*tile_w, 3), 255, np.uint8)  # 白底

    for i, (r, g, b) in enumerate(colors):
        row, col = divmod(i, cols)
        x0, y0 = col*tile_w, row*tile_h

        # OpenCV 用 BGR，因此填充时要 (b,g,r)
        tile = np.full((tile_h, tile_w, 3), (b, g, r), np.uint8)
        cv2.rectangle(tile, (0, 0), (tile_w-1, tile_h-1), (0, 0, 0), 1)

        # 文字颜色（深色块用白字）
        txt_color = (255, 255, 255) if luminance(r, g, b) < 128 else (0, 0, 0)

        # 标注：RGB、HEX、占比
        pct = counts[i] * 100.0 / total
        cv2.putText(tile, f"{i+1}: ({r},{g},{b})", (8, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, txt_color, 2, cv2.LINE_AA)
        cv2.putText(tile, f"#{r:02X}{g:02X}{b:02X}  {pct:.2f}%", (8, 65),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, txt_color, 2, cv2.LINE_AA)

        canvas[y0:y0+tile_h, x0:x0+tile_w] = tile

    return canvas

def main():
    ap = argparse.ArgumentParser(description="用 OpenCV 显示语义图里出现过的 RGB 颜色")
    ap.add_argument("image", help="语义图路径 (PNG/JPG)")
    ap.add_argument("--top", type=int, default=0, help="只显示前 N 个最常见颜色(0=全部)")
    ap.add_argument("--cols", type=int, default=6, help="网格列数")
    ap.add_argument("--tilew", type=int, default=240, help="色块宽度")
    ap.add_argument("--tileh", type=int, default=100, help="色块高度")
    ap.add_argument("--save", default="", help="另存为图片路径(可选)")
    args = ap.parse_args()

    # 读图为 RGB（用 PIL 保证是 RGB 顺序）
    arr = np.array(Image.open(args.image).convert("RGB"))
    flat = arr.reshape(-1, 3)
    uniq, counts = np.unique(flat, axis=0, return_counts=True)
    order = counts.argsort()[::-1]
    uniq, counts = uniq[order], counts[order]
    total = flat.shape[0]

    N = len(uniq) if args.top <= 0 else min(args.top, len(uniq))
    colors = [tuple(map(int, uniq[i])) for i in range(N)]
    counts_top = counts[:N]

    grid = make_grid(colors, counts_top, total,
                     cols=args.cols, tile_w=args.tilew, tile_h=args.tileh)

    # 显示（需要有 GUI 环境）
    cv2.imshow("Semantic Colors (RGB shown, tile filled in BGR)", grid)
    cv2.waitKey(0)
    cv2.destroyAllWindows()

    if args.save:
        cv2.imwrite(args.save, grid)

if __name__ == "__main__":
    main()
