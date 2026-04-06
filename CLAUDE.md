# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A Raspberry Pi Python script that displays cryptocurrency prices on a Waveshare ePaper display. It fetches data from the CoinGecko API and renders a sparkline chart with price, change percentage, and optional volume/rank info.

## Running the Script

```bash
# Install dependencies (requires Waveshare epd library copied separately - see README)
python3 -m pip install -r requirements.txt

# Run the main ticker (requires Raspberry Pi with Waveshare 2.7in ePaper HAT)
python3 btcticker.py

# Run with debug logging
python3 btcticker.py --log debug

# Look up CoinGecko IDs from ticker symbols
python3 tickerhelp.py -s "xmr, dot, avax"
```

## Hardware Variants

There are three entry-point scripts for different display hardware:
- `btcticker.py` — Waveshare 2.7in ePaper (primary, V1 by default; swap import for V2)
- `btcticker2in13.py` — Waveshare 2.13in V2 ePaper
- `btcticker4in0e.py` — Waveshare 4.0in ePaper (color)

All three share the same logic pattern but import different `waveshare_epd` drivers. The `waveshare_epd` library is **not included** in this repo — it must be copied from the Waveshare e-Paper GitHub repo into the project directory.

## Configuration

Copy `config_example.yaml` to `config.yaml` before running. Key settings:

```yaml
display:
  cycle: true          # cycle through coin list
  cyclefiat: true      # also cycle fiat currencies
  inverted: false      # invert display colors
  orientation: 90      # 0/90/180/270 degrees
  trendingmode: false  # append CoinGecko trending coins
  showvolume: false
  showrank: false
  24h: true
  locale: en_US
ticker:
  currency: bitcoin,ethereum,cardano   # CoinGecko IDs (not ticker symbols)
  exchange: default                    # or specific exchange e.g. gdax, binance
  fiatcurrency: usd,btc,gbp
  sparklinedays: 1
  updatefrequency: 300                 # minimum 60s
```

`currency` values must be CoinGecko IDs (e.g. `bitcoin`, not `BTC`). Use `tickerhelp.py` to resolve symbols to IDs.

## Architecture

The main loop in `btcticker.py::main()`:
1. Waits for internet connectivity
2. Every `updatefrequency` seconds calls `fullupdate(config, lastcoinfetch)`
3. `fullupdate` → `getData` (CoinGecko API) → `makeSpark` (matplotlib sparkline) → `updateDisplay` (PIL image composition) → `display_image` (Waveshare EPD driver)

Button presses (GPIO pins 5/6/13/19) trigger `keypress()`, which modifies and writes `config.yaml`, then calls `fullupdate` immediately. Button state is persisted to `config.yaml` so the display returns to its last state after power cycling.

The `getData` function fetches two endpoints: historical price range (for sparkline) and current market data (for live price, ATH, volume, rank). For non-default exchanges, ATH and rank are unavailable.

Token images are cached to `images/currency/<coinid>.bmp`. If not found locally, they are fetched from CoinGecko and saved.

## External Dependencies

- `waveshare_epd` — must be manually installed from Waveshare's GitHub repo
- `RPi.GPIO` — Raspberry Pi GPIO; script will fail on non-Pi hardware
- CoinGecko public API (no key required, but rate-limited)
- `tzupdate` — optional, used to set timezone from IP at startup
