"""Regenerate the clearly-labelled placeholder logos and icons shipped in device/.

These stand in for your own logos so the badge runs out of the box.
Replace them with your own via tools/convert_image.py.
"""
import os
import sys

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from convert_image import convert  # noqa: E402

IMAGES = os.path.join(ROOT, "device", "images")
APPS = os.path.join(ROOT, "device", "badge")


def _font(size):
    return ImageFont.load_default(size=size)


def full_logo(path, label):
    im = Image.new("L", (296, 128), 255)
    d = ImageDraw.Draw(im)
    d.rectangle((4, 4, 291, 123), outline=0, width=3)
    d.text((148, 40), "PLACEHOLDER", font=_font(26), fill=0, anchor="mm")
    d.text((148, 78), label, font=_font(22), fill=0, anchor="mm")
    d.text((148, 104), "use tools/convert_image.py", font=_font(12), fill=0, anchor="mm")
    im.convert("1", dither=Image.NONE).save(path, optimize=True)


def photo(path):
    """A 104x128 labelled stand-in for a real head-shot (replace with --kind photo)."""
    im = Image.new("L", (104, 128), 255)
    d = ImageDraw.Draw(im)
    d.rectangle((3, 3, 100, 124), outline=0, width=3)
    d.ellipse((34, 28, 70, 64), outline=0, width=3)          # head
    d.arc((22, 74, 82, 134), start=180, end=360, fill=0, width=3)  # shoulders
    d.text((52, 98), "PHOTO", font=_font(16), fill=0, anchor="mm")
    d.text((52, 114), "PLACEHOLDER", font=_font(11), fill=0, anchor="mm")
    im.convert("1", dither=Image.NONE).save(path, optimize=True)


def icon(path, label):
    im = Image.new("L", (104, 104), 255)
    d = ImageDraw.Draw(im)
    d.rectangle((2, 2, 101, 101), outline=0, width=5)
    d.text((52, 38), label, font=_font(34), fill=0, anchor="mm")
    d.text((52, 74), "TODO", font=_font(22), fill=0, anchor="mm")
    tmp = path + ".tmp.png"
    im.save(tmp)
    try:
        convert(tmp, path, "icon")
    finally:
        os.remove(tmp)


def main():
    full_logo(os.path.join(IMAGES, "company.png"), "COMPANY LOGO")
    full_logo(os.path.join(IMAGES, "event.png"), "EVENT LOGO")
    icon(os.path.join(APPS, "icon-company.png"), "CO")
    icon(os.path.join(APPS, "icon-event.png"), "EV")
    icon(os.path.join(APPS, "icon-project.png"), "PRJ")
    icon(os.path.join(APPS, "icon-work.png"), "WRK")
    photo(os.path.join(IMAGES, "me.png"))
    # profile icon is derived from the sample photo placeholder
    convert(os.path.join(IMAGES, "me.png"), os.path.join(APPS, "icon-profile.png"), "icon", dither=True)
    print("placeholders written")


if __name__ == "__main__":
    main()
