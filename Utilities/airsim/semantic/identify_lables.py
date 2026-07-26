# Visualize the given RGB colors as labeled swatches and also provide a table.
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import math
import pandas as pd

# Keep the order as provided by the user (do not treat as a Python set to avoid reordering).
colors = [
    (71, 146, 227), (167, 140, 147), (157, 23, 236), (29, 26, 199), (215, 4, 215),
    (75, 50, 243), (121, 67, 28), (161, 171, 27), (184, 145, 182), (54, 72, 205),
    (146, 52, 70), (158, 114, 88), (89, 121, 72), (68, 218, 116), (153, 108, 6),
    (53, 118, 126), (55, 181, 57), (206, 190, 59), (226, 149, 143), (43, 47, 206),
    (241, 77, 149), (98, 55, 74), (242, 107, 146), (40, 63, 99), (3, 177, 32),
    (245, 22, 110), (151, 126, 171), (185, 243, 231), (67, 17, 35), (115, 176, 195),
    (156, 198, 23), (181, 213, 93), (222, 153, 109), (24, 175, 120), (134, 57, 119),
    (170, 179, 42), (253, 41, 164)
]

def rgb_to_hex(rgb):
    return "#{:02X}{:02X}{:02X}".format(*rgb)

# Perceived luminance (approximate, sRGB coefficients without gamma correction step)
def luminance(rgb):
    r, g, b = rgb
    return 0.2126 * r + 0.7152 * g + 0.0722 * b

# Build a dataframe for users to review/export
df = pd.DataFrame(
    [{
        "index": i+1,
        "R": r, "G": g, "B": b,
        "hex": rgb_to_hex((r,g,b)),
        "luminance": round(luminance((r,g,b)), 2)
    } for i, (r,g,b) in enumerate(colors)]
)


# Draw swatches
n = len(colors)
cols = 7  # grid columns
rows = math.ceil(n / cols)

cell_w, cell_h = 1.0, 1.0
label_h = 0.35  # extra height for text line within each cell

fig_w = cols * cell_w * 1.6
fig_h = rows * (cell_h) * 1.6
fig, ax = plt.subplots(figsize=(fig_w, fig_h))

# Background
ax.set_xlim(0, cols * cell_w)
ax.set_ylim(0, rows * cell_h)
ax.set_aspect('equal')
ax.axis('off')

for idx, rgb in enumerate(colors):
    c = idx % cols
    r = rows - 1 - (idx // cols)  # plot top-to-bottom
    x = c * cell_w
    y = r * cell_h

    # Swatch rectangle
    ax.add_patch(Rectangle((x, y), cell_w, cell_h, facecolor=(rgb[0]/255, rgb[1]/255, rgb[2]/255), edgecolor='black', linewidth=0.5))

    # Label text (choose white/black based on luminance for readability)
    text_color = 'white' if luminance(rgb) < 128 else 'black'
    label = f"{idx+1}: {rgb} {rgb_to_hex(rgb)}"
    ax.text(x + 0.03, y + 0.03, label, fontsize=8, va='bottom', ha='left', color=text_color)

# Save the figure
out_path = "color_swatches.png"
plt.tight_layout(pad=0.5)
plt.savefig(out_path, dpi=200, bbox_inches='tight')
plt.show()

out_path
