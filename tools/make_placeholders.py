"""Regenerate the clearly-labelled placeholder logos and icons shipped in device/.

These stand in for trademarked logos (AWS, Microsoft, GitHub) so the badge runs
out of the box. Replace them with your own via tools/convert_image.py.
"""
import os
import sys

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from convert_image import convert  # noqa: E402

IMAGES = os.path.join(ROOT, "device", "images")
APPS = os.path.join(ROOT, "device", "henniefrancis")


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
    full_logo(os.path.join(IMAGES, "aws.png"), "AWS LOGO")
    full_logo(os.path.join(IMAGES, "microsoft.png"), "MICROSOFT LOGO")
    icon(os.path.join(APPS, "icon-aws.png"), "AWS")
    icon(os.path.join(APPS, "icon-microsoft.png"), "MS")
    icon(os.path.join(APPS, "icon-project.png"), "GIT")
    # personal icon is derived from the owner's own public photo
    convert(os.path.join(IMAGES, "hennie.png"), os.path.join(APPS, "icon-personal.png"), "icon", dither=True)
    print("placeholders written")


if __name__ == "__main__":
    main()
