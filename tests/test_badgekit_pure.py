"""Pure logic in badgekit: config validation, vCard, paging, state, layout, wrapping."""
import copy
import json
import os

import pytest

import badgekit as bk
import qr_capacity

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLE = os.path.join(ROOT, "config", "badge.example.json")


@pytest.fixture
def cfg():
    with open(EXAMPLE, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------- config
def test_example_config_is_valid(cfg):
    assert bk.validate_config(cfg) is cfg


def test_load_config_missing_file(tmp_path):
    with pytest.raises(bk.ConfigError, match="Cannot read"):
        bk.load_config(str(tmp_path / "nope.json"))


def test_load_config_bad_json(tmp_path):
    p = tmp_path / "x.json"
    p.write_text("{not json")
    with pytest.raises(bk.ConfigError, match="not valid JSON"):
        bk.load_config(str(p))


def test_load_config_ok(tmp_path, cfg):
    p = tmp_path / "x.json"
    p.write_text(json.dumps(cfg))
    assert bk.load_config(str(p))["sections"]["a"]["title"] == "Profile"


def _extend_pages(c):
    c["sections"]["a"]["pages"].extend([c["sections"]["a"]["pages"][0]] * 8)


@pytest.mark.parametrize("mutate,msg", [
    (lambda c: c.update(sections={}), "no sections"),
    (lambda c: c.update(sections=[]), "no sections"),
    (lambda c: c["sections"].update(z=c["sections"]["a"]), "unknown section"),
    (lambda c: c["sections"]["a"].update(pages=[]), "no pages"),
    (lambda c: c["sections"]["a"].update(pages=[{"type": "video"}]), "unknown type"),
    (lambda c: c["sections"]["a"].update(title=""), "empty"),
    (lambda c: c["sections"]["a"].update(title="x" * 21), "too long"),
    (_extend_pages, "too many pages"),
    (lambda c: c["sections"]["a"]["pages"][0].update(image="/images/../x.png"), r"\.\."),
    (lambda c: c["sections"]["a"]["pages"][0].update(image="images/x.png"), "absolute"),
    (lambda c: c["sections"]["a"]["pages"][0].update(image="/images/x y.png"), "bad character"),
    (lambda c: c["sections"]["a"]["pages"][0].update(image=5), "text"),
    (lambda c: c["sections"]["a"]["pages"][0].pop("name"), "name"),
    (lambda c: c["sections"]["a"]["pages"][0].update(lines=["a"]), "replaced by"),
    (lambda c: c["sections"]["a"]["pages"][0].update(company="x"), "replaced by"),
    (lambda c: c["sections"]["a"]["pages"][0].pop("header"), "header"),
    (lambda c: c["sections"]["a"]["pages"][0].update(header="x" * 41), "too long"),
    (lambda c: c["sections"]["a"]["pages"][0].update(header=""), "empty"),
    (lambda c: c["sections"]["a"]["pages"][0].update(title="x" * 41), "too long"),
    (lambda c: c["sections"]["a"]["pages"][0].update(website="x" * 41), "too long"),
    (lambda c: c["sections"]["a"]["pages"][0].update(title=5), "must be text"),
    (lambda c: c["sections"]["a"]["pages"][0].update(website="a" + chr(0x85)), "control"),
    (lambda c: c["sections"]["a"]["pages"][0].update(header="a" + chr(10)), "control"),
    (lambda c: c["sections"]["a"]["pages"][0].update(image_w=0), "image_w"),
    (lambda c: c["sections"]["a"]["pages"][0].update(image_w=297), "image_w"),
    (lambda c: c["sections"]["a"]["pages"][0].update(image_w=True), "image_w"),
    (lambda c: c["sections"]["a"]["pages"][0].update(image_w=10.5), "image_w"),
    (lambda c: c["sections"]["a"]["pages"][0].update(image_y=-1), "image_y"),
    (lambda c: c["sections"]["a"]["pages"][0].update(image_y=129), "image_y"),
    (lambda c: c["sections"]["a"]["pages"][0].update(image_y="3"), "image_y"),
    (lambda c: c["sections"]["a"]["pages"][2].update(url="javascript:alert(1)"), "http"),
    (lambda c: c["sections"]["a"]["pages"][2].update(url="https://a b"), "spaces"),
    (lambda c: c["sections"]["a"]["pages"][2].update(vcard={"name": "x"}), "exactly one"),
    (lambda c: c["sections"]["a"]["pages"][2].pop("url"), "exactly one"),
    (lambda c: c["sections"]["a"]["pages"][1]["vcard"].update(fax="1"), "unknown field"),
    (lambda c: c["sections"]["a"]["pages"][1]["vcard"].pop("name"), "name"),
    (lambda c: c["sections"]["a"]["pages"][1]["vcard"].update(email=7), "text"),
    (lambda c: c["sections"]["a"]["pages"][1].update(header=["a", "b"]), "replaced by"),
    (lambda c: c["sections"]["a"]["pages"][1].update(title="x" * 41), "too long"),
    (lambda c: c["sections"]["a"]["pages"][1].update(title=""), "empty"),
    (lambda c: c["sections"]["a"]["pages"][1].update(text="x" * 61), "too long"),
    (lambda c: c["sections"]["a"]["pages"][1].update(text=5), "must be text"),
    (lambda c: c["sections"]["a"]["pages"][1].update(title="a" + chr(0x2028) + "b"), "control"),
    (lambda c: c["sections"]["a"]["pages"][1].update(text="a" + chr(0x85) + "b"), "control"),
    (lambda c: c["sections"]["a"]["pages"][1].update(text="a" + chr(10) + "b"), "control"),
    (lambda c: c["sections"]["p"]["pages"][1].update(header="a" + chr(0x9f)), "control"),
    (lambda c: c["sections"]["p"]["pages"][1].update(lines=["ok", "a" + chr(0x2029) + "b"]), "control"),
    (lambda c: c["sections"]["a"]["pages"][0].update(name="Bad" + chr(7)), "control"),
        (lambda c: c.update(project={"url": "https://x.io"}), "replaced by section p"),
    (lambda c: c.update(project=[]), "replaced by section p"),
    (lambda c: c["sections"]["p"]["pages"].append({"type": "text", "header": "H"}), "lines is required"),
    (lambda c: c["sections"]["p"]["pages"].append({"type": "text", "lines": []}), "header"),
    (lambda c: c["sections"]["p"]["pages"].append({"type": "text", "header": "H", "lines": "x"}), "must be a list"),
    (lambda c: c["sections"]["p"]["pages"].append({"type": "text", "header": "H", "lines": ["x"] * 7}), "too many lines"),
    (lambda c: c["sections"]["p"]["pages"].append({"type": "text", "header": "H", "lines": ["x" * 61]}), "too long"),
    (lambda c: c["sections"]["p"]["pages"].append({"type": "text", "header": "H", "lines": [5]}), "must be text"),
    (lambda c: c["sections"]["p"]["pages"].append({"type": "text", "header": "", "lines": []}), "empty"),
])
def test_validate_config_rejects(cfg, mutate, msg):
    bad = copy.deepcopy(cfg)
    mutate(bad)
    with pytest.raises(bk.ConfigError, match=msg):
        bk.validate_config(bad)


def test_validate_config_not_object():
    with pytest.raises(bk.ConfigError):
        bk.validate_config([])


def test_section_p_is_a_normal_section_and_old_project_key_is_gone(cfg):
    assert "project" not in cfg and "p" in cfg["sections"]
    bk.validate_config(cfg)
    assert bk.SECTION_APPS["p"] == "project"
    assert bk.apply_button(cfg, "p", 0, "p") == ("p", 0)       # no button jumps to p
    assert bk.apply_button(cfg, "p", 0, "a") == ("a", 0)       # A/B/C jump away from it
    assert bk.apply_button(cfg, "p", 2, "down") == ("p", 0)    # wrap
    assert bk.apply_button(cfg, "p", 0, "up") == ("p", 2)


def test_text_page_accepts_spacer_and_six_lines(cfg):
    cfg["sections"]["p"]["pages"].append({"type": "text", "header": "H", "lines": ["a", "", "b", "", "c", "d"]})
    bk.validate_config(cfg)
    cfg["sections"]["p"]["pages"].append({"type": "text", "header": "H", "lines": []})
    bk.validate_config(cfg)


# ----------------------------------------------------------------- vCard
def test_escape_vcard():
    assert bk.escape_vcard("a;b,c\\d") == "a\\;b\\,c\\\\d"
    assert bk.escape_vcard("l1\nl2\r\nl3\rl4") == "l1\\nl2\\nl3\\nl4"


def test_escape_backslash_first():
    assert bk.escape_vcard("\\;") == "\\\\\\;"


def test_build_vcard_full():
    v = {"name": "Ann Marie Lee", "title": "Eng, Lead", "company": "A;B", "email": "a@x.org",
         "phone": "+1 2", "url": "https://x.org", "linkedin": "https://l.in/a"}
    lines = bk.build_vcard(v).split("\r\n")
    assert lines[0] == "BEGIN:VCARD" and lines[1] == "VERSION:3.0" and lines[-1] == "END:VCARD"
    assert "N:Lee;Ann Marie;;;" in lines
    assert "FN:Ann Marie Lee" in lines
    assert "ORG:A\\;B" in lines
    assert "TITLE:Eng\\, Lead" in lines
    assert "TEL:+1 2" in lines and "EMAIL:a@x.org" in lines
    assert lines.count("URL:https://x.org") == 1 and "URL:https://l.in/a" in lines
    assert lines.index("URL:https://x.org") < lines.index("URL:https://l.in/a")


def test_build_vcard_skips_empty_and_single_name():
    out = bk.build_vcard({"name": "Madonna", "email": "  "})
    assert "N:Madonna;;;" in out
    assert "EMAIL" not in out and "TEL" not in out


def test_vcard_injection_is_neutralised():
    nl = chr(10)
    cr = chr(13)
    evil = "Evil" + nl + "END:VCARD" + nl + "BEGIN:VCARD"
    out = bk.build_vcard({"name": evil, "title": "x" + cr + nl + "TEL:911"})
    lines = out.split(cr + nl)
    assert lines.count("BEGIN:VCARD") == 1 and lines.count("END:VCARD") == 1
    assert not any(x.startswith("TEL:") for x in lines)


def test_example_vcard_fits_two_px(cfg):
    page = cfg["sections"]["a"]["pages"][1]
    assert qr_capacity.analyse(bk.qr_payload(page))["px"] >= 2


def test_qr_payload_url(cfg):
    assert bk.qr_payload(cfg["sections"]["a"]["pages"][2]) == "https://example.com"


# ---------------------------------------------------------------- paging
@pytest.mark.parametrize("page,count,step,expect", [
    (0, 3, 1, 1), (2, 3, 1, 0), (0, 3, -1, 2), (1, 3, -1, 0), (0, 1, 1, 0), (0, 1, -1, 0), (0, 0, 1, 0),
])
def test_step_page(page, count, step, expect):
    assert bk.step_page(page, count, step) == expect


def test_apply_button(cfg):
    assert bk.apply_button(cfg, "a", 2, "b") == ("b", 0)
    assert bk.apply_button(cfg, "a", 2, "a") == ("a", 0)
    assert bk.apply_button(cfg, "a", 0, "down") == ("a", 1)
    assert bk.apply_button(cfg, "a", 2, "down") == ("a", 0)
    assert bk.apply_button(cfg, "a", 0, "up") == ("a", 2)
    one = copy.deepcopy(cfg)
    one["sections"]["c"]["pages"] = one["sections"]["c"]["pages"][:1]
    assert bk.apply_button(one, "c", 0, "up") == ("c", 0)      # one-page section
    assert bk.apply_button(one, "c", 0, "down") == ("c", 0)
    assert bk.apply_button(cfg, "c", 0, "down") == ("c", 1)    # two-page section
    assert bk.apply_button(cfg, "zz", 0, "down") == ("zz", 0)  # unknown section
    assert bk.apply_button(cfg, "a", 1, "weird") == ("a", 1)


# ----------------------------------------------------------------- state
@pytest.mark.parametrize("raw,expect", [
    ({"section": "b", "page": 2}, ("b", 2)),
    ({"section": "a", "page": 0}, ("a", 0)),
    ({"section": "b", "page": 3}, None),
    ({"section": "b", "page": -1}, None),
    ({"section": "b", "page": True}, None),
    ({"section": "b", "page": "1"}, None),
    ({"section": "b", "page": 1.0}, None),
    ({"section": "q", "page": 0}, None),
    ({"section": 3, "page": 0}, None),
    ({"page": 0}, None),
    ([], None),
    (None, None),
    ("junk", None),
])
def test_sanitize_state(cfg, raw, expect):
    assert bk.sanitize_state(raw, cfg) == expect


def test_sanitize_state_section_removed_from_config(cfg):
    del cfg["sections"]["b"]
    assert bk.sanitize_state({"section": "b", "page": 0}, cfg) is None


# ---------------------------------------------------------------- layout
def test_qr_layout_57_modules_is_two_px():
    lay = bk.qr_layout(57)
    assert lay["px"] == 2 and lay["size"] == 114
    assert lay["top"] == 7


@pytest.mark.parametrize("modules", [21, 25, 29, 33, 37, 41, 45, 49, 53, 57, 61, 64])
def test_qr_layout_fits_and_is_right_aligned(modules):
    lay = bk.qr_layout(modules)
    assert lay["px"] == bk.HEIGHT // modules >= 2
    assert lay["size"] <= bk.HEIGHT
    assert lay["top"] + lay["size"] <= bk.HEIGHT
    assert lay["left"] + lay["size"] + lay["top"] == bk.WIDTH   # right margin == top margin
    assert lay["text_w"] == lay["left"] - 2 * bk.HEADER_PAD
    assert lay["text_w"] > 100


def test_qr_layout_too_dense_or_invalid():
    assert bk.qr_layout(65) is None      # 1 px per module is refused
    assert bk.qr_layout(129) is None
    assert bk.qr_layout(0) is None
    assert bk.qr_layout(64)["px"] == 2


def meas(s, scale=1):
    return int(len(s) * 6 * scale)


def test_wrap_text_basic():
    assert bk.wrap_text(meas, "aaa bbb ccc", 50) == ["aaa bbb", "ccc"]
    assert bk.wrap_text(meas, "", 40) == []
    assert bk.wrap_text(meas, "   ", 40) == []


def test_wrap_text_long_word_is_broken():
    lines = bk.wrap_text(meas, "supercalifragilistic", 60)
    assert "".join(lines) == "supercalifragilistic"
    assert all(meas(x) <= 60 for x in lines)


def test_wrap_text_tiny_width_terminates():
    assert "".join(bk.wrap_text(meas, "abc", 1)) == "abc"


def test_header_lines_caps_lines():
    out = bk.header_lines(meas, ["one two three four five six seven eight"], 30, 3)
    assert len(out) == 3


def test_fit_title():
    assert bk.fit_title(meas, "Hi", 100) == ("Hi", 2)
    assert bk.fit_title(meas, "Companies", 60) == ("Companies", 1)   # 108 > 60 at 2x, 54 fits at 1x
    text, scale = bk.fit_title(meas, "A very long title indeed", 60)
    assert scale == 1 and text.endswith("..") and meas(text, 1) <= 60


# ------------------------------------------------ fix round
def test_vcard_urls_are_not_text_escaped_but_text_is():
    out = bk.build_vcard({"name": "A B", "title": "a,b", "url": "https://x.io/a,b;c", "linkedin": "https://l.io/in/x"})
    lines = out.split(chr(13) + chr(10))
    assert "URL:https://x.io/a,b;c" in lines
    assert "TITLE:a\\,b" in lines


def test_vcard_url_cannot_inject_a_property():
    nl, cr = chr(10), chr(13)
    out = bk.build_vcard({"name": "A B", "url": "https://x.io" + cr + nl + "TEL:911", "linkedin": "x" + nl + "EMAIL:e@x.io"})
    lines = out.split(cr + nl)
    assert not any(x.startswith(("TEL:", "EMAIL:")) for x in lines)


def test_config_rejects_control_chars_in_vcard_urls(cfg):
    cfg["sections"]["a"]["pages"][1]["vcard"]["url"] = "https://x.io" + chr(10) + "TEL:1"
    with pytest.raises(bk.ConfigError, match="control"):
        bk.validate_config(cfg)


@pytest.mark.parametrize("path", ["/elsewhere/a.png", "/images/sub/a.png", "/images/.png", "/a.png", "/images/"])
def test_image_path_must_be_images_dir(cfg, path):
    cfg["sections"]["b"]["pages"][0]["image"] = path
    with pytest.raises(bk.ConfigError):
        bk.validate_config(cfg)


def test_header_lines_ellipsis_when_cut():
    out = bk.header_lines(meas, ["one two three four five six seven eight"], 40, 2)
    assert len(out) == 2 and out[-1].endswith("..") and meas(out[-1]) <= 40


def test_header_lines_unlimited_by_default():
    assert len(bk.header_lines(meas, ["word " * 30], 60)) > 4


def test_fit_whole_uses_whole_scales_then_cuts():
    def m(t, sc):
        return len(t) * 5 * sc
    assert bk.fit_whole(m, "abcd", 100, (2, 1)) == ("abcd", 2)             # 40 at scale 2
    assert bk.fit_whole(m, "x" * 15, 100, (2, 1)) == ("x" * 15, 1)         # 150 at 2, 75 at 1
    text, sc = bk.fit_whole(m, "x" * 40, 100, (2, 1))                       # 200 at scale 1: cut
    assert sc == 1 and text.endswith("..") and m(text, 1) <= 100
    assert type(sc) is int
    text, sc = bk.fit_whole(m, "x" * 40, 100, (1,))
    assert sc == 1 and text.endswith("..")
    assert not hasattr(bk, "fit_scaled") and not hasattr(bk, "NAME_SCALE") and not hasattr(bk, "SANS_CHAR_WIDTH")


def test_badgekit_source_has_no_vector_font_or_thickness():
    import inspect
    src = inspect.getsource(bk)
    assert '"sans"' not in src and "set_thickness" not in src



LINE_BREAKERS = [chr(0x85), chr(0x80), chr(0x9f), chr(0x7f), chr(0x2028), chr(0x2029), chr(0x0b), chr(0x0c), chr(0x1c)]


@pytest.mark.parametrize("ch", LINE_BREAKERS)
@pytest.mark.parametrize("field", ["name", "title", "company", "email", "phone", "url", "linkedin"])
def test_vcard_strips_line_breaking_characters_in_every_field(ch, field):
    card = {"name": "A B", "title": "t", "company": "c", "email": "e@x.io", "phone": "1",
            "url": "https://x.io", "linkedin": "https://l.io/x"}
    card[field] = card[field] + ch + "XINJ:911"
    out = bk.build_vcard(card)
    assert not any(c in out for c in LINE_BREAKERS)
    assert not any(x.startswith("XINJ:") for x in out.split(chr(13) + chr(10)))


@pytest.mark.parametrize("ch", LINE_BREAKERS)
def test_config_rejects_line_breakers_in_vcard_urls(cfg, ch):
    cfg["sections"]["a"]["pages"][1]["vcard"]["linkedin"] = "https://x.io" + ch + "x"
    with pytest.raises(bk.ConfigError, match="control"):
        bk.validate_config(cfg)


# ------------------------------------------------------------ qr_border
@pytest.mark.parametrize("modules,border,px,size", [
    (25, 0, 5, 125), (25, 2, 4, 116), (25, 4, 3, 99), (57, 0, 2, 114), (57, 2, 2, 122),
])
def test_qr_layout_with_border(modules, border, px, size):
    lay = bk.qr_layout(modules, border=border)
    assert (lay["px"], lay["size"]) == (px, size)
    assert lay["left"] + lay["size"] + lay["top"] == bk.WIDTH           # box stays right aligned
    assert lay["code_left"] == lay["left"] + border * px
    assert lay["code_top"] == lay["top"] + border * px
    assert lay["code_left"] + modules * px + border * px == bk.WIDTH - lay["top"]
    assert lay["text_w"] == lay["left"] - 2 * bk.HEADER_PAD             # header clear of code plus border


def test_qr_layout_border_below_two_px_is_refused():
    assert bk.qr_layout(57, border=4) is None      # 65 modules -> 1 px
    assert bk.qr_layout(57, border=3) is not None  # 63 modules -> 2 px


def test_qr_layout_default_border_is_zero_and_unchanged():
    assert bk.qr_layout(57) == bk.qr_layout(57, border=0)
    assert bk.qr_layout(57)["code_left"] == bk.qr_layout(57)["left"]


@pytest.mark.parametrize("value", [0, 1, 2, 3, 4])
def test_qr_border_accepts_0_to_4(cfg, value):
    cfg["qr_border"] = value
    bk.validate_config(cfg)


@pytest.mark.parametrize("value", [-1, 5, 2.0, "2", True, None, [2]])
def test_qr_border_rejects_others(cfg, value):
    cfg["qr_border"] = value
    with pytest.raises(bk.ConfigError, match="qr_border"):
        bk.validate_config(cfg)


@pytest.mark.parametrize("modules,border", [(25, 0), (29, 1), (33, 4), (57, 3)])
def test_auto_border_picks_largest_that_keeps_px(modules, border):
    assert bk.auto_border(modules) == border
    assert bk.qr_layout(modules, border="auto")["px"] == bk.qr_layout(modules, border=0)["px"]
    assert bk.qr_layout(modules, border="auto")["border"] == border


def test_auto_border_never_shrinks_any_size():
    for n in range(21, 65):
        lay = bk.qr_layout(n, border="auto")
        assert lay["px"] == bk.HEIGHT // n >= 2
        assert lay["text_w"] == lay["left"] - 2 * bk.HEADER_PAD


def test_explicit_borders_still_work_and_auto_is_accepted(cfg):
    assert bk.qr_layout(57, border=2)["border"] == 2
    cfg["qr_border"] = "auto"
    bk.validate_config(cfg)
    cfg.pop("qr_border")
    bk.validate_config(cfg)


@pytest.mark.parametrize("value", ["Auto", "AUTO", "", "none"])
def test_qr_border_rejects_other_strings(cfg, value):
    cfg["qr_border"] = value
    with pytest.raises(bk.ConfigError, match="qr_border"):
        bk.validate_config(cfg)


# ------------------------------------------------ house title bar and QR text block
def bmeas(t, scale=1):
    return int(round(len(t) * 4.9 * scale))


def test_qr_title_and_text_are_optional(cfg):
    p = cfg["sections"]["a"]["pages"][2]
    p.pop("title")
    p.pop("text")
    bk.validate_config(cfg)


def test_vcard_text_fields_may_still_contain_newlines_in_config(cfg):
    cfg["sections"]["a"]["pages"][1]["vcard"]["title"] = "line1" + chr(10) + "line2"
    bk.validate_config(cfg)


@pytest.mark.parametrize("border", [0, 1, 2, 3, 4, "auto"])
@pytest.mark.parametrize("modules", range(21, 65))
def test_title_bar_never_overlaps_qr_box(modules, border):
    lay = bk.qr_layout(modules, border=border)
    if lay is None:
        pytest.skip("too dense for this border")
    bar_x1 = lay["left"] - bk.BAR_GAP
    assert bar_x1 + bk.BAR_GAP <= lay["left"]
    assert bar_x1 <= lay["left"] - 4                   # the 4 px gap
    assert bar_x1 > 100                                 # still a usable bar
    # bar spans x 0..bar_x1; the QR box spans left..left+size: disjoint
    assert bar_x1 <= lay["left"] and lay["left"] + lay["size"] <= bk.WIDTH
    assert lay["code_left"] >= lay["left"]


def test_text_block_prefers_scale_two_and_is_centred():
    blk = bk.place_text_block(bmeas, "Hi there", 160)
    assert blk["scale"] == 2 and blk["fits"]
    assert all(bmeas(t, 2) <= 160 - 2 * bk.TEXT_BAR_PAD for t in blk["lines"])
    height = (len(blk["lines"]) - 1) * blk["pitch"] + 8 * 2
    assert blk["y"] == 16 + (112 - height) // 2
    assert blk["x"] == (160 - blk["width"]) // 2
    assert blk["pitch"] == 20


def test_text_block_falls_back_to_scale_one():
    word = "x" * 20                                   # 196 px at scale 2 does not fit 152; 98 at scale 1 does
    blk = bk.place_text_block(bmeas, word, 160)
    assert blk["scale"] == 1 and blk["fits"] and blk["lines"] == [word]
    assert blk["pitch"] == 10 and blk["y"] == 16 + (112 - 8) // 2


def test_text_block_multi_line_is_centred_vertically_and_wrapped():
    blk = bk.place_text_block(bmeas, "Save my Contact Details", 157)
    assert len(blk["lines"]) >= 2
    assert all(bmeas(t, blk["scale"]) <= 157 - 2 * bk.TEXT_BAR_PAD for t in blk["lines"])
    assert blk["width"] == max(bmeas(t, blk["scale"]) for t in blk["lines"])
    height = (len(blk["lines"]) - 1) * blk["pitch"] + 8 * blk["scale"]
    assert blk["y"] == 16 + (112 - height) // 2 and 16 <= blk["y"] and blk["y"] + height <= bk.HEIGHT


def test_text_block_unbreakable_overflow_is_flagged_not_crashing():
    blk = bk.place_text_block(bmeas, "w" * 60, 60)
    assert blk["scale"] == 1 and not blk["fits"]
    assert all(bmeas(t, 1) <= 60 - 2 * bk.TEXT_BAR_PAD for t in blk["lines"])
    assert bk.place_text_block(bmeas, "", 160)["lines"] == []


# ------------------------------------------------ extra sections
@pytest.mark.parametrize("key", ["work", "extra", "ab", "a1", "a_b", "x" * 16, "z9_"])
def test_valid_extra_keys(key):
    assert bk.valid_extra_key(key)


@pytest.mark.parametrize("key", ["a", "", "A1", "Work", "1ab", "_ab", "ab-c", "a b", "x" * 17, "ab.c", None, 5, ["ab"]])
def test_invalid_extra_keys(key):
    assert not bk.valid_extra_key(key)


def test_config_accepts_extra_sections_and_rejects_bad_keys(cfg):
    bk.validate_config(cfg)                                  # example holds "work"
    assert "work" in cfg["sections"]
    for bad in ("Work", "w", "x" * 17, "1ab", "ab-c", "a b"):
        c = copy.deepcopy(cfg)
        c["sections"][bad] = copy.deepcopy(c["sections"]["work"])
        with pytest.raises(bk.ConfigError, match="unknown section"):
            bk.validate_config(c)


def test_extra_section_is_validated_like_the_others(cfg):
    cfg["sections"]["work"]["pages"] = []
    with pytest.raises(bk.ConfigError, match="no pages"):
        bk.validate_config(cfg)
    cfg["sections"]["work"]["pages"] = [{"type": "qr", "url": "javascript:x"}]
    with pytest.raises(bk.ConfigError, match="http"):
        bk.validate_config(cfg)
    cfg["sections"]["work"] = {"pages": [{"type": "image", "image": "/images/a.png"}]}
    with pytest.raises(bk.ConfigError, match="title"):
        bk.validate_config(cfg)


def test_app_for():
    assert bk.app_for("a") == "profile" and bk.app_for("p") == "project"
    assert bk.app_for("work") == "work" and bk.app_for("b") == "company" and bk.app_for("c") == "event"
    assert bk.app_for("Z") is None and bk.app_for("z") is None


def test_wrap_around_for_two_page_and_one_page_extra_sections(cfg):
    cfg["sections"]["two"] = {"title": "Two", "pages": cfg["sections"]["work"]["pages"][:2]}
    cfg["sections"]["one"] = {"title": "One", "pages": cfg["sections"]["work"]["pages"][:1]}
    assert bk.apply_button(cfg, "two", 0, "down") == ("two", 1)
    assert bk.apply_button(cfg, "two", 1, "down") == ("two", 0)    # loops back to page 1
    assert bk.apply_button(cfg, "two", 0, "up") == ("two", 1)
    assert bk.apply_button(cfg, "two", 1, "up") == ("two", 0)
    assert bk.apply_button(cfg, "one", 0, "down") == ("one", 0)
    assert bk.apply_button(cfg, "one", 0, "up") == ("one", 0)
    for b in ("a", "b", "c"):
        assert bk.apply_button(cfg, "two", 1, b) == (b, 0)


def test_qr_text_block_scales_are_whole_numbers():
    for text in ("Hi", "Save my Contact Details", "x" * 20, "w" * 60, "a b c d e f g h i j k l m n o p"):
        blk = bk.place_text_block(lambda t, sc: int(len(t) * 4.9 * sc), text, 157)
        assert type(blk["scale"]) is int and blk["scale"] in (1, 2)


def test_badge_page_new_schema_accepts_bounds_and_optional_fields(cfg):
    page = cfg["sections"]["a"]["pages"][0]
    assert {"header", "name", "title", "website", "image", "image_w", "image_y"} <= set(page)
    for w in (1, 104, 296):
        page["image_w"] = w
        bk.validate_config(cfg)
    for y in (0, 128):
        page["image_y"] = y
        bk.validate_config(cfg)
    for k in ("title", "website", "image_w", "image_y"):
        page.pop(k, None)
    bk.validate_config(cfg)                                              # only header, name and image are required
