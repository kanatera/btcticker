#!/usr/bin/python3

"""
  btcticker2in15g.py - cryptocurrency ticker for Waveshare 2.15inch e-Paper HAT (G)
  4-color ePaper display: black, white, red, yellow

     Copyright (C) 2023 Veeb Projects https://veeb.ch

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <https://www.gnu.org/licenses/>
"""

from babel.numbers import decimal, format_currency
from babel import Locale
import argparse
import textwrap
import socket
import yaml
import matplotlib.pyplot as plt
from PIL import Image, ImageOps
from PIL import ImageFont
from PIL import ImageDraw
import currency
import os
import sys
import logging
from gpiozero import Button as GPIOButton
from waveshare_epd import epd2in15g
import time
import threading
import queue
import requests
import json
import matplotlib as mpl

mpl.use("Agg")

# The 4 colors supported by the display
BLACK  = (0,   0,   0)
WHITE  = (255, 255, 255)
RED    = (255, 0,   0)
YELLOW = (255, 255, 0)

dirname = os.path.dirname(__file__)
picdir = os.path.join(os.path.dirname(os.path.realpath(__file__)), "images")
fontdir = os.path.join(os.path.dirname(os.path.realpath(__file__)), "fonts/googlefonts")
configfile = os.path.join(os.path.dirname(os.path.realpath(__file__)), "config.yaml")
font_date = ImageFont.truetype(os.path.join(fontdir, "PixelSplitter-Bold.ttf"), 11)
headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/39.0.2171.95 Safari/537.36"
}
button_pressed = 0
alert_queue = queue.Queue()
_epd = None  # singleton EPD instance — avoids re-init flicker

# Display resolution for Waveshare 2.15inch e-Paper HAT (G)
# Driver expects portrait 160×296 — landscape layouts (296×160) are rotated before passing.
EPD_W = 296   # landscape width
EPD_H = 160   # landscape height

# CoinGecko ID → Binance USDT perpetual symbol
COINGECKO_TO_BINANCE = {
    "bitcoin":                   "BTCUSDT",
    "ethereum":                  "ETHUSDT",
    "cardano":                   "ADAUSDT",
    "binancecoin":               "BNBUSDT",
    "solana":                    "SOLUSDT",
    "ripple":                    "XRPUSDT",
    "polkadot":                  "DOTUSDT",
    "dogecoin":                  "DOGEUSDT",
    "avalanche-2":               "AVAXUSDT",
    "chainlink":                 "LINKUSDT",
    "litecoin":                  "LTCUSDT",
    "uniswap":                   "UNIUSDT",
    "stellar":                   "XLMUSDT",
    "cosmos":                    "ATOMUSDT",
    "near":                      "NEARUSDT",
    "matic-network":             "MATICUSDT",
    "the-sandbox":               "SANDUSDT",
    "decentraland":              "MANAUSDT",
    "aave":                      "AAVEUSDT",
    "shiba-inu":                 "SHIBUSDT",
    "tron":                      "TRXUSDT",
    "filecoin":                  "FILUSDT",
    "fantom":                    "FTMUSDT",
    "maker":                     "MKRUSDT",
    "monero":                    "XMRUSDT",
}


def internet(hostname="google.com"):
    try:
        host = socket.gethostbyname(hostname)
        s = socket.create_connection((host, 80), 2)
        s.close()
        return True
    except:
        logging.info("No internet")
        time.sleep(1)
    return False


def human_format(num):
    num = float("{:.3g}".format(num))
    magnitude = 0
    while abs(num) >= 1000:
        magnitude += 1
        num /= 1000.0
    return "{}{}".format(
        "{:f}".format(num).rstrip("0").rstrip("."), ["", "K", "M", "B", "T"][magnitude]
    )


def _place_text(img, text, x_offset=0, y_offset=0, fontsize=40, fontstring="Forum-Regular", fill=BLACK):
    draw = ImageDraw.Draw(img)
    try:
        filename = os.path.join(dirname, "./fonts/googlefonts/" + fontstring + ".ttf")
        font = ImageFont.truetype(filename, fontsize)
    except OSError:
        font = ImageFont.truetype("/usr/share/fonts/TTF/DejaVuSans.ttf", fontsize)
    img_width, img_height = img.size
    try:
        text_width = font.getbbox(text)[2]
        text_height = font.getbbox(text)[3]
    except:
        text_width = font.getsize(text)[0]
        text_height = font.getsize(text)[1]
    draw_x = (img_width - text_width) // 2 + x_offset
    draw_y = (img_height - text_height) // 2 + y_offset
    draw.text((draw_x, draw_y), text, font=font, fill=fill)


def writewrappedlines(img, text, fontsize=16, y_text=20, height=15, width=25, fontstring="Roboto-Light", fill=BLACK):
    lines = textwrap.wrap(text, width)
    for line in lines:
        _place_text(img, line, 0, y_text, fontsize, fontstring, fill)
        y_text += height
    return img


def getgecko(url):
    try:
        geckojson = requests.get(url, headers=headers).json()
        connectfail = False
    except requests.exceptions.RequestException as e:
        logging.error("Issue with CoinGecko")
        connectfail = True
        geckojson = {}
    return geckojson, connectfail


def getData(config, other):
    if config["ticker"].get("datasource") != "coingecko":
        return getBinanceFutures(config, other)
    sleep_time = 10
    num_retries = 5
    whichcoin, fiat = configtocoinandfiat(config)
    logging.info("Getting Data")
    days_ago = int(config["ticker"]["sparklinedays"])
    endtime = int(time.time())
    starttime = endtime - 60 * 60 * 24 * days_ago
    fiathistory = fiat
    if fiat == "usdt":
        fiathistory = "usd"
    geckourlhistorical = (
        "https://api.coingecko.com/api/v3/coins/"
        + whichcoin
        + "/market_chart/range?vs_currency="
        + fiathistory
        + "&from="
        + str(starttime)
        + "&to="
        + str(endtime)
    )
    timeseriesstack = []
    for x in range(0, num_retries):
        rawtimeseries, connectfail = getgecko(geckourlhistorical)
        if not connectfail:
            timeseriesarray = rawtimeseries["prices"]
            timeseriesstack = [float(p[1]) for p in timeseriesarray]
            time.sleep(1)

        if config["ticker"]["exchange"] == "default":
            geckourl = (
                "https://api.coingecko.com/api/v3/coins/markets?vs_currency="
                + fiat
                + "&ids="
                + whichcoin
            )
            rawlivecoin, connectfail = getgecko(geckourl)
            if not connectfail:
                liveprice = rawlivecoin[0]
                pricenow = float(liveprice["current_price"])
                alltimehigh = float(liveprice["ath"])
                try:
                    other["market_cap_rank"] = int(liveprice["market_cap_rank"])
                except:
                    config["display"]["showrank"] = False
                    other["market_cap_rank"] = 0
                other["volume"] = float(liveprice["total_volume"])
                timeseriesstack.append(pricenow)
                other["ATH"] = pricenow > alltimehigh
        else:
            geckourl = (
                "https://api.coingecko.com/api/v3/exchanges/"
                + config["ticker"]["exchange"]
                + "/tickers?coin_ids="
                + whichcoin
                + "&include_exchange_logo=false"
            )
            rawlivecoin, connectfail = getgecko(geckourl)
            if not connectfail:
                upperfiat = fiat.upper()
                theindex = next(
                    (i for i, t in enumerate(rawlivecoin["tickers"]) if t["target"] == upperfiat),
                    -1
                )
                if theindex == -1:
                    logging.error("Exchange not listing in " + upperfiat + ". Shutting down.")
                    sys.exit()
                liveprice = rawlivecoin["tickers"][theindex]
                pricenow = float(liveprice["last"])
                other["market_cap_rank"] = 0
                other["volume"] = float(liveprice["converted_volume"]["usd"])
                timeseriesstack.append(pricenow)
                other["ATH"] = pricenow > 1000000.0

        if connectfail:
            logging.warning("Retrying in %d seconds", sleep_time)
            time.sleep(sleep_time)
            sleep_time *= 2
        else:
            break
    return timeseriesstack, other


def getBinanceFutures(config, other):
    """Fetch perpetual futures price and kline history from Binance FAPI."""
    whichcoin, _ = configtocoinandfiat(config)

    # Resolve CoinGecko ID to Binance symbol; fall back to uppercased ID + USDT
    symbol = COINGECKO_TO_BINANCE.get(whichcoin, whichcoin.upper().replace("-", "") + "USDT")
    logging.info("Binance symbol: %s", symbol)

    days_ago = int(config["ticker"]["sparklinedays"])
    limit = min(days_ago * 24, 1500)  # hourly candles, Binance max 1500
    sleep_time = 10
    num_retries = 5

    for attempt in range(num_retries):
        try:
            # Historical klines for sparkline
            klines_url = (
                "https://fapi.binance.com/fapi/v1/klines"
                "?symbol=" + symbol + "&interval=1h&limit=" + str(limit)
            )
            klines = requests.get(klines_url, headers=headers, timeout=10).json()
            pricestack = [float(k[4]) for k in klines]  # close prices

            # Live mark price + funding rate
            mark_url = "https://fapi.binance.com/fapi/v1/premiumIndex?symbol=" + symbol
            mark_data = requests.get(mark_url, headers=headers, timeout=10).json()
            pricenow = float(mark_data["markPrice"])
            funding_rate = float(mark_data["lastFundingRate"]) * 100  # as percent

            pricestack.append(pricenow)
            other["ATH"] = False
            other["volume"] = 0
            other["market_cap_rank"] = 0
            other["funding_rate"] = funding_rate
            other["quote"] = "USDT"
            return pricestack, other

        except Exception as e:
            logging.warning("Binance fetch error (attempt %d): %s", attempt + 1, e)
            time.sleep(sleep_time)
            sleep_time *= 2

    return [], other


def beanaproblem(message):
    thebean = Image.open(os.path.join(picdir, "thebean.bmp"))
    image = Image.new("RGB", (EPD_H, EPD_W), WHITE)  # always portrait 160x296
    draw = ImageDraw.Draw(image)
    bean_rgb = thebean.convert("RGB")
    image.paste(bean_rgb, (30, 10))
    draw.text((5, 5), str(time.strftime("%-H:%M, %-d %b %Y")), font=font_date, fill=BLACK)
    writewrappedlines(image, "Issue: " + message, fill=RED)
    return image


def makeSpark(pricestack, positive_change):
    themean = sum(pricestack) / float(len(pricestack))
    x = [xx - themean for xx in pricestack]
    line_color = "#ff0000"  # always red — yellow is near-invisible on white ePaper
    fig, ax = plt.subplots(1, 1, figsize=(10, 3))
    fig.patch.set_facecolor("white")
    plt.plot(x, color=line_color, linewidth=6)
    plt.plot(len(x) - 1, x[-1], color=line_color, marker="o")
    for k, v in ax.spines.items():
        v.set_visible(False)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_facecolor("white")
    ax.axhline(c="black", linewidth=4, linestyle=(0, (5, 2, 1, 2)))
    plt.savefig(os.path.join(picdir, "spark.png"), dpi=17)
    imgspk = Image.open(os.path.join(picdir, "spark.png")).convert("RGB")
    imgspk.save(os.path.join(picdir, "spark.bmp"))
    plt.close(fig)
    plt.cla()
    ax.cla()
    imgspk.close()


def custom_format_currency(value, currency_code, locale):
    value = decimal.Decimal(value)
    locale = Locale.parse(locale)
    pattern = locale.currency_formats["standard"]
    force_frac = (0, 0) if value == int(value) else None
    return pattern.apply(value, locale, currency=currency_code, force_frac=force_frac)


def updateDisplay(config, pricestack, other):
    whichcoin, fiat = configtocoinandfiat(config)
    days_ago = int(config["ticker"]["sparklinedays"])
    pricenow = pricestack[-1]
    pricechangeraw = round((pricestack[-1] - pricestack[0]) / pricestack[-1] * 100, 2)
    positive_change = pricechangeraw >= 0
    # Yellow is near-invisible on white ePaper — use BLACK for positive, RED for negative
    change_color = BLACK if positive_change else RED

    if pricechangeraw >= 10:
        pricechange = str("%+d" % pricechangeraw) + "%"
    else:
        pricechange = str("%+.2f" % pricechangeraw) + "%"

    if "24h" in config["display"] and config["display"]["24h"]:
        timestamp = str(time.strftime("%-H:%M, %d %b %Y"))
    else:
        timestamp = str(time.strftime("%-I:%M %p, %d %b %Y"))

    localetag = config["display"].get("locale", "en_US")

    # In Binance mode other["quote"] is set to "USDT"; fall back to configured fiat
    fiatupper = other.get("quote", fiat).upper()
    if fiatupper == "USDT":
        fiatupper = "USD"
    if fiatupper == "BTC":
        fiatupper = "₿"

    fontreduce = 0
    if pricenow > 10000:
        pricestring = custom_format_currency(int(pricenow), fiatupper, localetag)
    else:
        pricestring = format_currency(pricenow, fiatupper, locale=localetag, decimal_quantization=False)
    if len(pricestring) > 9:
        fontreduce = 6

    # Token image
    currencythumbnail = "currency/" + whichcoin + ".bmp"
    tokenfilename = os.path.join(picdir, currencythumbnail)
    if os.path.isfile(tokenfilename):
        tokenimage = Image.open(tokenfilename).convert("RGB")
    else:
        tokenimageurl = (
            "https://api.coingecko.com/api/v3/coins/"
            + whichcoin
            + "?tickers=false&market_data=false&community_data=false&developer_data=false&sparkline=false"
        )
        rawimage = requests.get(tokenimageurl, headers=headers).json()
        tokenimage = Image.open(
            requests.get(rawimage["image"]["large"], headers=headers, stream=True).raw
        ).convert("RGBA")
        tokenimage.thumbnail((100, 100), Image.BICUBIC)
        new_image = Image.new("RGBA", (120, 120), "WHITE")
        new_image.paste(tokenimage, (10, 10), tokenimage)
        tokenimage = new_image.convert("RGB")
        tokenimage.thumbnail((100, 100), Image.BICUBIC)
        tokenimage.save(tokenfilename)

    sparkbitmap = Image.open(os.path.join(picdir, "spark.bmp")).convert("RGB")
    ATHbitmap = Image.open(os.path.join(picdir, "ATH.bmp")).convert("RGB")

    try:
        font_price_ls = ImageFont.truetype(os.path.join(fontdir, "IBMPlexSans-Medium.ttf"), 36 - fontreduce)
        font_price_pt = ImageFont.truetype(os.path.join(fontdir, "IBMPlexSans-Medium.ttf"), 26 - fontreduce)
    except OSError:
        font_price_ls = ImageFont.load_default()
        font_price_pt = ImageFont.load_default()

    # Landscape layout (296x160) — rotated to portrait 160x296 for driver
    if config["display"]["orientation"] in (90, 270):
        image = Image.new("RGB", (EPD_W, EPD_H), WHITE)  # 296x160
        draw = ImageDraw.Draw(image)

        # Token left side, vertically centred: (160-70)//2 = 45
        image.paste(tokenimage.resize((70, 70), Image.BICUBIC), (4, 45))

        # Right panel: x=82 onward (214px wide × 160px tall)
        draw.text((82, 5),  timestamp, font=font_date, fill=BLACK)
        draw.text((82, 20), pricestring, font=font_price_ls, fill=BLACK)
        draw.text((82, 72), str(days_ago) + " day : ", font=font_date, fill=BLACK)
        draw.text((150, 72), pricechange, font=font_date, fill=change_color)

        if config["ticker"].get("datasource") != "coingecko" and "funding_rate" in other:
            fr = other["funding_rate"]
            fr_color = BLACK if fr >= 0 else RED
            draw.text((82, 86), "fund: " + ("%+.4f" % fr) + "%", font=font_date, fill=fr_color)
        elif config["display"].get("showvolume"):
            draw.text((82, 86), "vol : " + human_format(other["volume"]), font=font_date, fill=BLACK)

        if config["display"].get("showrank") and other.get("market_cap_rank", 0) > 1:
            draw.text((82, 100), "rank : " + str(other["market_cap_rank"]), font=font_date, fill=BLACK)

        if other.get("ATH"):
            image.paste(ATHbitmap, (258, 5))

        # Sparkline — bottom-right: 210px wide × 58px tall
        spark_ls = sparkbitmap.resize((210, 56), Image.BICUBIC)
        image.paste(spark_ls, (82, 102))

        # Rotate landscape 296x160 → portrait 160x296 for driver
        if config["display"]["orientation"] == 90:
            image = image.rotate(90, expand=True)
        else:
            image = image.rotate(270, expand=True)

    # Portrait layout (160x296) for orientations 0 and 180
    else:
        image = Image.new("RGB", (EPD_H, EPD_W), WHITE)  # 160x296
        draw = ImageDraw.Draw(image)

        draw.text((5, 3), timestamp, font=font_date, fill=BLACK)
        image.paste(tokenimage.resize((100, 100), Image.BICUBIC), (30, 20))
        draw.text((5, 128), str(days_ago) + " day :", font=font_date, fill=BLACK)
        draw.text((5, 142), pricechange, font=font_date, fill=change_color)
        draw.text((5, 158), pricestring, font=font_price_pt, fill=BLACK)

        # Sparkline resized to fit portrait width
        spark_pt = sparkbitmap.resize((148, 46), Image.BICUBIC)
        image.paste(spark_pt, (6, 240))

        if config["display"]["orientation"] == 180:
            image = image.rotate(180, expand=True)

    if config["display"]["inverted"]:
        r, g, b = image.split()
        r = ImageOps.invert(r)
        g = ImageOps.invert(g)
        b = ImageOps.invert(b)
        image = Image.merge("RGB", (r, g, b))

    return image


def currencystringtolist(currstring):
    curr_list = currstring.split(",")
    curr_list = [x.strip(" ") for x in curr_list]
    return curr_list


def currencycycle(curr_string):
    curr_list = currencystringtolist(curr_string)
    curr_list = curr_list[1:] + curr_list[:1]
    return curr_list


def display_image(img):
    global _epd
    if _epd is None:
        _epd = epd2in15g.EPD()
        _epd.init()  # init only once per session — avoids extra clear/reset flicker
    _epd.display(_epd.getbuffer(img))
    # No sleep() between updates — keeps display ready and avoids re-init overhead.
    # sleep() is called on KeyboardInterrupt only.
    logging.info("Sent image to screen")


def initkeys():
    bounce = 0.5
    buttons = [
        GPIOButton(5,  pull_up=True, bounce_time=bounce),
        GPIOButton(6,  pull_up=True, bounce_time=bounce),
        GPIOButton(13, pull_up=True, bounce_time=bounce),
        GPIOButton(19, pull_up=True, bounce_time=bounce),
    ]
    buttons[0].when_pressed = lambda: keypress(5)
    buttons[1].when_pressed = lambda: keypress(6)
    buttons[2].when_pressed = lambda: keypress(13)
    buttons[3].when_pressed = lambda: keypress(19)
    return buttons


def addkeyevent(thekeys):
    pass  # callbacks set in initkeys()


def removekeyevent(thekeys):
    for btn in thekeys:
        btn.when_pressed = None


def keypress(channel):
    global button_pressed
    with open(configfile) as f:
        config = yaml.load(f, Loader=yaml.FullLoader)
    lastcoinfetch = time.time()
    if channel == 5 and button_pressed == 0:
        logging.info("Cycle currencies")
        button_pressed = 1
        config["ticker"]["currency"] = ",".join(currencycycle(config["ticker"]["currency"]))
        fullupdate(config, lastcoinfetch)
        configwrite(config)
    elif channel == 6 and button_pressed == 0:
        logging.info("Rotate -90")
        button_pressed = 1
        config["display"]["orientation"] = (config["display"]["orientation"] + 90) % 360
        fullupdate(config, lastcoinfetch)
        configwrite(config)
    elif channel == 13 and button_pressed == 0:
        logging.info("Invert Display")
        button_pressed = 1
        config["display"]["inverted"] = not config["display"]["inverted"]
        fullupdate(config, lastcoinfetch)
        configwrite(config)
    elif channel == 19 and button_pressed == 0:
        logging.info("Cycle fiat")
        button_pressed = 1
        config["ticker"]["fiatcurrency"] = ",".join(currencycycle(config["ticker"]["fiatcurrency"]))
        fullupdate(config, lastcoinfetch)
        configwrite(config)


def configwrite(config):
    with open(configfile, "w") as f:
        yaml.dump(config, f)
    global button_pressed
    button_pressed = 0


def fullupdate(config, lastcoinfetch):
    other = {}
    try:
        pricestack, other = getData(config, other)
        positive_change = pricestack[-1] >= pricestack[0]
        makeSpark(pricestack, positive_change)
        image = updateDisplay(config, pricestack, other)
        display_image(image)
        lastgrab = time.time()
        time.sleep(0.2)
    except Exception as e:
        image = beanaproblem(str(e) + " Line: " + str(e.__traceback__.tb_lineno))
        display_image(image)
        time.sleep(20)
        lastgrab = lastcoinfetch
    return lastgrab


def configtocoinandfiat(config):
    crypto_list = currencystringtolist(config["ticker"]["currency"])
    fiat_list = currencystringtolist(config["ticker"]["fiatcurrency"])
    return crypto_list[0], fiat_list[0]


def gettrending(config):
    coinlist = config["ticker"]["currency"]
    url = "https://api.coingecko.com/api/v3/search/trending"
    config["display"]["cycle"] = True
    trendingcoins = requests.get(url, headers=headers).json()
    for i in range(len(trendingcoins["coins"])):
        coinlist += "," + str(trendingcoins["coins"][i]["item"]["id"])
    config["ticker"]["currency"] = coinlist
    return config


def render_alert(text, config):
    """Render a TradingView alert as a full-screen image."""
    try:
        font_body = ImageFont.truetype(os.path.join(fontdir, "IBMPlexSans-Medium.ttf"), 24)
        font_hdr  = ImageFont.truetype(os.path.join(fontdir, "IBMPlexSans-Medium.ttf"), 16)
    except OSError:
        font_body = ImageFont.load_default()
        font_hdr  = font_body

    orientation = config["display"]["orientation"]

    if orientation in (90, 270):
        # Landscape 296x160: header 32px tall, body fills remaining 128px
        image = Image.new("RGB", (EPD_W, EPD_H), WHITE)
        draw = ImageDraw.Draw(image)
        draw.rectangle([(0, 0), (EPD_W, 32)], fill=RED)
        draw.text((8, 8), "TRADINGVIEW ALERT", font=font_hdr, fill=WHITE)
        # ~21 chars per line at size 24 on 296px wide canvas
        lines = textwrap.wrap(text, width=21)
        for i, line in enumerate(lines[:4]):
            draw.text((8, 38 + i * 30), line, font=font_body, fill=BLACK)
        if orientation == 90:
            image = image.rotate(90, expand=True)
        else:
            image = image.rotate(270, expand=True)
    else:
        # Portrait 160x296: header 32px tall, body fills remaining 264px
        image = Image.new("RGB", (EPD_H, EPD_W), WHITE)
        draw = ImageDraw.Draw(image)
        draw.rectangle([(0, 0), (EPD_H, 32)], fill=RED)
        draw.text((8, 8), "TV ALERT", font=font_hdr, fill=WHITE)
        lines = textwrap.wrap(text, width=13)
        for i, line in enumerate(lines[:8]):
            draw.text((8, 38 + i * 30), line, font=font_body, fill=BLACK)
        if orientation == 180:
            image = image.rotate(180, expand=True)

    if config["display"].get("inverted"):
        r, g, b = image.split()
        image = Image.merge("RGB", (ImageOps.invert(r), ImageOps.invert(g), ImageOps.invert(b)))

    return image


def alert_login(alerts_cfg):
    """Login to the alert server and return a fresh session token."""
    server = alerts_cfg.get("server", "").rstrip("/")
    username = alerts_cfg.get("username", "")
    password = alerts_cfg.get("password", "")
    if not username or not password:
        return alerts_cfg.get("session_token", "")
    try:
        resp = requests.post(
            server + "/api/auth/login",
            json={"username": username, "password": password},
            headers=headers,
            timeout=10
        )
        token = resp.cookies.get("trade_alert_session", "")
        if token:
            logging.info("Alert server: login successful")
        else:
            logging.warning("Alert server: login returned no session cookie")
        return token
    except Exception as e:
        logging.error("Alert server login failed: %s", e)
        return ""


def sse_listener(config, alert_q):
    """Background thread: streams the TradingView app SSE endpoint and queues alert text."""
    alerts_cfg = config.get("alerts", {})
    server = alerts_cfg.get("server", "").rstrip("/")

    if not server:
        logging.info("alerts.server not configured — SSE listener disabled")
        return

    sse_url      = server + "/api/messages/stream"
    messages_url = server + "/api/messages?page=1&limit=1"
    retry_delay = 5

    # Login once at startup; re-login on 401
    session_token = alert_login(alerts_cfg)
    cookies = {"trade_alert_session": session_token} if session_token else {}

    while True:
        try:
            logging.info("Connecting to alert SSE stream: " + sse_url)
            with requests.get(sse_url, stream=True, timeout=90, headers=headers) as resp:
                retry_delay = 5
                for raw in resp.iter_lines():
                    line = raw.decode("utf-8") if isinstance(raw, bytes) else raw
                    if not line.startswith("data:"):
                        continue
                    try:
                        data = json.loads(line[5:].strip())
                    except ValueError:
                        continue
                    if data.get("type") != "new-message":
                        continue
                    try:
                        r = requests.get(messages_url, cookies=cookies,
                                         headers=headers, timeout=10)
                        if r.status_code == 401:
                            logging.info("Alert session expired — re-logging in")
                            session_token = alert_login(alerts_cfg)
                            cookies = {"trade_alert_session": session_token} if session_token else {}
                            r = requests.get(messages_url, cookies=cookies,
                                             headers=headers, timeout=10)
                        payload = r.json()
                        items = payload if isinstance(payload, list) else payload.get("messages", [])
                        if items:
                            alert_q.put(items[0]["text"])
                            logging.info("Alert queued: " + items[0]["text"])
                    except Exception as fetch_err:
                        logging.error("Failed to fetch alert message: " + str(fetch_err))
        except Exception as conn_err:
            logging.error("SSE connection lost: " + str(conn_err))

        logging.info("SSE reconnecting in %ds", retry_delay)
        time.sleep(retry_delay)
        retry_delay = min(retry_delay * 2, 60)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", default="info", help="Set the log level (default: info)")
    args = parser.parse_args()
    loglevel = getattr(logging, args.log.upper(), logging.WARN)
    logging.basicConfig(level=loglevel)

    try:
        os.system("sudo /home/pi/.local/bin/tzupdate")
    except:
        logging.info("Timezone Not Set")

    try:
        logging.info("epd2in15g BTC Frame")
        with open(configfile) as f:
            config = yaml.load(f, Loader=yaml.FullLoader)
        logging.info(config)
        config["display"]["orientation"] = int(config["display"]["orientation"])
        staticcoins = config["ticker"]["currency"]

        thekeys = initkeys()
        addkeyevent(thekeys)

        howmanycoins = len(config["ticker"]["currency"].split(","))
        datapulled = False
        lastcoinfetch = time.time()

        updatefrequency = max(60.0, float(config["ticker"]["updatefrequency"]))

        while not internet():
            logging.info("Waiting for internet")

        # Start TradingView alert listener if configured
        if config.get("alerts", {}).get("server"):
            t = threading.Thread(target=sse_listener, args=(config, alert_queue), daemon=True)
            t.start()
            logging.info("Alert SSE listener started")

        alert_duration = int(config.get("alerts", {}).get("display_seconds", 10))

        while True:
            # Show TradingView alert if one arrived
            if not alert_queue.empty():
                alert_text = alert_queue.get()
                logging.info("Displaying alert: " + alert_text)
                display_image(render_alert(alert_text, config))
                time.sleep(alert_duration)
                lastcoinfetch = 0  # force immediate price refresh after alert

            if config["display"]["trendingmode"]:
                if (time.time() - lastcoinfetch > (7 + howmanycoins) * updatefrequency) or not datapulled:
                    config["ticker"]["currency"] = staticcoins
                    config = gettrending(config)

            if (time.time() - lastcoinfetch > updatefrequency) or not datapulled:
                if config["display"]["cycle"] and datapulled:
                    crypto_list = currencycycle(config["ticker"]["currency"])
                    fiat_list = currencycycle(config["ticker"]["fiatcurrency"])
                    config["ticker"]["currency"] = ",".join(crypto_list)
                    if config["display"].get("cyclefiat"):
                        config["ticker"]["fiatcurrency"] = ",".join(fiat_list)
                lastcoinfetch = fullupdate(config, lastcoinfetch)
                datapulled = True

            time.sleep(0.01)

    except IOError as e:
        logging.error(e)
        display_image(beanaproblem(str(e)))
    except Exception as e:
        logging.error(e)
        display_image(beanaproblem(str(e)))
    except KeyboardInterrupt:
        logging.info("ctrl + c:")
        display_image(beanaproblem("Keyboard Interrupt"))
        if _epd is not None:
            _epd.sleep()
            epd2in15g.epdconfig.module_exit()
        exit()


if __name__ == "__main__":
    main()
