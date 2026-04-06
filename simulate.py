#!/usr/bin/python3
"""
simulate.py - renders btcticker2in13g display output without Raspberry Pi hardware.

Usage:
    python3 simulate.py                   # rising price, all orientations
    python3 simulate.py --falling         # falling price scenario
    python3 simulate.py --orientation 90  # single orientation
    python3 simulate.py --coin ethereum --fiat eur
"""

import sys
import types
import math
import random
import argparse
import os
from PIL import Image, ImageDraw

# ---------------------------------------------------------------------------
# Mock hardware modules before importing btcticker2in13g
# ---------------------------------------------------------------------------

def _make_gpio_mock():
    gpio = types.ModuleType("RPi.GPIO")
    for attr in ("BCM", "IN", "PUD_UP", "FALLING"):
        setattr(gpio, attr, 0)
    for fn in ("setmode", "setup", "add_event_detect", "remove_event_detect", "cleanup"):
        setattr(gpio, fn, lambda *a, **kw: None)
    rpi = types.ModuleType("RPi")
    rpi.GPIO = gpio
    sys.modules["RPi"] = rpi
    sys.modules["RPi.GPIO"] = gpio

def _make_epd_mock():
    class MockEPD:
        width = 122
        height = 250
        def init(self): pass
        def display(self, buf): pass
        def sleep(self): pass
        def getbuffer(self, img): return None
        class epdconfig:
            @staticmethod
            def module_exit(): pass

    epd_mod = types.ModuleType("waveshare_epd.epd2in13g")
    epd_mod.EPD = MockEPD
    wrapper = types.ModuleType("waveshare_epd")
    wrapper.epd2in13g = epd_mod
    sys.modules["waveshare_epd"] = wrapper
    sys.modules["waveshare_epd.epd2in13g"] = epd_mod

def _make_currency_mock():
    mod = types.ModuleType("currency")
    mod.symbol = lambda x: "$"
    sys.modules["currency"] = mod

_make_gpio_mock()
_make_epd_mock()
_make_currency_mock()

import btcticker2in13g  # noqa: E402 - must come after mocks

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PICDIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "images")


def make_placeholder_token(coin):
    """Create a simple grey placeholder BMP if no real token image exists."""
    path = os.path.join(PICDIR, "currency", coin + ".bmp")
    if not os.path.isfile(path):
        img = Image.new("RGB", (100, 100), (200, 200, 200))
        draw = ImageDraw.Draw(img)
        draw.rectangle([10, 10, 89, 89], outline=(100, 100, 100), width=3)
        label = coin[:3].upper()
        draw.text((28, 38), label, fill=(60, 60, 60))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        img.save(path)


def synthetic_prices(base, n=288, rising=True):
    """Generate a plausible-looking price series of length n."""
    random.seed(42)
    prices = []
    drift = base * 0.03 if rising else -base * 0.03  # ~3% total move
    for i in range(n):
        noise = random.gauss(0, base * 0.003)
        trend = drift * (i / n)
        wave = base * 0.005 * math.sin(i / 20)
        prices.append(base + trend + wave + noise)
    return prices


def build_config(coin, fiat, orientation, inverted=False):
    return {
        "display": {
            "cycle": False,
            "cyclefiat": False,
            "inverted": inverted,
            "orientation": orientation,
            "trendingmode": False,
            "showvolume": True,
            "showrank": True,
            "24h": True,
            "locale": "en_US",
        },
        "ticker": {
            "currency": coin,
            "exchange": "default",
            "fiatcurrency": fiat,
            "sparklinedays": 1,
            "updatefrequency": 300,
        },
    }


def render(coin, fiat, orientation, pricestack, other, inverted=False):
    config = build_config(coin, fiat, orientation, inverted)
    positive_change = pricestack[-1] >= pricestack[0]
    btcticker2in13g.makeSpark(pricestack, positive_change)
    return btcticker2in13g.updateDisplay(config, pricestack, other)


def compose_grid(images, labels):
    """Lay out images in a row with labels underneath, on a light grey canvas."""
    padding = 16
    label_height = 20
    cell_w = max(img.size[0] for img in images)
    cell_h = max(img.size[1] for img in images)
    total_w = (cell_w + padding) * len(images) + padding
    total_h = cell_h + label_height + padding * 2

    canvas = Image.new("RGB", (total_w, total_h), (180, 180, 180))
    from PIL import ImageFont
    try:
        font = ImageFont.truetype(
            os.path.join(os.path.dirname(__file__), "fonts/googlefonts/PixelSplitter-Bold.ttf"), 11
        )
    except Exception:
        font = ImageFont.load_default()

    draw = ImageDraw.Draw(canvas)
    for i, (img, label) in enumerate(zip(images, labels)):
        x = padding + i * (cell_w + padding)
        y = padding
        # Centre smaller images in their cell
        x_off = (cell_w - img.size[0]) // 2
        y_off = (cell_h - img.size[1]) // 2
        canvas.paste(img, (x + x_off, y + y_off))
        draw.text((x + x_off, y + cell_h + 4), label, font=font, fill=(40, 40, 40))

    return canvas


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Simulate btcticker2in13g display output")
    parser.add_argument("--falling", action="store_true", help="Show falling price scenario")
    parser.add_argument("--orientation", type=int, choices=[0, 90, 180, 270],
                        help="Render a single orientation (default: all four)")
    parser.add_argument("--coin", default="bitcoin", help="CoinGecko coin ID (default: bitcoin)")
    parser.add_argument("--fiat", default="usd", help="Fiat currency (default: usd)")
    parser.add_argument("--inverted", action="store_true", help="Simulate inverted display")
    parser.add_argument("--alert", metavar="TEXT", help="Simulate a TradingView alert screen instead of price")
    parser.add_argument("--output", default="simulation.png", help="Output filename (default: simulation.png)")
    args = parser.parse_args()

    if args.orientation is not None:
        orientations = [args.orientation]
    else:
        orientations = [0, 90, 180, 270]

    if args.alert:
        images, labels = [], []
        for o in orientations:
            cfg = build_config(args.coin, args.fiat, o, args.inverted)
            img = btcticker2in13g.render_alert(args.alert, cfg)
            images.append(img)
            labels.append(f"{o}°")
            print(f"  alert orientation={o}°  size={img.size}")
    else:
        make_placeholder_token(args.coin)

        base_price = 65000 if args.coin == "bitcoin" else 3200
        pricestack = synthetic_prices(base_price, rising=not args.falling)

        other = {
            "ATH": False,
            "market_cap_rank": 1,
            "volume": 28_500_000_000,
        }

        images, labels = [], []
        for o in orientations:
            img = render(args.coin, args.fiat, o, pricestack, other, args.inverted)
            images.append(img)
            labels.append(f"{o}°")
            print(f"  orientation={o}°  size={img.size}")

    if len(images) == 1:
        out = images[0]
    else:
        out = compose_grid(images, labels)

    out.save(args.output)
    print(f"\nSaved → {args.output}")


if __name__ == "__main__":
    main()
