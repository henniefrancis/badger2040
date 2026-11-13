"""Guards for a public repo: no real config, no personal contact data, MicroPython-safe device code."""
import json
import os
import re
import shutil
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLE = os.path.join(ROOT, "config", "badge.example.json")

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")
PHONE_RE = re.compile(r"\+?\d[\d ()-]{6,}\d")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
SAFE_EMAIL_DOMAINS = ("example.com", "example.org", "example.net")
TEXT_EXT = (".py", ".md", ".json", ".yaml", ".yml", ".toml", ".cfg", ".ini", ".txt", ".csv",
            ".html", ".svg", ".xml", ".gitignore", ".gitattributes")
PHONE_EXT = (".json", ".md", ".yaml", ".yml", ".txt", ".csv", ".toml", ".cfg", ".ini")
BINARY_BAD = (".bin", ".uf2")
SKIP_DIRS = {".git", ".venv", "__pycache__", ".pytest_cache", ".claude"}

have_git = shutil.which("git") is not None and os.path.isdir(os.path.join(ROOT, ".git"))


def git(*args):
    return subprocess.run(["git", "-C", ROOT] + list(args), capture_output=True, text=True)


def repo_text_files():
    """Files that would be committed: tracked plus untracked-but-not-ignored."""
    if have_git:
        names = git("ls-files").stdout.split() + git("ls-files", "--others", "--exclude-standard").stdout.split()
        paths = [os.path.join(ROOT, n) for n in names]
    else:
        paths = []
        for base, dirs, files in os.walk(ROOT):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            paths += [os.path.join(base, f) for f in files]
    return [p for p in paths if os.path.isfile(p) and p.lower().endswith(TEXT_EXT)]


@pytest.mark.skipif(not have_git, reason="needs a git checkout")
def test_real_config_is_not_tracked_and_is_ignored():
    tracked = git("ls-files").stdout.split()
    assert "config/badge.json" not in tracked
    assert not [t for t in tracked if t.endswith("/badge.json") or t == "badge.json"]
    assert git("check-ignore", "-q", "config/badge.json").returncode == 0
    assert git("check-ignore", "-q", "config/images/aws.png").returncode == 0


def test_real_config_file_is_not_in_the_working_tree_by_accident():
    # Fine to exist locally (it is gitignored), but it must never be one of the committable files.
    committable = [os.path.relpath(p, ROOT).replace(os.sep, "/") for p in repo_text_files()]
    assert "config/badge.json" not in committable


def test_example_has_only_placeholder_contact_data():
    with open(EXAMPLE, encoding="utf-8") as f:
        raw = f.read()
    for email in EMAIL_RE.findall(raw):
        assert email.lower().endswith(SAFE_EMAIL_DOMAINS), "looks like a real email: " + email
    for phone in PHONE_RE.findall(raw):
        digits = re.sub(r"\D", "", phone)
        assert set(digits) == {"0"}, "looks like a real phone number: " + phone
    vcard = json.loads(raw)["sections"]["a"]["pages"][1]["vcard"]
    assert vcard["email"].endswith(SAFE_EMAIL_DOMAINS)
    assert set(re.sub(r"\D", "", vcard["phone"])) == {"0"}
    assert vcard["name"] == "Your Name"


def test_no_real_looking_emails_or_phones_anywhere_in_committable_files():
    offenders = []
    for p in repo_text_files():
        rel = os.path.relpath(p, ROOT).replace(os.sep, "/")
        if rel.startswith("tests/"):
            continue
        with open(p, encoding="utf-8", errors="replace") as f:
            text = f.read()
        for email in EMAIL_RE.findall(text):
            if not email.lower().endswith(SAFE_EMAIL_DOMAINS) and "users.noreply.github.com" not in email:
                offenders.append((os.path.relpath(p, ROOT), email))
        if p.endswith(PHONE_EXT):
            for phone in PHONE_RE.findall(text):
                if set(re.sub(r"\D", "", phone)) != {"0"} and not DATE_RE.match(phone):
                    offenders.append((os.path.relpath(p, ROOT), phone))
    assert offenders == []


def test_no_linkedin_profile_url_with_real_handle():
    for p in repo_text_files():
        with open(p, encoding="utf-8", errors="replace") as f:
            text = f.read()
        for handle in re.findall(r"linkedin\.com/in/([A-Za-z0-9_%-]+)", text):
            assert handle in ("your-handle", "jroe"), "%s: %s" % (p, handle)


def test_device_code_is_micropython_friendly():
    banned = [r"\bimport typing\b", r"\bfrom typing\b", r"\bdataclass", r"\{[^{}]*=\s*\}", r"\basyncio\b",
              r"\bpathlib\b", r"\bre\.", r"\bimport re\b"]
    device = os.path.join(ROOT, "device")
    for base, _, files in os.walk(device):
        for n in files:
            if not n.endswith(".py") or n in ("hennie.py", "summit.py"):
                continue
            path = os.path.join(base, n)
            with open(path, encoding="utf-8") as f:
                text = f.read()
            for pat in banned:
                assert not re.search(pat, text), "%s matches %s" % (path, pat)
            compile(text, path, "exec")   # must at least be valid Python


def test_wrapper_apps_only_call_badgekit():
    apps = os.path.join(ROOT, "device", "henniefrancis")
    expect = {"personal": 'run_section("a")', "aws": 'run_section("b")',
              "microsoft": 'run_section("c")', "project": 'run_section("p")',
              "awscommza": 'run_section("awscommza")', "dotcore": 'run_section("dotcore")',
              "devconf": 'run_section("devconf")'}
    for name, call in expect.items():
        with open(os.path.join(apps, name + ".py"), encoding="utf-8") as f:
            text = f.read()
        assert "import badgekit" in text and call in text


def test_launcher_order_is_owner_defined():
    with open(os.path.join(ROOT, "device", "launcher.py"), encoding="utf-8") as f:
        text = f.read()
    assert 'first_page = ["personal", "aws", "awscommza"]' in text
    assert 'second_page = ["project", "devconf", "dotcore"]' in text
    assert 'third_page = ["microsoft"]' in text
    assert 'APP_DIR = "/henniefrancis"' in text
    assert '"microsoft": "c"' in text and '"aws": "b"' in text and '"personal": "a"' in text
    assert '"project": "p"' in text
    assert '"awscommza": "awscommza"' in text and '"dotcore": "dotcore"' in text and '"devconf": "devconf"' in text
    ordering = text[text.index("first_page ="):text.index("# Section apps")]
    for gone in ("hennie", "summit", "clock", "help", "image"):
        assert '"%s"' % gone not in ordering
    assert "[x for x in ordered if x in all_files]" in text          # missing apps are skipped
    assert "launcher C" in text and "awscommza" in text               # the C difference is documented


def test_launcher_order_logic_with_missing_and_extra_apps():
    with open(os.path.join(ROOT, "device", "launcher.py"), encoding="utf-8") as f:
        text = f.read()
    code = text[text.index("first_page ="):text.index("# Section apps")]
    ns = {"all_files": ["socials", "info", "personal", "aws", "awscommza", "microsoft", "project", "devconf", "hennie"]}
    exec(code, ns)
    assert ns["henniefrancis"] == ["personal", "aws", "awscommza", "project", "devconf", "microsoft",
                                   "socials", "info", "hennie"]


def test_readme_and_plan_document_launcher_c_difference():
    for rel in ("README.md", "docs/build-plan.md"):
        with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
            text = f.read()
        assert "awscommza" in text and "Microsoft" in text and "C" in text
        assert "launcher C" in text, rel


# ---- restored (dropped by mistake when the launcher-order test was rewritten)
def committable_files():
    if have_git:
        names = git("ls-files").stdout.split() + git("ls-files", "--others", "--exclude-standard").stdout.split()
        return [n.replace("\\", "/") for n in names]
    out = []
    for base, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        out += [os.path.relpath(os.path.join(base, f), ROOT).replace(os.sep, "/") for f in files]
    return out


def test_no_flash_dumps_or_firmware_images_committable():
    bad = [n for n in committable_files()
           if n.lower().endswith(BINARY_BAD) or os.path.basename(n).lower().startswith("flash-dump")]
    assert bad == []


def test_gitignore_blocks_dumps_and_firmware():
    with open(os.path.join(ROOT, ".gitignore"), encoding="utf-8") as f:
        rules = [ln.strip() for ln in f if ln.strip() and not ln.startswith("#")]
    for rule in ("*.uf2", "*.bin", "flash-dump*"):
        assert rule in rules


@pytest.mark.skipif(not have_git, reason="needs a git checkout")
@pytest.mark.parametrize("name", ["x.uf2", "badger2040-full-flash.bin", "flash-dump-1.img", "dump/flash-dump.txt",
                                  "config/badge.json", "config/images/aws.png", "config/icons/icon-aws.png"])
def test_git_ignores_sensitive_names(name):
    assert git("check-ignore", "-q", name).returncode == 0


def test_summit_has_no_third_party_email():
    with open(os.path.join(ROOT, "device", "henniefrancis", "summit.py"), encoding="utf-8", errors="replace") as f:
        assert not EMAIL_RE.findall(f.read())


def test_public_docs_have_no_private_names_or_local_paths():
    forbidden = ["github.com/henniefrancis/config", "hft-config", "A:\\", "G:\\", "C:\\Users", "C:\\private",
                 "Obsidian", "OneDrive"]
    for rel in ("README.md", "docs/build-plan.md", "THIRD_PARTY_NOTICES.md"):
        with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
            text = f.read()
        for bad in forbidden:
            assert bad not in text, "%s mentions %s" % (rel, bad)


def test_pimoroni_notice_on_derived_files():
    for rel in ("device/launcher.py", "device/henniefrancis/hennie.py", "device/henniefrancis/summit.py"):
        with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
            head = f.read(400)
        assert "Copyright (c) Pimoroni Ltd" in head and "MIT" in head, rel
    with open(os.path.join(ROOT, "THIRD_PARTY_NOTICES.md"), encoding="utf-8") as f:
        text = f.read()
    assert "https://github.com/pimoroni/badger2040" in text and "MIT" in text


def test_readme_documents_qr_border_troubleshooting():
    with open(os.path.join(ROOT, "README.md"), encoding="utf-8") as f:
        text = f.read()
    assert "qr_border" in text and '"qr_border": 2' in text


def test_launcher_clamps_saved_page_after_max_page():
    with open(os.path.join(ROOT, "device", "launcher.py"), encoding="utf-8") as f:
        text = f.read()
    start = text.index("MAX_PAGE = math.ceil")
    snippet = text[start:text.index("WIDTH = 296")]
    for saved, expect in ((0, 0), (1, 1), (2, 2), (3, 0), (99, 0), (-1, 0), ("2", 0), (None, 0), (True, 0), (False, 0)):
        ns = {"math": __import__("math"), "henniefrancis": ["a"] * 8, "state": {"page": saved}}   # 8 apps -> 3 pages
        exec(snippet, ns)
        assert ns["MAX_PAGE"] == 3 and ns["state"]["page"] == expect, saved
    ns = {"math": __import__("math"), "henniefrancis": ["a"] * 3, "state": {"page": 1}}            # apps deleted: 1 page
    exec(snippet, ns)
    assert ns["state"]["page"] == 0


def test_public_repo_has_no_owner_org_content_in_example_config():
    with open(os.path.join(ROOT, "config", "badge.example.json"), encoding="utf-8") as f:
        text = f.read().lower()
    for bad in ("awscommunity.co.za", "dotcoresolutions", "dotcore solutions", "south africa"):
        assert bad not in text
