from PIL import Image

paths = [
    "1.png",
    "2.png",
    "3.png",
    "4.png",
    "5.png",
    "6.png",
]

imgs = [Image.open(p) for p in paths]

# ensure same size
w, h = imgs[0].size

# create canvas 2 rows x 3 cols
canvas = Image.new("RGB", (3*w, 2*h), (255,255,255))

for idx, img in enumerate(imgs):
    r = idx // 3
    c = idx % 3
    canvas.paste(img, (c*w, r*h))

out_path = "trajectory_2x3.png"
canvas.save(out_path)

out_path
