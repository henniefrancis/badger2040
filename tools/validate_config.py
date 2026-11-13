"""Validate a badge config on the PC before it goes anywhere near the badge.

  python tools/validate_config.py <folder containing badge.json> [--allow-placeholders]
  python tools/validate_config.py config/badge.example.json --allow-placeholders

Checks: structure (the same rules the badge applies), every QR page is at least
2 px per module at error correction L (standard capacity table, no extra
library), referenced images exist, and (unless --allow-placeholders) the config
is not still the example placeholders.
"""
import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "device", "lib"))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import badgekit  # noqa: E402
import qr_capacity  # noqa: E402

PLACEHOLDER_NAMES = ("Your Name",)
PLACEHOLDER_EMAIL_DOMAINS = ("example.com", "example.org", "example.net")
PLACEHOLDER_URL_HOSTS = ("example.com", "example.org", "example.net")
PLACEHOLDER_LINKEDIN = "your-handle"
REPO_IMAGES = os.path.join(ROOT, "device", "images")
REPO_ICONS = os.path.join(ROOT, "device", "badge")
# Repo files that stand in for trademarked logos. They must never silently replace real ones.
PLACEHOLDER_IMAGES = ("company.png", "event.png")
PLACEHOLDER_ICONS = ("icon-company.png", "icon-event.png", "icon-project.png")


def resolve_config_file(path):
    return os.path.join(path, "badge.json") if os.path.isdir(path) else path


def iter_pages(cfg):
    for key in sorted(cfg["sections"]):
        sec = cfg["sections"][key]
        for i, page in enumerate(sec["pages"]):
            yield key, i, sec, page


def qr_report(cfg):
    """Return (rows, errors). A row is (where, bytes, modules, px, size, border)."""
    rows, errors = [], []
    border = cfg.get("qr_border", 0)
    targets = [("section %s page %d" % (k, i + 1), p) for k, i, _, p in iter_pages(cfg) if p["type"] == "qr"]
    for where, page in targets:
        info = qr_capacity.analyse(badgekit.qr_payload(page), border=border)
        rows.append((where, info["bytes"], info["modules"], info["px"], info["size"], info["border"]))
        if info["modules"] is None:
            errors.append("%s: payload of %d bytes does not fit any QR code" % (where, info["bytes"]))
        elif info["px"] < qr_capacity.MIN_PIXELS_PER_MODULE:
            errors.append("%s: QR is %d modules (%d bytes) plus qr_border %s, only %d px per module; "
                          "shorten the content or lower qr_border" % (where, info["modules"], info["bytes"], border, info["px"]))
    return rows, errors


def find_placeholders(cfg):
    """List values that are still the example placeholders."""
    found = []

    def host(url):
        m = re.match(r"https?://([^/:]+)", url)
        return m.group(1).lower() if m else ""

    for key, i, _, page in iter_pages(cfg):
        where = "section %s page %d" % (key, i + 1)
        if page.get("name") in PLACEHOLDER_NAMES:
            found.append(where + ": name is the placeholder")
        if "url" in page and host(page["url"]) in PLACEHOLDER_URL_HOSTS:
            found.append(where + ": url is the placeholder")
        v = page.get("vcard")
        if v:
            if v.get("name") in PLACEHOLDER_NAMES:
                found.append(where + ": vcard name is the placeholder")
            if v.get("email", "").lower().rsplit("@", 1)[-1] in PLACEHOLDER_EMAIL_DOMAINS:
                found.append(where + ": vcard email is the placeholder")
            digits = re.sub(r"\D", "", v.get("phone", ""))
            if digits and set(digits) == {"0"}:
                found.append(where + ": vcard phone is the placeholder")
            if PLACEHOLDER_LINKEDIN in v.get("linkedin", ""):
                found.append(where + ": vcard linkedin is the placeholder")
    return found


def wrapper_sections():
    """Map wrapper app file name -> section key it opens, for wrappers in device/badge."""
    found = {}
    if not os.path.isdir(REPO_ICONS):
        return found
    for n in sorted(os.listdir(REPO_ICONS)):
        if not n.endswith(".py"):
            continue
        with open(os.path.join(REPO_ICONS, n), encoding="utf-8") as f:
            text = f.read()
        m = re.search(r'badgekit\.run_section\("([a-z0-9_]+)"\)', text)
        if "import badgekit" in text and m:
            found[n] = m.group(1)
    return found


def wrapper_warnings(cfg):
    return ["wrapper app %s opens section %r, which is not in the config (it will show an error page)" % (n, k)
            for n, k in wrapper_sections().items() if k not in cfg["sections"]]


def image_paths(cfg):
    paths = set()
    for _, _, _, page in iter_pages(cfg):
        if "image" in page:
            paths.add(page["image"])
    return sorted(paths)


def image_findings(cfg, config_dir):
    """Return (missing, placeholder_fallbacks, notes) for images and launcher icons.

    Config images must be /images/<name>.png; they are looked up as
    <config>/images/<name> and deploy copies them to exactly /images/<name>.
    """
    missing, fallbacks, notes = [], [], []
    for p in image_paths(cfg):
        name = os.path.basename(p)
        if os.path.isfile(os.path.join(config_dir, "images", name)):
            continue
        if not os.path.isfile(os.path.join(REPO_IMAGES, name)):
            missing.append(p)
        elif name in PLACEHOLDER_IMAGES:
            fallbacks.append("image " + p)
        else:
            notes.append("note: %s not in your config folder, the repo copy will be used" % p)
    for name in PLACEHOLDER_ICONS:
        if not os.path.isfile(os.path.join(config_dir, "icons", name)):
            fallbacks.append("launcher icon " + name)
    return missing, fallbacks, notes


def _bad_chars(t):
    return any(ord(c) > 126 or ord(c) < 32 for c in t)


def non_ascii_texts(cfg):
    """Drawn text containing characters the fonts cannot show."""
    bad = []
    for key, i, sec, page in iter_pages(cfg):
        where = "section %s page %d" % (key, i + 1)
        texts = [sec["title"], page.get("name", ""), page.get("website", "")]
        header = page.get("header", [])
        texts += page.get("lines", []) + ([header] if isinstance(header, str) else header)
        texts += [page.get("title", ""), page.get("text", "")]
        for t in texts:
            if _bad_chars(t):
                bad.append("%s: non-ASCII text %r will not draw correctly" % (where, t))
    return bad


def est_bitmap(text, scale=1):
    return int(round(len(text) * badgekit.BITMAP_CHAR_WIDTH * scale))


def bar_and_text_findings(cfg):
    """Return (errors, warnings) for house title bars and QR body text (widths are estimates)."""
    errors, warnings = [], []
    pad2 = 2 * badgekit.TEXT_BAR_PAD
    for key, i, sec, page in iter_pages(cfg):
        where = "section %s page %d" % (key, i + 1)
        if page["type"] == "badge":
            fit = badgekit.WIDTH - pad2
            if est_bitmap(page["header"].strip()) > fit:
                errors.append("%s: header %r does not fit the %d px bar at scale 1 (estimate)" % (where, page["header"], fit))
            avail = badgekit.WIDTH - badgekit.BADGE_TEXT_X
            if est_bitmap(page["name"], badgekit.BADGE_NAME_SCALE) > avail:
                errors.append("%s: name %r does not fit %d px at scale %d (estimate)"
                              % (where, page["name"], avail, badgekit.BADGE_NAME_SCALE))
            for k in ("title", "website"):
                if page.get(k) and est_bitmap(page[k], badgekit.BADGE_LINE_SCALE) > avail:
                    warnings.append("%s: %s %r is wider than the screen at scale %d and will be cut (estimate)"
                                    % (where, k, page[k], badgekit.BADGE_LINE_SCALE))
        elif page["type"] == "qr":
            info = qr_capacity.analyse(badgekit.qr_payload(page), border=cfg.get("qr_border", 0))
            if not info["modules"]:
                continue
            lay = badgekit.qr_layout(info["modules"], border=cfg.get("qr_border", 0))
            if not lay:
                continue
            bar_w = lay["left"] - badgekit.BAR_GAP
            title = page.get("title") or sec["title"]
            if est_bitmap(title) > bar_w - pad2:
                errors.append("%s: title %r does not fit the %d px bar at scale 1 (estimate)" % (where, title, bar_w - pad2))
            text = page.get("text")
            if text:
                words = text.split()
                wide = [w for w in words if est_bitmap(w) > bar_w - pad2]
                if wide:
                    errors.append("%s: word %r does not fit the text area at scale 1 (estimate)" % (where, wide[0]))
                else:
                    blk = badgekit.place_text_block(lambda t, sc: est_bitmap(t, sc), text, bar_w)
                    if blk["scale"] == 1:
                        warnings.append("%s: text only fits at the small size (estimate)" % where)
                    if not blk["fits"]:
                        warnings.append("%s: text is too long and will be cut with .. (estimate)" % where)
    return errors, warnings


def layout_warnings(cfg):
    """Estimated text fit warnings (bitmap8 widths are approximate: about 5 px per character at scale 1)."""
    out = []
    for key, i, _, page in iter_pages(cfg):
        where = "section %s page %d" % (key, i + 1)
        if page["type"] == "text":
            full = badgekit.WIDTH - 2 * badgekit.LEFT_PADDING
            for n, t in enumerate(page["lines"]):
                if est_bitmap(t) > full:
                    out.append("%s: text line %d %r will be truncated with .. (estimate)" % (where, n + 1, t))
            if est_bitmap(page["header"]) > badgekit.WIDTH - 2 * badgekit.TEXT_BAR_PAD:
                out.append("%s: header %r will be truncated with .. (estimate)" % (where, page["header"]))

    return out


def image_width_warnings(cfg, config_dir):
    """Warn when a badge page's image_w does not match the PNG's real width (pngdec cannot scale down)."""
    out = []
    try:
        from PIL import Image
    except ImportError:
        return out
    for key, i, _, page in iter_pages(cfg):
        if page["type"] != "badge":
            continue
        name = os.path.basename(page["image"])
        for folder in (os.path.join(config_dir, "images"), REPO_IMAGES):
            path = os.path.join(folder, name)
            if os.path.isfile(path):
                try:
                    with Image.open(path) as im:
                        width = im.width
                except (OSError, ValueError):
                    break
                want = page.get("image_w", badgekit.DEFAULT_IMAGE_W)
                if width != want:
                    out.append("section %s page %d: image_w is %d but %s is %d px wide (pngdec cannot scale it down)"
                               % (key, i + 1, want, name, width))
                break
    return out


def validate(path, allow_placeholders=False, allow_placeholder_images=False):
    """Return (errors, report_lines). Warnings are report lines starting with 'warning:'."""
    cfg_file = resolve_config_file(path)
    config_dir = os.path.dirname(os.path.abspath(cfg_file))
    report = []
    try:
        with open(cfg_file, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except (OSError, ValueError) as e:
        return ["cannot read %s: %s" % (cfg_file, e)], report
    try:
        badgekit.validate_config(cfg)
    except badgekit.ConfigError as e:
        return ["config: %s" % e], report
    errors = []
    for key in badgekit.SECTION_KEYS:
        if key not in cfg["sections"]:
            errors.append("section %s is missing; launcher app %s would show an error page"
                          % (key, badgekit.SECTION_APPS[key]))
    rows, qr_errors = qr_report(cfg)
    errors.extend(qr_errors)
    for where, nbytes, modules, px, size, border in rows:
        report.append("QR %-18s %4d bytes  %s modules  border %d  %d px/module  %d px" % (where, nbytes, modules, border, px, size))
    missing, fallbacks, notes = image_findings(cfg, config_dir)
    report.extend(notes)
    for p in missing:
        errors.append("image %s not found in %s or device/images" % (p, os.path.join(config_dir, "images")))
    for f in fallbacks:
        msg = "%s would fall back to a repo PLACEHOLDER; put your own file in %s" % (f, config_dir)
        if allow_placeholder_images:
            report.append("WARNING: " + msg)
        else:
            errors.append(msg + " (or pass --allow-placeholder-images)")
    bar_errors, bar_warnings = bar_and_text_findings(cfg)
    errors.extend(bar_errors)
    report.extend("warning: " + w for w in non_ascii_texts(cfg) + layout_warnings(cfg) + bar_warnings
                  + wrapper_warnings(cfg) + image_width_warnings(cfg, config_dir))
    if not allow_placeholders:
        errors.extend("placeholder: " + m for m in find_placeholders(cfg))
    return errors, report


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("config", help="folder containing badge.json, or the json file")
    ap.add_argument("--allow-placeholders", action="store_true", help="accept example text values")
    ap.add_argument("--allow-placeholder-images", action="store_true",
                    help="accept repo placeholder logos and icons (prints a warning)")
    args = ap.parse_args(argv)
    errors, report = validate(args.config, args.allow_placeholders, args.allow_placeholder_images)
    for line in report:
        print(line)
    for e in errors:
        print("ERROR: " + e, file=sys.stderr)
    print("config OK" if not errors else "config has %d problem(s)" % len(errors))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
