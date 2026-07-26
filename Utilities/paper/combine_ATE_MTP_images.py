from PIL import Image

# Load the three uploaded images
img1 = Image.open("ATE_heatmap_mono_log.png")
img2 = Image.open("ATE_heatmap_rgbd_log.png")
img3 = Image.open("MTP_heatmap_combined_log.png")

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

combined_path = "Combined_3_Heatmaps.png"
combined.save(combined_path)
combined_path
