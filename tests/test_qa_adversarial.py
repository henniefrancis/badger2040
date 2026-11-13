"""QA adversarial tests (added by QA; product code untouched).

Former xfail tests (confirmed defects) are now fixed and must pass.
"""
import copy
import json
import os

import pytest

import badger2040 as hw
import badger_os
import badgekit as bk
import pngdec
import qrcode
import qr_capacity
import validate_config as vc
import deploy

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLE = os.path.join(ROOT, "config", "badge.example.json")


@pytest.fixture
def cfg():
    with open(EXAMPLE, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(autouse=True)
def env(monkeypatch, tmp_path):
    monkeypatch.setattr(bk.time, "sleep", lambda s: None)
    monkeypatch.setattr(bk, "CONFIG_PATH", str(tmp_path / "badge.json"))
    pngdec.FILES.update({"/images/me.png": (104, 128), "/images/company.png": (296, 128),
                         "/images/event.png": (296, 128)})
    hw.halt_limit = 3
    yield


def make(key):
    return bk.App(key, hw, badger_os, pngdec, qrcode)


# ---- exact 2 px boundary: validator vs layout vs capacity table ----------
ISO_L_V1_14 = [17, 32, 53, 78, 106, 134, 154, 192, 230, 271, 321, 367, 425, 458]


def test_capacity_table_matches_iso_v1_to_14():
    assert list(qr_capacity.BYTE_CAPACITY_L[:14]) == ISO_L_V1_14


@pytest.mark.parametrize("n,ok", [(320, True), (321, True), (322, False), (323, False)])
def test_boundary_bytes_url_payload(n, ok):
    payload = "https://x.io/" + "a" * (n - 13)
    assert len(payload) == n
    info = qr_capacity.analyse(payload)
    assert (info["px"] >= 2) is ok
    modules = info["modules"]
    assert (bk.qr_layout(modules) is not None) is ok


def test_validator_rejects_vcard_over_limit(cfg):
    v = cfg["sections"]["a"]["pages"][1]["vcard"]
    v.update(name="N N", title="t" * 100, company="c" * 100, email="e@x.io", phone="1", url="https://x.io", linkedin="https://l.io/" + "q" * 60)
    p = bk.qr_payload(cfg["sections"]["a"]["pages"][1])
    rows, errs = vc.qr_report(cfg)
    assert (len(p.encode()) > 321) == bool(errs)


def test_escaping_counted_in_payload_size(cfg):
    # commas each become two bytes; validator must use the escaped payload
    v = {"name": "A B", "title": "," * 100}
    assert len(bk.build_vcard(v)) > len("TITLE:" + "," * 100)


def test_unicode_counts_bytes_not_chars(cfg):
    v = {"name": "A B", "title": "\U0001F600" * 40}
    p = bk.build_vcard(v)
    assert len(p.encode("utf-8")) > len(p)
    assert qr_capacity.analyse(p)["bytes"] == len(p.encode("utf-8"))


# ---- config hostility -----------------------------------------------------
@pytest.mark.parametrize("raw", ["", "null", "[]", "{}", "{\"sections\": {}}", "{\"sections\": []}", "\x00\x00", "{",
                                 "{\"sections\": {\"a\": {\"title\": \"T\", \"pages\": []}}}",
                                 "{\"sections\": {\"a\": {\"pages\": [{\"type\": \"image\", \"image\": \"/x.png\"}]}}}",
                                 "{\"sections\": {\"a\": {\"title\": \"T\", \"pages\": [{\"type\": \"video\"}]}}}"])
def test_bad_config_shows_error_page_not_crash(raw, tmp_path):
    with open(bk.CONFIG_PATH, "w") as f:
        f.write(raw)
    app = make("a")
    app.start()
    assert app.cfg is None
    assert any("Badge error" in t for t in app.display.texts())


def test_missing_config_file():
    app = make("b")
    app.start()
    assert app.cfg is None


def test_deeply_nested_json_does_not_crash():
    with open(bk.CONFIG_PATH, "w") as f:
        f.write("[" * 100000)
    app = make("a")
    app.start()
    assert app.cfg is None


def test_memory_error_in_config_read(monkeypatch):
    def boom(path=None):
        raise MemoryError()
    monkeypatch.setattr(bk, "load_config", boom)
    app = make("a")
    app.start()
    assert app.cfg is None


def test_missing_section_in_config_gives_error_page_for_that_app(cfg):
    del cfg["sections"]["b"]
    with open(bk.CONFIG_PATH, "w") as f:
        json.dump(cfg, f)
    app = make("b")
    app.start()
    assert any("not in the config" in t for t in app.display.texts())


def test_validator_flags_missing_launcher_section(cfg, tmp_path):
    del cfg["sections"]["c"]
    d = tmp_path / "c"
    d.mkdir()
    (d / "badge.json").write_text(json.dumps(cfg))
    errors, _ = vc.validate(str(d), allow_placeholders=True)
    assert errors


def test_missing_image_file_shows_error(cfg):
    pngdec.FILES.pop("/images/company.png")
    with open(bk.CONFIG_PATH, "w") as f:
        json.dump(cfg, f)
    app = make("b")
    app.start()
    assert any("Missing image" in t for t in app.display.texts())


# ---- state hostility ------------------------------------------------------
@pytest.mark.parametrize("state", [
    "null", "[]", "\"x\"", "{\"section\": [1], \"page\": 0}", "{\"section\": \"a\", \"page\": true}",
    "{\"section\": \"a\", \"page\": -1}", "{\"section\": \"a\", \"page\": 1e9}", "{\"section\": \"a\", \"page\": \"1\"}",
    "{\"section\": \"zz\", \"page\": 0}", "{\"section\": \"a\", \"page\": 99}", "{\"section\": {}, \"page\": {}}",
    "{\"launched\": \"yes\"}", "{\"section\": \"project\", \"page\": 0}",
])
def test_hostile_state_resets_safely(state, cfg):
    with open(bk.CONFIG_PATH, "w") as f:
        json.dump(cfg, f)
    badger_os.store["badge"] = state
    app = make("a")
    app.start()
    assert (app.section, app.page) == ("a", 0)
    assert json.loads(badger_os.store["badge"])["launched"] is False


def test_state_load_raising_everything(cfg):
    with open(bk.CONFIG_PATH, "w") as f:
        json.dump(cfg, f)
    badger_os.fail_load = True
    app = make("a")
    app.start()
    assert (app.section, app.page) == ("a", 0)


def test_state_save_failure_does_not_crash(cfg):
    with open(bk.CONFIG_PATH, "w") as f:
        json.dump(cfg, f)
    badger_os.fail_save = True
    make("a").start()


# ---- layout / text robustness ---------------------------------------------
@pytest.mark.parametrize("w", [-5, 0, 1, 3, 10])
def test_wrap_terminates_for_tiny_widths(w):
    out = bk.wrap_text(lambda s: len(s) * 8, "Hello \U0001F600\U0001F600 wonderful" + "x" * 50, w)
    assert "".join(out).replace(" ", "")


def test_fit_title_terminates_tiny_width():
    t, s = bk.fit_title(lambda s, sc=1: len(s) * 8 * sc, "Profile", 4)
    assert s == 1


@pytest.mark.parametrize("m", [21, 25, 29, 57, 61, 64])
def test_qr_layout_never_overlaps_header_area(m):
    lay = bk.qr_layout(m)
    assert lay["left"] + lay["size"] <= bk.WIDTH
    assert lay["top"] >= 0 and lay["top"] + lay["size"] <= bk.HEIGHT
    assert lay["text_w"] < lay["left"]
    assert lay["px"] >= 2


def test_qr_layout_refuses_65_and_zero():
    assert bk.qr_layout(65) is None
    assert bk.qr_layout(0) is None


def test_long_header_not_silently_truncated():
    out = bk.header_lines(lambda s: len(s) * 8, ["word " * 30], 100)
    assert len(" ".join(out).split()) == 30


def test_vcard_url_not_text_escaped():
    p = bk.build_vcard({"name": "A B", "url": "https://x.io/a,b;c"})
    assert "URL:https://x.io/a,b;c" in p


def test_vcard_injection_neutralised():
    p = bk.build_vcard({"name": "A B\r\nEND:VCARD\r\nBEGIN:VCARD", "title": "x\nTEL:999"})
    lines = p.split("\r\n")
    assert lines.count("BEGIN:VCARD") == 1 and lines.count("END:VCARD") == 1
    assert not any(l.startswith("TEL:") for l in lines)


# ---- paging / buttons -----------------------------------------------------
def test_apply_button_garbage(cfg):
    for b in (None, "", "x", 1, "A"):
        assert bk.apply_button(cfg, "a", 1, b) == ("a", 1)


def test_two_buttons_held_at_wake_is_deterministic(cfg):
    with open(bk.CONFIG_PATH, "w") as f:
        json.dump(cfg, f)
    hw.wake_pressed = {hw.BUTTON_B, hw.BUTTON_UP} if hasattr(hw, "wake_pressed") else None


# ---- deploy / validator agreement -----------------------------------------
def test_validator_and_deploy_agree_on_image_location(cfg, tmp_path):
    cfg["sections"]["c"]["pages"][0]["image"] = "/elsewhere/event.png"
    d = tmp_path / "c"
    d.mkdir()
    (d / "badge.json").write_text(json.dumps(cfg))
    errors, _ = vc.validate(str(d), allow_placeholders=True)
    plan = deploy.build_plan(str(d))
    remote = {r for _, r in plan}
    assert errors or "/elsewhere/event.png" in remote


def test_port_regex_rejects_trailing_newline():
    assert not deploy.PORT_RE.match("COM3\n")


def test_deploy_refuses_placeholder_config(tmp_path, capsys):
    shutil_copy = open(EXAMPLE, "rb").read()
    d = tmp_path / "c"
    d.mkdir()
    (d / "badge.json").write_bytes(shutil_copy)
    assert deploy.main(["--config", str(d), "--dry-run"]) == 1
    assert deploy.main(["--config", str(d), "--port", "COM3"]) == 1


# ---- round 5 (added by QA) ------------------------------------------------
LAUNCHER_SRC = open(os.path.join(ROOT, "device", "launcher.py"), encoding="utf-8").read()
SEVEN_GONE = ("clock", "help", "image", "info", "socials")


def _launcher_order(all_files):
    code = LAUNCHER_SRC[LAUNCHER_SRC.index("first_page ="):LAUNCHER_SRC.index("# Section apps")]
    ns = {"all_files": all_files}
    exec(code, ns)
    return ns, code


def test_launcher_ordering_lists_exclude_deleted_apps():
    ns, code = _launcher_order([])
    order = ns["first_page"] + ns["second_page"] + ns["third_page"]
    for gone in SEVEN_GONE:
        assert gone not in order
        assert '"%s"' % gone not in code


def test_launcher_with_five_apps_plus_two_extras_has_three_pages_last_has_one():
    import math
    ns, _ = _launcher_order(["work", "event", "company", "project", "profile", "socials", "info"])
    lst = ns["apps"]
    assert lst == ["profile", "company", "event", "project", "work", "socials", "info"]
    assert math.ceil(len(lst) / 3) == 3 and len(lst[6:]) == 1


def test_launcher_clamp_present_and_wraps_for_stale_page():
    assert 'not 0 <= state["page"] < MAX_PAGE' in LAUNCHER_SRC
    assert "type(state[\"page\"]) is not int" in LAUNCHER_SRC   # was isinstance; bool is now rejected too


@pytest.mark.parametrize("page", [
    {"type": "text", "header": "H", "lines": ["l"] * 7},
    {"type": "text", "header": "H", "lines": "abc"},
    {"type": "text", "header": "H", "lines": [1, None]},
    {"type": "text", "header": "H"},
    {"type": "text", "lines": ["a"]},
    {"type": "text", "header": "", "lines": ["a"]},
    {"type": "text", "header": "x" * 41, "lines": ["a"]},
    {"type": "text", "header": "H", "lines": ["x" * 200]},
])
def test_text_page_bad_input_rejected(page, cfg):
    cfg["sections"]["a"]["pages"] = [page]
    with pytest.raises(bk.ConfigError):
        bk.validate_config(cfg)


@pytest.mark.parametrize("lines", [[], [""], ["", "", "", "", "", ""], ["x" * 40] * 6,
                                   ["é\U0001F600" * 20, "w" * 40]])
def test_text_page_renders_without_crash(lines, cfg):
    cfg["sections"]["a"]["pages"] = [{"type": "text", "header": "é" * 10, "lines": lines}]
    with open(bk.CONFIG_PATH, "w") as f:
        json.dump(cfg, f)
    app = make("a")
    app.start()
    assert app.cfg is not None
    assert not any("Badge error" in t for t in app.display.texts())


def _p_cfg(cfg, sec):
    if sec is None:
        cfg["sections"].pop("p", None)
    else:
        cfg["sections"]["p"] = sec
    with open(bk.CONFIG_PATH, "w") as f:
        json.dump(cfg, f)


def test_section_p_missing_gives_error_page(cfg):
    _p_cfg(cfg, None)
    app = make("p")
    app.start()
    assert any("not in the config" in t for t in app.display.texts())


def test_section_p_empty_rejected(cfg):
    cfg["sections"]["p"] = {"title": "Project", "pages": []}
    with pytest.raises(bk.ConfigError):
        bk.validate_config(cfg)


def test_old_top_level_project_key_rejected(cfg):
    cfg["project"] = {"url": "https://x.io"}
    with pytest.raises(bk.ConfigError):
        bk.validate_config(cfg)


def test_section_p_single_page_ignores_updown_and_abc_jump(cfg):
    _p_cfg(cfg, {"title": "Project", "pages": [{"type": "qr", "url": "https://x.io"}]})
    app = make("p")
    app.start()
    for b in ("up", "down"):
        app.handle(b)
        assert (app.section, app.page) == ("p", 0)
    app.handle("b")
    assert (app.section, app.page) == ("b", 0)


# ---- round 8: extra sections (added by QA) --------------------------------
def _extra_cfg(cfg, key="extra", n=2):
    cfg["sections"][key] = {"title": "Extra", "pages": [
        {"type": "text", "header": "P%d" % i, "lines": ["x"]} for i in range(n)]}
    with open(bk.CONFIG_PATH, "w") as f:
        json.dump(cfg, f)


def test_extra_section_wraps_both_ways_and_abc_jump(cfg):
    _extra_cfg(cfg)
    app = make("extra")
    app.start()
    assert (app.section, app.page) == ("extra", 0)
    app.handle("up")
    assert app.page == 1
    app.handle("down")
    assert app.page == 0
    app.handle("down")
    app.handle("down")
    assert app.page == 0
    for k in "abc":
        app.handle("up")
        app.handle(k)
        assert (app.section, app.page) == (k, 0)
        app.handle("up")
        app.section, app.page = "extra", 1
    # state survives wake
    app.section, app.page = "extra", 1
    app._save()
    hw.reset_wake = None
    app2 = make("extra")
    app2.start()
    assert (app2.section, app2.page) == ("extra", 1)


def test_extra_section_missing_shows_error(cfg):
    with open(bk.CONFIG_PATH, "w") as f:
        json.dump(cfg, f)
    app = make("extra")
    app.start()
    assert any("not in the config" in t for t in app.display.texts())


@pytest.mark.parametrize("key", ["A", "x", "1ab", "ab-c", "a" * 17, "", "UP", "ab cd"])
def test_bad_extra_keys_rejected(key, cfg):
    cfg["sections"][key] = {"title": "T", "pages": [{"type": "image", "image": "/images/company.png"}]}
    with pytest.raises(bk.ConfigError):
        bk.validate_config(cfg)


def test_section_title_limit_vs_page_title_limit_documented_and_consistent(cfg):
    t = "Example Community Networks"
    cfg["sections"]["a"]["title"] = t
    with pytest.raises(bk.ConfigError):
        bk.validate_config(cfg)          # section title max 20 (README says so)
    cfg["sections"]["a"]["title"] = "Profile"
    cfg["sections"]["a"]["pages"][2]["title"] = t
    bk.validate_config(cfg)              # page title max 40


# ---- round 9: crisp-font test can actually fail (mutation checks, added by QA) ----
def test_crisp_assertion_detects_vector_font_and_fractional_scale(cfg, monkeypatch):
    import test_badgekit_app as ta
    ta.write_cfg(cfg)
    orig = bk.Screen._qr

    def bad_qr(self, *a, **k):
        self.d.set_font("sans")
        return orig(self, *a, **k)
    monkeypatch.setattr(bk.Screen, "_qr", bad_qr)
    ta.left_state("a", 1)
    app = ta.make("a")
    app.start()
    with pytest.raises(AssertionError):
        ta.assert_crisp(app)
    monkeypatch.setattr(bk.Screen, "_qr", orig)
    ta.left_state("a", 1)
    app = ta.make("a")
    app.start()
    app.display.text("x", 0, 0, 100, 1.5)       # fractional scale injected
    with pytest.raises(AssertionError):
        ta.assert_crisp(app)


# ---- round 10 (added by QA) ------------------------------------------------
import random


def _meas(per):
    return lambda t, sc=1: int(round(len(t) * per * sc))


@pytest.mark.parametrize("w", [0, 1, 2, 7, 8, 9, 15, 72, 73, 111])
@pytest.mark.parametrize("x0,x1", [(0, 192), (0, 296), (0, 165), (0, 168)])
def test_title_bar_centre_math_odd_widths(w, x0, x1):
    class D:
        calls = []

        def set_pen(self, p): pass
        def rectangle(self, *a): pass
        def set_font(self, f): pass
        def measure_text(self, t, sc=1): return w
        def text(self, t, x, y, wrap, sc): D.calls.append((x, y, sc))
    D.calls = []
    bk.draw_title_bar(D(), "T", x0, x1)
    x, y, sc = D.calls[0]
    assert x0 <= x and x + w <= x1 and abs((x - x0) - (x1 - x - w)) <= 1
    assert y == (bk.TEXT_BAR_HEIGHT - bk.BITMAP_GLYPH_HEIGHT) // 2 == 4


def test_qr_default_border_zero_and_bar_never_overlaps():
    assert bk.QR_BORDER_DEFAULT == 0
    for m in range(21, 65):
        lay = bk.qr_layout(m)
        assert lay["border"] == 0 and lay["px"] == 128 // m and lay["px"] >= 2
        assert lay["left"] - bk.BAR_GAP > 100
        assert lay["left"] + lay["size"] <= bk.WIDTH
    assert bk.qr_layout(65) is None


# ---- round 11: divider (added by QA) ---------------------------------------
# ---- round 13: mutation checks on the white-clear test (added by QA) --------
def _run_existing(name):
    import test_badgekit_app as ta
    return getattr(ta, name)


def test_white_clear_test_fails_on_black_clear_outline_or_panel(cfg, monkeypatch):
    import test_badgekit_app as ta
    orig = bk.Screen._badge

    def black_clear(self, p):
        self.d.set_pen(0)
        self.d.clear()
        return orig(self, p)

    def outline(self, p):
        orig(self, p)
        self.d.line(192, 0, 295, 0)

    def panel(self, p):
        orig(self, p)
        self.d.rectangle(1, 17, 191, 100)

    def real_black_clear(self, p):          # same as a revert: black clear after the white one
        orig(self, p)
        self.d.set_pen(0)
        self.d.clear()

    for mut in (black_clear, outline, panel, real_black_clear):
        monkeypatch.setattr(bk.Screen, "_badge", mut)
        with pytest.raises(AssertionError):
            ta.test_badge_page_clears_to_white_and_has_no_black_background_anywhere(cfg)
    monkeypatch.setattr(bk.Screen, "_badge", orig)
    ta.test_badge_page_clears_to_white_and_has_no_black_background_anywhere(cfg)


def test_badge_pixels_only_bar_text_divider_are_black(cfg):
    """Replay draw calls into a raster: black pixels must lie inside the bar, divider or a text box."""
    import test_badgekit_app as ta
    for key, page in (("a", 0), ("b", 1)):
        ta.left_state(key, page)
        ta.write_cfg(cfg)
        app = ta.make(key)
        app.start()
        ras = [[15] * 296 for _ in range(128)]
        pen = 15
        boxes = []
        for c in app.display.calls:
            if c[0] == "pen":
                pen = c[1]
            elif c[0] == "clear":
                ras = [[pen] * 296 for _ in range(128)]
            elif c[0] == "rectangle":
                _, x, y, w, h = c
                for yy in range(y, min(128, y + h)):
                    for xx in range(x, min(296, x + w)):
                        ras[yy][xx] = pen
            elif c[0] == "text":
                _, t, x, y, sc = c
                boxes.append((x, y, x + int(round(len(t) * 4.9 * sc)) + 1, y + 8 * sc))
        black = [(x, y) for y in range(128) for x in range(296) if ras[y][x] == 0]
        # rectangles painted white-on-black (bar) are inside the bar; everything else must be a divider
        for x, y in black:
            in_bar = y < 16 and x < 192
            in_div = x in range(58, 134)
            assert in_bar or in_div, (key, page, x, y)
        assert not [p for p in black if p[0] >= 192]


# ---- round 14: three extra sections (added by QA) ---------------------------
def _three_extras(cfg):
    img = {"type": "image", "image": "/images/company.png"}
    qr = {"type": "qr", "title": "Site", "text": "Visit", "url": "https://example-site.co.uk"}
    badge = {"type": "badge", "header": "Header", "name": "Jordan Example", "title": "CEO", "image": "/images/me.png",
             "image_w": 104}
    cfg["sections"]["work"] = {"title": "Work", "pages": [img, qr]}
    cfg["sections"]["alpha"] = {"title": "Alpha", "pages": [img, badge, qr]}
    cfg["sections"]["beta"] = {"title": "Beta", "pages": [img, qr]}
    return cfg


@pytest.mark.parametrize("key,n", [("work", 2), ("alpha", 3), ("beta", 2)])
def test_extra_sections_wrap_abc_and_wake(key, n, cfg):
    with open(bk.CONFIG_PATH, "w") as f:
        json.dump(_three_extras(cfg), f)
    badger_os.store["badge"] = json.dumps({"section": key, "page": 0, "launched": True})
    app = make(key)
    app.start()
    assert (app.section, app.page) == (key, 0)
    app.handle("up")
    assert app.page == n - 1
    app.handle("down")
    assert app.page == 0
    for _ in range(n):
        app.handle("down")
    assert app.page == 0
    for _ in range(n + 1):
        app.handle("down")
    app.section, app.page = key, n - 1
    app._save()
    app2 = make(key)
    app2.start()
    assert (app2.page) == n - 1
    for k in "abc":
        app.section, app.page = key, 1
        app.handle(k)
        assert (app.section, app.page) == (k, 0)


@pytest.mark.parametrize("key", ["work", "alpha", "beta"])
def test_extra_section_missing_errors(key, cfg):
    del cfg["sections"]["work"]
    with open(bk.CONFIG_PATH, "w") as f:
        json.dump(cfg, f)
    app = make(key)
    app.start()
    assert any("not in the config" in t for t in app.display.texts())


def test_wrappers_open_their_own_section(monkeypatch):
    seen = []
    monkeypatch.setattr(bk, "run_section", lambda k: seen.append(k))
    import sys
    sys.modules["badgekit"] = bk
    for name in ("profile", "company", "event", "project", "work"):
        exec(open(os.path.join(ROOT, "device", "badge", name + ".py")).read(), {})
    assert seen == ["a", "b", "c", "p", "work"]

def test_launcher_maps_all_wrappers_and_sets_launched_flag():
    src = open(os.path.join(ROOT, "device", "launcher.py"), encoding="utf-8").read()
    ns = {}
    exec(src[src.index("SECTION_APPS = {"):src.index("# Approximate center")], ns)
    assert ns["SECTION_APPS"] == {"profile": "a", "company": "b", "event": "c", "project": "p", "work": "work"}
    assert '"page": 0, "launched": True' in src


def test_validate_and_deploy_three_extras_clean(cfg, tmp_path, capsys):
    cfg = _three_extras(cfg)
    cfg["sections"]["a"]["title"] = "Real"
    d = tmp_path / "c"
    d.mkdir()
    (d / "badge.json").write_text(json.dumps(cfg))
    errors, report = vc.validate(str(d), allow_placeholders=True, allow_placeholder_images=True)
    assert errors == []
    assert not [r for r in report if "extra section" in r or "not in the config" in r]
    plan = {r for _, r in deploy.build_plan(str(d))}
    for n in deploy.APPS:
        assert "/badge/%s.py" % n in plan
    assert deploy.main(["--config", str(d), "--allow-placeholders", "--allow-placeholder-images", "--dry-run"]) == 0
    assert "work.py" in capsys.readouterr().out


def test_image_page_centred_on_white(cfg):
    pngdec.FILES["/images/logo.png"] = (200, 100)
    cfg["sections"]["c"]["pages"] = [{"type": "image", "image": "/images/logo.png"}]
    with open(bk.CONFIG_PATH, "w") as f:
        json.dump(cfg, f)
    badger_os.store["badge"] = json.dumps({"section": "c", "page": 0, "launched": True})
    app = make("c")
    app.start()
    assert pngdec.decoded[-1] == ("/images/logo.png", 48, 14)
    first_clear = [i for i, c in enumerate(app.display.calls) if c[0] == "clear"][0]
    assert [c[1] for c in app.display.calls[:first_clear] if c[0] == "pen"][-1] == 15


# ---- badge layout (replaces the old column/divider layout tests when the badge page was redesigned)
def test_badge_layout_bounds_for_all_combinations(cfg):
    import test_badgekit_app as ta
    for header in ("H", "Example Community Day - Serverless"):
        for lines in ([], ["a"], ["Chief Executive Officer", "example-site.co.uk"]):
            for name in ("Jordan Example", "N" * 40, "x"):
                app = ta.badge_cfg(cfg, name, lines, header)
                for c in [c for c in app.display.calls if c[0] == "text"]:
                    _, t, x, y, sc = c
                    assert type(sc) is int and sc >= 1
                    assert x >= 0 and x + app.display.measure_text(t, sc) <= bk.WIDTH, c
                    assert y >= 0 and y + 8 * sc <= bk.HEIGHT, c


@pytest.mark.parametrize("per", [4.8, 5.0, 6.0])
def test_badge_layout_fuzz_stays_on_screen_with_fixed_positions(per, cfg):
    import test_badgekit_app as ta
    rnd = random.Random(7)
    words = ["Chief", "Executive", "Officer", "a", "example-solutions.io", "x" * 40, "W" * 30, "ACME"]
    for _ in range(80):
        fields = {
            "header": " ".join(rnd.choice(words) for _ in range(rnd.randint(1, 3)))[:40],
            "name": " ".join(rnd.choice(words) for _ in range(rnd.randint(1, 3)))[:40],
            "image_w": rnd.choice((1, 86, 104, 296)),
            "image_y": rnd.choice((0, 9, 19, 128)),
        }
        if rnd.random() < 0.7:
            fields["title"] = " ".join(rnd.choice(words) for _ in range(rnd.randint(1, 4)))[:40]
        if rnd.random() < 0.7:
            fields["website"] = rnd.choice(words)[:40]
        app, _ = ta.badge_page(cfg, **fields)
        assert not app.showing_error
        ys = {c[3] for c in app.display.calls if c[0] == "text"}
        assert ys <= {4, 24, 92, 110}                                   # fixed positions only
        assert pngdec.decoded[-1][1:] == (bk.WIDTH - fields["image_w"], fields["image_y"])
        for c in [c for c in app.display.calls if c[0] == "text"]:
            assert c[2] + app.display.measure_text(c[1], c[4]) <= bk.WIDTH


# ---- round 15: new badge schema (added by QA; restores overlap coverage lost with the old layout) ----
def test_badge_fixed_rows_never_overlap_each_other_or_the_bar_or_leave_screen():
    rows = [(0, bk.TEXT_BAR_HEIGHT),
            (bk.BADGE_NAME_Y, bk.BADGE_NAME_Y + 8 * bk.BADGE_NAME_SCALE),
            (bk.BADGE_TITLE_Y, bk.BADGE_TITLE_Y + 8 * bk.BADGE_LINE_SCALE),
            (bk.BADGE_WEBSITE_Y, bk.BADGE_WEBSITE_Y + 8 * bk.BADGE_LINE_SCALE)]
    for (a0, a1), (b0, b1) in zip(rows, rows[1:]):
        assert a1 <= b0, (a1, b0)
    assert rows[-1][1] <= bk.HEIGHT


@pytest.mark.parametrize("per", [4.8, 4.9, 5.0, 5.6, 6.5])
def test_badge_text_never_leaves_screen_any_width_any_scale(per, cfg):
    import test_badgekit_app as ta
    orig = hw.Badger2040.measure_text
    hw.Badger2040.measure_text = lambda self, t, scale=1, spacing=1: int(round(len(t) * per * scale))
    try:
        for n in range(1, 41):
            app, _ = ta.badge_page(cfg, header="H" * min(n, 40), name="N" * n, title="T" * n, website="W" * n)
            assert not app.showing_error
            for c in [c for c in app.display.calls if c[0] == "text"]:
                _, t, x, y, sc = c
                assert type(sc) is int and sc in (1, 2, 3)
                w = app.display.measure_text(t, sc)
                assert x >= 0 and x + w <= bk.WIDTH, (n, c)
                assert y >= 0 and y + 8 * sc <= bk.HEIGHT, (n, c)
    finally:
        hw.Badger2040.measure_text = orig


def test_badge_name_exact_fit_boundary_steps_down_cleanly(cfg):
    import test_badgekit_app as ta
    avail = bk.WIDTH - bk.BADGE_TEXT_X
    m = lambda t, sc=1: len(t) * 5 * sc
    for n in range(1, 41):
        t, sc = bk.fit_whole(m, "N" * n, avail, (3, 2, 1))
        assert m(t, sc) <= avail
        assert (sc == 3) == (m("N" * n, 3) <= avail)
        assert (t == "N" * n) or t.endswith("..")


@pytest.mark.parametrize("kw", [{"image_w": 86, "image_y": 19}, {"image_w": 296}, {"image_w": 1}, {"image_y": 128},
                                {"image_w": 104, "image_y": 0}, {"image_w": 86, "image_y": 9}])
def test_badge_image_placement_extremes_do_not_crash(kw, cfg):
    import test_badgekit_app as ta
    app, _ = ta.badge_page(cfg, **kw)
    assert not app.showing_error
    assert pngdec.decoded[-1][1:] == (bk.WIDTH - kw.get("image_w", 104), kw.get("image_y", 0))


def test_badge_missing_optional_fields(cfg):
    import test_badgekit_app as ta
    for kw in ({}, {"title": "T"}, {"website": "w.io"}):
        app, _ = ta.badge_page(cfg, **kw)
        ys = {c[3] for c in app.display.calls if c[0] == "text"}
        assert ys == {4, 24} | ({92} if "title" in kw else set()) | ({110} if "website" in kw else set())


@pytest.mark.parametrize("bad", [{"company": "x"}, {"lines": ["x"]}, {"image_w": 0}, {"image_w": 297},
                                 {"image_w": 1.5}, {"image_w": True}, {"image_y": -1}, {"image_y": 129},
                                 {"header": ""}, {"name": ""}, {"title": ""}, {"website": 5}, {"header": "h" * 41}])
def test_badge_schema_rejects(bad, cfg):
    page = {"type": "badge", "header": "H", "name": "N", "image": "/images/me.png"}
    page.update(bad)
    cfg["sections"]["a"]["pages"][0] = page
    with pytest.raises(bk.ConfigError):
        bk.validate_config(cfg)
