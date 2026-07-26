from PIL import Image, ImageDraw, ImageFont
import os

# ===== Settings =====
image_folder = ""                   # folder with your images
output_file  = "combined_2x2.png"         # output file
rows, cols   = 2, 2                        # grid size
# Provide exactly 4 (filename, caption) pairs in display order (row-major)
items = [
    ("roundabout.png",       "(a) Roundabout"),
    ("road.png",             "(b) Road"),
    ("roundabout_square.png","(c) Roundabout Square"),
    ("building.png",         "(d) Building"),
]
# Caption placement & style
caption_margin_xy = (18, 16)              # (left, top) margin inside each tile
target_caption_w_ratio = 0.45             # caption target width ≈ 45% of tile width
max_font_size = 28
min_font_size = 14

# ===== Robust font loader =====
def load_font(size):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
        "arial.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    return ImageFont.load_default()

# ===== Load images =====
imgs = []
for fname, _ in items:
    p = os.path.join(image_folder, fname)
    if not os.path.exists(p):
        raise FileNotFoundError(p)
    imgs.append(Image.open(p).convert("RGB"))

# ===== Ensure uniform size (use size of first) =====
w, h = imgs[0].size
imgs = [im.resize((w, h)) for im in imgs]

# ===== Create canvas =====
W, H = cols * w, rows * h
combined = Image.new("RGB", (W, H), (255, 255, 255))

# ===== Helper: draw top-left caption, auto-scale to tile width =====
def draw_caption(draw, text, tile_origin_xy, tile_size_wh):
    ox, oy = tile_origin_xy
    tw, th = tile_size_wh
    # choose font size so that caption width ≈ target_caption_w_ratio * tile width
    size = max_font_size
    font = load_font(size)
    # textbbox is preferred; fallback to textsize
    def measure(txt, fnt):
        try:
            x0, y0, x1, y1 = draw.textbbox((0, 0), txt, font=fnt, stroke_width=2)
            return (x1 - x0, y1 - y0)
        except Exception:
            return draw.textsize(txt, font=fnt)
    cw, ch = measure(text, font)
    while (cw > tw * target_caption_w_ratio) and (size > min_font_size):
        size -= 2
        font = load_font(size)
        cw, ch = measure(text, font)

    # top-left position with margin
    mx, my = caption_margin_xy
    x = ox + mx
    y = oy + my
    # draw with white stroke for visibility
    draw.text((x, y), text, font=font, fill="black", stroke_width=3, stroke_fill="white")

# ===== Paste tiles and captions =====
draw = ImageDraw.Draw(combined)
for idx, (img, (_, cap)) in enumerate(zip(imgs, items)):
    r = idx // cols
    c = idx % cols
    x, y = c * w, r * h
    combined.paste(img, (x, y))
    draw_caption(draw, cap, (x, y), (w, h))

# ===== Save =====
combined.save(output_file)
print(f"Saved: {output_file}")
