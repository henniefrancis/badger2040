# badger2040

MicroPython scripts for the Pimoroni Badger 2040, a programmable e-ink conference badge.

The `henniefrancis` folder holds the badge layouts: `hennie.py` renders a personal name badge (name, title, company, and a QR code) on the e-ink display, `summit/summit.py` is a variant used for a summit event, and `hennie.png` is the badge image asset.

## Usage

Copy the scripts onto your Badger 2040 (for example with Thonny or the Pimoroni tooling) and run the badge script from the device. The scripts use the `badger2040`, `badger_os`, `jpegdec`, `pngdec`, and `qrcode` MicroPython modules that ship with the Pimoroni Badger firmware, so flash a recent Badger 2040 build first.

## License

Released under the MIT License. See LICENSE for details.
