"""Fake badger2040 module for host tests."""
WIDTH = 296
HEIGHT = 128
BUTTON_A, BUTTON_B, BUTTON_C, BUTTON_UP, BUTTON_DOWN = 12, 13, 14, 15, 11
UPDATE_NORMAL, UPDATE_MEDIUM, UPDATE_FAST, UPDATE_TURBO = 0, 1, 2, 3

# Test controls (reset by conftest)
wake_buttons = set()
held = set()          # buttons currently held down
script = []           # list of sets: what is held on successive pressed_any() polls
halt_limit = 3
instances = []


def reset():
    wake_buttons.clear()
    held.clear()
    script[:] = []
    instances[:] = []


def pressed_to_wake(pin):
    return pin in wake_buttons


def woken_by_button():
    return bool(wake_buttons)


def reset_pressed_to_wake():
    wake_buttons.clear()


class StopLoop(Exception):
    pass


class _Gfx:
    pass


class Badger2040:
    def __init__(self):
        self.calls = []
        self.display = _Gfx()
        self.halts = 0
        self.updates = 0
        self.speed = None
        self._cur = set()
        self.font = "bitmap8"
        instances.append(self)

    def _rec(self, name, *a):
        self.calls.append((name,) + a)

    def set_update_speed(self, s):
        self.speed = s

    def set_thickness(self, t):
        pass

    def set_font(self, f):
        self.font = f
        self._rec("font", f)

    def led(self, v):
        pass

    def set_pen(self, p):
        self._rec("pen", p)

    def clear(self):
        self._rec("clear")

    def rectangle(self, x, y, w, h):
        self._rec("rect", x, y, w, h)

    def line(self, *a):
        self._rec("line", *a)

    def text(self, t, x, y, wrap=None, scale=1):
        self._rec("text", t, x, y, scale)

    def measure_text(self, t, scale=1, spacing=1):
        # bitmap8 measured on the device: about 4.8 px per character at scale 1 (172 px for 18 chars at scale 2); vector fonts wider
        per = 4.8 if self.font == "bitmap8" else 6
        return int(round(len(t) * per * scale))

    def update(self):
        self.updates += 1
        self._rec("update")

    def keepalive(self):
        pass

    def pressed(self, pin):
        return pin in self._cur

    def pressed_any(self):
        self._cur = script.pop(0) if script else set(held)
        return bool(self._cur)

    def halt(self):
        self.halts += 1
        if self.halts >= halt_limit:
            raise StopLoop()

    def texts(self):
        return [c[1] for c in self.calls if c[0] == "text"]

    def rects(self):
        return [c[1:] for c in self.calls if c[0] == "rect"]
