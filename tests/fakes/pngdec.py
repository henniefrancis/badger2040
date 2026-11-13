"""Fake pngdec. FILES maps path -> (width, height); decode calls are recorded."""
FILES = {}
decoded = []


def reset():
    FILES.clear()
    decoded[:] = []


class PNG:
    def __init__(self, display):
        self.cur = None

    def open_file(self, path):
        if path not in FILES:
            raise OSError("no such file " + path)
        self.cur = path

    def get_width(self):
        return FILES[self.cur][0]

    def get_height(self):
        return FILES[self.cur][1]

    def decode(self, x, y):
        decoded.append((self.cur, x, y))
