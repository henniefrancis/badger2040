"""badgekit: shared code for the Badger 2040 section badge.

Lives at /lib/badgekit.py on the badge. The apps in /badge (profile,
company, event, project, ...) are thin wrappers that call run_section() with a
section key: a, b, c, p, or the name of an extra section (for example work).

The badge page look is adapted from Pimoroni's Badger 2040 badge example
(MIT, Copyright (c) Pimoroni Ltd, https://github.com/pimoroni/badger2040).

Written for MicroPython 1.23 (Badger OS v0.0.5) and also importable on a PC:
everything above the "Hardware" marker is pure Python with no hardware imports
so it can be unit tested and reused by tools/validate_config.py.
"""
import gc
import json
import time

# ---------------------------------------------------------------- constants
WIDTH = 296
HEIGHT = 128

APP_DIR = "/badge"
CONFIG_PATH = "/badge/config/badge.json"
STATE_NAME = "badge"

SECTION_KEYS = ("a", "b", "c", "p")
SECTION_APPS = {"a": "profile", "b": "company", "c": "event", "p": "project"}
EXTRA_KEY_MAX = 16  # extra section keys match ^[a-z][a-z0-9_]{1,15}$ (no re module on the badge)
_KEY_FIRST = "abcdefghijklmnopqrstuvwxyz"
_KEY_REST = _KEY_FIRST + "0123456789_"
BUTTON_SECTIONS = ("a", "b", "c")  # A, B, C jump to these; p is reached from the launcher
IMAGE_DIR = "/images/"

MAX_PAGES = 8
MAX_TITLE = 20
MAX_TEXT = 40
MAX_FIELD = 100
MAX_URL = 200
MAX_PATH = 64
MAX_BAR_TITLE = 40  # bar title (QR title, text-page header, company)
MAX_QR_TEXT = 60
MAX_TEXT_LINES = 6
MAX_TEXT_LINE = 60

VCARD_FIELDS = ("name", "title", "company", "email", "phone", "url", "linkedin")
PAGE_TYPES = ("badge", "image", "qr", "text")
URI_FIELDS = ("url", "linkedin")  # URI values: not text-escaped in a vCard

# Badge page layout (fixed positions, all bitmap8 at whole scales)
DEFAULT_IMAGE_W = 104      # photo width when the page has no image_w; the photo sits at the right edge
LEFT_PADDING = 5
BADGE_TEXT_X = 2           # name, title and website are left aligned here, drawn over the image
BADGE_NAME_SCALE = 3
BADGE_NAME_Y = 24
BADGE_LINE_SCALE = 2       # title and website
BADGE_TITLE_Y = 92
BADGE_WEBSITE_Y = 110

# QR page layout
MAX_QR_BORDER = 4
QR_BORDER_AUTO = "auto"     # explicit "auto": largest border that does not shrink the code
QR_BORDER_DEFAULT = 0       # default: no quiet-zone padding, so the code is as large as density allows
MIN_QR_PX = 2  # modules smaller than this do not scan reliably on e-ink
HEADER_PAD = 5
BAR_GAP = 4            # gap between a QR title bar and the QR box
QR_TEXT_SCALES = (2, 1)  # bitmap8 scales tried for the QR body text, largest first
QR_TEXT_PITCH = 10     # line pitch per scale unit (bitmap8 glyphs are 8 px tall)
BITMAP_GLYPH_HEIGHT = 8

# House title bar (text pages, QR pages, badge company line)
TEXT_BAR_HEIGHT = 16
TEXT_BAR_PAD = 4

# Text page layout (like the Pimoroni info app)
TEXT_LINE_HEIGHT = 15
TEXT_FIRST_Y = 22
BITMAP_CHAR_WIDTH = 4.8  # bitmap8 width per char at scale 1, averaged from device measurements; PC validator only

# Error page layout
ERROR_LINE_PITCH = 11
ERROR_MAX_LINES = 8
ERROR_HINT = "Check /badge/config/badge.json"

SETTLE_SECONDS = 0.06
RELEASE_POLL_SECONDS = 0.01

_PATH_CHARS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-./"


def _describe(e):
    return str(e) or type(e).__name__


def _log(msg):
    print("badgekit: " + str(msg))


# ------------------------------------------------------------------- config
class ConfigError(Exception):
    pass


def valid_extra_key(key):
    """True for keys matching ^[a-z][a-z0-9_]{1,15}$ (extra sections, named like their wrapper app)."""
    if not isinstance(key, str) or not 2 <= len(key) <= EXTRA_KEY_MAX or key[0] not in _KEY_FIRST:
        return False
    for c in key:
        if c not in _KEY_REST:
            return False
    return True


def app_for(section):
    """Wrapper app name for a section key, or None."""
    if section in SECTION_APPS:
        return SECTION_APPS[section]
    return section if valid_extra_key(section) else None


def _need(cond, msg):
    if not cond:
        raise ConfigError(msg)


def _check_text(v, where, maxlen, required=True, no_ctrl=True):
    _need(isinstance(v, str), where + " must be text")
    _need(len(v) <= maxlen, where + " is too long")
    if no_ctrl:
        for c in v:
            _need(not _is_ctrl(c), where + " must not contain control characters")
    if required:
        _need(len(v.strip()) > 0, where + " is empty")


def _check_lines(v, where, maxn, maxlen=MAX_TEXT, required=True):
    _need(isinstance(v, list), where + " must be a list")
    _need(len(v) <= maxn, where + " has too many lines (max %d)" % maxn)
    for i, line in enumerate(v):
        _check_text(line, "%s[%d]" % (where, i), maxlen, required=required)


def _check_path(v, where):
    _need(isinstance(v, str), where + " must be text")
    _need(0 < len(v) <= MAX_PATH, where + " has a bad length")
    _need(v[0] == "/" and v.endswith(".png"), where + " must be an absolute .png path")
    _need(".." not in v, where + " must not contain ..")
    for c in v:
        _need(c in _PATH_CHARS, where + " has a bad character")
    name = v[len(IMAGE_DIR):]
    _need(v.startswith(IMAGE_DIR) and "/" not in name and name[0] != ".",
          where + " must be /images/<name>.png")


def _check_url(v, where):
    _need(isinstance(v, str), where + " must be text")
    _need(len(v) <= MAX_URL, where + " is too long")
    _need(v.startswith("http://") or v.startswith("https://"), where + " must start with http(s)://")
    for c in v:
        _need(c > " ", where + " must not contain spaces or control characters")


def _check_vcard(v, where):
    _need(isinstance(v, dict), where + " must be an object")
    for k in v:
        _need(k in VCARD_FIELDS, where + " has unknown field " + str(k))
        _check_text(v[k], where + "." + k, MAX_FIELD, required=(k == "name"), no_ctrl=False)
        if k in URI_FIELDS:
            for c in v[k]:
                _need(c > " " and not _is_ctrl(c), where + "." + k + " must not contain spaces or control characters")
    _need("name" in v, where + ".name is required")


def _check_page(p, where):
    _need(isinstance(p, dict), where + " must be an object")
    t = p.get("type")
    _need(t in PAGE_TYPES, where + " has unknown type " + str(t))
    if t == "badge":
        _need("company" not in p and "lines" not in p,
              where + ' "company" and "lines" were replaced by "header", "title" and "website"')
        _check_path(p.get("image"), where + ".image")
        _check_text(p.get("header"), where + ".header", MAX_BAR_TITLE)
        _check_text(p.get("name"), where + ".name", MAX_TEXT)
        for k in ("title", "website"):
            if k in p:
                _check_text(p[k], where + "." + k, MAX_TEXT)
        w = p.get("image_w", DEFAULT_IMAGE_W)
        _need(type(w) is int and 1 <= w <= WIDTH, where + ".image_w must be a whole number 1 to %d" % WIDTH)
        y = p.get("image_y", 0)
        _need(type(y) is int and 0 <= y <= HEIGHT, where + ".image_y must be a whole number 0 to %d" % HEIGHT)
    elif t == "image":
        _check_path(p.get("image"), where + ".image")
    elif t == "text":
        _check_text(p.get("header"), where + ".header", MAX_BAR_TITLE)
        _need("lines" in p, where + ".lines is required")
        _check_lines(p["lines"], where + ".lines", MAX_TEXT_LINES, MAX_TEXT_LINE, required=False)  # "" = spacer
    else:
        _need(("vcard" in p) != ("url" in p), where + " needs exactly one of vcard or url")
        _need("header" not in p, where + ' "header" was replaced by "title" and "text"')
        if "title" in p:
            _check_text(p["title"], where + ".title", MAX_BAR_TITLE)
        if "text" in p:
            _check_text(p["text"], where + ".text", MAX_QR_TEXT)
        if "vcard" in p:
            _check_vcard(p["vcard"], where + ".vcard")
        else:
            _check_url(p["url"], where + ".url")


def _check_section(key, sec):
    where = "section " + key
    _need(isinstance(sec, dict), where + " must be an object")
    _check_text(sec.get("title"), where + ".title", MAX_TITLE)
    pages = sec.get("pages")
    _need(isinstance(pages, list) and len(pages) > 0, where + " has no pages")
    _need(len(pages) <= MAX_PAGES, where + " has too many pages")
    for i, p in enumerate(pages):
        _check_page(p, "%s.pages[%d]" % (where, i))


def validate_config(cfg):
    """Raise ConfigError with a short message if cfg is unusable; else return it."""
    _need(isinstance(cfg, dict), "config must be an object")
    secs = cfg.get("sections")
    _need(isinstance(secs, dict) and len(secs) > 0, "config has no sections")
    for key in secs:
        _need(key in SECTION_KEYS or valid_extra_key(key), "unknown section " + str(key))
        _check_section(key, secs[key])
    border = cfg.get("qr_border", QR_BORDER_DEFAULT)
    _need(border == QR_BORDER_AUTO or (type(border) is int and 0 <= border <= MAX_QR_BORDER),
          'qr_border must be "auto" or a whole number 0 to 4')
    _need("project" not in cfg, 'top-level "project" was replaced by section p under "sections"')
    return cfg


def load_config(path=CONFIG_PATH):
    try:
        with open(path, "r") as f:
            raw = f.read()
    except OSError:
        raise ConfigError("Cannot read config file")
    try:
        cfg = json.loads(raw)
    except ValueError:
        raise ConfigError("Config is not valid JSON")
    raw = None
    return validate_config(cfg)


# -------------------------------------------------------------------- vCard
def _is_ctrl(c):
    """Control, DEL, C1 (incl. NEL U+0085), U+2028 and U+2029: line breaks in some parsers."""
    n = ord(c)
    return n < 32 or 127 <= n <= 159 or n == 0x2028 or n == 0x2029


def strip_ctrl(value):
    return "".join(c for c in value if not _is_ctrl(c))


def escape_vcard(value):
    """Escape a text value per RFC 2426: backslash, semicolon, comma, newline."""
    v = value.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
    v = v.replace("\r\n", "\\n").replace("\r", "\\n").replace("\n", "\\n")
    return strip_ctrl(v)


def _split_name(name):
    parts = name.split()
    if len(parts) < 2:
        return name.strip(), ""
    return parts[-1], " ".join(parts[:-1])


def build_vcard(f):
    """Build a vCard 3.0 string from the config vcard object."""
    family, given = _split_name(f["name"])
    lines = [
        "BEGIN:VCARD",
        "VERSION:3.0",
        "N:%s;%s;;;" % (escape_vcard(family), escape_vcard(given)),
        "FN:" + escape_vcard(" ".join(f["name"].split())),
    ]
    for key, prop in (("company", "ORG"), ("title", "TITLE"), ("phone", "TEL"),
                      ("email", "EMAIL"), ("url", "URL"), ("linkedin", "URL")):
        val = f.get(key, "")
        if key in URI_FIELDS:
            # RFC 2426: URL is a URI, so , and ; are legal. Drop control characters so a
            # value can never start a new property.
            val = strip_ctrl(val)
            if val.strip():
                lines.append(prop + ":" + val.strip())
        elif val.strip():
            lines.append(prop + ":" + escape_vcard(val.strip()))
    lines.append("END:VCARD")
    return "\r\n".join(lines)


def qr_payload(page):
    if "vcard" in page:
        return build_vcard(page["vcard"])
    return page["url"]


# ------------------------------------------------------- paging and state
def step_page(page, count, step):
    """Move within a section with wrap-around; one-page sections stay put."""
    if count <= 1:
        return 0
    return (page + step) % count


def apply_button(cfg, section, page, btn):
    """Return the (section, page) that results from pressing btn."""
    if btn in BUTTON_SECTIONS:
        return btn, 0
    if btn in ("up", "down") and section in cfg["sections"]:
        count = len(cfg["sections"][section]["pages"])
        return section, step_page(page, count, -1 if btn == "up" else 1)
    return section, page


def sanitize_state(raw, cfg):
    """Return a valid (section, page) from saved state, or None if it is corrupt."""
    if not isinstance(raw, dict):
        return None
    sec = raw.get("section")
    page = raw.get("page")
    secs = cfg["sections"]
    if not isinstance(sec, str) or sec not in secs:
        return None
    if type(page) is not int or page < 0 or page >= len(secs[sec]["pages"]):
        return None
    return sec, page


# ------------------------------------------------------------------ layout
def auto_border(modules, height=HEIGHT):
    """Largest border 0..MAX_QR_BORDER that keeps the same px per module as border 0."""
    base = height // modules if modules > 0 else 0
    best = 0
    for b in range(MAX_QR_BORDER + 1):
        if height // (modules + 2 * b) == base:
            best = b
    return best


def qr_layout(modules, width=WIDTH, height=HEIGHT, border=0):
    """Largest whole-pixel module size that fits the height; right aligned.

    The code plus a quiet-zone border of `border` modules per side (an int, or "auto" =
    the largest border that does not shrink the code) is sized to fit. "left"/"top"/"size" describe that bordered box,
    "code_left"/"code_top" the code itself. Returns None if modules would be smaller than MIN_QR_PX pixels.
    """
    if modules < 1:
        return None
    if border == QR_BORDER_AUTO:
        border = auto_border(modules, height)
    total = modules + 2 * border
    px = height // total
    if px < MIN_QR_PX:
        return None
    size = px * total
    margin = (height - size) // 2
    left = width - margin - size
    return {
        "px": px,
        "border": border,
        "size": size,
        "left": left,
        "top": margin,
        "code_left": left + border * px,
        "code_top": margin + border * px,
        "text_w": left - 2 * HEADER_PAD,
    }


def wrap_text(measure, text, max_w):
    """Greedy word wrap. measure(str) -> pixel width. Long words are hard-broken."""
    lines = []
    cur = ""
    for word in text.split():
        trial = word if not cur else cur + " " + word
        if measure(trial) <= max_w:
            cur = trial
            continue
        if cur:
            lines.append(cur)
            cur = ""
        while len(word) > 1 and measure(word) > max_w:
            i = len(word) - 1
            while i > 1 and measure(word[:i]) > max_w:
                i -= 1
            lines.append(word[:i])
            word = word[i:]
        cur = word
    if cur:
        lines.append(cur)
    return lines


def header_lines(measure, header, max_w, max_lines=None):
    """Wrap header entries. With max_lines, extra text is cut and the last line ends in '..'."""
    out = []
    for entry in header:
        out.extend(wrap_text(measure, entry, max_w))
    if max_lines is None or len(out) <= max_lines:
        return out
    out = out[:max_lines]
    out[-1] = _shorten(measure, out[-1], max_w)
    return out


def place_text_block(measure, text, area_w, top=TEXT_BAR_HEIGHT, bottom=HEIGHT):
    """Word-wrap text into area_w at the largest whole bitmap8 scale (2, then 1) where every
    line fits, and centre the block horizontally in the area and vertically in top..bottom.

    measure(text, scale) -> pixel width. Returns a dict: scale, lines, pitch, x, y (top of
    the first line), width (widest line), fits (False if even scale 1 needs cut/broken words).
    """
    inner = area_w - 2 * TEXT_BAR_PAD
    avail_h = bottom - top
    chosen = None
    for scale in QR_TEXT_SCALES:
        lines = wrap_text(lambda t: measure(t, scale), text, inner)
        pitch = QR_TEXT_PITCH * scale
        height = (len(lines) - 1) * pitch + BITMAP_GLYPH_HEIGHT * scale if lines else 0
        intact = " ".join(lines).split() == text.split()  # no word had to be broken
        ok = intact and all(measure(t, scale) <= inner for t in lines) and height <= avail_h
        chosen = (scale, lines, pitch, height, ok)
        if ok:
            break
    scale, lines, pitch, height, ok = chosen
    if height > avail_h and lines:  # too many lines even at scale 1: keep what fits, end with ..
        keep = (avail_h - BITMAP_GLYPH_HEIGHT * scale) // pitch + 1
        lines = lines[:keep]
        lines[-1] = _shorten(lambda t: measure(t, scale), lines[-1], inner)
        height = (len(lines) - 1) * pitch + BITMAP_GLYPH_HEIGHT * scale
        ok = False
    width = max([measure(t, scale) for t in lines] or [0])
    return {
        "scale": scale,
        "lines": lines,
        "pitch": pitch,
        "x": max(0, (area_w - width) // 2),
        "y": top + (avail_h - height) // 2,
        "width": width,
        "fits": ok,
    }


def _shorten(measure, text, max_w):
    """Truncate text so text + '..' fits max_w."""
    text = text.rstrip()
    while len(text) > 1 and measure(text + "..") > max_w:
        text = text[:-1].rstrip()
    return text + ".."


def fit_whole(measure, text, max_w, scales):
    """Pick the first whole bitmap scale in scales where text fits max_w; if none does, use the
    last scale and cut the text with '..'. measure(text, scale) -> pixel width. -> (text, scale)."""
    for sc in scales:
        if measure(text, sc) <= max_w:
            return text, sc
    sc = scales[-1]
    return _shorten(lambda t: measure(t, sc), text, max_w), sc


def fit_title(measure, text, max_w):
    """Pick scale 2 then 1; truncate with '..' if still too wide. -> (text, scale)."""
    for scale in (2, 1):
        if measure(text, scale) <= max_w:
            return text, scale
    while len(text) > 1 and measure(text + "..", 1) > max_w:
        text = text[:-1]
    return text + "..", 1


# ======================================================== Hardware (device)
class PageError(Exception):
    pass


def draw_title_bar(display, text, x0, x1):
    """House header: black bar TEXT_BAR_HEIGHT high from x0 to x1, white bitmap8 scale 1 text,
    centred horizontally and vertically in the bar. Over-wide text is cut with '..'."""
    display.set_pen(0)
    display.rectangle(x0, 0, x1 - x0, TEXT_BAR_HEIGHT)
    display.set_pen(15)
    display.set_font("bitmap8")
    # bitmap8 only draws cleanly at whole scales, so too-wide text is cut with '..' (no shrinking)
    text, sc = fit_whole(display.measure_text, text, x1 - x0 - 2 * TEXT_BAR_PAD, (1,))
    w = display.measure_text(text, sc)
    display.text(text, x0 + (x1 - x0 - w) // 2, (TEXT_BAR_HEIGHT - BITMAP_GLYPH_HEIGHT) // 2, x1, int(sc))


class Screen:
    """Draws pages on the e-ink display."""

    def __init__(self, display, png, qrmod):
        self.d = display
        self.png = png
        self.qrmod = qrmod

    # -- helpers
    def _open_png(self, path):
        try:
            self.png.open_file(path)
        except (OSError, RuntimeError):
            raise PageError("Missing image " + path)

    def draw(self, title, page, border=QR_BORDER_DEFAULT):
        t = page["type"]
        if t == "badge":
            self._badge(page)
        elif t == "image":
            self._image(page)
        elif t == "qr":
            self._qr(title, page, border)
        elif t == "text":
            self._text(page)
        else:
            raise PageError("Unknown page type")
        self.d.update()

    # -- badge page
    def _badge(self, p):
        # Exact layout, bitmap8 and whole scales only. 1: clear to white; 2: photo at the right edge,
        # no border; 3: full-width black header bar over the top of the photo; 4: name (scale 3),
        # title and website (scale 2) left aligned over the photo at fixed y positions, no divider.
        d = self.d
        d.set_pen(15)
        d.clear()
        self._open_png(p["image"])
        self.png.decode(WIDTH - p.get("image_w", DEFAULT_IMAGE_W), p.get("image_y", 0))
        draw_title_bar(d, p["header"], 0, WIDTH)
        d.set_pen(0)
        d.set_font("bitmap8")
        avail = WIDTH - BADGE_TEXT_X
        # too-wide text steps down whole scales and is then cut, so it never leaves the screen
        text, sc = fit_whole(d.measure_text, p["name"], avail, (BADGE_NAME_SCALE, 2, 1))
        d.text(text, BADGE_TEXT_X, BADGE_NAME_Y, WIDTH, sc)
        for key, y in (("title", BADGE_TITLE_Y), ("website", BADGE_WEBSITE_Y)):
            if p.get(key):
                text, sc = fit_whole(d.measure_text, p[key], avail, (BADGE_LINE_SCALE, 1))
                d.text(text, BADGE_TEXT_X, y, WIDTH, sc)

    # -- full screen image page
    def _image(self, p):
        d = self.d
        d.set_pen(15)
        d.clear()
        self._open_png(p["image"])
        w = self.png.get_width()
        h = self.png.get_height()
        self.png.decode(max(0, (WIDTH - w) // 2), max(0, (HEIGHT - h) // 2))

    # -- QR page
    def _qr(self, title, p, border=QR_BORDER_DEFAULT):
        d = self.d
        qrm = self.qrmod
        code = qrm.QRCode(qrm.ECC_LOW)
        if not code.set_text(qr_payload(p)):  # the real module returns False if the text does not fit
            raise PageError("QR text does not fit")
        n = code.get_size()[0]
        lay = qr_layout(n, WIDTH, HEIGHT, border)
        if lay is None:
            raise PageError("QR too large: %d modules, border %s" % (n, border))
        px = lay["px"]
        left = lay["code_left"]
        top = lay["code_top"]

        d.set_pen(15)
        d.clear()
        d.set_pen(0)
        for y in range(n):
            x = 0
            while x < n:
                if code.get_module(x, y):
                    x0 = x
                    while x < n and code.get_module(x, y):
                        x += 1
                    d.rectangle(left + x0 * px, top + y * px, (x - x0) * px, px)
                else:
                    x += 1

        bar_x1 = lay["left"] - BAR_GAP  # the bar never reaches the QR box
        draw_title_bar(d, p.get("title") or title, 0, bar_x1)
        if p.get("text"):
            d.set_font("bitmap8")
            blk = place_text_block(d.measure_text, p["text"], bar_x1)
            d.set_pen(0)
            for i, line in enumerate(blk["lines"]):
                d.text(line, blk["x"], blk["y"] + i * blk["pitch"], bar_x1, blk["scale"])

    # -- text page: black header bar, then bitmap8 lines
    def _text(self, p):
        d = self.d
        d.set_pen(15)
        d.clear()
        draw_title_bar(d, p["header"], 0, WIDTH)
        d.set_pen(0)
        avail = WIDTH - 2 * LEFT_PADDING
        for i, line in enumerate(p["lines"][:MAX_TEXT_LINES]):
            if not line.strip():
                continue  # spacer
            text, sc = fit_whole(d.measure_text, line, avail, (1,))
            d.text(text, LEFT_PADDING, TEXT_FIRST_Y + i * TEXT_LINE_HEIGHT, WIDTH, sc)

    # -- error page
    def error(self, message):
        d = self.d
        d.set_pen(15)
        d.clear()
        d.set_pen(0)
        d.rectangle(0, 0, WIDTH, 20)
        d.set_pen(15)
        d.set_font("bitmap8")
        d.text("Badge error", 4, 3, WIDTH, 2)
        d.set_pen(0)

        def measure(s):
            return d.measure_text(s, 1)

        lines = wrap_text(measure, str(message), WIDTH - 12)[:ERROR_MAX_LINES]
        y = 28
        for line in lines:
            d.text(line, 6, y, WIDTH, 1)
            y += ERROR_LINE_PITCH
        d.text(ERROR_HINT, 6, HEIGHT - 12, WIDTH, 1)
        d.update()


class App:
    """One running badge session (one section)."""

    def __init__(self, key, b2040, bos, pngdec, qrmod):
        self.key = key
        self.b = b2040
        self.os = bos
        self.display = b2040.Badger2040()
        self.display.set_update_speed(b2040.UPDATE_NORMAL)
        self.display.led(128)
        self.screen = Screen(self.display, pngdec.PNG(self.display.display), qrmod)
        self.cfg = None
        self.error = None
        self.section = key
        self.page = 0
        self.running_key = key
        self.showing_error = False

    # -- config and state
    def load(self):
        gc.collect()
        try:
            self.cfg = load_config(CONFIG_PATH)
            self.error = None
        except ConfigError as e:
            self.cfg = None
            self.error = str(e)
            _log("config: " + self.error)
        except Exception as e:  # MemoryError, RecursionError, anything else: show the error page
            self.cfg = None
            self.error = "Cannot load config: " + _describe(e)
            _log("config: " + self.error)
        gc.collect()

    def _restore(self):
        """Return (section, page, fresh_launch)."""
        raw = {"section": self.key, "page": 0, "launched": False}
        try:
            self.os.state_load(STATE_NAME, raw)
        except Exception as e:  # corrupt or unreadable state must never crash the badge
            _log("state: " + str(e))
            raw = {}
        fresh = raw.get("launched") is True
        if self.cfg is None:
            return self.key, 0, fresh
        st = sanitize_state(raw, self.cfg)
        if st is None or st[0] != self.key:
            return self.key, 0, fresh
        return st[0], st[1], fresh

    def _save(self):
        try:
            self.os.state_save(STATE_NAME, {"section": self.section, "page": self.page, "launched": False})
            app = app_for(self.section)
            if app and self.section != self.running_key:
                st = {"page": 0, "running": "launcher"}
                self.os.state_load("launcher", st)
                st["running"] = APP_DIR + "/" + app
                self.os.state_save("launcher", st)
                self.running_key = self.section
        except OSError as e:
            _log("save: " + str(e))

    # -- input
    def wake_button(self):
        b = self.b
        if b.pressed_to_wake(b.BUTTON_A) and b.pressed_to_wake(b.BUTTON_C):
            return "exit"
        for name, pin in (("a", b.BUTTON_A), ("b", b.BUTTON_B), ("c", b.BUTTON_C),
                          ("up", b.BUTTON_UP), ("down", b.BUTTON_DOWN)):
            if b.pressed_to_wake(pin):
                return name
        return None

    def read_button(self):
        d = self.display
        b = self.b
        if not d.pressed_any():
            return None
        time.sleep(SETTLE_SECONDS)  # let a near-simultaneous A+C settle
        if d.pressed(b.BUTTON_A) and d.pressed(b.BUTTON_C):
            return "exit"
        for name, pin in (("a", b.BUTTON_A), ("b", b.BUTTON_B), ("c", b.BUTTON_C),
                          ("up", b.BUTTON_UP), ("down", b.BUTTON_DOWN)):
            if d.pressed(pin):
                return name
        return None

    def wait_release(self):
        while self.display.pressed_any():
            time.sleep(RELEASE_POLL_SECONDS)

    # -- actions
    def render(self):
        gc.collect()
        self.showing_error = False
        try:
            if self.cfg is None:
                self.showing_error = True
                self.screen.error(self.error)
            else:
                sec = self.cfg["sections"].get(self.section)
                if sec is None:
                    raise PageError("Section %s is not in the config" % self.section.upper())
                self.screen.draw(sec["title"], sec["pages"][self.page], self.cfg.get("qr_border", QR_BORDER_DEFAULT))
        except Exception as e:  # any draw failure shows an error page, never a crash
            _log("draw: " + _describe(e))
            self.showing_error = True
            gc.collect()
            self.screen.error(_describe(e))
        self._save()

    def exit_to_launcher(self):
        self.os.state_clear_running()
        import machine
        machine.reset()

    def handle(self, btn):
        if btn == "exit":
            self.exit_to_launcher()
            return
        if self.cfg is None:
            self.load()  # any button retries after a config fix
            self.render()
            return
        new = apply_button(self.cfg, self.section, self.page, btn)
        if new == (self.section, self.page) and not self.showing_error:
            return  # nothing changed; after an error page the same button retries
        self.section, self.page = new
        self.render()

    def start(self):
        self.load()
        self.section, self.page, fresh = self._restore()
        wake = None if fresh else self.wake_button()
        if wake == "exit":
            self.exit_to_launcher()
            return
        if wake and self.cfg is not None:
            self.section, self.page = apply_button(self.cfg, self.section, self.page, wake)
        self.render()
        self.wait_release()

    def loop(self):
        while True:
            # A held button can keep the board powered through halt().
            self.display.keepalive()
            btn = self.read_button()
            if btn:
                self.handle(btn)
                self.wait_release()
            self.display.halt()


def _run(key):
    import badger2040
    import badger_os
    import pngdec
    import qrcode
    app = App(key, badger2040, badger_os, pngdec, qrcode)
    app.start()
    app.loop()


def run_section(key):
    if key not in SECTION_KEYS and not valid_extra_key(key):
        raise ValueError("bad section")
    _run(key)

