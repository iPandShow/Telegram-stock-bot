# bot.py
import logging
import os
import re
import sqlite3
import requests
import asyncio
from typing import Optional
from bs4 import BeautifulSoup
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)
from urllib.parse import urlparse

# --- CONFIG / LOG ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")  # es: "@mio_canale" o chat_id numerico

DB_FILE = "products.db"
PLACEHOLDER_IMG = "https://i.imgur.com/8fKQZt6.png"
REQUEST_TIMEOUT = 10

# -------------------------
# Database semplice (SQLite)
# -------------------------
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS products (
            url TEXT PRIMARY KEY,
            name TEXT,
            title TEXT,
            image TEXT,
            max_price REAL,
            last_price REAL
        )
        """
    )
    conn.commit()
    conn.close()

def add_product_db(url: str, name: Optional[str], title: str, image: str, max_price: float):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute(
        "INSERT OR REPLACE INTO products (url, name, title, image, max_price, last_price) VALUES (?, ?, ?, ?, ?, ?)",
        (url, name or title, title, image, max_price, None),
    )
    conn.commit()
    conn.close()

def remove_product_db(url: str):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("DELETE FROM products WHERE url = ?", (url,))
    conn.commit()
    conn.close()

def list_products_db():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT url, name, title, image, max_price, last_price FROM products")
    rows = cur.fetchall()
    conn.close()
    return rows

def update_last_price_db(url: str, price: float):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("UPDATE products SET last_price = ? WHERE url = ?", (price, url))
    conn.commit()
    conn.close()

# -------------------------
# Scraping (sincrono) - run in thread
# -------------------------
def _extract_image_from_soup(soup: BeautifulSoup) -> str:
    # meta og:image
    meta = soup.find("meta", property="og:image")
    if meta and meta.get("content"):
        return meta["content"]

    # link rel image_src
    link = soup.find("link", {"rel": "image_src"})
    if link and link.get("href"):
        return link["href"]

    # img landingImage
    img = soup.find("img", {"id": "landingImage"})
    if img and img.get("src"):
        return img["src"]

    # data-a-dynamic-image on image block
    dyn = soup.find(attrs={"data-a-dynamic-image": True})
    if dyn:
        try:
            import json
            data = json.loads(dyn["data-a-dynamic-image"])
            # first key is url
            for k in data.keys():
                return k
        except Exception:
            pass

    # fallback
    return PLACEHOLDER_IMG

def _parse_price_from_soup(soup: BeautifulSoup) -> Optional[float]:
    # Proviamo varie classi / tag usate da Amazon
    candidates = []
    # common Amazon price tags
    price_whole = soup.find("span", {"class": "a-price-whole"})
    price_fraction = soup.find("span", {"class": "a-price-fraction"})
    if price_whole:
        whole = price_whole.get_text().strip().replace(".", "").replace(",", ".")
        frac = price_fraction.get_text().strip() if price_fraction else "0"
        try:
            return float(f"{whole}.{frac}")
        except Exception:
            pass

    # some pages use span#priceblock_ourprice or priceblock_dealprice
    p = soup.find(id="priceblock_ourprice") or soup.find(id="priceblock_dealprice") or soup.find(id="price_inside_buybox")
    if p:
        txt = p.get_text().strip()
        txt = re.sub(r"[^\d,\.]", "", txt)
        txt = txt.replace(".", "").replace(",", ".")
        try:
            return float(txt)
        except Exception:
            pass

    # fallback - try to search first currency-looking text
    txts = soup.find_all(text=re.compile(r"\d+[.,]\d+"))
    for t in txts:
        s = re.sub(r"[^\d,\.]", "", t)
        s = s.replace(".", "").replace(",", ".")
        try:
            return float(s)
        except Exception:
            continue

    return None

def scrape_amazon(url: str):
    """Blocking scraping. Return dict or None"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/115.0 Safari/537.36"
    }
    try:
        r = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "lxml")

        title_tag = soup.find("span", {"id": "productTitle"})
        title = title_tag.get_text(strip=True) if title_tag else soup.title.string.strip() if soup.title else "Prodotto sconosciuto"

        price = _parse_price_from_soup(soup)
        image = _extract_image_from_soup(soup)

        return {"title": title, "price": price, "image": image}
    except Exception as e:
        logger.exception("Errore scraping Amazon")
        return None

# -------------------------
# Helper: estrai ASIN da url
# -------------------------
def extract_asin(url: str) -> Optional[str]:
    # try common patterns
    patterns = [
        r"/dp/([A-Z0-9]{10})",
        r"/gp/product/([A-Z0-9]{10})",
        r"/product/([A-Z0-9]{10})",
        r"ASIN=([A-Z0-9]{10})",
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    # fallback: last path chunk if looks like ASIN
    path = urlparse(url).path
    last = path.rstrip("/").split("/")[-1]
    if re.fullmatch(r"[A-Z0-9]{10}", last):
        return last
    return None

# -------------------------
# Bot command handlers
# -------------------------
async def cmd_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Accept two formats:
    # 1) /add <url> <prezzo>
    # 2) /add <nome> <url> <prezzo>
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("⚠️ Usa il formato:\n/add <nome_opzionale> <link> <prezzo>\nEsempio:\n/add Pulsar https://amzn.it/d/XXXXX 29.90")
        return

    # detect if first arg is URL
    if args[0].startswith("http"):
        url = args[0]
        try:
            max_price = float(args[1].replace(",", "."))
        except Exception:
            await update.message.reply_text("Prezzo non valido.")
            return
        name = None
    else:
        if len(args) < 3:
            await update.message.reply_text("⚠️ Usa il formato:\n/add <nome> <link> <prezzo>")
            return
        name = args[0]
        url = args[1]
        try:
            max_price = float(args[2].replace(",", "."))
        except Exception:
            await update.message.reply_text("Prezzo non valido.")
            return

    await update.message.reply_text("⌛ Verifico il prodotto, attendi...")
    scraped = await asyncio.to_thread(scrape_amazon, url)
    if not scraped:
        await update.message.reply_text("Errore durante lo scraping del prodotto.")
        return

    add_product_db(url=url, name=name, title=scraped["title"], image=scraped["image"], max_price=max_price)
    await update.message.reply_text(f"✅ Prodotto aggiunto:\n{scraped['title']}\nPrezzo max: {max_price}€\nLink: {url}")

async def cmd_remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usa: /remove <url>")
        return
    url = context.args[0]
    remove_product_db(url)
    await update.message.reply_text("🗑️ Prodotto rimosso (se esisteva).")

async def cmd_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = list_products_db()
    if not rows:
        await update.message.reply_text("📦 Al momento non ci sono prodotti salvati.")
        return
    msg_lines = ["📋 Prodotti salvati:"]
    for url, name, title, image, max_price, last_price in rows:
        display = name if name else title
        msg_lines.append(f"- {display} — max {max_price}€\n  {url}")
    await update.message.reply_text("\n".join(msg_lines))

async def cmd_commands(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "🤖 Comandi disponibili:\n"
        "/add <nome_opzionale> <link> <prezzo> → aggiungi prodotto\n"
        "/remove <link> → rimuovi prodotto\n"
        "/list → lista prodotti monitorati\n"
        "/commands → mostra questo messaggio\n\n"
        "⚠️ Nota: assicurati che il bot sia admin del canale e che sia in esecuzione solo 1 istanza."
    )
    await update.message.reply_text(msg)

# -------------------------
# Job: controllo prezzi (periodico)
# -------------------------
async def price_checker(context: ContextTypes.DEFAULT_TYPE):
    logger.info("Eseguo controllo prezzi...")
    rows = list_products_db()
    for url, name, title, image, max_price, last_price in rows:
        scraped = await asyncio.to_thread(scrape_amazon, url)
        if not scraped:
            logger.info(f"Non ho recuperato dati per {url}")
            continue
        price = scraped.get("price")
        if price is None:
            logger.info(f"Nessun prezzo trovato per {url}")
            continue

        # aggiorno last price
        update_last_price_db(url, price)

        # notifica se prezzo <= max
        if price <= (max_price or 0):
            display_title = name if name else scraped["title"]
            asin = extract_asin(url)
            if asin:
                buy_url_1 = f"https://www.amazon.it/dp/{asin}?psc=1"
                buy_url_2 = f"https://www.amazon.it/dp/{asin}?psc=1&quantity=2"
            else:
                # fallback link diretto
                buy_url_1 = url
                buy_url_2 = url

            caption = (
                f"🔥 <b>RESTOCK</b> — <b>{display_title}</b>\n\n"
                f"🏷️ Prezzo: <b>{price:.2f}€</b> (max impostato: {max_price:.2f}€)\n"
                f"🏬 Venduto da: Amazon\n\n"
                "🔗 Per acquistare durante un restock clicca sui pulsanti qui sotto.\n"
            )

            keyboard = InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton("x1 Acquisto ⚡", url=buy_url_1)],
                    [InlineKeyboardButton("x2 Acquisto ⚡", url=buy_url_2)],
                ]
            )

            # prova a mandare foto; se fallisce mando testo semplice
            try:
                await context.bot.send_photo(
                    chat_id=CHANNEL_ID,
                    photo=scraped.get("image") or PLACEHOLDER_IMG,
                    caption=caption,
                    parse_mode="HTML",
                    reply_markup=keyboard,
                )
            except Exception as e:
                logger.exception("Errore invio foto, mando messaggio testuale")
                try:
                    await context.bot.send_message(
                        chat_id=CHANNEL_ID,
                        text=f"{caption}\n{url}",
                        parse_mode="HTML",
                        reply_markup=keyboard,
                    )
                except Exception:
                    logger.exception("Invio messaggio fallito")

# -------------------------
# Error handler
# -------------------------
async def err_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.exception("Unhandled exception in update: %s", context.error)

# -------------------------
# Main
# -------------------------
def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN non impostato. Esci.")
        return
    if not CHANNEL_ID:
        logger.error("CHANNEL_ID non impostato. Esci.")
        return

    init_db()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("add", cmd_add))
    app.add_handler(CommandHandler("remove", cmd_remove))
    app.add_handler(CommandHandler("list", cmd_list))
    app.add_handler(CommandHandler("commands", cmd_commands))
    app.add_error_handler(err_handler)

    # JOB: controllo prezzi ogni 5 secondi (modifica qui se vuoi 60s)
    app.job_queue.run_repeating(price_checker, interval=5, first=5)

    # Avvia polling (nota sul 409: assicurati che non ci siano altre istanze)
    logger.info("Avvio bot (polling)...")
    try:
        app.run_polling()
    except Exception as e:
        logger.exception("app.run_polling ha sollevato un'eccezione")

if __name__ == "__main__":
    main()