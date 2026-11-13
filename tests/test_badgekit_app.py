"""badgekit App flows against the fake badger2040 / badger_os / pngdec / qrcode modules."""
import copy
import json
import os

import pytest

import badger2040 as hw
import badger_os
import badgekit as bk
import machine
import pngdec
import qrcode

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
    pngdec.FILES.update({"/images/hennie.png": (108, 146), "/images/aws.png": (296, 128),
                         "/images/microsoft.png": (296, 128)})
    hw.halt_limit = 3
    yield


def write_cfg(cfg):
    with open(bk.CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f)


def make(key):
    return bk.App(key, hw, badger_os, pngdec, qrcode)


def saved():
    return json.loads(badger_os.store["badge"])


def fresh_launch(section, page=0):
    badger_os.store["badge"] = json.dumps({"section": section, "page": page, "launched": True})


def left_state(section, page):
    badger_os.store["badge"] = json.dumps({"section": section, "page": page, "launched": False})


# ------------------------------------------------------------- start-up
def test_fresh_launch_opens_page_one_and_persists(cfg):
    write_cfg(cfg)
    app = make("a")
    fresh_launch("a")
    app.start()
    assert (app.section, app.page) == ("a", 0)
    assert pngdec.decoded[-1] == ("/images/hennie.png", bk.WIDTH - 108, 0)      # image_w 108 in the example
    assert app.display.updates == 1
    assert app.display.speed == hw.UPDATE_NORMAL
    assert saved() == {"section": "a", "page": 0, "launched": False}


def test_fresh_launch_ignores_stale_wake_button(cfg):
    write_cfg(cfg)
    hw.wake_buttons.add(hw.BUTTON_C)
    app = make("a")
    fresh_launch("a")
    app.start()
    assert app.section == "a"


def test_wake_restores_last_page(cfg):
    write_cfg(cfg)
    left_state("b", 2)
    app = make("b")
    app.start()
    assert (app.section, app.page) == ("b", 2)
    assert qrcode.created[-1].text == "https://builder.aws.com/community/@henniefrancis"
    assert qrcode.created[-1].ecc == qrcode.ECC_LOW


def test_wake_button_is_acted_on(cfg):
    write_cfg(cfg)
    left_state("b", 0)
    hw.wake_buttons.add(hw.BUTTON_DOWN)
    app = make("b")
    app.start()
    assert (app.section, app.page) == ("b", 1)


def test_wake_up_wraps_to_last_page(cfg):
    write_cfg(cfg)
    left_state("a", 0)
    hw.wake_buttons.add(hw.BUTTON_UP)
    app = make("a")
    app.start()
    assert (app.section, app.page) == ("a", 2)


def test_wake_with_section_button_switches_and_updates_running_app(cfg):
    write_cfg(cfg)
    left_state("b", 2)
    badger_os.store["launcher"] = json.dumps({"page": 0, "running": "/henniefrancis/aws"})
    hw.wake_buttons.add(hw.BUTTON_A)
    app = make("b")
    app.start()
    assert (app.section, app.page) == ("a", 0)
    assert json.loads(badger_os.store["launcher"])["running"] == "/henniefrancis/personal"


def test_wake_with_two_buttons_picks_one(cfg):
    write_cfg(cfg)
    left_state("a", 0)
    hw.wake_buttons.update({hw.BUTTON_B, hw.BUTTON_DOWN})
    app = make("a")
    app.start()
    assert (app.section, app.page) == ("b", 0)


def test_wake_with_a_and_c_returns_to_launcher(cfg):
    write_cfg(cfg)
    left_state("a", 1)
    hw.wake_buttons.update({hw.BUTTON_A, hw.BUTTON_C})
    app = make("a")
    with pytest.raises(machine.Reset):
        app.start()
    assert badger_os.running_cleared


@pytest.mark.parametrize("raw", [
    "[]", "null", "\"x\"", "{\"section\": \"b\", \"page\": 99}", "{\"section\": 5}", "{\"page\": \"1\"}",
])
def test_corrupt_state_resets_to_own_section_page_one(cfg, raw):
    write_cfg(cfg)
    badger_os.store["badge"] = raw
    app = make("b")
    app.start()
    assert (app.section, app.page) == ("b", 0)


def test_state_loader_exception_is_survived(cfg):
    write_cfg(cfg)
    badger_os.fail_load = True
    app = make("a")
    app.start()
    assert (app.section, app.page) == ("a", 0)


def test_state_for_other_section_is_ignored(cfg):
    write_cfg(cfg)
    left_state("b", 2)
    app = make("a")      # personal wrapper started while state says section b
    app.start()
    assert (app.section, app.page) == ("a", 0)


def test_state_save_failure_does_not_crash(cfg):
    write_cfg(cfg)
    badger_os.fail_save = True
    app = make("a")
    app.start()
    assert app.display.updates == 1


# ----------------------------------------------------------- error pages
def error_texts(app):
    return " ".join(app.display.texts())


def test_missing_config_shows_error_page():
    app = make("a")
    app.start()
    assert "Badge error" in app.display.texts()
    assert "Cannot read config file" in error_texts(app)
    assert bk.ERROR_HINT in app.display.texts()
    assert app.display.updates == 1


def test_bad_config_message_is_shown():
    with open(bk.CONFIG_PATH, "w") as f:
        f.write("{oops")
    app = make("a")
    app.start()
    assert "not valid JSON" in error_texts(app)


def test_invalid_config_message_is_shown(cfg):
    cfg["sections"]["a"]["pages"] = []
    write_cfg(cfg)
    app = make("a")
    app.start()
    assert "no pages" in error_texts(app)


def test_button_after_fixing_config_recovers(cfg):
    app = make("a")
    app.start()
    write_cfg(cfg)
    app.handle("down")
    assert app.cfg is not None
    assert app.display.updates == 2
    assert "Badge error" not in app.display.texts()[-3:]


def test_missing_image_shows_error_not_crash(cfg):
    write_cfg(cfg)
    pngdec.FILES.pop("/images/aws.png")
    app = make("b")
    fresh_launch("b")
    app.start()
    assert "Missing image /images/aws.png" in error_texts(app)
    app.handle("down")                      # can still navigate away
    assert (app.section, app.page) == ("b", 1)


def test_oversized_vcard_shows_error(cfg):
    big = {k: "x" * 100 for k in ("title", "company", "email", "phone", "url", "linkedin")}
    big["name"] = "Name Surname"
    cfg["sections"]["a"]["pages"][1]["vcard"] = big
    write_cfg(cfg)
    left_state("a", 1)
    app = make("a")
    app.start()
    assert "QR too large" in error_texts(app)


def test_press_for_unconfigured_section_shows_error(cfg):
    del cfg["sections"]["b"]
    write_cfg(cfg)
    app = make("a")
    fresh_launch("a")
    app.start()
    app.handle("b")
    assert "Section B is not in the config" in error_texts(app)


# ---------------------------------------------------------- QR rendering
def box_rects(app):
    """Rectangles drawn for the QR modules (everything except the 16 px title bar)."""
    return [r for r in app.display.rects() if not (r[1] == 0 and r[3] == bk.TEXT_BAR_HEIGHT)]


def qr_rects(app):
    return [r for r in app.display.rects() if r[3] <= 2 and r[0] >= 100]


def test_qr_page_layout_right_aligned_and_header_clear_of_qr(cfg):
    write_cfg(cfg)
    left_state("a", 1)
    app = make("a")
    app.start()
    n = qrcode.created[-1].get_size()[0]
    lay = bk.qr_layout(n)
    assert lay["px"] >= 2
    rects = box_rects(app)
    right_edge = max(x + w for x, y, w, h in rects)
    assert right_edge == bk.WIDTH - lay["top"]
    assert min(x for x, y, w, h in rects) >= lay["left"]
    assert all(y >= lay["top"] and y + h <= bk.HEIGHT - lay["top"] + 1 for x, y, w, h in rects)
    # all text sits entirely left of the QR
    for c in app.display.calls:
        if c[0] == "text":
            _, text, x, y, scale = c
            assert x + app.display.measure_text(text, scale) <= lay["left"]
    assert "Contact Details" in app.display.texts()               # the bar title
    assert "Save my Contact Details" in " ".join(app.display.texts())  # body text, possibly wrapped


def test_url_qr_is_bigger_modules(cfg):
    write_cfg(cfg)
    left_state("a", 2)
    app = make("a")
    app.start()
    n = qrcode.created[-1].get_size()[0]
    assert n == 25
    assert bk.qr_layout(n)["px"] == 5
    assert qrcode.created[-1].text == "https://example.com"


# ------------------------------------------------------------ main loop
def test_loop_paging_wraps_and_one_page_section_ignores(cfg):
    write_cfg(cfg)
    app = make("a")
    fresh_launch("a")
    app.start()
    hw.halt_limit = 6
    hw.script[:] = [{hw.BUTTON_DOWN}, set(), {hw.BUTTON_DOWN}, set(), {hw.BUTTON_DOWN}, set()]
    with pytest.raises(hw.StopLoop):
        app.loop()
    assert (app.section, app.page) == ("a", 0)     # 0 -> 1 -> 2 -> wrapped to 0
    assert app.display.updates == 4                # start + three page changes
    assert saved()["page"] == 0

    app2 = make("c")
    fresh_launch("c")
    app2.start()
    updates = app2.display.updates
    hw.script[:] = [{hw.BUTTON_DOWN}, set(), {hw.BUTTON_UP}, set()]
    hw.halt_limit = 4
    with pytest.raises(hw.StopLoop):
        app2.loop()
    assert app2.display.updates == updates          # no pointless e-ink refresh


def test_loop_pressing_same_section_button_on_page_one_does_nothing(cfg):
    write_cfg(cfg)
    app = make("a")
    fresh_launch("a")
    app.start()
    hw.script[:] = [{hw.BUTTON_A}, set()]
    hw.halt_limit = 2
    with pytest.raises(hw.StopLoop):
        app.loop()
    assert app.display.updates == 1


def test_loop_switching_sections_resets_to_page_one(cfg):
    write_cfg(cfg)
    app = make("a")
    fresh_launch("a")
    app.start()
    app.handle("down")
    assert (app.section, app.page) == ("a", 1)
    app.handle("b")
    assert (app.section, app.page) == ("b", 0)
    app.handle("c")
    assert (app.section, app.page) == ("c", 0)
    assert json.loads(badger_os.store["launcher"])["running"] == "/henniefrancis/microsoft"
    app.handle("a")
    assert json.loads(badger_os.store["launcher"])["running"] == "/henniefrancis/personal"


def test_loop_a_plus_c_exits_to_launcher(cfg):
    write_cfg(cfg)
    app = make("a")
    fresh_launch("a")
    app.start()
    hw.script[:] = [{hw.BUTTON_A, hw.BUTTON_C}]
    with pytest.raises(machine.Reset):
        app.loop()
    assert badger_os.running_cleared


def test_rapid_presses_do_not_crash(cfg):
    write_cfg(cfg)
    app = make("a")
    fresh_launch("a")
    app.start()
    seq = []
    for b in (hw.BUTTON_UP, hw.BUTTON_DOWN, hw.BUTTON_B, hw.BUTTON_C, hw.BUTTON_A) * 5:
        seq += [{b}, set()]
    hw.script[:] = seq
    hw.halt_limit = 25
    with pytest.raises(hw.StopLoop):
        app.loop()


# ----------------------------------------------------------- project app
def test_project_section_pages_wrap_and_jump(cfg):
    write_cfg(cfg)
    app = make("p")
    fresh_launch("p")
    app.start()
    assert (app.section, app.page) == ("p", 0)
    assert qrcode.created[-1].text == "https://github.com/henniefrancis/badger2040"
    assert "Project" in app.display.texts() and "Build your own badge" in " ".join(app.display.texts())
    app.handle("down")
    assert (app.section, app.page) == ("p", 1)
    app.handle("down")
    assert qrcode.created[-1].text == "https://pimoroni.com/badger2040"
    app.handle("down")
    assert (app.section, app.page) == ("p", 0)             # wrap
    app.handle("up")
    assert (app.section, app.page) == ("p", 2)
    for key, sec in (("a", "a"), ("b", "b"), ("c", "c")):
        app2 = make("p")
        fresh_launch("p")
        app2.start()
        app2.handle(key)
        assert (app2.section, app2.page) == (sec, 0)


def test_project_section_restores_page_and_keeps_launcher_running_entry(cfg):
    write_cfg(cfg)
    left_state("p", 1)
    app = make("p")
    app.start()
    assert (app.section, app.page) == ("p", 1)
    assert "About this badge" in app.display.texts()
    badger_os.store["launcher"] = json.dumps({"page": 1, "running": "/henniefrancis/project"})
    app.handle("b")
    assert json.loads(badger_os.store["launcher"])["running"] == "/henniefrancis/aws"


def test_project_wrapper_without_section_p_shows_error(cfg):
    del cfg["sections"]["p"]
    write_cfg(cfg)
    app = make("p")
    app.start()
    assert "Section P is not in the config" in error_texts(app)


def test_project_a_plus_c_exits(cfg):
    write_cfg(cfg)
    app = make("p")
    app.start()
    with pytest.raises(machine.Reset):
        app.handle("exit")


def test_text_page_draws_bar_header_and_lines(cfg):
    write_cfg(cfg)
    left_state("p", 1)
    app = make("p")
    app.start()
    rects = app.display.rects()
    assert (0, 0, bk.WIDTH, 16) in rects                     # 16 px header bar
    calls = [c for c in app.display.calls if c[0] == "text"]
    by_text = {c[1]: c for c in calls}
    _, _, hx, hy, hs = by_text["About this badge"]
    assert (hx, hy, hs) == ((bk.WIDTH - app.display.measure_text("About this badge", 1)) // 2, 4, 1)  # centred
    lines = cfg["sections"]["p"]["pages"][1]["lines"]
    for i, line in enumerate(lines):
        if not line:
            continue
        _, text, x, y, scale = by_text[line]
        assert (x, y, scale) == (bk.LEFT_PADDING, bk.TEXT_FIRST_Y + i * bk.TEXT_LINE_HEIGHT, 1)
    assert "" not in by_text                                  # spacer draws nothing
    ys = sorted(c[3] for c in calls if c[1] in lines)
    assert all(b - a >= 15 for a, b in zip(ys, ys[1:]))      # 15 px line pitch
    assert max(ys) + 8 <= bk.HEIGHT


def test_text_page_wide_lines_are_cut_with_ellipsis(cfg):
    cfg["sections"]["p"]["pages"][1]["lines"] = ["W" * 60, "short"]
    write_cfg(cfg)
    left_state("p", 1)
    app = make("p")
    app.start()
    wide = [t for t in app.display.texts() if t.endswith("..")]
    assert wide and app.display.measure_text(wide[0], 1) <= bk.WIDTH - 2 * bk.LEFT_PADDING
    assert "short" in app.display.texts()


def test_text_page_six_lines_fit_on_screen(cfg):
    cfg["sections"]["p"]["pages"][1]["lines"] = ["line %d" % i for i in range(6)]
    write_cfg(cfg)
    left_state("p", 1)
    app = make("p")
    app.start()
    assert not app.showing_error
    assert all(c[3] + 8 <= bk.HEIGHT for c in app.display.calls if c[0] == "text")


def test_run_section_rejects_bad_key():
    with pytest.raises(ValueError):
        bk.run_section("z")


def test_run_section_end_to_end(cfg):
    write_cfg(cfg)
    fresh_launch("a")
    hw.halt_limit = 1
    with pytest.raises(hw.StopLoop):
        bk.run_section("a")
    assert hw.instances[-1].updates == 1
    assert hw.instances[-1].halts == 1


# ------------------------------------------------------ badge page text
def test_badge_page_without_company_uses_full_height(cfg):
    write_cfg(cfg)
    app = make("a")
    fresh_launch("a")
    app.start()
    texts = app.display.texts()
    assert "Your Name" in texts and "Your title" in texts and "example.com" in texts
    assert "AWS Community Builder" not in texts


def test_badge_page_with_company(cfg):
    write_cfg(cfg)
    left_state("b", 1)
    app = make("b")
    app.start()
    assert "AWS Community Builder" in app.display.texts()


def test_full_image_page_is_centred(cfg):
    cfg["sections"]["c"]["pages"][0]["image"] = "/images/microsoft.png"
    write_cfg(cfg)
    pngdec.FILES["/images/microsoft.png"] = (200, 60)
    app = make("c")
    fresh_launch("c")
    app.start()
    assert pngdec.decoded[-1] == ("/images/microsoft.png", 48, 34)


def test_config_not_mutated_by_rendering(cfg):
    before = copy.deepcopy(cfg)
    write_cfg(cfg)
    app = make("a")
    left_state("a", 1)
    app.start()
    assert app.cfg == before


def test_same_button_retries_after_draw_error(cfg):
    write_cfg(cfg)
    pngdec.FILES.pop("/images/hennie.png")
    app = make("a")
    fresh_launch("a")
    app.start()
    assert app.showing_error
    updates = app.display.updates
    pngdec.FILES["/images/hennie.png"] = (108, 146)
    app.handle("a")                       # the current section's own button retries
    assert not app.showing_error
    assert app.display.updates == updates + 1
    app.handle("a")                       # now nothing changes, so no refresh
    assert app.display.updates == updates + 1


def test_config_load_survives_any_exception(cfg, monkeypatch):
    def boom(path=None):
        raise RuntimeError()
    monkeypatch.setattr(bk, "load_config", boom)
    app = make("a")
    app.start()
    assert app.cfg is None
    assert any("RuntimeError" in t for t in app.display.texts())


@pytest.mark.parametrize("border", [0, 2, 4])
def test_qr_page_draws_with_border(cfg, border):
    cfg["qr_border"] = border
    write_cfg(cfg)
    left_state("a", 2)                      # 25-module URL QR
    app = make("a")
    app.start()
    lay = bk.qr_layout(25, border=border)
    rects = box_rects(app)
    assert min(x for x, y, w, h in rects) >= lay["code_left"]
    assert max(x + w for x, y, w, h in rects) <= bk.WIDTH - lay["top"] - border * lay["px"]
    assert all(y >= lay["code_top"] for x, y, w, h in rects)
    for c in app.display.calls:
        if c[0] == "text":
            _, text, x, y, scale = c
            assert x + app.display.measure_text(text, scale) <= lay["left"]


def test_vcard_page_errors_when_border_makes_it_too_small(cfg):
    v = cfg["sections"]["a"]["pages"][1]["vcard"]
    v.update(title="T" * 40)
    n = 0
    while True:                              # grow to exactly 57 modules
        n += 1
        v["company"] = "C" * n
        payload = bk.qr_payload(cfg["sections"]["a"]["pages"][1])
        if len(payload.encode()) > 230:
            break
    cfg["qr_border"] = 4
    write_cfg(cfg)
    left_state("a", 1)
    app = make("a")
    app.start()
    assert app.showing_error
    assert any("QR too large" in t for t in app.display.texts())


def test_default_border_is_zero_and_the_code_is_as_large_as_density_allows(cfg):
    write_cfg(cfg)
    for page, expect_px in ((1, 2), (2, 4)):          # vCard (53 modules) and website QR
        hw.instances.clear()
        left_state("a", page)
        app = make("a")
        app.start()
        n = qrcode.created[-1].get_size()[0]
        lay = bk.qr_layout(n)
        assert lay["border"] == 0 and lay["code_left"] == lay["left"] and lay["code_top"] == lay["top"]
        assert lay["px"] == bk.HEIGHT // n and lay["size"] == lay["px"] * n
        rects = box_rects(app)
        assert min(x for x, y, w, h in rects) == lay["left"]
        assert max(x + w for x, y, w, h in rects) <= bk.WIDTH - lay["top"]
        assert min(y for x, y, w, h in rects) >= lay["top"]
        assert lay["top"] == (bk.HEIGHT - lay["size"]) // 2                 # centred vertically
        assert lay["left"] + lay["size"] + lay["top"] == bk.WIDTH            # right aligned
        for c in app.display.calls:
            if c[0] == "text":
                assert c[2] + app.display.measure_text(c[1], c[4]) <= lay["left"]


def test_explicit_auto_border_still_works(cfg):
    cfg["qr_border"] = "auto"
    write_cfg(cfg)
    left_state("a", 2)
    app = make("a")
    app.start()
    n = qrcode.created[-1].get_size()[0]
    lay = bk.qr_layout(n, border="auto")
    assert lay["border"] == bk.auto_border(n)
    assert min(x for x, y, w, h in box_rects(app)) >= lay["code_left"]


def test_set_text_returning_false_shows_error_page(cfg, monkeypatch):
    monkeypatch.setattr(qrcode.QRCode, "set_text", lambda self, text: False)
    write_cfg(cfg)
    left_state("a", 2)
    app = make("a")
    app.start()
    assert app.showing_error
    assert any("QR text does not fit" in t for t in app.display.texts())


def test_fake_set_text_returns_false_when_too_long():
    code = qrcode.QRCode(qrcode.ECC_LOW)
    assert code.set_text("x" * 3000) is False
    assert code.set_text("x" * 10) is True


# ------------------------------------------------ house title bar
def bar_rects(app):
    return [r for r in app.display.rects() if r[1] == 0 and r[3] == bk.TEXT_BAR_HEIGHT and r[0] == 0]


def test_qr_bar_stops_before_the_qr_box_with_gap_and_never_overlaps(cfg):
    write_cfg(cfg)
    left_state("a", 1)
    app = make("a")
    app.start()
    n = qrcode.created[-1].get_size()[0]
    lay = bk.qr_layout(n)
    bars = bar_rects(app)
    assert len(bars) == 1
    x, y, w, h = bars[0]
    assert (x, w) == (0, lay["left"] - bk.BAR_GAP) and h == 16
    assert x + w + bk.BAR_GAP == lay["left"]
    assert all(r[0] >= lay["code_left"] for r in box_rects(app))


def test_qr_title_falls_back_to_section_title(cfg):
    cfg["sections"]["a"]["pages"][2].pop("title")
    write_cfg(cfg)
    left_state("a", 2)
    app = make("a")
    app.start()
    assert "Personal" in app.display.texts()


def test_qr_text_block_is_centred_in_left_area_below_the_bar(cfg):
    write_cfg(cfg)
    left_state("a", 2)                     # website QR, text "Visit my website"
    app = make("a")
    app.start()
    n = qrcode.created[-1].get_size()[0]
    lay = bk.qr_layout(n)
    area = lay["left"] - bk.BAR_GAP
    calls = [c for c in app.display.calls if c[0] == "text" and c[1] in ("Visit my website", "Visit my", "website")]
    assert calls
    scale = calls[0][4]
    assert scale in (1, 2)
    widths = [app.display.measure_text(c[1], scale) for c in calls]
    height = (len(calls) - 1) * 10 * scale + 8 * scale
    assert calls[0][2] == (area - max(widths)) // 2
    assert calls[0][3] == 16 + (112 - height) // 2
    assert all(c[3] >= 16 for c in calls)
    assert all(c[2] + app.display.measure_text(c[1], scale) <= area for c in calls)


def test_every_page_type_draws_its_bar_through_the_one_shared_function(cfg, monkeypatch):
    calls = []
    real = bk.draw_title_bar

    def spy(display, text, x0, x1):
        calls.append((text, x0, x1))
        return real(display, text, x0, x1)

    monkeypatch.setattr(bk, "draw_title_bar", spy)
    write_cfg(cfg)
    shown = {}
    for name, key, page in (("badge", "b", 1), ("qr", "a", 1), ("text", "p", 1)):
        left_state(key, page)
        app = make(key)
        app.start()
        shown[name] = app
    assert [c[0] for c in calls] == ["AWS Community Builder", "Contact Details", "About this badge"]
    assert calls[0][1:] == (0, bk.WIDTH)                      # badge: full-width bar over the photo
    assert calls[2][1:] == (0, bk.WIDTH)
    # identical font, scale, height and offsets on every page type
    seen = set()
    for name, app in shown.items():
        dc = app.display.calls
        bar = [r for r in app.display.rects() if r[1] == 0 and r[3] == bk.TEXT_BAR_HEIGHT and r[0] == 0][0]
        title = calls[["badge", "qr", "text"].index(name)][0]
        i = max(k for k, c in enumerate(dc) if c[0] == "text" and c[1] == title)
        font_before = [c[1] for c in dc[:i] if c[0] == "font"][-1]
        _, _, x, y, scale = dc[i]
        centred = x - bar[0] == (bar[2] - app.display.measure_text(title, 1)) // 2     # horizontally centred
        seen.add((font_before, scale, bar[3], centred, y, bar[1]))
    assert seen == {("bitmap8", 1, 16, True, 4, 0)}


def test_bars_are_drawn_only_by_draw_title_bar(cfg, monkeypatch):
    """With draw_title_bar disabled no page draws any 16 px bar at x=0, y=0."""
    monkeypatch.setattr(bk, "draw_title_bar", lambda display, text, x0, x1: None)
    write_cfg(cfg)
    for key, page in (("b", 1), ("a", 1), ("p", 1)):
        left_state(key, page)
        app = make(key)
        app.start()
        assert bar_rects(app) == []


def test_over_wide_bar_text_is_cut_not_shrunk(cfg):
    cfg["sections"]["a"]["pages"][1]["title"] = "T" * 40
    write_cfg(cfg)
    left_state("a", 1)
    app = make("a")
    app.start()
    bar_w = bar_rects(app)[0][2]
    title_calls = [c for c in app.display.calls if c[0] == "text" and c[1].startswith("T")]
    assert title_calls[0][4] == 1                                       # never a smaller or larger scale
    assert app.display.measure_text(title_calls[0][1], 1) <= bar_w - 2 * bk.TEXT_BAR_PAD


# ------------------------------------------------ extra sections and their wrapper apps
def test_wrapper_opens_its_own_section(cfg):
    write_cfg(cfg)
    app = make("work")
    fresh_launch("work")
    app.start()
    assert (app.section, app.page) == ("work", 0)
    assert "Your Organisation" in app.display.texts()               # company bar of the badge page
    assert pngdec.decoded[-1][0] == "/images/hennie.png"
    assert saved() == {"section": "work", "page": 0, "launched": False}


def test_two_page_extra_section_wraps_both_ways(cfg):
    write_cfg(cfg)
    app = make("work")
    fresh_launch("work")
    app.start()
    app.handle("down")
    assert (app.section, app.page) == ("work", 1)
    assert qrcode.created[-1].text == "https://example.org"
    app.handle("down")
    assert (app.section, app.page) == ("work", 0)                   # loops back to page 1
    app.handle("up")
    assert (app.section, app.page) == ("work", 1)
    app.handle("up")
    assert (app.section, app.page) == ("work", 0)


def test_one_page_extra_section_ignores_up_down(cfg):
    cfg["sections"]["solo"] = {"title": "Solo", "pages": cfg["sections"]["work"]["pages"][:1]}
    write_cfg(cfg)
    app = make("solo")
    fresh_launch("solo")
    app.start()
    updates = app.display.updates
    app.handle("down")
    app.handle("up")
    assert (app.section, app.page) == ("solo", 0) and app.display.updates == updates


def test_abc_jump_out_of_an_extra_section_and_running_entry_follows(cfg):
    write_cfg(cfg)
    app = make("work")
    fresh_launch("work")
    app.start()
    badger_os.store["launcher"] = json.dumps({"page": 0, "running": "/henniefrancis/work"})
    app.handle("b")
    assert (app.section, app.page) == ("b", 0)
    assert json.loads(badger_os.store["launcher"])["running"] == "/henniefrancis/aws"


def test_extra_section_wake_restores_page(cfg):
    write_cfg(cfg)
    left_state("work", 1)
    app = make("work")
    app.start()
    assert (app.section, app.page) == ("work", 1)


def test_extra_section_wake_down_button(cfg):
    write_cfg(cfg)
    left_state("work", 1)
    hw.wake_buttons.add(hw.BUTTON_DOWN)
    app = make("work")
    app.start()
    assert (app.section, app.page) == ("work", 0)


@pytest.mark.parametrize("name", ["awscommza", "dotcore", "devconf"])
def test_wrapper_with_missing_section_shows_error_page_not_crash(cfg, name):
    write_cfg(cfg)                                # the example has no awscommza or dotcore section
    app = make(name)
    fresh_launch(name)
    app.start()
    assert app.showing_error
    assert "Section %s is not in the config" % name.upper() in error_texts(app)
    app.handle("down")                            # still alive; can jump away
    app.handle("a")
    assert app.section == "a" and not app.showing_error


def test_run_section_accepts_extra_keys(cfg):
    write_cfg(cfg)
    fresh_launch("work")
    hw.halt_limit = 1
    with pytest.raises(hw.StopLoop):
        bk.run_section("work")
    with pytest.raises(ValueError):
        bk.run_section("Work")


# ------------------------------------------------ crisp text: bitmap fonts, whole scales only
BITMAP_FONTS = {"bitmap6", "bitmap8", "bitmap14_outline"}


def assert_crisp(app):
    fonts = {c[1] for c in app.display.calls if c[0] == "font"}
    assert fonts <= BITMAP_FONTS, fonts          # image pages draw no text at all
    for c in app.display.calls:
        if c[0] == "text":
            assert type(c[4]) is int and c[4] >= 1, c


def test_every_page_of_every_section_uses_only_bitmap_fonts_and_whole_scales(cfg):
    write_cfg(cfg)
    n = 0
    for key, sec in cfg["sections"].items():
        for page in range(len(sec["pages"])):
            left_state(key, page)
            app = make(key)
            app.start()
            assert not app.showing_error, (key, page)
            assert_crisp(app)
            n += 1
    assert n >= 12


def test_error_page_uses_only_bitmap_fonts_and_whole_scales():
    app = make("a")                       # no config file: error page
    app.start()
    assert app.showing_error
    assert_crisp(app)


def test_no_vector_font_is_ever_selected(cfg):
    write_cfg(cfg)
    for key in ("a", "b", "p", "work"):
        for page in range(2):
            left_state(key, page)
            app = make(key)
            app.start()
            assert not [c for c in app.display.calls if c[0] == "font" and c[1] == "sans"]


def badge_cfg(cfg, name, lines, company=None, **extra):
    """Render badge page 1 of section a with the new schema (lines[0] = title, lines[1] = website)."""
    page = cfg["sections"]["a"]["pages"][0]
    page["name"] = name
    page["header"] = company or "Header"
    page.pop("title", None)
    page.pop("website", None)
    if len(lines) > 0:
        page["title"] = lines[0]
    if len(lines) > 1:
        page["website"] = lines[1]
    page.update(extra)
    write_cfg(cfg)
    fresh_launch("a")
    app = make("a")
    app.start()
    return app


def text_calls(app):
    return {c[1]: c for c in app.display.calls if c[0] == "text"}


def test_badge_page_clears_to_white_and_has_no_black_background_anywhere(cfg):
    for key, page in (("a", 0), ("b", 1)):
        left_state(key, page)
        write_cfg(cfg)
        app = make(key)
        app.start()
        calls = app.display.calls
        first_clear = [i for i, c in enumerate(calls) if c[0] == "clear"]
        assert len(first_clear) == 1                                         # cleared exactly once ...
        pens_before = [c[1] for c in calls[:first_clear[0]] if c[0] == "pen"]
        assert pens_before and pens_before[-1] == 15                         # ... to white (pen 15)
        rects = app.display.rects()
        assert rects == [(0, 0, bk.WIDTH, bk.TEXT_BAR_HEIGHT)]               # only the full-width header bar
        assert [c for c in calls if c[0] == "line"] == []                    # no outline, no divider


# ------------------------------------------------ devconf wrapper
def devconf_cfg(cfg):
    cfg["sections"]["devconf"] = {"title": "DevConf", "pages": [
        {"type": "image", "image": "/images/aws.png"},
        {"type": "qr", "title": "DevConf", "text": "Visit the event", "url": "https://example.org/devconf"}]}
    write_cfg(cfg)


def test_devconf_wrapper_opens_section_devconf_with_wrap(cfg):
    devconf_cfg(cfg)
    wrapper = os.path.join(ROOT, "device", "henniefrancis", "devconf.py")
    with open(wrapper, encoding="utf-8") as f:
        assert 'badgekit.run_section("devconf")' in f.read()
    fresh_launch("devconf")
    app = make("devconf")
    app.start()
    assert (app.section, app.page) == ("devconf", 0) and not app.showing_error
    assert saved() == {"section": "devconf", "page": 0, "launched": False}
    app.handle("down")
    assert qrcode.created[-1].text == "https://example.org/devconf"
    app.handle("down")
    assert (app.section, app.page) == ("devconf", 0)                  # two pages loop back to page 1
    badger_os.store["launcher"] = json.dumps({"page": 1, "running": "/henniefrancis/devconf"})
    app.handle("a")
    assert json.loads(badger_os.store["launcher"])["running"] == "/henniefrancis/personal"


def test_devconf_wrapper_without_section_shows_error_page(cfg):
    write_cfg(cfg)
    app = make("devconf")
    fresh_launch("devconf")
    app.start()
    assert app.showing_error and "Section DEVCONF is not in the config" in error_texts(app)


# ------------------------------------------------ new badge page layout (header, name, title, website)
def badge_page(cfg, **fields):
    page = {"type": "badge", "header": "Header", "name": "Hennie Francis", "image": "/images/hennie.png"}
    page.update(fields)
    cfg["sections"]["a"]["pages"][0] = page
    write_cfg(cfg)
    fresh_launch("a")
    app = make("a")
    app.start()
    return app, page


def texts_by_y(app):
    return {c[3]: c for c in app.display.calls if c[0] == "text"}


def test_badge_three_field_render_and_fixed_layout_coordinates(cfg):
    app, _ = badge_page(cfg, header="AWS Community Builder", name="Hennie Francis", title="Chief Executive Officer",
                        website="awscommunity.co.za")
    assert (bk.BADGE_TEXT_X, bk.BADGE_NAME_Y, bk.BADGE_NAME_SCALE) == (2, 24, 3)
    assert (bk.BADGE_TITLE_Y, bk.BADGE_WEBSITE_Y, bk.BADGE_LINE_SCALE) == (92, 110, 2)
    c = text_calls(app)
    assert c["Hennie Francis"][2:] == (2, 24, 3)                       # name: x 2, y 24, scale 3
    assert c["Chief Executive Officer"][2:] == (2, 92, 2)              # title: x 2, y 92, scale 2
    assert c["awscommunity.co.za"][2:] == (2, 110, 2)                  # website: x 2, y 110, scale 2
    bar = c["AWS Community Builder"]
    assert bar[3] == 4 and bar[4] == 1                                 # header text in the bar, scale 1
    assert bar[2] == (bk.WIDTH - app.display.measure_text("AWS Community Builder", 1)) // 2   # centred
    assert app.display.rects() == [(0, 0, 296, 16)]                    # full-width bar, nothing else (no divider)


def test_badge_name_title_website_are_left_aligned_and_black(cfg):
    app, _ = badge_page(cfg, title="T", website="W")
    calls = app.display.calls
    i = max(k for k, c in enumerate(calls) if c[0] == "text" and c[1] == "Hennie Francis")
    assert [c[1] for c in calls[:i] if c[0] == "pen"][-1] == 0         # black text
    assert all(c[2] == 2 for c in calls if c[0] == "text" and c[1] in ("Hennie Francis", "T", "W"))


def test_badge_image_position_uses_image_w_and_image_y(cfg):
    for w, y in ((104, 0), (86, 19), (86, 9), (296, 0), (50, 128), (1, 5)):
        app, _ = badge_page(cfg, image_w=w, image_y=y)
        assert pngdec.decoded[-1] == ("/images/hennie.png", bk.WIDTH - w, y)
    app, _ = badge_page(cfg)                                            # defaults: 104 wide, y 0
    assert pngdec.decoded[-1] == ("/images/hennie.png", 296 - 104, 0)


def test_badge_header_bar_is_drawn_over_the_image(cfg, monkeypatch):
    order = []
    real_decode = pngdec.PNG.decode
    real_bar = bk.draw_title_bar
    monkeypatch.setattr(pngdec.PNG, "decode", lambda self, x, y: (order.append("image"), real_decode(self, x, y))[1])
    monkeypatch.setattr(bk, "draw_title_bar", lambda d, t, x0, x1: (order.append(("bar", x0, x1)), real_bar(d, t, x0, x1))[1])
    badge_page(cfg, image_w=104)
    assert order == ["image", ("bar", 0, 296)]                          # bar after the image, across the whole width


def test_badge_title_and_website_are_optional(cfg):
    app, _ = badge_page(cfg)
    assert sorted(texts_by_y(app)) == [4, 24]                           # header and name only
    app, _ = badge_page(cfg, title="Only title")
    assert sorted(texts_by_y(app)) == [4, 24, 92]
    app, _ = badge_page(cfg, website="only.site")
    assert sorted(texts_by_y(app)) == [4, 24, 110]
    assert not app.showing_error


def test_badge_name_fits_at_scale_three_and_overflow_steps_down_whole_scales(cfg):
    app, _ = badge_page(cfg, name="Hennie Francis")
    n = text_calls(app)["Hennie Francis"]
    assert n[4] == 3 and n[2] + app.display.measure_text("Hennie Francis", 3) <= bk.WIDTH     # 201 px fits in 296
    app, _ = badge_page(cfg, name="N" * 40)                             # 576 px at scale 3: never leaves the screen
    name = [c for c in app.display.calls if c[0] == "text" and c[1].startswith("NN")][0]
    assert type(name[4]) is int and name[4] < 3
    assert name[2] + app.display.measure_text(name[1], name[4]) <= bk.WIDTH


def test_badge_title_and_website_may_run_over_the_image(cfg):
    app, _ = badge_page(cfg, title="Chief Executive Officer", website="www.awscommunity.co.za", image_w=104)
    c = text_calls(app)
    for t in ("Chief Executive Officer", "www.awscommunity.co.za"):
        assert c[t][2] + app.display.measure_text(t, 2) > bk.WIDTH - 104       # over the photo: allowed
        assert c[t][2] + app.display.measure_text(t, 2) <= bk.WIDTH            # but on screen


def test_badge_text_over_screen_width_is_cut_not_off_screen(cfg):
    app, _ = badge_page(cfg, title="T" * 40, website="W" * 40)
    for c in app.display.calls:
        if c[0] == "text":
            assert c[2] + app.display.measure_text(c[1], c[4]) <= bk.WIDTH, c


def test_badge_page_has_no_border_around_the_photo(cfg):
    for key, page in (("a", 0), ("b", 1)):
        left_state(key, page)
        write_cfg(cfg)
        app = make(key)
        app.start()
        assert [c for c in app.display.calls if c[0] == "line"] == []
        assert pngdec.decoded[-1][0] == "/images/hennie.png"
