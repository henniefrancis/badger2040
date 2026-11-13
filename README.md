# badger2040: a section badge for the Pimoroni Badger 2040

A conference badge for the [Pimoroni Badger 2040](https://shop.pimoroni.com/products/badger-2040) e-ink badge. Three buttons pick a section (for example Personal, AWS, Microsoft). Up and Down page through the section. A page can be a photo badge, a full-screen logo, or a QR code (a website, or a vCard that adds you to someone's contacts).

All content comes from one JSON file. Your real details and logos stay in a private place and are copied to the badge by one command, so this public repo holds no personal data.

![vCard QR page mock-up](docs/images/vcard-preview.svg)

(The mock-up uses placeholder text only.)

## What you get

| Button | Opens | Pages (Up/Down, wraps around) |
|---|---|---|
| A | Personal | photo badge, vCard QR, website QR |
| B | AWS | logo, Builder badge, profile QR |
| C | Microsoft | logo (one page, Up/Down do nothing) |

The **Project** app (launcher page 2) is a fourth section, `p`: QR to this repo, an about page, and a QR to the hardware. It pages with Up/Down like the others, and A, B, C inside it jump to Personal, AWS, Microsoft.

The launcher order is chosen by the badge owner and is set in `device/launcher.py`: page 1 is Personal, AWS, AWS Community (`awscommza`); page 2 is **Project** (section `p`, which starts with a QR code to this repo), `devconf` and `dotcore`; page 3 is Microsoft; any other apps follow. Apps that are not on the badge are skipped. So **launcher C on page 1 opens `awscommza`, while C inside the badge still means Microsoft.** Everything you can change is in the JSON config.

QR pages: the QR code is as tall as the screen allows, with whole-pixel modules (at least 2 px, so phones scan it), right-aligned. A black title bar runs across the top of the left area and stops 4 px before the code and its border, and a short body text is centred in the space below the bar.

## Hardware and software

- Pimoroni Badger 2040 (the RP2040 model, 296x128 e-ink)
- USB cable
- Badger OS **v0.0.5** (MicroPython 1.23.0)
- A PC with Python 3.11 or newer

## 1. Flash Badger OS v0.0.5

1. Download the Badger 2040 `v0.0.5` release `.uf2` from [pimoroni/badger2040 releases](https://github.com/pimoroni/badger2040/releases).
2. Hold the BOOT/USR button on the back, plug in USB (or press RESET while holding BOOT), and a drive called `RPI-RP2` appears.
3. Drag the `.uf2` onto that drive. The badge restarts into the launcher.

## 2. Install the tools

```
git clone https://github.com/henniefrancis/badger2040.git
cd badger2040
python -m venv .venv
.venv\Scripts\activate            # Windows. On macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

`requirements.txt` pins exact versions. `mpremote` copies files to the badge, Pillow converts images, pytest runs the tests.

## 3. Make your private config

Keep your real config **outside** this repo (for example in a private repo or a private folder).

```
mkdir <private-folder>        (a private location of your choice)
copy config\badge.example.json <private-folder>\badge.json
```

Edit `badge.json`. The shape:

```json
{
  "sections": {
    "a": {"title": "Personal", "pages": [
      {"type": "badge", "header": "Welcome", "name": "Your Name", "title": "Your title", "website": "example.com",
       "image": "/images/hennie.png", "image_w": 108, "image_y": 0},
      {"type": "qr", "title": "Contact Details", "text": "Save my Contact Details", "vcard": {"name": "Your Name", "title": "", "company": "",
        "email": "", "phone": "", "url": "", "linkedin": ""}},
      {"type": "qr", "title": "My Personal Website", "text": "Visit my website", "url": "https://example.com"}
    ]},
    "b": {"title": "AWS", "pages": [{"type": "image", "image": "/images/aws.png"}]},
    "c": {"title": "Microsoft", "pages": [{"type": "image", "image": "/images/microsoft.png"}]},
    "p": {"title": "Project", "pages": [
      {"type": "qr", "title": "Project", "text": "Build your own badge", "url": "https://github.com/henniefrancis/badger2040"},
      {"type": "text", "header": "About this badge", "lines": ["Made by Pimoroni", "", "https://pimoroni.com/badger2040"]}
    ]}
  }
}
```

- Sections are `a`, `b`, `c` (the A, B, C buttons) and `p` (the Project app on the launcher). All four are required. Each has a `title` (max 20 characters) and 1 to 8 `pages`. Inside any section Up/Down page and wrap, and A, B, C jump to Personal, AWS, Microsoft. The old top-level `"project"` key is gone; use section `p`.
- Page types: `badge` (a photo at the right edge with a black `header` bar across the top, then `name`, and optional `title` and `website`, drawn over the photo; see "Badge pages" below), `image` (full-screen 1-bit PNG), `qr` (either `url` or `vcard`; optional `title` for the bar, falling back to the section title, max 40 characters; optional `text` body, max 60 characters; the old `header` list is gone), `text` (a `header` title in a black bar, then up to 6 `lines` in the small bitmap font, 15 px apart; an empty string is a spacer; lines that are too wide are cut with `..`).
- **Title bars** look the same on every page type: a black bar 16 px high with white small-font text, centred in the bar (`text` pages across the screen, `qr` pages left of the code, `badge` pages across the full width over the photo). Bar text is never shrunk; the validator fails a title or header that will not fit. QR body text uses the largest whole size (2, then 1) at which every word fits, centred in the left area. Text must not contain control characters.
- The vCard is vCard 3.0 with `name`, `title`, `company`, `email`, `phone`, `url` (website) and `linkedin`. Special characters are escaped for you. Leave a field empty to skip it.
- Image paths are paths on the badge and must be `/images/<name>.png`; the file is taken from `images/<name>.png` in your private folder.
- `qr_border` (optional, top level) sets a quiet-zone border around every QR code, in modules per side. The default is `0` (no padding), so the black code is as large as its density allows: `128 // modules` pixels per module, centred vertically and right-aligned. A whole number 1 to 4 adds that border, which may shrink the code; `"auto"` adds the largest border (0 to 4) that does **not** shrink the code. The validator prints modules, the border, px per module and the code px size for every QR page, and fails if one would drop under 2 px per module (a 57-module vCard is capped at 2 px, 114 px, by its density; forcing border 4 does not fit).
- Text is ASCII only (the fonts have no accented characters). All text uses the crisp built-in bitmap font at whole sizes only (no vector fonts). See "Badge pages" for how badge text is placed; text-page lines are cut with `..`, QR body text uses the largest whole size that fits. detail lines are always the small size and cut with `..` if too wide; text-page lines are cut with `..`. The validator warns about both.

### Add your own sections

Besides the required sections `a`, `b`, `c` and `p`, `badge.json` may hold extra sections. A key must match `^[a-z][a-z0-9_]{1,15}$` (for example `work`), and the example config has one called `work`. An extra section is validated like the others, pages with Up/Down and wraps around (a two-page section loops back to page 1), and A, B, C inside it jump to Personal, AWS, Microsoft.

A section is opened by a small wrapper app with the same name. To add one:

1. Create `device/henniefrancis/<key>.py` with `import badgekit` and `badgekit.run_section("<key>")` (copy `personal.py` and change the key).
2. Add the app name to `APPS` in `tools/deploy.py` and to `SECTION_APPS` in `device/launcher.py` (and to the order lists there if you want it on a specific launcher page).
3. Optionally add `icon-<key>.png` (52x52, see `--kind icon`) to your private `icons/` folder.

The repo ships wrappers named `awscommza` and `dotcore`; they open sections of those names and show an error page if your config does not have them (the validator warns). Deploy overwrites older apps of the same name on the badge, so back the badge up first. Icons for these two come only from your private `icons/` folder and are skipped if absent.

### Badge pages

A `badge` page is `{"type": "badge", "header": "<bar text>", "name": "<name>", "title": "<optional>", "website": "<optional>", "image": "/images/x.png", "image_w": <width>, "image_y": <y>}` (`image_w` defaults to 104, `image_y` to 0; the older `company` and `lines` keys are gone). The layout is fixed, white background, no border or divider, bitmap font at whole sizes only:

1. The photo is drawn at the right edge, x = 296 - `image_w`, y = `image_y`. Make the PNG exactly `image_w` pixels wide (the badge cannot scale an image down; `tools/convert_image.py --kind photo` makes 104x128). The validator warns when `image_w` does not match the file.
2. A full-width black bar, 16 px high, over the top of the photo, with the `header` centred in white.
3. Black text, left aligned at x 2, over the photo: the `name` at size 3 (y 24), the `title` at size 2 (y 92) and the `website` at size 2 (y 110). `title` and `website` may run over the photo.

The validator fails a `header` or `name` that will not fit (name at size 3 must fit the screen width: about 20 characters) and warns when a `title` or `website` is wider than the screen. On the device, over-wide text steps down a whole size and is then cut with `..` so it never leaves the screen.

**Privacy:** everything in `badge.json` (including the vCard) is stored as plain text on the badge, and anyone who plugs the badge into USB can read it. Only put business-card-level details on it, and wipe the badge (re-flash Badger OS, or delete `/henniefrancis/config/badge.json` and `/state`) before you lend it, sell it or throw it away.

Validate it any time (no badge needed):

```
python tools\validate_config.py <private-folder>
```

The validator prints each QR code's size and refuses any QR that would be smaller than 2 px per module (more than 64 modules, roughly 320 bytes at error correction L). A vCard with all 7 fields of normal length is about 57 to 61 modules.

## 4. Convert your own logos

Use **your own** logos and trademarks, or ones you are licensed to use. This repo ships clearly-labelled placeholder images in `device/images/` and icons in `device/henniefrancis/` so the badge runs out of the box; replace them with yours.

```
python tools\convert_image.py my-aws-logo.png <private-folder>\images\aws.png --kind logo
python tools\convert_image.py my-aws-logo.png <private-folder>\icons\icon-aws.png --kind icon
python tools\convert_image.py my-photo.jpg <private-folder>\images\me.png --kind photo
```

| Kind | Size | Used for |
|---|---|---|
| `logo` | 296x128, centred on white | full-screen `image` pages |
| `icon` | 52x52 | launcher icons (`icon-personal`, `icon-aws`, `icon-microsoft`, `icon-project`) |
| `photo` | 104x128 | **recommended** for the photo on a `badge` page: tight crop, contrast, sharpen, brighten, Floyd-Steinberg dithering |
| `badge` | 104x128 | the same slot, plain fit and threshold (no tuning) |

All output is 1-bit PNG. The converter refuses a result that is entirely white (for example a fully transparent input) unless you pass `--allow-blank`, and it stops with a one-line error on corrupt or oversized images.

Files in your private `images/` and `icons/` folders replace the placeholders of the same name. Validation and deploy **fail** if a logo or launcher icon you reference would fall back to a repo placeholder (`aws.png`, `microsoft.png`, `icon-aws.png`, `icon-microsoft.png`, `icon-project.png`). For a first trial with placeholders, pass `--allow-placeholder-images` (it prints a warning).

## 5. Deploy

Take a backup first (see "Restore" below). Then, with the badge plugged in:

```
python tools\deploy.py --config <private-folder> --port COM3
```

Use `--dry-run` to see the file list without touching the badge. The script validates your config, then copies only these files and nothing else:

- `launcher.py`, `lib/badgekit.py`
- `henniefrancis/personal.py`, `aws.py`, `microsoft.py`, `project.py` and their icons
- `images/*.png`
- a reset launcher state (`/state/launcher.json`) so the badge boots to launcher page 1 instead of re-opening the last app (skip with `--keep-state`)
- your `badge.json` to `/henniefrancis/config/badge.json`

It refuses to deploy a config that is still the example text values (override with `--allow-placeholders`) or one that would use placeholder logos (see above). Your older apps on the badge are left alone.

## Known limitations

- vCard lines are not folded at 75 octets (RFC 2425 section 5.8.1). Phone scanners accept this; strict parsers may not.
- Button presses made while the screen is refreshing are dropped.

## Troubleshooting

- **A phone will not scan a QR code:** the codes are full size with no quiet zone by default. Set `"qr_border": 2` (or `"auto"`) in `badge.json` to add a quiet zone around the code (ISO/IEC 18004 recommends 4 modules; the code gets smaller), validate, and deploy again. If validation says the code gets too small, shorten the vCard (fewer or shorter fields).
- **Error page on the badge:** it names the problem (missing or invalid config, missing image, QR too dense). Fix the config, deploy, and press any button.
- **Validation says a logo or icon would use a placeholder:** put your own file in `images/` or `icons/` in your private folder (see "Convert your own logos").

## Buttons

| Button | In a section |
|---|---|
| A, B, C | open that section, page 1 |
| Up | previous page (wraps from the first page to the last) |
| Down | next page (wraps from the last page to the first) |
| A + C together | back to the launcher |

The badge remembers the section and page it was on. The e-ink screen holds the image with no power, so the badge is usually off. When you press a button on battery it wakes, shows the page you pressed for, and powers down again. Over USB it stays awake and keeps listening for buttons.

If the config is missing or wrong, the badge shows an error page naming the problem instead of crashing. Fix the config, deploy again, and press any button.

## Restore from a backup

Before you change a badge, copy its files to your PC (Thonny's file browser works, or `python -m mpremote connect COM3 fs cp -r :images backup/files/` for each folder, and `fs cp :launcher.py backup/files/` for single files).

To put single files back: `python -m mpremote cp backup\files\launcher.py :launcher.py`.

For a bit-for-bit restore (firmware and files), dump the whole 2 MB flash before you start and keep the `.uf2`. To restore, hold BOOT/USR, plug in USB, and drag that `.uf2` onto the `RPI-RP2` drive.

## Develop and test

```
python -m pytest -q tests
```

The tests run on a PC against fake `badger2040`, `badger_os`, `pngdec` and `qrcode` modules in `tests/fakes/`. They cover config validation, vCard escaping, QR sizing, paging and wrap-around, state restore, error pages, the validator, the image converter, and the deploy planner. They also fail if `config/badge.json` is ever tracked or the example contains anything that looks like a real email or phone number.

Layout:

```
device/            mirrors the badge filesystem
  launcher.py      Badger OS launcher (owner-defined order, see above)
  lib/badgekit.py  shared drawing, config, paging and state code
  henniefrancis/   one small wrapper app per launcher entry, plus the older badges
  images/          placeholder logos and the sample photo
config/            badge.example.json (placeholders only)
tools/             deploy.py, validate_config.py, convert_image.py
tests/             pytest suite and fakes
docs/              build plan
```

The older `hennie.py` and `summit.py` badges are kept as they were.

## License

MIT. See LICENSE. Parts are based on Pimoroni's MIT-licensed Badger 2040 code, see THIRD_PARTY_NOTICES.md. Logos and trademarks you add are yours or their owners'; this project does not license them.

AWS, Microsoft and GitHub are trademarks of their respective owners. This project is not affiliated with or endorsed by them.
