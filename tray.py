from PIL import Image, ImageDraw

def create_tray_icon_image():
    """Create a simple colored circle as the tray icon."""
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((4, 4, 60, 60), fill=(0, 120, 215))
    return img