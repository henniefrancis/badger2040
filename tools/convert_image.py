"""Convert a logo or photo into a 1-bit PNG for the Badger 2040.

Examples:
  python tools/convert_image.py my-logo.png config/images/aws.png --kind logo
  python tools/convert_image.py my-logo.png config/icons/icon-aws.png --kind icon
  python tools/convert_image.py photo.jpg config/images/me.png --kind photo

Kinds:
  logo   fits inside the full 296x128 screen, centred on white (full-screen page)
  icon   52x52, as drawn by the launcher (icon-<app>.png)
  badge  fits inside 104x128 (the photo on a badge page), plain
  photo  104x128 portrait pipeline tuned for e-ink: tight crop, contrast, sharpen, brighten,
         Floyd-Steinberg (recommended for the badge photo)

Only use logos and trademarks you are entitled to use.
"""
import argparse
import os
import sys
import warnings

from PIL import Image, ImageChops, ImageFilter, ImageOps

# Explicit decompression-bomb limit (Pillow warns above this, errors above twice this).
Image.MAX_IMAGE_PIXELS = 50_000_000

KINDS = {"logo": (296, 128), "icon": (52, 52), "badge": (104, 128), "photo": (104, 128)}
DEFAULT_THRESHOLD = 128

# --kind photo pipeline parameters (chosen from previews by the owner)
PHOTO_INVERT_THRESHOLD = 12   # inverted pixel > 12, i.e. pixel < 243, counts as content
PHOTO_MARGIN = 3
PHOTO_AUTOCONTRAST_CUTOFF = 1
PHOTO_UNSHARP = (1.2, 160, 2)  # radius, percent, threshold
PHOTO_GAMMA = 0.75
PHOTO_MIN_SIZE = 16  # smaller inputs cannot give a usable photo (a 1x1 input became solid black)


class BlankImageError(ValueError):
    """The converted image is entirely white (for example a fully transparent input)."""


def photo_pipeline(gray, size=(104, 128)):
    """Tight crop -> pad to aspect -> LANCZOS -> autocontrast -> unsharp -> gamma -> Floyd-Steinberg."""
    box_w, box_h = size
    mask = ImageOps.invert(gray).point(lambda p: 255 if p > PHOTO_INVERT_THRESHOLD else 0)
    bbox = mask.getbbox()
    if bbox:
        x0, y0, x1, y1 = bbox
        m = PHOTO_MARGIN
        gray = gray.crop((max(0, x0 - m), max(0, y0 - m), min(gray.width, x1 + m), min(gray.height, y1 + m)))
    w, h = gray.size
    aspect = box_w / box_h
    new_w, new_h = (w, int(round(w / aspect))) if w / h > aspect else (int(round(h * aspect)), h)
    new_w, new_h = max(new_w, w), max(new_h, h)
    padded = Image.new("L", (new_w, new_h), 255)
    padded.paste(gray, ((new_w - w) // 2, (new_h - h) // 2))
    img = padded.resize((box_w, box_h), Image.LANCZOS)
    img = ImageOps.autocontrast(img, cutoff=PHOTO_AUTOCONTRAST_CUTOFF)
    radius, percent, threshold = PHOTO_UNSHARP
    img = img.filter(ImageFilter.UnsharpMask(radius=radius, percent=percent, threshold=threshold))
    lut = [int(round(255 * (i / 255) ** PHOTO_GAMMA)) for i in range(256)]
    img = img.point(lut)
    return img.convert("1", dither=Image.FLOYDSTEINBERG)


def convert(src, dst, kind, threshold=DEFAULT_THRESHOLD, dither=False, invert=False, allow_blank=False):
    """Write a 1-bit PNG at the exact size for kind. Returns the output size."""
    if kind not in KINDS:
        raise ValueError("kind must be one of " + ", ".join(sorted(KINDS)))
    if not 0 <= threshold <= 255:
        raise ValueError("threshold must be 0..255")
    if os.path.abspath(src) == os.path.abspath(dst):
        raise ValueError("output must differ from input")
    box_w, box_h = KINDS[kind]
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)  # treat as an error, not a warning
        with Image.open(src) as im:
            if kind == "photo" and (im.width < PHOTO_MIN_SIZE or im.height < PHOTO_MIN_SIZE):
                raise ValueError("input is %dx%d; --kind photo needs at least %dx%d"
                                 % (im.width, im.height, PHOTO_MIN_SIZE, PHOTO_MIN_SIZE))
            im = im.convert("RGBA")
            white = Image.new("RGBA", im.size, (255, 255, 255, 255))
            gray = Image.alpha_composite(white, im).convert("L")
    if kind == "photo":
        out = photo_pipeline(gray, (box_w, box_h))
    else:
        gray.thumbnail((box_w, box_h), Image.LANCZOS)
        canvas = Image.new("L", (box_w, box_h), 255)
        canvas.paste(gray, ((box_w - gray.width) // 2, (box_h - gray.height) // 2))
        if invert:
            canvas = canvas.point(lambda p: 255 - p)
        if dither:
            out = canvas.convert("1", dither=Image.FLOYDSTEINBERG)
        else:
            out = canvas.point(lambda p: 255 if p >= threshold else 0).convert("1", dither=Image.NONE)
    if not allow_blank and out.getextrema() == (255, 255):
        raise BlankImageError("output is entirely white (transparent or blank input?); use --allow-blank to keep it")
    os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)
    out.save(dst, format="PNG", optimize=True)
    return out.size


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input")
    ap.add_argument("output")
    ap.add_argument("--kind", choices=sorted(KINDS), required=True)
    ap.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD)
    ap.add_argument("--dither", action="store_true", help="Floyd-Steinberg dithering (photos)")
    ap.add_argument("--allow-blank", action="store_true", help="write the file even if it is entirely white")
    ap.add_argument("--invert", action="store_true", help="swap black and white")
    args = ap.parse_args(argv)
    try:
        size = convert(args.input, args.output, args.kind, args.threshold, args.dither, args.invert,
                       args.allow_blank)
    except (OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning) as e:
        print("error: %s: %s" % (type(e).__name__, str(e).splitlines()[0] if str(e) else "failed"), file=sys.stderr)
        return 1
    print("wrote %s (%dx%d, 1-bit)" % (args.output, size[0], size[1]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
