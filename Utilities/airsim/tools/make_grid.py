# Write a more robust v1.2 of make_grid.py
# - Fix autocontrast crash by handling I/I;16/F with NumPy percentile scaling
# - Add --depth-pcts (default 1,99), --depth-ignore-zero (default on), --depth-colormap (none|gray)
# - Keep --order column etc.
from pathlib import Path

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_grid.py (v1.2)
Arrange R x C images on a white canvas with optional bottom column labels.

New in v1.2:
- Robust depth rendering for single-channel/16-bit/float images using NumPy percentile scaling.
- CLI:
  --order {row,column}
  --depth-pcts "1,99"         # percentiles for auto scaling (ignored if vmin/vmax set later)
  --depth-ignore-zero         # ignore zeros when estimating percentiles (default: on)
  --no-depth-ignore-zero
  --depth-colormap {gray,none}# currently 'gray' (default) or 'none' (replicate L to RGB)
Requires: Pillow, NumPy
"""
import os
import glob
import argparse
from typing import List, Optional, Tuple
import numpy as np
from PIL import Image, ImageDraw, ImageFont

def load_font(px: int):
    for p in (
        "DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/Library/Fonts/Arial.ttf",
        "arial.ttf",
    ):
        try:
            return ImageFont.truetype(p, px)
        except Exception:
            pass
    from PIL import ImageFont as IF
    return IF.load_default()

def fit_into(img: Image.Image, max_w: int, max_h: int) -> Image.Image:
    w, h = img.size
    scale = min(max_w / w, max_h / h)
    return img.resize((max(1, int(round(w * scale))), max(1, int(round(h * scale)))), Image.LANCZOS)

def depth_to_L8_numpy(img: Image.Image, pcts=(1.0, 99.0), ignore_zero=True) -> Image.Image:
    """Convert single-channel (L/I;16/I/F) to 8-bit luminance using robust scaling."""
    arr = np.array(img)
    # Flatten and mask
    flat = arr.reshape(-1).astype(np.float64)
    m = np.isfinite(flat)
    if ignore_zero:
        m &= (flat != 0)
    data = flat[m]
    if data.size == 0:
        # fallback: everything zero
        L = np.zeros_like(flat, dtype=np.uint8).reshape(arr.shape)
        return Image.fromarray(L, mode="L")
    lo = np.percentile(data, pcts[0])
    hi = np.percentile(data, pcts[1])
    if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
        lo, hi = float(np.min(data)), float(np.max(data))
        if hi <= lo:
            hi = lo + 1.0
    # scale
    scaled = (np.clip(flat, lo, hi) - lo) / (hi - lo) * 255.0
    L = scaled.astype(np.uint8).reshape(arr.shape)
    return Image.fromarray(L, mode="L")

def render_depth_like(img: Image.Image, pcts=(1.0, 99.0), ignore_zero=True, colormap="gray") -> Image.Image:
    if img.mode in ("L", "I;16", "I", "F"):
        L = depth_to_L8_numpy(img, pcts=pcts, ignore_zero=ignore_zero)
        if colormap == "gray":
            return Image.merge("RGB", (L, L, L))
        else:  # none
            return Image.merge("RGB", (L, L, L))
    else:
        return img.convert("RGB")

def make_grid(
    image_paths: List[str],
    rows: int = 3,
    cols: int = 4,
    out_path: str = "grid.png",
    cell_w: int = 480,
    cell_h: int = 320,
    margin: int = 16,
    hgap: int = 12,
    vgap: int = 12,
    pad: int = 8,
    draw_cell_border: bool = True,
    border_color: Tuple[int, int, int] = (210, 210, 210),
    border_width: int = 2,
    column_labels: Optional[List[str]] = None,
    label_area_px: int = 64,
    bg_color: Tuple[int, int, int] = (255, 255, 255),
    fill_order: str = "row",
    depth_pcts=(1.0, 99.0),
    depth_ignore_zero=True,
    depth_colormap="gray",
) -> None:
    assert rows * cols == len(image_paths), f"Need exactly rows*cols={rows*cols} images, got {len(image_paths)}"
    label_h = label_area_px if (column_labels and len(column_labels) > 0) else 0

    canvas_w = margin * 2 + cols * cell_w + (cols - 1) * hgap
    canvas_h = margin * 2 + rows * cell_h + (rows - 1) * vgap + label_h
    canvas = Image.new("RGB", (canvas_w, canvas_h), bg_color)
    draw = ImageDraw.Draw(canvas)

    for idx, img_path in enumerate(image_paths):
        raw = Image.open(img_path)

        if fill_order == "row":
            r = idx // cols
            c = idx % cols
        else:
            r = idx % rows
            c = idx // rows

        x0 = margin + c * (cell_w + hgap)
        y0 = margin + r * (cell_h + vgap)

        if draw_cell_border:
            draw.rectangle([x0, y0, x0 + cell_w - 1, y0 + cell_h - 1], outline=border_color, width=border_width)

        img = render_depth_like(raw, pcts=depth_pcts, ignore_zero=depth_ignore_zero, colormap=depth_colormap)

        target_w = max(1, cell_w - 2 * pad)
        target_h = max(1, cell_h - 2 * pad)
        img_fit = fit_into(img, target_w, target_h)

        px = x0 + (cell_w - img_fit.width) // 2
        py = y0 + (cell_h - img_fit.height) // 2
        canvas.paste(img_fit, (px, py))

    if label_h > 0:
        font_px = max(10, int(label_h * 0.5))
        font = load_font(font_px)
        base_y = margin + rows * cell_h + (rows - 1) * vgap
        for c in range(cols):
            text = column_labels[c] if c < len(column_labels) else ""
            if not text:
                continue
            tw, th = font.getsize(text)
            cx = margin + c * (cell_w + hgap) + cell_w // 2
            tx = int(cx - tw / 2)
            ty = int(base_y + (label_h - th) / 2)
            draw.text((tx, ty), text, fill=(0, 0, 0), font=font)

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    canvas.save(out_path)
    print(f"[OK] Saved: {out_path}  ({canvas_w}x{canvas_h})")

def list_images_in_dir(d: str):
    exts = ("*.png", "*.jpg", "*.jpeg", "*.bmp", "*.tif", "*.tiff", "*.webp")
    files = []
    for ext in exts:
        files.extend(glob.glob(os.path.join(d, ext)))
    files.sort()
    return files

def parse_args():
    p = argparse.ArgumentParser(description="Arrange images into an R x C grid with white background and bottom labels.")
    gsrc = p.add_mutually_exclusive_group(required=True)
    gsrc.add_argument("--dir", type=str, help="Directory containing images; first R*C (sorted) will be used.")
    gsrc.add_argument("--images", nargs="+", help="Explicit image list (must be exactly R*C).")

    p.add_argument("--rows", type=int, default=3)
    p.add_argument("--cols", type=int, default=4)
    p.add_argument("--out", type=str, default="grid.png")

    p.add_argument("--cell-width", type=int, default=480)
    p.add_argument("--cell-height", type=int, default=320)
    p.add_argument("--margin", type=int, default=16)
    p.add_argument("--hgap", type=int, default=12)
    p.add_argument("--vgap", type=int, default=12)
    p.add_argument("--pad", type=int, default=8)

    p.add_argument("--no-border", action="store_true", help="Disable subtle cell borders.")
    p.add_argument("--label-area", type=int, default=64, help="Height of bottom label band in pixels (0 = hide).")
    p.add_argument("--labels", type=str, default="", help='Comma-separated column labels, e.g. "office,corridor,home,cafe"')

    p.add_argument("--order", type=str, choices=["row","column"], default="row",
                   help="Fill order: 'row' (row-major) or 'column' (column-major; top->bottom per column).")

    p.add_argument("--depth-pcts", type=str, default="1,99", help="Percentiles for depth scaling, e.g. '0.5,99.5'")
    p.add_argument("--depth-ignore-zero", dest="depth_ignore_zero", action="store_true", default=True)
    p.add_argument("--no-depth-ignore-zero", dest="depth_ignore_zero", action="store_false")
    p.add_argument("--depth-colormap", type=str, choices=["gray","none"], default="gray")

    return p.parse_args()

def main():
    args = parse_args()
    if args.dir:
        imgs = list_images_in_dir(args.dir)
        needed = args.rows * args.cols
        if len(imgs) < needed:
            raise SystemExit(f"Found {len(imgs)} images in {args.dir}, but need {needed}.")
        imgs = imgs[:needed]
    else:
        imgs = args.images
        needed = args.rows * args.cols
        if len(imgs) != needed:
            raise SystemExit(f"--images must list exactly rows*cols={needed} files. Got {len(imgs)}.")

    labels = [s.strip() for s in args.labels.split(",")] if args.labels else []
    if labels and len(labels) < args.cols:
        labels = labels + [""] * (args.cols - len(labels))

    # parse percentiles
    try:
        p_lo, p_hi = [float(x.strip()) for x in args.depth_pcts.split(",")]
    except Exception:
        p_lo, p_hi = 1.0, 99.0

    make_grid(
        imgs,
        rows=args.rows,
        cols=args.cols,
        out_path=args.out,
        cell_w=args.cell_width,
        cell_h=args.cell_height,
        margin=args.margin,
        hgap=args.hgap,
        vgap=args.vgap,
        pad=args.pad,
        draw_cell_border=(not args.no_border),
        column_labels=labels if args.label_area > 0 else None,
        label_area_px=args.label_area,
        fill_order=args.order,
        depth_pcts=(p_lo, p_hi),
        depth_ignore_zero=args.depth_ignore_zero,
        depth_colormap=args.depth_colormap,
    )

if __name__ == "__main__":
    main()
