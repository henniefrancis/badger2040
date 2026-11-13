"""QR code size maths for byte mode at error correction level L (no extra library).

Capacities are the standard ISO/IEC 18004 byte-mode data capacities at ECC L
for versions 1..40. Modules per side = 17 + 4 * version.
"""

BYTE_CAPACITY_L = (
    17, 32, 53, 78, 106, 134, 154, 192, 230, 271,
    321, 367, 425, 458, 520, 586, 644, 718, 792, 858,
    929, 1003, 1091, 1171, 1273, 1367, 1465, 1528, 1628, 1732,
    1840, 1952, 2068, 2188, 2303, 2431, 2563, 2699, 2809, 2953,
)

DISPLAY_HEIGHT = 128
MIN_PIXELS_PER_MODULE = 2


def qr_version(num_bytes):
    """Smallest version holding num_bytes in byte mode at ECC L, or None if > 40."""
    for i, cap in enumerate(BYTE_CAPACITY_L):
        if num_bytes <= cap:
            return i + 1
    return None


def modules_for_version(version):
    return 17 + 4 * version


MAX_BORDER = 4


def auto_border(modules, height=DISPLAY_HEIGHT):
    """Largest border 0..4 that keeps the same px per module as border 0."""
    base = height // modules
    return max(b for b in range(MAX_BORDER + 1) if height // (modules + 2 * b) == base)


def analyse(text, height=DISPLAY_HEIGHT, border=0):
    """Return dict(bytes, version, modules, px, size) for a payload string.

    border is an int or "auto"; px and size are for the code plus that many
    quiet-zone modules per side, and the result includes the border used.
    """
    n = len(text.encode("utf-8"))
    version = qr_version(n)
    if version is None:
        return {"bytes": n, "version": None, "modules": None, "px": 0, "size": 0, "border": 0}
    modules = modules_for_version(version)
    if border == "auto":
        border = auto_border(modules, height)
    total = modules + 2 * border
    px = height // total
    return {"bytes": n, "version": version, "modules": modules, "px": px, "size": px * total, "border": border}
