import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for sub in ("tests/fakes", "device/lib", "tools"):
    sys.path.insert(0, os.path.join(ROOT, sub))

import badger2040  # noqa: E402
import badger_os  # noqa: E402
import pngdec  # noqa: E402
import qrcode  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_fakes():
    badger2040.reset()
    badger_os.reset()
    pngdec.reset()
    qrcode.created[:] = []
    yield
