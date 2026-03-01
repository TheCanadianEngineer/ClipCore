import time
import pyperclip
from database import Database
from PIL import ImageGrab, Image
import io
import re

import sys, os

def _app_data_path(filename):
    if getattr(sys, "frozen", False):
        folder = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "ClipCore")
    else:
        folder = os.path.dirname(os.path.abspath(__file__))
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, filename)

db = Database(_app_data_path("clipboard.db"))

last_clip = ""

def check_clips(stop_event, app):
    global last_clip

    while not stop_event.is_set():
        content, category = get_clipboard_content()

        if content is None or content == last_clip:
            pass
        elif db.exists(content):
            print("Already in database")
            db.delete_clip(content)
            db.save(content, category, False)
            last_clip = content
            app.root.after(0, app.update_content)
        else:
            print(f"Different value: {content}")
            db.save(content, category, False)
            last_clip = content
            app.root.after(0, app.update_content)

        time.sleep(1)


def get_clipboard_content():
    clip = ImageGrab.grabclipboard()

    if isinstance(clip, Image.Image):
        buffer = io.BytesIO()
        clip.save(buffer, format="PNG")
        return buffer.getvalue(), "image"
    elif isinstance(clip, list):
        # files copied in explorer
        return clip[0], "file"
    else:
        text = pyperclip.paste()
        if text:
            text = text.strip()

            # 🌐 LINK DETECTION
            url_pattern = re.compile(
                r'^(https?:\/\/)?'      # http:// or https:// (optional)
                r'([\w\-]+\.)+'         # domain
                r'[a-zA-Z]{2,}'         # TLD (.com, .org, etc.)
                r'(\/\S*)?$'            # optional path
            )

            if url_pattern.match(text):
                return text, "link"

        return text, "text"