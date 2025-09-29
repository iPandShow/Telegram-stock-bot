import os
import json
import logging
import requests
from bs4 import BeautifulSoup
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, ContextTypes
)

# Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Token e Chat ID dal Railway
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID", "@pokemonmonitorpanda")

PRODUCTS_FILE = "products.json"
PLACEHOLDER_IMG = "https://i.imgur.com/8fKQZt6.png"

# --- GESTIONE FILE JSON ---
def load_products():
    if not os.path.exists(PRODUCTS_FILE):
        return []
    with open(PRODUCTS_FILE, "r") as f:
        return json.load(f)

def save_products(products):
    with open(PRODUCTS_FILE, "w") as f:
        json.dump(products, f, indent=4)

# --- FUNZIONI AMAZON ---
def scrape_amazon(url):
    """Estrae titolo, prezzo, immagine, asin e offeringID (se disponibile)"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }
    try:
        r = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")

        # Titolo
        title = soup.find("span", {"id": "productTitle"})
        title = title.get_text(strip=True) if title else "Prodotto sconosciuto"

        # Prezzo
        price = None
        price_tag = soup.find("span", {"class": "a-price-whole"})
        if price_tag:
            price_text = price_tag.get_text().replace(".", "").replace(",", "").strip()
            try:
                price = int(price_text)
            except ValueError:
                pass

        # Immagine
        img_tag = soup.find("img", {"id": "landingImage"})
        image_url = img_tag["src"] if img_tag else PLACEHOLDER_IMG

        # ASIN
        asin = None
        if "/dp/" in url:
            asin = url.split("/dp/")[1].split("/")[0]
        elif "/d/" in url:
            asin = url.split("/d/")[1].split("?")[0]

        # OfferingID (se appare nel sorgente)
        offering_id = None
        if "offeringID" in r.text:
            start = r.text.find("offeringID") + 11
            offering_id = r.text[start:start+50].split('"')[0]

        return {"title": title, "price": price, "image": image_url, "asin": asin, "offering": offering_id}

    except Exception as e:
        logger.error(f"Errore scraping {url}: {e}")
        return None

def build_checkout_links(asin, offering, tag="romoloepicc00-21"):
    """Costruisce i due link checkout (x1 e x2)"""
    base = "https://www.amazon.it/gp/checkoutportal/enter-checkout.html"
    return [
        f"{base}?asin={asin}&offeringID={offering}&buyNow=1&quantity=1&tag={tag}",
        f"{base}?asin={asin}&offeringID={offering}&buyNow=1&quantity=2&tag={tag}",
    ]

# --- COMANDI TELEGRAM ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Ciao! Usa /help per vedere i comandi disponibili.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📋 Comandi disponibili:\n"
        "/add <link> <prezzo> - Aggiungi un prodotto\n"
        "/list - Mostra prodotti salvati\n"
        "/remove <id> - Elimina prodotto\n"
        "/test <id> - Forza pubblicazione nel canale"
    )

async def add_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("⚠️ Usa: /add <link> <prezzo>")
        return

    url = context.args[0]
    try:
        target_price = int(context.args[1])
    except ValueError:
        await update.message.reply_text("⚠️ Il prezzo deve essere un numero intero.")
        return

    products = load_products()
    products.append({"url": url, "target": target_price})
    save_products(products)

    await update.message.reply_text(f"✅ Prodotto aggiunto!\n{url}\n🎯 Target: {target_price}€")

async def list_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    products = load_products()
    if not products:
        await update.message.reply_text("📦 Nessun prodotto salvato.")
        return

    msg = "📋 Prodotti monitorati:\n\n"
    for i, p in enumerate(products, start=1):
        msg += f"{i}. {p['url']} → 🎯 {p['target']}€\n"
    await update.message.reply_text(msg)

async def remove_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ Usa: /remove <id>")
        return

    try:
        idx = int(context.args[0]) - 1
    except ValueError:
        await update.message.reply_text("⚠️ L'ID deve essere un numero.")
        return

    products = load_products()
    if idx < 0 or idx >= len(products):
        await update.message.reply_text("❌ ID non valido.")
        return

    removed = products.pop(idx)
    save_products(products)
    await update.message.reply_text(f"✅ Prodotto rimosso:\n{removed['url']}")

async def test_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Forza la pubblicazione su canale"""
    if not context.args:
        await update.message.reply_text("⚠️ Usa: /test <id>")
        return

    try:
        idx = int(context.args[0]) - 1
    except ValueError:
        await update.message.reply_text("⚠️ L'ID deve essere un numero.")
        return

    products = load_products()
    if idx < 0 or idx >= len(products):
        await update.message.reply_text("❌ ID non valido.")
        return

    p = products[idx]
    data = scrape_amazon(p["url"])
    if not data:
        await update.message.reply_text("❌ Errore scraping.")
        return

    caption = (
        f"🔥 <b>RESTOCK TEST</b>\n\n"
        f"{data['title']}\n"
        f"💶 Prezzo attuale: {data['price']}€\n"
        f"🎯 Target: {p['target']}€"
    )

    # Se abbiamo ASIN + offering creiamo checkout
    if data["asin"] and data["offering"]:
        links = build_checkout_links(data["asin"], data["offering"])
        keyboard = [
            [InlineKeyboardButton("x1 Acquisto ⚡", url=links[0]),
             InlineKeyboardButton("x2 Acquisto ⚡", url=links[1])]
        ]
    else:
        keyboard = [[InlineKeyboardButton("🔗 Vai al prodotto", url=p["url"])]]

    reply_markup = InlineKeyboardMarkup(keyboard)

    await context.bot.send_photo(
        chat_id=CHANNEL_ID,
        photo=data["image"],
        caption=caption,
        parse_mode="HTML",
        reply_markup=reply_markup
    )

    await update.message.reply_text("✅ Messaggio test inviato al canale!")

# --- JOB AUTOMATICO ---
async def price_checker(context: ContextTypes.DEFAULT_TYPE):
    products = load_products()
    if not products:
        return

    for p in products:
        data = scrape_amazon(p["url"])
        if not data or not data["price"]:
            continue

        if data["price"] <= p["target"]:
            caption = (
                f"🔥 <b>RESTOCK!</b>\n\n"
                f"{data['title']}\n"
                f"💶 Prezzo attuale: {data['price']}€\n"
                f"🎯 Target: {p['target']}€"
            )

            if data["asin"] and data["offering"]:
                links = build_checkout_links(data["asin"], data["offering"])
                keyboard = [
                    [InlineKeyboardButton("x1 Acquisto ⚡", url=links[0]),
                     InlineKeyboardButton("x2 Acquisto ⚡", url=links[1])]
                ]
            else:
                keyboard = [[InlineKeyboardButton("🔗 Vai al prodotto", url=p["url"])]]

            reply_markup = InlineKeyboardMarkup(keyboard)

            await context.bot.send_photo(
                chat_id=CHANNEL_ID,
                photo=data["image"],
                caption=caption,
                parse_mode="HTML",
                reply_markup=reply_markup
            )

# --- MAIN ---
def main():
    application = Application.builder().token(TOKEN).build()

    # Comandi
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("add", add_product))
    application.add_handler(CommandHandler("list", list_products))
    application.add_handler(CommandHandler("remove", remove_product))
    application.add_handler(CommandHandler("test", test_product))

    # Job queue ogni 30 secondi
    job_queue = application.job_queue
    job_queue.run_repeating(price_checker, interval=30, first=10)

    application.run_polling()

if __name__ == "__main__":
    main()