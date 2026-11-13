# Badger 2040 section badge: build plan

Status: built and tested on a PC (host tests with fake hardware modules). On-device testing (rendering, memory, phone scans) is the next step. This document describes what was built.

## Summary

A set of apps on the Badger OS launcher. Inside the badge, A, B and C pick a section (Profile, Company, Event by default) and Up/Down page through that section, wrapping at the ends. All content comes from one JSON config. A **project** app is a fourth section (`p`) with a QR code to this repository (whose README teaches people to build their own), an about-this-badge text page, and a QR to the hardware. Personal details (the vCard) and trademarked logos are kept in a private location of your choice and copied to the badge by `tools/deploy.py`; they are never committed here.

## Decisions

| Topic | Decision |
|---|---|
| A, Profile | p1 photo badge, p2 vCard QR, p3 QR to a website |
| B, Company | p1 logo, p2 badge page with a header bar, p3 QR to a profile |
| C, Event | p1 logo, p2 QR to a schedule |
| vCard | vCard 3.0: N, FN, ORG, TITLE, TEL, EMAIL, URL (website), URL (LinkedIn). Text values escaped per RFC 2426; URL values are URIs so they are not text-escaped; control characters, DEL, C1 characters, U+2028 and U+2029 are stripped from every field |
| QR pages | QR as tall as fits with whole-pixel modules, at least 2 px per module, right aligned; a black house title bar and a centred body text only left of the code, never overlapping the code box (4 px gap); no page numbers |
| QR error correction | `qrcode.QRCode(qrcode.ECC_LOW)`. A 268-byte 7-field vCard is 65 modules at the default Medium (1 px per module, too small) and 57 modules at Low (2 px per module, 114 px) |
| QR border | optional top-level `"qr_border"`, default 0: no quiet-zone padding, so the code is as large as density allows (`px = 128 // modules`, centred vertically, right aligned; the title bar stops 4 px before it). 1 to 4 adds that many modules per side (the code may shrink); `"auto"` adds the largest border that keeps the same px per module. The 2 px minimum applies to the bordered size. ISO/IEC 18004 recommends a 4-module quiet zone; the owner chose full-size codes, tested scanning on the badge, and can raise `qr_border` if a scan fails (ADR-005) |
badge pages (full width, over the photo). Titles are never shrunk: the validator fails one that does not fit, and the device cuts with `..` only as a last resort. QR body text: whole bitmap8 scale 2, else 1, wrapped to the left area, centred horizontally and in the space below the bar |
| Extra sections | besides the required `a`, `b`, `c`, `p`, the config may hold sections whose keys match `^[a-z][a-z0-9_]{1,15}$`; a wrapper app with the same name opens one (`work` ships in the repo and the example config has a matching `work` section). A, B, C inside any section jump to a, b, c; Up/Down wrap (also for 2-page sections). A missing section shows the error page; the validator warns about a wrapper without a section |
| Text rendering | every page uses the bitmap8 font at whole scales only; no vector fonts. Title bars centre their text. Badge pages (fixed layout): clear to white; photo at x = 296 - `image_w`, y = `image_y`, no border; full-width black header bar (16 px) over the photo with the centred header; then black text left aligned at x 2 over the photo: name scale 3 at y 24, title scale 2 at y 92, website scale 2 at y 110; no divider. The validator fails a header or name that does not fit and warns about over-wide title or website text and an `image_w` that does not match the PNG |
| Paging | Up/Down wrap; a one-page section ignores them; a press that changes nothing causes no refresh |
| State | last section and page saved in `/state/badge.json` and restored on wake; the launcher's `running` entry follows the section |
| Return | A+C returns to the launcher (Badger OS convention) |
| Errors | missing or bad config, missing image, QR too dense, missing section: an on-screen error page, never a crash. Any button retries |
| Launcher | page 1 `profile`, `company`, `event`; page 2 `project`, `work`; then any other apps. `profile`, `company`, `event`, `project` and `work` are thin wrapper apps that open the shared code at a section, so launcher A, B and C match A, B and C inside the badge. Apps missing from the badge are skipped |
| Deploy state | after copying, deploy resets `/state/launcher.json` so the badge boots to launcher page 1 (`--keep-state` skips this) |
| Config on the badge | `/badge/config/badge.json`; shared code in `/lib/badgekit.py` (the launcher treats every .py in `/badge` as an app) |

## Architecture

```
 your private location                         this public repo
 +- badge.json  (real details)                 device/   (mirrors the badge filesystem)
 +- images/   company.png, event.png, ...         launcher.py
 +- icons/    icon-company.png, ...              lib/badgekit.py
          |                                      badge/{profile,company,event,project}.py
          |                                        + icon-{profile,company,event,project}.png (52x52)
          |                                      images/{me,company,event}.png (company, event are placeholders)
          v                                    config/badge.example.json (placeholders only)
   tools/deploy.py --config <folder>           tools/ deploy, validate_config, convert_image,
          |                                          qr_capacity, make_placeholders
          v                                    tests/ (pytest, fake badger2040 modules)
   Badger 2040 (mpremote over USB)             docs/, README.md, requirements.txt
```

The wrapper apps are three lines each: `import badgekit` then `badgekit.run_section("a")` (or `"b"`, `"c"`, `"p"`).

## Config shape

See `config/badge.example.json`. Top level: `sections` (`a`, `b`, `c`, `p`, all required, each with `title` and 1 to 8 `pages`; the old top-level `project` key is gone) and optional `qr_border` (0 to 4 or `"auto"`, default 0).

Page types: `badge` (`header` bar, `name`, optional `title` and `website`, `image`, optional `image_w` default 104 and `image_y` default 0; the old `company` and `lines` are gone), `image` (centred 1-bit PNG, full screen), `qr` (`url` or `vcard`, optional `title` and `text`; the old `header` list is gone), `text` (`header` title in a 16 px black bar, then up to 6 bitmap8 `lines`, 15 px apart, an empty string is a spacer, too-wide lines are cut with `..`). Image paths must be `/images/<name>.png`.

## Runtime flow

Load config, restore state, apply the wake button (unless the app was just opened from the launcher), draw, save state, then wait for buttons. On battery the board powers down after drawing and wakes on the next press; over USB it keeps listening. Refresh speed is `UPDATE_NORMAL` everywhere to avoid ghosting.

## Tooling

- `tools/validate_config.py`: structure, QR size per page (bytes, modules, border, px per module, px), images present, placeholder values and placeholder logos refused, warnings for text that will shrink or be cut, non-ASCII text, long QR headers.
- `tools/deploy.py`: validates, then copies a fixed list of files with `mpremote` (no shell). Old apps on the badge are left alone.
- `tools/convert_image.py`: logos (296x128), icons (52x52) and photos (104x128) to 1-bit PNG. `--kind photo` is the recommended badge-photo pipeline (tight crop, pad to 104:128, LANCZOS, autocontrast, unsharp, gamma 0.75, Floyd-Steinberg).
- `tools/make_placeholders.py`: regenerates the labelled placeholder logos and icons.

## Tech stack

MicroPython 1.23 with Pimoroni Badger OS v0.0.5 (`badger2040`, `badger_os`, `pngdec`, `qrcode`). Host: Python 3.11 or newer, `mpremote`, Pillow, pytest (pinned in `requirements.txt`). No cloud services and no network use on the badge.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| A vCard with all fields makes a dense QR | ECC_LOW; the validator and the badge refuse anything under 2 px per module (about 321 bytes without a border) |
| A phone will not scan a QR code | codes have no quiet zone by default; set `"qr_border"` to 2 or `"auto"` (the code shrinks; the validator reports the result) |
| vCard lines are not folded at 75 octets (RFC 2425 5.8.1) | known limitation; scanners accept it |
| Personal data leaks into the public repo | `.gitignore`, example-only config, tests that fail on a tracked real config or real-looking contact data |
| Trademarked logos | logos only in your private location; labelled placeholders in the repo; validate and deploy refuse to ship placeholders unless told to |
| Compiling `badgekit.py` uses too much memory on the badge | compile with `mpy-cross` and ship the `.mpy` (to be checked on the device) |

## Acceptance criteria

- A, B, C open page 1 of their section; Up/Down move within it and wrap.
- After power-off and wake, the last viewed page is restored.
- Every QR page: as tall as fits, flush right, at least 2 px per module, title bar and text never overlap the code, scans on iOS and Android (confirm on the device, and raise `qr_border` if a phone will not scan).
- The vCard QR imports as a contact with all fields.
- No personal contact data and no real logo files in the public repo.
- A+C returns to the launcher; the existing apps still work; the launcher shows the owner-defined order.

## Privacy note

Everything in `badge.json`, including the vCard, is plain text on the badge and readable by anyone who plugs the badge into USB. Only put business-card-level details on it, and wipe the badge before lending or disposing of it.
