"""Fake qrcode with the real device API; sizes follow the standard ECC L table."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "tools"))
import qr_capacity  # noqa: E402

ECC_LOW, ECC_MEDIUM, ECC_QUARTILE, ECC_HIGH = 0, 1, 2, 3
created = []


class QRCode:
    def __init__(self, ecc=ECC_MEDIUM):
        self.ecc = ecc
        self.text = None
        self.n = 21
        created.append(self)

    def set_text(self, text):
        self.text = text
        v = qr_capacity.qr_version(len(text.encode("utf-8")))
        self.n = qr_capacity.modules_for_version(v) if v else 0
        return bool(v)  # like the real module: False when the text does not fit

    def get_size(self):
        return (self.n, self.n)

    def get_module(self, x, y):
        return (x * 7 + y * 3) % 5 < 2
