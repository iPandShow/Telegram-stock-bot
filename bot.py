# bot.py — versione corretta: /test funzionante (invia direttamente)
import os
import json
import logging
import re
import urllib.parse
import html
from typing import Optional, Dict

import requests
from bs4 import BeautifulSoup
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes

# -------------------------
# Config / Logging
# -------------------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger("pokemon-monitor-panda")

# --- Impostazioni fisse (metti qui i tuoi valori, lasciando solo TOKEN in env) ---
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")  # 🔑 variabile su Railway

# Sostituisci con l'ID numerico reale del canale (es. -1001234567890)
CHANNEL_ID = -1001234567890

# Link testuale che deve restare così
CHAT_LINK = "https://t.me/pokemonmonitorpandachat"
# Link del canale usato per il pulsante share (il testo che verrà inoltrato)
CHANNEL_LINK = "https://t.me/pokemonmonitorpanda"

PRODUCTS_FILE = "products.json"
CHECK_INTERVAL_SECONDS = 60  # intervallo controllo prezzi

if not TOKEN:
    logger.error("TELEGRAM_BOT_TOKEN non trovato nelle env. Impostalo su Railway.")
    raise SystemExit("Missing TELEGRAM_BOT_TOKEN")

# -------------------------
# File prodotti
# -------------------------
def load_products():
    if not os.path.exists(PRODUCTS_FILE):
        return []
    with open(PRODUCTS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_products(products):
    with open(PRODUCTS_FILE, "w", encoding="utf-8") as f:
        json.dump(products, f, indent=2, ensure_ascii=False)

# -------------------------
# Scraping Amazon (best-effort)
# -------------------------
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

def extract_price_from_text(s: str) -> Optional[float]:
    if not s:
        return None
    m = re.search(r"(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{1,2})?)", s)
    if not m:
        return None
    raw = m.group(1)
    # normalizza numero italiano
    if "." in raw and "," in raw:
        raw = raw.replace(".", "").replace(",", ".")
    else:
        raw = raw.replace(".", "").replace(",", ".")
    try:
        return float(raw)
    except Exception:
        return None

def scrape_amazon(url: str) -> Dict[str, Optional[str]]:
    """Ritorna {title, price, asin, offeringID, image} (price float quando possibile)"""
    try:
        r = requests.get(url, headers=HEADERS, timeout=12)
        html_text = r.text
        soup = BeautifulSoup(html_text, "html.parser")

        # title (prefer og:title)
        title = None
        og_title = soup.select_one('meta[property="og:title"]')
        if og_title and og_title.get("content"):
            title = og_title["content"].strip()
        else:
            el = soup.find(id="productTitle")
            if el:
                title = el.get_text(strip=True)

        # price (prefer a-offscreen)
        price = None
        el = soup.select_one("span.a-offscreen")
        if el:
            price = extract_price_from_text(el.get_text())
        if price is None:
            candidates = [
                soup.select_one("#priceblock_ourprice"),
                soup.select_one("#priceblock_dealprice"),
                soup.select_one(".a-price .a-price-whole")
            ]
            for c in candidates:
                if c:
                    price = extract_price_from_text(c.get_text())
                    if price is not None:
                        break

        # asin from url
        asin = None
        if "/dp/" in url:
            asin = url.split("/dp/")[1].split("/")[0]
        elif "/gp/product/" in url:
            asin = url.split("/gp/product/")[1].split("/")[0]
        elif "/d/" in url:
            asin = url.split("/d/")[1].split("?")[0]

        # offeringID search (best-effort)
        offeringID = None
        m_off = re.search(r"offeringID=([A-Za-z0-9%\-+/=]+)", html_text)
        if m_off:
            offeringID = m_off.group(1)

        # image (og:image o landingImage)
        image = None
        og_img = soup.select_one('meta[property="og:image"]')
        if og_img and og_img.get("content"):
            image = og_img["content"]
        else:
            img_tag = soup.find("img", id="landingImage")
            if img_tag and img_tag.get("src"):
                image = img_tag["src"]

        return {"title": title or "Prodotto", "price": price, "asin": asin, "offeringID": offeringID, "image": image}
    except Exception as e:
        logger.exception("Errore scraping Amazon per %s", url)
        return {"title": None, "price": None, "asin": None, "offeringID": None, "image": None}

# -------------------------
# Costruzione link checkout e share
# -------------------------
CHECKOUT_TAG = "romoloepicc00-21"  # mantieni o cambia

def build_checkout_links(asin: Optional[str], offeringID: Optional[str], fallback_url: str):
    if asin and offeringID:
        base = "https://www.amazon.it/gp/checkoutportal/enter-checkout.html/ref=dp_mw_buy_now"
        l1 = f"{base}?asin={asin}&offeringID={offeringID}&buyNow=1&quantity=1&tag={CHECKOUT_TAG}"
        l2 = f"{base}?asin={asin}&offeringID={offeringID}&buyNow=1&quantity=2&tag={CHECKOUT_TAG}"
        return l1, l2
    else:
        sep = "&" if "?" in fallback_url else "?"
        return f"{fallback_url}{sep}quantity=1", f"{fallback_url}{sep}quantity=2"

def build_share_url(channel_link: str):
    text = "🔥 Unisciti a Pokémon Monitor Panda 🐼"
    return "https://t.me/share/url?url=" + urllib.parse.quote(channel_link) + "&text=" + urllib.parse.quote(text)

# -------------------------
# Invio al canale (ora invia direttamente)
# -------------------------
async def send_to_channel(bot, p: dict, price: Optional[float] = None, test: bool = False):
    url = p.get("url")
    title = p.get("title") or url
    asin = p.get("asin")
    offeringID = p.get("offeringID")
    image = p.get("image")

    link_x1, link_x2 = build_checkout_links(asin, offeringID, url)
    share_url = build_share_url(CHANNEL_LINK)

    keyboard = [
        [
            InlineKeyboardButton("⚡ x1 Acquisto", url=link_x1),
            InlineKeyboardButton("⚡ x2 Acquisto", url=link_x2),
        ],
        [InlineKeyboardButton("👥 Condividi / Invita amici", url=share_url)]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # testo HTML (escape di eventuali caratteri)
    header = '<b>🐼 Pokémon Monitor Panda</b>\n'
    header += '<b>🧭 TEST RESTOCK</b>\n\n' if test else '<b>🔥 RESTOCK TROVATO!</b>\n\n'

    caption = header
    caption += f'📦 <b>Prodotto:</b> <a href="{html.escape(url)}">{html.escape(title)}</a>\n'
    caption += f'🎯 <b>Prezzo target:</b> {p.get("target")}€\n'
    if price is not None:
        caption += f'💶 <b>Prezzo attuale:</b> {price}€\n\n'
    caption += '🛒 <i>Per acquistare clicca i pulsanti qui sotto</i>\n\n'
    # Unisciti alla chat deve rimanere testo-link
    caption += f'💬 <a href="{html.escape(CHAT_LINK)}">Unisciti alla chat</a>'

    try:
        if image:
            await bot.send_photo(chat_id=CHANNEL_ID, photo=image, caption=caption, parse_mode="HTML", reply_markup=reply_markup)
        else:
            await bot.send_message(chat_id=CHANNEL_ID, text=caption, parse_mode="HTML", reply_markup=reply_markup)
        logger.info("Inviato messaggio al canale per %s", url)
    except Exception:
        logger.exception("Errore invio al canale per %s", url)

# -------------------------
# Handlers comandi
# -------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Benvenuto su Pokémon Monitor Panda 🐼 — usa /help")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Comandi:\n"
        "/add <link> <prezzo> - Aggiungi prodotto\n"
        "/list - Lista prodotti\n"
        "/remove <id> - Rimuovi\n"
        "/test <id> - Pubblica test nel canale"
    )

async def add_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("⚠️ Usa /add <link> <prezzo>")
        return
    url = context.args[0]
    try:
        target = float(context.args[1])
    except ValueError:
        await update.message.reply_text("⚠️ Prezzo non valido.")
        return

    scraped = scrape_amazon(url)
    products = load_products()
    products.append({
        "url": url,
        "target": target,
        "asin": scraped.get("asin"),
        "offeringID": scraped.get("offeringID"),
        "title": scraped.get("title"),
        "image": scraped.get("image")
    })
    save_products(products)
    await update.message.reply_text(f"✅ Aggiunto: {scraped.get('title')}\n🎯 Target: {target}€")

async def list_products_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    products = load_products()
    if not products:
        await update.message.reply_text("Nessun prodotto salvato.")
        return
    msg = "📋 Prodotti salvati:\n"
    for i, p in enumerate(products, 1):
        t = p.get("title") or p.get("url")
        msg += f"{i}. {t} → {p.get('target')}€\n"
    await update.message.reply_text(msg)

async def remove_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ Usa /remove <id>")
        return
    try:
        idx = int(context.args[0]) - 1
    except ValueError:
        await update.message.reply_text("⚠️ ID non valido.")
        return
    products = load_products()
    if idx < 0 or idx >= len(products):
        await update.message.reply_text("❌ ID non valido.")
        return
    removed = products.pop(idx)
    save_products(products)
    await update.message.reply_text(f"✅ Rimosso: {removed.get('title') or removed.get('url')}")

async def test_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Invia direttamente al canale (test) — PROBLEMA PRECEDENTE: ora risolto"""
    if not context.args:
        await update.message.reply_text("⚠️ Usa /test <id>")
        return
    try:
        idx = int(context.args[0]) - 1
    except ValueError:
        await update.message.reply_text("⚠️ ID non valido.")
        return
    products = load_products()
    if idx < 0 or idx >= len(products):
        await update.message.reply_text("❌ ID non valido.")
        return
    p = products[idx]
    # aggiorna dati prima del test
    scraped = scrape_amazon(p["url"])
    p.update({"asin": scraped.get("asin"), "offeringID": scraped.get("offeringID"),
              "title": scraped.get("title"), "image": scraped.get("image")})
    save_products(products)

    await send_to_channel(context.bot, p, price=None, test=True)
    await update.message.reply_text("✅ Messaggio TEST inviato al canale!")

# -------------------------
# Job di controllo prezzi
# -------------------------
async def price_checker(context: ContextTypes.DEFAULT_TYPE):
    try:
        products = load_products()
        if not products:
            return
        for p in products:
            scraped = scrape_amazon(p["url"])
            price = scraped.get("price")
            # aggiorna meta info se presenti
            if scraped.get("asin"):
                p["asin"] = scraped.get("asin")
            if scraped.get("offeringID"):
                p["offeringID"] = scraped.get("offeringID")
            if scraped.get("title"):
                p["title"] = scraped.get("title")
            if scraped.get("image"):
                p["image"] = scraped.get("image")
            save_products(products)

            if price is None:
                continue
            if price <= float(p["target"]):
                await send_to_channel(context.bot, p, price=price, test=False)
    except Exception:
        logger.exception("Errore nel job price_checker")

# -------------------------
# MAIN
# -------------------------
def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("add", add_product))
    app.add_handler(CommandHandler("list", list_products_cmd))
    app.add_handler(CommandHandler("remove", remove_product))
    app.add_handler(CommandHandler("test", test_product))

    app.job_queue.run_repeating(price_checker, interval=CHECK_INTERVAL_SECONDS, first=10)

    logger.info("Avvio polling...")
    app.run_polling()

if __name__ == "__main__":
    main()