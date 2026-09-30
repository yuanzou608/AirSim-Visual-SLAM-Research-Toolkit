#!/usr/bin/env python3
"""Combine the mono ATE, RGB-D ATE and combined MTP heatmaps horizontally."""

import argparse
from pathlib import Path


def combine_heatmaps(input_dir, output_file):
    input_dir = Path(input_dir)
    output_file = Path(output_file)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    from PIL import Image

    # Load the three uploaded images
    img1 = Image.open(input_dir / "ATE_heatmap_mono_log.png")
    img2 = Image.open(input_dir / "ATE_heatmap_rgbd_log.png")
    img3 = Image.open(input_dir / "MTP_heatmap_combined_log.png")

    # Resize images to same height for consistent horizontal alignment
    target_height = min(img1.height, img2.height, img3.height)
    def resize_keep_aspect(img, target_h):
        aspect_ratio = img.width / img.height
        new_w = int(aspect_ratio * target_h)
        return img.resize((new_w, target_h), Image.LANCZOS)

    img1_r = resize_keep_aspect(img1, target_height)
    img2_r = resize_keep_aspect(img2, target_height)
    img3_r = resize_keep_aspect(img3, target_height)

    # Combine horizontally
    total_width = img1_r.width + img2_r.width + img3_r.width
    combined = Image.new("RGB", (total_width, target_height), (255, 255, 255))
    combined.paste(img1_r, (0, 0))
    combined.paste(img2_r, (img1_r.width, 0))
    combined.paste(img3_r, (img1_r.width + img2_r.width, 0))

    combined_path = output_file
    combined.save(combined_path)
    combined_path

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True,
                        help="Directory containing the three source heatmaps")
    parser.add_argument("--output", type=Path,
                        help="Output PNG (default: INPUT_DIR/Combined_3_Heatmaps.png)")
    args = parser.parse_args(argv)
    output = args.output if args.output is not None else args.input_dir / "Combined_3_Heatmaps.png"
    combine_heatmaps(args.input_dir, output)


if __name__ == "__main__":
    main()
