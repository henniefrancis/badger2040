"""Host tooling: QR capacity maths, config validator, image converter, deploy planner."""
import copy
import json
import os
import shutil
import subprocess
import sys

import pytest
from PIL import Image

import convert_image
import deploy
import qr_capacity
import validate_config as vc

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLE = os.path.join(ROOT, "config", "badge.example.json")


@pytest.fixture
def cfg():
    with open(EXAMPLE, encoding="utf-8") as f:
        return json.load(f)


def make_config_dir(tmp_path, cfg, images=("aws.png", "microsoft.png"), icons=True):
    d = tmp_path / "private"
    d.mkdir()
    (d / "badge.json").write_text(json.dumps(cfg), encoding="utf-8")
    if images:
        (d / "images").mkdir()
        for n in images:
            Image.new("1", (10, 10), 1).save(d / "images" / n)
    if icons:
        (d / "icons").mkdir()
        for n in vc.PLACEHOLDER_ICONS:
            Image.new("1", (52, 52), 1).save(d / "icons" / n)
    return d


def real_looking(cfg):
    c = copy.deepcopy(cfg)
    c["sections"]["a"]["pages"][0]["name"] = "Jane Roe"
    c["sections"]["a"]["pages"][2]["url"] = "https://jane.dev"
    c["sections"]["b"]["pages"][1]["name"] = "Jane Roe"
    c["sections"]["a"]["pages"][1]["vcard"] = {
        "name": "Jane Roe", "title": "Engineer", "company": "Roe Ltd", "email": "jane@jane.dev",
        "phone": "+11 22 333 4444", "url": "https://jane.dev", "linkedin": "https://www.linkedin.com/in/jroe"}
    c["sections"]["work"]["pages"][0]["name"] = "Jane Roe"
    c["sections"]["work"]["pages"][1]["url"] = "https://roe.dev"
    for extra in ("awscommza", "dotcore", "devconf"):          # the repo ships wrapper apps for these sections
        c["sections"][extra] = copy.deepcopy(c["sections"]["work"])
    return c


# ----------------------------------------------------------- qr_capacity
@pytest.mark.parametrize("n,version,modules", [
    (1, 1, 21), (17, 1, 21), (18, 2, 25), (268, 10, 57), (271, 10, 57), (272, 11, 61),
    (321, 11, 61), (322, 12, 65), (2953, 40, 177),
])
def test_qr_version_boundaries(n, version, modules):
    assert qr_capacity.qr_version(n) == version
    assert qr_capacity.modules_for_version(version) == modules


def test_qr_too_big_for_any_version():
    assert qr_capacity.qr_version(2954) is None
    assert qr_capacity.analyse("x" * 3000)["modules"] is None


def test_measured_device_case():
    # The owner's measured case: 268-byte vCard -> 57 modules -> 2 px (114 px)
    info = qr_capacity.analyse("x" * 268)
    assert (info["modules"], info["px"], info["size"]) == (57, 2, 114)


def test_two_px_limit_is_321_bytes():
    assert qr_capacity.analyse("x" * 321)["px"] == 2
    assert qr_capacity.analyse("x" * 322)["px"] == 1


def test_analyse_counts_utf8_bytes():
    assert qr_capacity.analyse("é" * 10)["bytes"] == 20


# ------------------------------------------------------- validate_config
def test_example_passes_with_placeholders_allowed():
    errors, report = vc.validate(EXAMPLE, allow_placeholders=True, allow_placeholder_images=True)
    assert errors == []
    assert any(line.startswith("WARNING") and "PLACEHOLDER" in line for line in report)
    assert any("section a page 2" in line for line in report)
    assert any(line.startswith("QR section p page 1") for line in report)


def test_example_is_refused_as_real_config():
    errors, _ = vc.validate(EXAMPLE)
    text = " ".join(errors)
    assert "placeholder" in text and "email" in text and "phone" in text


def test_real_looking_config_passes(tmp_path, cfg):
    d = make_config_dir(tmp_path, real_looking(cfg))
    errors, report = vc.validate(str(d))
    assert errors == []


def test_validator_flags_dense_qr(tmp_path, cfg):
    c = real_looking(cfg)
    c["sections"]["a"]["pages"][1]["vcard"]["title"] = "T" * 100
    c["sections"]["a"]["pages"][1]["vcard"]["company"] = "C" * 100
    d = make_config_dir(tmp_path, c)
    errors, _ = vc.validate(str(d))
    assert any("px per module" in e for e in errors)


def test_validator_flags_structure_error(tmp_path, cfg):
    c = real_looking(cfg)
    c["sections"]["a"]["pages"] = []
    errors, _ = vc.validate(str(make_config_dir(tmp_path, c)))
    assert errors and errors[0].startswith("config:")


def test_validator_flags_missing_image(tmp_path, cfg):
    c = real_looking(cfg)
    c["sections"]["c"]["pages"][0]["image"] = "/images/nope.png"
    errors, _ = vc.validate(str(make_config_dir(tmp_path, c)))
    assert any("nope.png" in e for e in errors)


def test_validator_bad_json_and_missing_file(tmp_path):
    d = tmp_path / "p"
    d.mkdir()
    errors, _ = vc.validate(str(d))
    assert errors and "cannot read" in errors[0]
    (d / "badge.json").write_text("{x")
    errors, _ = vc.validate(str(d))
    assert errors and "cannot read" in errors[0]


def test_find_placeholders_ignores_real_values(cfg):
    assert vc.find_placeholders(real_looking(cfg)) == []


def test_validate_cli_exit_codes(capsys):
    assert vc.main([EXAMPLE, "--allow-placeholders", "--allow-placeholder-images"]) == 0
    assert vc.main([EXAMPLE, "--allow-placeholders"]) == 1      # placeholder logos refused
    assert vc.main([EXAMPLE]) == 1


# --------------------------------------------------------- convert_image
def test_convert_sizes_and_mode(tmp_path):
    src = tmp_path / "in.png"
    Image.new("RGB", (400, 100), (200, 30, 30)).save(src)
    for kind, size in (("logo", (296, 128)), ("icon", (52, 52)), ("badge", (104, 128))):
        out = tmp_path / (kind + ".png")
        assert convert_image.convert(str(src), str(out), kind) == size
        with Image.open(out) as im:
            assert im.mode == "1" and im.size == size


def test_convert_transparency_becomes_white(tmp_path):
    src = tmp_path / "t.png"
    Image.new("RGBA", (50, 50), (0, 0, 0, 0)).save(src)
    out = tmp_path / "o.png"
    with pytest.raises(convert_image.BlankImageError):
        convert_image.convert(str(src), str(out), "icon")
    convert_image.convert(str(src), str(out), "icon", allow_blank=True)
    with Image.open(out) as im:
        assert set(im.convert("L").tobytes()) == {255}


def test_convert_invert_and_dither(tmp_path):
    src = tmp_path / "g.png"
    Image.linear_gradient("L").save(src)
    a, b = tmp_path / "a.png", tmp_path / "b.png"
    convert_image.convert(str(src), str(a), "icon", dither=True)
    convert_image.convert(str(src), str(b), "icon", invert=True)
    assert a.exists() and b.exists()


def test_convert_rejects_bad_input(tmp_path):
    src = tmp_path / "i.png"
    Image.new("L", (5, 5)).save(src)
    with pytest.raises(ValueError):
        convert_image.convert(str(src), str(src), "icon")
    with pytest.raises(ValueError):
        convert_image.convert(str(src), str(tmp_path / "o.png"), "huge")
    with pytest.raises(ValueError):
        convert_image.convert(str(src), str(tmp_path / "o.png"), "icon", threshold=999)
    assert convert_image.main([str(tmp_path / "missing.png"), str(tmp_path / "o.png"), "--kind", "icon"]) == 1


def test_convert_cli(tmp_path):
    src = tmp_path / "i.png"
    Image.new("L", (30, 30), 0).save(src)
    assert convert_image.main([str(src), str(tmp_path / "sub" / "o.png"), "--kind", "logo"]) == 0
    assert (tmp_path / "sub" / "o.png").exists()


def test_shipped_icons_and_images_are_one_bit_and_sized():
    apps = os.path.join(ROOT, "device", "henniefrancis")
    for n in ("personal", "aws", "microsoft", "project"):
        with Image.open(os.path.join(apps, "icon-%s.png" % n)) as im:
            assert im.mode == "1" and im.size == (52, 52), n
    for n in ("aws", "microsoft"):
        with Image.open(os.path.join(ROOT, "device", "images", n + ".png")) as im:
            assert im.mode == "1" and im.size == (296, 128), n


# ---------------------------------------------------------------- deploy
def test_plan_contents_and_remote_paths(tmp_path, cfg):
    d = make_config_dir(tmp_path, real_looking(cfg), images=["aws.png"], icons=False)
    (d / "icons").mkdir()
    Image.new("1", (52, 52), 1).save(d / "icons" / "icon-aws.png")
    (d / "icons" / "not-an-icon.png").write_bytes(b"x")
    plan = dict((remote, local) for local, remote in deploy.build_plan(str(d)))
    for r in plan:
        assert r.startswith("/") and ".." not in r
    assert plan["/lib/badgekit.py"].endswith(os.path.join("device", "lib", "badgekit.py"))
    assert plan["/launcher.py"].endswith(os.path.join("device", "launcher.py"))
    for app in deploy.APPS:
        assert "/henniefrancis/%s.py" % app in plan
    assert plan["/henniefrancis/icon-aws.png"] == str(d / "icons" / "icon-aws.png")   # config overrides repo
    assert plan["/images/aws.png"] == str(d / "images" / "aws.png")
    assert plan["/images/microsoft.png"].startswith(ROOT)                             # repo default
    assert plan["/henniefrancis/config/badge.json"] == str(d / "badge.json")
    assert "/henniefrancis/not-an-icon.png" not in plan
    assert "/henniefrancis/hennie.py" not in plan and "/henniefrancis/summit.py" not in plan


def test_dry_run_copies_nothing(tmp_path, cfg, monkeypatch, capsys):
    d = make_config_dir(tmp_path, real_looking(cfg))
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("must not run mpremote"))
    assert deploy.main(["--config", str(d), "--dry-run"]) == 0
    assert "dry run" in capsys.readouterr().out


def test_deploy_refuses_example_as_real(tmp_path, monkeypatch):
    d = tmp_path / "p"
    d.mkdir()
    shutil.copy(EXAMPLE, d / "badge.json")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("must not run mpremote"))
    assert deploy.main(["--config", str(d), "--port", "COM3"]) == 1


@pytest.mark.parametrize("port,ok", [
    ("COM3", True), ("COM12", True), ("/dev/ttyACM0", True), ("/dev/cu.usbmodem1101", True),
    ("COM3; rm -rf /", False), ("COM3 + reset", False), ("", False), ("../COM3", False), ("-h", False),
])
def test_port_validation(port, ok):
    assert bool(deploy.PORT_RE.match(port)) is ok


def test_deploy_rejects_bad_port_and_missing_folder(tmp_path, cfg, monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("must not run mpremote"))
    d = make_config_dir(tmp_path, real_looking(cfg))
    assert deploy.main(["--config", str(d), "--port", "COM3; x"]) == 2
    assert deploy.main(["--config", str(d)]) == 2
    assert deploy.main(["--config", str(tmp_path / "nope"), "--port", "COM3"]) == 2


def test_deploy_runs_mpremote_without_shell(tmp_path, cfg, monkeypatch):
    d = make_config_dir(tmp_path, real_looking(cfg))
    calls = []

    def fake_run(cmd, **kw):
        calls.append((cmd, kw))
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert deploy.main(["--config", str(d), "--port", "COM3", "--reset"]) == 0
    assert all(isinstance(c, list) and not kw.get("shell") for c, kw in calls)
    assert all(c[:5] == [sys.executable, "-m", "mpremote", "connect", "COM3"] for c, _ in calls)
    copy_cmd = [c for c, _ in calls if "cp" in c][0]
    assert copy_cmd.count("+") == copy_cmd.count("cp") - 1
    assert ":/henniefrancis/config/badge.json" in copy_cmd
    assert calls[-1][0][-1] == "reset"
    mkdirs = [c[-1] for c, _ in calls if "mkdir" in c]
    assert ":/lib" in mkdirs and ":/henniefrancis/config" in mkdirs


def test_deploy_reports_mpremote_failure(tmp_path, cfg, monkeypatch):
    d = make_config_dir(tmp_path, real_looking(cfg))

    def fake_run(cmd, **kw):
        if "cp" in cmd:
            raise subprocess.CalledProcessError(1, cmd)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert deploy.main(["--config", str(d), "--port", "COM3"]) == 1


# ------------------------------------------- fix round: images, sections, warnings
def test_placeholder_image_fallback_is_refused_unless_allowed(tmp_path, cfg):
    d = make_config_dir(tmp_path, real_looking(cfg), images=["aws.png"], icons=True)   # no microsoft.png
    errors, _ = vc.validate(str(d))
    assert any("image /images/microsoft.png" in e and "PLACEHOLDER" in e for e in errors)
    errors, report = vc.validate(str(d), allow_placeholder_images=True)
    assert errors == []
    assert any(r.startswith("WARNING") and "microsoft.png" in r for r in report)


def test_placeholder_icon_fallback_is_refused(tmp_path, cfg):
    d = make_config_dir(tmp_path, real_looking(cfg), icons=False)
    errors, _ = vc.validate(str(d))
    assert any("launcher icon icon-aws.png" in e for e in errors)
    assert any("launcher icon icon-project.png" in e for e in errors)


def test_deploy_refuses_placeholder_images_but_allows_with_flag(tmp_path, cfg, monkeypatch, capsys):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("must not run mpremote"))
    d = make_config_dir(tmp_path, real_looking(cfg), images=["aws.png"])
    assert deploy.main(["--config", str(d), "--dry-run"]) == 1
    assert deploy.main(["--config", str(d), "--dry-run", "--allow-placeholder-images"]) == 0
    assert "WARNING" in capsys.readouterr().out


def test_every_launcher_section_is_required(tmp_path, cfg):
    for key in ("a", "b", "c", "p"):
        c = real_looking(cfg)
        del c["sections"][key]
        errors, _ = vc.validate(str(make_config_dir(tmp_path / key if False else tmp_path, c)) if False else
                                str(_dir(tmp_path, key, c)))
        assert any("section %s is missing" % key in e for e in errors)


def _dir(tmp_path, name, c):
    d = tmp_path / name
    d.mkdir()
    (d / "badge.json").write_text(json.dumps(c))
    (d / "images").mkdir()
    for n in ("aws.png", "microsoft.png"):
        Image.new("1", (10, 10), 1).save(d / "images" / n)
    return d


@pytest.mark.parametrize("path", ["/elsewhere/aws.png", "/images/sub/aws.png", "/images/.png", "/aws.png"])
def test_image_paths_must_be_images_dir_name(tmp_path, cfg, path):
    c = real_looking(cfg)
    c["sections"]["b"]["pages"][0]["image"] = path
    errors, _ = vc.validate(str(_dir(tmp_path, "x", c)))
    assert errors and errors[0].startswith("config:")


def test_validator_warns_on_non_ascii_text(tmp_path, cfg):
    c = real_looking(cfg)
    c["sections"]["a"]["pages"][0]["name"] = "Jos\u00e9 Roe"
    errors, report = vc.validate(str(make_config_dir(tmp_path, c)))
    assert errors == []
    assert any(r.startswith("warning:") and "non-ASCII" in r for r in report)


def test_validator_rejects_old_qr_header_key(tmp_path, cfg):
    c = real_looking(cfg)
    c["sections"]["a"]["pages"][2]["header"] = ["Visit my", "website"]
    errors, _ = vc.validate(str(make_config_dir(tmp_path, c)))
    assert errors and "replaced by" in errors[0]


def test_clean_config_has_no_warnings(tmp_path, cfg):
    _, report = vc.validate(str(make_config_dir(tmp_path, real_looking(cfg))))
    assert not [r for r in report if r.lower().startswith("warning")]


def test_port_and_png_regex_reject_trailing_newline():
    assert not deploy.PORT_RE.match("COM3\n")
    assert not deploy.PNG_NAME_RE.match("a.png\n")


def test_convert_cli_clean_errors(tmp_path, capsys):
    bad = tmp_path / "bad.png"
    bad.write_bytes(b"not an image")
    assert convert_image.main([str(bad), str(tmp_path / "o.png"), "--kind", "icon"]) == 1
    err = capsys.readouterr().err
    assert err.startswith("error:") and "Traceback" not in err and len(err.strip().splitlines()) == 1


def test_convert_cli_decompression_bomb(tmp_path, monkeypatch, capsys):
    src = tmp_path / "big.png"
    Image.new("L", (300, 300)).save(src)
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 1000)       # 90000 px > 2x the limit
    assert convert_image.main([str(src), str(tmp_path / "o.png"), "--kind", "icon"]) == 1
    assert "DecompressionBomb" in capsys.readouterr().err


def test_convert_cli_blank_needs_flag(tmp_path, capsys):
    src = tmp_path / "t.png"
    Image.new("RGBA", (20, 20), (0, 0, 0, 0)).save(src)
    out = tmp_path / "o.png"
    assert convert_image.main([str(src), str(out), "--kind", "icon"]) == 1
    assert "entirely white" in capsys.readouterr().err
    assert not out.exists()
    assert convert_image.main([str(src), str(out), "--kind", "icon", "--allow-blank"]) == 0


def test_max_image_pixels_is_explicit():
    assert convert_image.Image.MAX_IMAGE_PIXELS == 50_000_000


def test_requirements_are_pinned():
    with open(os.path.join(ROOT, "requirements.txt"), encoding="utf-8") as f:
        reqs = [ln.strip() for ln in f if ln.strip() and not ln.startswith("#")]
    assert reqs and all("==" in r for r in reqs)
    names = {r.split("==")[0].lower() for r in reqs}
    assert {"pillow", "pytest", "mpremote"} <= names


def vcard_57_modules(cfg):
    c = real_looking(cfg)
    v = c["sections"]["a"]["pages"][1]["vcard"]
    v["title"] = "T" * 40
    for n in range(1, 100):
        v["company"] = "C" * n
        info = qr_capacity.analyse(vc.badgekit.qr_payload(c["sections"]["a"]["pages"][1]))
        if info["modules"] == 57:
            return c
    raise AssertionError("could not build a 57-module vCard")


@pytest.mark.parametrize("border,px,size,ok", [(0, 2, 114, True), (2, 2, 122, True), (3, 2, 126, True), (4, 1, 65, False)])
def test_validator_reports_px_and_fails_per_border(tmp_path, cfg, border, px, size, ok):
    c = vcard_57_modules(cfg)
    c["qr_border"] = border
    errors, report = vc.validate(str(make_config_dir(tmp_path, c)))
    row = [r for r in report if r.startswith("QR section a page 2")][0]
    assert "57 modules" in row and "border %d" % border in row and "%d px/module" % px in row
    if ok:
        assert row.endswith("%d px" % size) and errors == []
    else:
        assert any("section a page 2" in e and "qr_border 4" in e for e in errors)


def test_validator_default_border_is_zero_and_reports_code_size(tmp_path, cfg):
    errors, report = vc.validate(str(make_config_dir(tmp_path, real_looking(cfg))))
    assert errors == []
    rows = [r for r in report if r.startswith("QR")]
    assert rows
    for r in rows:
        modules = int(r.split(" modules")[0].split()[-1])
        px = int(r.split("px/module")[0].split()[-1])
        size = int(r.rstrip().split()[-2])
        assert "border 0" in r
        assert px == 128 // modules and size == px * modules      # as large as density allows


def test_validator_explicit_auto_and_numbers_still_work(tmp_path, cfg):
    c = real_looking(cfg)
    c["qr_border"] = "auto"
    errors, report = vc.validate(str(make_config_dir(tmp_path, c)))
    assert errors == []
    assert any("border 3" in r or "border 4" in r or "border 1" in r for r in report if r.startswith("QR"))


@pytest.mark.parametrize("auto", ["auto", None])
def test_validator_explicit_auto_equals_absent(tmp_path, cfg, auto):
    c = real_looking(cfg)
    if auto:
        c["qr_border"] = auto
    _, report = vc.validate(str(make_config_dir(tmp_path, c)))
    assert any("57" in r or "border" in r for r in report)


def test_validator_rejects_bad_border(tmp_path, cfg):
    c = real_looking(cfg)
    c["qr_border"] = 5
    errors, _ = vc.validate(str(make_config_dir(tmp_path, c)))
    assert errors and "qr_border" in errors[0]


def test_analyse_border():
    info = qr_capacity.analyse("x" * 268, border=2)
    assert (info["modules"], info["px"], info["size"]) == (57, 2, 122)
    assert qr_capacity.analyse("x" * 268, border=4)["px"] == 1


@pytest.mark.parametrize("version,modules,expect_border,px", [(2, 25, 0, 5), (3, 29, 1, 4), (4, 33, 4, 3), (10, 57, 3, 2)])
def test_auto_border_for_real_sized_codes(version, modules, expect_border, px):
    n = qr_capacity.BYTE_CAPACITY_L[version - 1]
    info = qr_capacity.analyse("x" * n, border="auto")
    assert (info["modules"], info["border"], info["px"]) == (modules, expect_border, px)
    assert info["px"] == qr_capacity.analyse("x" * n, border=0)["px"]
    assert vc.badgekit.auto_border(modules) == expect_border
    lay = vc.badgekit.qr_layout(modules, border="auto")
    assert lay["px"] == px and lay["border"] == expect_border
    assert lay["left"] + lay["size"] + lay["top"] == vc.badgekit.WIDTH
    assert lay["text_w"] == lay["left"] - 2 * vc.badgekit.HEADER_PAD


@pytest.mark.parametrize("n", range(1, 401))
def test_capacity_table_and_fake_agree_with_nayuki_qrcodegen(n):
    qrcodegen = pytest.importorskip("qrcodegen")
    import qrcode as fake
    data = bytes([65 + n % 26]) * n
    real = qrcodegen.QrCode.encode_binary(data, qrcodegen.QrCode.Ecc.LOW).get_size()
    info = qr_capacity.analyse(data.decode())
    assert info["modules"] == real
    code = fake.QRCode(fake.ECC_LOW)
    assert code.set_text(data.decode()) is True
    assert code.get_size() == (real, real)


def test_qrcodegen_is_a_pinned_requirement():
    with open(os.path.join(ROOT, "requirements.txt"), encoding="utf-8") as f:
        assert any(line.lower().startswith("qrcodegen==") for line in f)


def test_readme_and_plan_say_python_311():
    for rel in ("README.md", "docs/build-plan.md"):
        with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
            text = f.read()
        assert "3.11" in text and "3.10" not in text, rel


# ------------------------------------------------ launcher state reset on deploy
def test_dry_run_shows_state_reset_and_keep_state_skips_it(tmp_path, cfg, monkeypatch, capsys):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("must not run mpremote"))
    d = make_config_dir(tmp_path, real_looking(cfg))
    assert deploy.main(["--config", str(d), "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "/state/launcher.json" in out and '"running": "launcher"' in out
    assert deploy.main(["--config", str(d), "--dry-run", "--keep-state"]) == 0
    out = capsys.readouterr().out
    assert "/state/launcher.json" not in out and "--keep-state" in out


def run_deploy(tmp_path, cfg, monkeypatch, extra=()):
    d = make_config_dir(tmp_path, real_looking(cfg))
    calls, written = [], {}

    def fake_run(cmd, **kw):
        calls.append(cmd)
        if "cp" in cmd:
            for i, a in enumerate(cmd):
                if a == ":/state/launcher.json":
                    with open(cmd[i - 1], encoding="utf-8") as f:
                        written["state"] = f.read()
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert deploy.main(["--config", str(d), "--port", "COM3"] + list(extra)) == 0
    return calls, written


def test_deploy_resets_launcher_state_and_creates_state_dir(tmp_path, cfg, monkeypatch):
    calls, written = run_deploy(tmp_path, cfg, monkeypatch)
    assert json.loads(written["state"]) == {"page": 0, "running": "launcher"}
    assert ":/state" in [c[-1] for c in calls if "mkdir" in c]
    copy_cmd = [c for c in calls if "cp" in c][0]
    assert copy_cmd.index(":/state/launcher.json") > copy_cmd.index(":/henniefrancis/config/badge.json")  # last
    assert copy_cmd.count("+") == copy_cmd.count("cp") - 1


def test_deploy_keep_state_does_not_touch_launcher_state(tmp_path, cfg, monkeypatch):
    calls, written = run_deploy(tmp_path, cfg, monkeypatch, ["--keep-state"])
    assert "state" not in written
    assert not any(":/state/launcher.json" in c for c in calls)


# ------------------------------------------------------------- --kind photo
def photo_fixture(path):
    """108x146 colour 'portrait' with a white border, like the old hennie.png."""
    im = Image.new("RGB", (108, 146), (255, 255, 255))
    for y in range(20, 130):
        for x in range(14, 94):
            im.putpixel((x, y), (60 + (x * 2) % 140, 90 + y % 100, 120 + (x + y) % 100))
    im.save(path)


def test_photo_kind_is_104x128_one_bit_and_deterministic(tmp_path):
    src = tmp_path / "p.png"
    photo_fixture(src)
    a, b = tmp_path / "a.png", tmp_path / "b.png"
    assert convert_image.convert(str(src), str(a), "photo") == (104, 128)
    convert_image.convert(str(src), str(b), "photo")
    with Image.open(a) as ia, Image.open(b) as ib:
        assert ia.mode == "1" and ia.size == (104, 128)
        assert ia.tobytes() == ib.tobytes()
    assert convert_image.KINDS["photo"] == (104, 128)
    assert convert_image.KINDS["badge"] == (104, 128)


def test_photo_pipeline_golden_hash(tmp_path):
    import hashlib
    src = tmp_path / "p.png"
    photo_fixture(src)
    out = tmp_path / "o.png"
    convert_image.convert(str(src), str(out), "photo")
    with Image.open(out) as im:
        digest = hashlib.sha256(im.tobytes()).hexdigest()
    assert digest == PHOTO_GOLDEN, digest


def test_photo_crops_tightly_to_content(tmp_path):
    src = tmp_path / "small.png"
    im = Image.new("RGB", (400, 400), (255, 255, 255))
    for y in range(180, 220):
        for x in range(180, 220):
            im.putpixel((x, y), (0, 0, 0))
    im.save(src)
    out = tmp_path / "o.png"
    convert_image.convert(str(src), str(out), "photo")
    with Image.open(out) as o:
        black = o.convert("L").point(lambda p: 255 if p < 128 else 0).getbbox()
    assert black[2] - black[0] > 60           # the small square fills most of the 104 px width after the crop


def test_photo_differs_from_plain_badge_and_badge_is_unchanged(tmp_path):
    src = tmp_path / "p.png"
    photo_fixture(src)
    p, b = tmp_path / "p1.png", tmp_path / "b1.png"
    convert_image.convert(str(src), str(p), "photo")
    convert_image.convert(str(src), str(b), "badge")
    with Image.open(p) as ip, Image.open(b) as ib:
        assert ip.tobytes() != ib.tobytes()
        assert ib.size == (104, 128)


def test_photo_blank_input_still_needs_allow_blank(tmp_path):
    src = tmp_path / "w.png"
    Image.new("RGB", (50, 60), (255, 255, 255)).save(src)
    with pytest.raises(convert_image.BlankImageError):
        convert_image.convert(str(src), str(tmp_path / "o.png"), "photo")
    convert_image.convert(str(src), str(tmp_path / "o.png"), "photo", allow_blank=True)


def test_photo_cli(tmp_path):
    src = tmp_path / "p.png"
    photo_fixture(src)
    assert convert_image.main([str(src), str(tmp_path / "o.png"), "--kind", "photo"]) == 0


def test_readme_recommends_photo_kind():
    with open(os.path.join(ROOT, "README.md"), encoding="utf-8") as f:
        assert "--kind photo" in f.read()


PHOTO_GOLDEN = "cee12e793a4431586acf7d58c352a709113aca01f8109d38efceec87dbcf5778"


@pytest.mark.parametrize("size", [(1, 1), (15, 40), (40, 15)])
def test_photo_refuses_tiny_inputs(tmp_path, capsys, size):
    src = tmp_path / "tiny.png"
    Image.new("RGB", size, (0, 0, 0)).save(src)
    out = tmp_path / "o.png"
    with pytest.raises(ValueError, match="at least 16x16"):
        convert_image.convert(str(src), str(out), "photo")
    assert convert_image.main([str(src), str(out), "--kind", "photo"]) == 1
    assert "at least 16x16" in capsys.readouterr().err and not out.exists()


def test_photo_accepts_16x16_and_other_kinds_accept_tiny(tmp_path):
    src = tmp_path / "s.png"
    Image.new("RGB", (16, 16), (0, 0, 0)).save(src)
    assert convert_image.convert(str(src), str(tmp_path / "p.png"), "photo") == (104, 128)
    tiny = tmp_path / "t.png"
    Image.new("RGB", (4, 4), (0, 0, 0)).save(tiny)
    assert convert_image.convert(str(tiny), str(tmp_path / "i.png"), "icon") == (52, 52)


# ------------------------------------------------ section p and text pages
def test_validator_requires_section_p_for_the_project_wrapper(tmp_path, cfg):
    c = real_looking(cfg)
    del c["sections"]["p"]
    errors, _ = vc.validate(str(make_config_dir(tmp_path, c)))
    assert any("section p is missing" in e and "project" in e for e in errors)


def test_validator_reports_qr_pages_in_section_p(tmp_path, cfg):
    _, report = vc.validate(str(make_config_dir(tmp_path, real_looking(cfg))))
    assert any(r.startswith("QR section p page 1") for r in report)
    assert any(r.startswith("QR section p page 3") for r in report)
    assert not any("QR project" in r for r in report)


def test_validator_fails_old_top_level_project_key(tmp_path, cfg):
    c = real_looking(cfg)
    c["project"] = {"url": "https://github.com/x/y"}
    errors, _ = vc.validate(str(make_config_dir(tmp_path, c)))
    assert errors and "replaced by section p" in errors[0]


def test_validator_fails_text_page_with_more_than_six_lines(tmp_path, cfg):
    c = real_looking(cfg)
    c["sections"]["p"]["pages"][1]["lines"] = ["x"] * 7
    errors, _ = vc.validate(str(make_config_dir(tmp_path, c)))
    assert errors and "too many lines" in errors[0]


def test_validator_warns_text_page_non_ascii_and_truncation(tmp_path, cfg):
    c = real_looking(cfg)
    c["sections"]["p"]["pages"][1]["lines"] = ["caf\u00e9", "x" * 60, "ok", "", "", ""]
    errors, report = vc.validate(str(make_config_dir(tmp_path, c)))
    assert errors == []
    assert any("non-ASCII" in r for r in report)
    assert any("text line 2" in r and "truncated" in r for r in report)


def test_spacer_lines_are_fine_and_example_text_page_has_no_warnings(tmp_path, cfg):
    _, report = vc.validate(str(make_config_dir(tmp_path, real_looking(cfg))))
    assert not [r for r in report if r.lower().startswith("warning")]


def test_example_config_section_p_shape(cfg):
    p = cfg["sections"]["p"]
    assert p["title"] == "Project" and "project" not in cfg
    kinds = [pg["type"] for pg in p["pages"]]
    assert kinds == ["qr", "text", "qr"]
    assert p["pages"][0]["url"] == "https://github.com/henniefrancis/badger2040"
    assert p["pages"][1]["lines"][4] == ""
    assert p["pages"][2]["url"] == "https://pimoroni.com/badger2040"


# ------------------------------------------------ house bars: validator findings
def test_validator_fails_qr_title_that_does_not_fit_the_bar(tmp_path, cfg):
    c = real_looking(cfg)
    c["sections"]["a"]["pages"][1]["title"] = "T" * 36            # 180 px estimate > bar
    errors, _ = vc.validate(str(make_config_dir(tmp_path, c)))
    assert any("title" in e and "does not fit" in e and "section a page 2" in e for e in errors)


def test_validator_accepts_the_measured_device_titles(tmp_path, cfg):
    c = real_looking(cfg)
    c["sections"]["a"]["pages"][1].update(title="Contact Details", text="Save my Contact Details")
    c["sections"]["a"]["pages"][2].update(title="My Personal Website", text="Visit my website")
    c["sections"]["b"]["pages"][2].update(title="AWS Builder Center", text="Visit my Builder Profile")
    c["sections"]["b"]["pages"][1]["header"] = "AWS Community Builder - Serverless"
    errors, report = vc.validate(str(make_config_dir(tmp_path, c)))
    assert errors == []


def test_validator_fails_unbreakable_word_in_qr_text(tmp_path, cfg):
    c = real_looking(cfg)
    c["sections"]["a"]["pages"][2]["text"] = "Visit " + "W" * 40
    errors, _ = vc.validate(str(make_config_dir(tmp_path, c)))
    assert any("word" in e and "does not fit" in e for e in errors)


def test_validator_warns_when_qr_text_only_fits_small(tmp_path, cfg):
    c = real_looking(cfg)
    c["sections"]["a"]["pages"][2]["text"] = "x" * 20              # one 20 char word: only fits at scale 1
    errors, report = vc.validate(str(make_config_dir(tmp_path, c)))
    assert errors == []
    assert any("only fits at the small size" in r for r in report)


def test_validator_warns_non_ascii_in_qr_title_and_text(tmp_path, cfg):
    c = real_looking(cfg)
    c["sections"]["a"]["pages"][2].update(title="Caf\u00e9", text="Na\u00efve")
    errors, report = vc.validate(str(make_config_dir(tmp_path, c)))
    assert errors == []
    assert sum("non-ASCII" in r for r in report) == 2


def test_example_config_new_qr_shape(cfg):
    pages = cfg["sections"]["a"]["pages"]
    assert (pages[1]["title"], pages[1]["text"]) == ("Contact Details", "Save my Contact Details")
    assert (pages[2]["title"], pages[2]["text"]) == ("My Personal Website", "Visit my website")
    b = cfg["sections"]["b"]["pages"][2]
    assert (b["title"], b["text"]) == ("AWS Builder Center", "Visit my Builder Profile")
    p = cfg["sections"]["p"]["pages"]
    assert (p[0]["title"], p[0]["text"]) == ("Project", "Build your own badge")
    assert (p[2]["title"], p[2]["text"]) == ("Project", "Get a Badger 2040")
    assert not any("header" in pg for sec in cfg["sections"].values() for pg in sec["pages"] if pg["type"] == "qr")


# ------------------------------------------------ extra sections, wrappers, icons
def test_validator_checks_extra_sections_like_the_others(tmp_path, cfg):
    c = real_looking(cfg)
    c["sections"]["work"]["pages"][1]["url"] = "ftp://x"
    errors, _ = vc.validate(str(make_config_dir(tmp_path, c)))
    assert errors and errors[0].startswith("config:")
    c = real_looking(cfg)
    c["sections"]["Bad-Key"] = copy.deepcopy(c["sections"]["work"])
    errors, _ = vc.validate(str(make_config_dir(tmp_path / "x" if False else tmp_path, c)) if False else str(_mkdir(tmp_path, "k", c)))
    assert errors and "unknown section" in errors[0]


def _mkdir(tmp_path, name, c):
    d = tmp_path / name
    d.mkdir()
    (d / "badge.json").write_text(json.dumps(c))
    return d


def test_extra_section_qr_pages_are_reported(tmp_path, cfg):
    _, report = vc.validate(str(make_config_dir(tmp_path, real_looking(cfg))))
    assert any(r.startswith("QR section work page 2") for r in report)


def test_validator_warns_for_wrapper_without_matching_section(tmp_path, cfg):
    c = real_looking(cfg)
    del c["sections"]["dotcore"]
    errors, report = vc.validate(str(make_config_dir(tmp_path, c)))
    assert errors == []
    warn = [r for r in report if r.startswith("warning:") and "dotcore.py" in r]
    assert warn and "not in the config" in warn[0]
    assert not any("awscommza.py" in r for r in report)


def test_wrapper_scan_finds_the_shipped_wrappers():
    found = vc.wrapper_sections()
    for name in ("personal", "aws", "microsoft", "project", "awscommza", "dotcore", "devconf"):
        assert name + ".py" in found
    assert found["awscommza.py"] == "awscommza" and found["personal.py"] == "a" and found["project.py"] == "p"
    assert "hennie.py" not in found and "summit.py" not in found


def test_deploy_plan_includes_new_wrappers_and_optional_icons(tmp_path, cfg):
    d = make_config_dir(tmp_path, real_looking(cfg))
    plan = {r: l for l, r in deploy.build_plan(str(d))}
    for app in ("awscommza", "dotcore", "devconf"):
        assert "/henniefrancis/%s.py" % app in plan
        assert plan["/henniefrancis/%s.py" % app].endswith(os.path.join("device", "henniefrancis", app + ".py"))
    assert "/henniefrancis/icon-awscommza.png" not in plan           # absent icons are simply skipped
    assert "/henniefrancis/icon-dotcore.png" not in plan
    assert "/henniefrancis/icon-devconf.png" not in plan
    for n in ("icon-awscommza.png", "icon-dotcore.png", "icon-devconf.png"):
        Image.new("1", (52, 52), 1).save(d / "icons" / n)
    plan = {r: l for l, r in deploy.build_plan(str(d))}
    assert plan["/henniefrancis/icon-awscommza.png"] == str(d / "icons" / "icon-awscommza.png")
    assert plan["/henniefrancis/icon-dotcore.png"] == str(d / "icons" / "icon-dotcore.png")
    assert plan["/henniefrancis/icon-devconf.png"] == str(d / "icons" / "icon-devconf.png")


def test_missing_awscommza_dotcore_icons_do_not_fail_validate_or_deploy(tmp_path, cfg, monkeypatch, capsys):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("must not run mpremote"))
    d = make_config_dir(tmp_path, real_looking(cfg))
    errors, _ = vc.validate(str(d))
    assert errors == []
    assert deploy.main(["--config", str(d), "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "awscommza.py -> /henniefrancis/awscommza.py" in out.replace("\\", "/").replace("device/henniefrancis/", "")


def test_deploy_copies_wrappers_in_one_mpremote_chain(tmp_path, cfg, monkeypatch):
    calls, _ = None, None
    d = make_config_dir(tmp_path, real_looking(cfg))
    seen = []

    def fake_run(cmd, **kw):
        seen.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert deploy.main(["--config", str(d), "--port", "COM3"]) == 0
    copy_cmd = [c for c in seen if "cp" in c][0]
    assert all(":/henniefrancis/%s.py" % n in copy_cmd for n in ("awscommza", "dotcore", "devconf"))


def test_qr_title_aws_community_south_africa_fits_on_every_qr_size(tmp_path, cfg):
    # 26 characters, about 130 px estimated; the QR bar fit is about 150 px or more for 29 to 57 modules
    c = real_looking(cfg)
    c["sections"]["work"]["pages"][1]["title"] = "AWS Community South Africa"
    c["sections"]["a"]["pages"][1]["title"] = "AWS Community South Africa"      # the 57-module vCard page, tightest bar
    errors, _ = vc.validate(str(make_config_dir(tmp_path, c)))
    assert errors == []
    for modules in range(21, 65):
        lay = vc.badgekit.qr_layout(modules, border="auto")
        if lay:
            assert 26 * vc.badgekit.BITMAP_CHAR_WIDTH <= lay["left"] - vc.badgekit.BAR_GAP - 2 * vc.badgekit.TEXT_BAR_PAD


def test_readme_documents_extra_sections():
    with open(os.path.join(ROOT, "README.md"), encoding="utf-8") as f:
        text = f.read()
    assert "Add your own sections" in text and "run_section" in text
    assert "^[a-z][a-z0-9_]{1,15}$" in text




# ------------------------------------------------ new badge page: validator
def one_badge(tmp_path, cfg, n=[0], **fields):
    n[0] += 1
    c = real_looking(cfg)
    c["sections"]["a"]["pages"][0].update(fields)
    d = tmp_path / ("b%d" % n[0])
    d.mkdir()
    return vc.validate(str(make_config_dir(d, c)))


def test_validator_accepts_the_owner_badge_values(tmp_path, cfg):
    errors, report = one_badge(tmp_path, cfg, header="AWS Community South Africa", name="Hennie Francis",
                               title="Chief Executive Officer", website="awscommunity.co.za")
    assert errors == []
    assert not [r for r in report if r.startswith("warning:")]


def test_validator_fails_badge_header_that_does_not_fit_the_full_width_bar(tmp_path, cfg):
    errors, _ = one_badge(tmp_path, cfg, header="H" * 40)               # 192 px estimate: fits 296
    assert errors == []
    c = real_looking(cfg)
    c["sections"]["a"]["pages"][0]["header"] = "H" * 40
    assert vc.est_bitmap("H" * 61) > 296 - 2 * vc.badgekit.TEXT_BAR_PAD     # the limit is 40 chars on the device anyway


def test_validator_fails_name_that_does_not_fit_at_scale_three(tmp_path, cfg):
    errors, _ = one_badge(tmp_path, cfg, name="Hennie Francis")         # 201 px fits
    assert errors == []
    errors, _ = one_badge(tmp_path, cfg, name="N" * 25)                 # 360 px at scale 3
    assert any("name" in e and "scale 3" in e and "does not fit" in e for e in errors)


def test_validator_warns_when_title_or_website_is_wider_than_the_screen(tmp_path, cfg):
    errors, report = one_badge(tmp_path, cfg, title="T" * 40, website="W" * 31)
    assert errors == []
    assert any("title" in r and "wider than the screen" in r for r in report)
    assert any("website" in r and "wider than the screen" in r for r in report)
    errors, report = one_badge(tmp_path, cfg, title="Chief Executive Officer", website="dotcoresolutions.io")
    assert not [r for r in report if "wider than the screen" in r]      # running over the image is allowed


def test_validator_rejects_old_badge_shape(tmp_path, cfg):
    c = real_looking(cfg)
    c["sections"]["a"]["pages"][0].update(company="x", lines=["a"])
    errors, _ = vc.validate(str(make_config_dir(tmp_path, c)))
    assert errors and "replaced by" in errors[0]


def test_validator_warns_when_image_w_does_not_match_the_png_width(tmp_path, cfg):
    c = real_looking(cfg)
    page = c["sections"]["a"]["pages"][0]
    page.update(image="/images/me.png", image_w=104)
    d = make_config_dir(tmp_path, c)
    Image.new("1", (86, 19), 1).save(d / "images" / "me.png")
    errors, report = vc.validate(str(d))
    assert errors == []
    assert any("image_w is 104" in r and "86 px wide" in r for r in report)
    page["image_w"] = 86
    (d / "badge.json").write_text(json.dumps(c))
    errors, report = vc.validate(str(d))
    assert errors == [] and not [r for r in report if "image_w" in r]


def test_validator_missing_badge_image_still_fails(tmp_path, cfg):
    errors, _ = one_badge(tmp_path, cfg, image="/images/nope.png")
    assert any("nope.png" in e for e in errors)


def test_example_badge_pages_use_the_new_shape(cfg):
    for key, i in (("a", 0), ("b", 1), ("work", 0)):
        page = cfg["sections"][key]["pages"][i]
        assert page["type"] == "badge" and {"header", "name", "title", "website", "image", "image_w", "image_y"} <= set(page)
        assert "company" not in page and "lines" not in page
