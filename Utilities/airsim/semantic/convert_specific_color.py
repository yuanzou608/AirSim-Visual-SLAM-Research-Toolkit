from PIL import Image

# Load image
input_path = "/home/yuan/Downloads/test/0.png"
output_path = "/home/yuan/Downloads/test/output.png"

# Open image
img = Image.open(input_path).convert("RGB")  # ensure RGB mode
pixels = img.load()

# Get image size
width, height = img.size

# Target and replacement colors
target_color = (57, 128, 27)
replace_color = (0, 0, 0)

# Loop through pixels
for x in range(width):
    for y in range(height):
        if pixels[x, y] == target_color:
            pixels[x, y] = replace_color

# Save output image
img.save(output_path)
print(f"Converted image saved to {output_path}")
