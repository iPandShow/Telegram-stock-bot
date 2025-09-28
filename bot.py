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
def get_price_and_stock(url):
    """Ritorna (disponibile, prezzo) da una pagina Amazon"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }
    try:
        r = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")

        # Trova prezzo
        price_tag = soup.find("span", {"class": "a-price-whole"})
        if not price_tag:
            return False, None
        price = int(price_tag.get_text().replace(".", "").replace(",", "").strip())

        return True, price
    except Exception as e:
        logger.error(f"Errore scraping {url}: {e}")
        return False, None


def get_checkout_links(url, tag="romoloepicc00-21"):
    """Restituisce link diretti al checkout (x1 e x2) se disponibili"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }
    try:
        r = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")

        # 1. Trova ASIN
        asin = None
        if "/dp/" in url:
            asin = url.split("/dp/")[1].split("/")[0]
        if not asin:
            asin_tag = soup.find("input", {"id": "ASIN"})
            if asin_tag:
                asin = asin_tag.get("value")

        # 2. Trova offeringID
        offering_id = None
        offering_tag = soup.find("input", {"name": "offeringID"})
        if offering_tag:
            offering_id = offering_tag.get("value")

        if not asin or not offering_id:
            return None, None

        # 3. Costruisci link checkout
        base = "https://www.amazon.it/gp/checkoutportal/enter-checkout.html/ref=dp_mw_buy_now"
        link_x1 = f"{base}?asin={asin}&offeringID={offering_id}&buyNow=1&quantity=1&tag={tag}"
        link_x2 = f"{base}?asin={asin}&offeringID={offering_id}&buyNow=1&quantity=2&tag={tag}"

        return link_x1, link_x2

    except Exception as e:
        logger.error(f"Errore estrazione checkout da {url}: {e}")
        return None, None


# --- COMANDI TELEGRAM ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Benvenuto! Usa /help per vedere i comandi disponibili.")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📋 *Comandi disponibili:*\n\n"
        "/add <link> <prezzo> – Aggiungi un prodotto da monitorare\n"
        "/list – Mostra prodotti salvati\n"
        "/remove <id> – Elimina un prodotto\n",
        parse_mode="Markdown"
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

    msg = "📋 *Prodotti monitorati:*\n\n"
    for i, p in enumerate(products, start=1):
        msg += f"{i}. {p['url']} → 🎯 {p['target']}€\n"
    await update.message.reply_text(msg, parse_mode="Markdown")


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


# --- JOB AUTOMATICO ---
async def price_checker(context: ContextTypes.DEFAULT_TYPE):
    products = load_products()
    if not products:
        return

    for p in products:
        available, price = get_price_and_stock(p["url"])
        if available and price is not None and price <= p["target"]:
            link_x1, link_x2 = get_checkout_links(p["url"])

            if link_x1 and link_x2:
                keyboard = [
                    [
                        InlineKeyboardButton("⚡ Acquisto x1", url=link_x1),
                        InlineKeyboardButton("⚡ Acquisto x2", url=link_x2),
                    ]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)

                await context.bot.send_message(
                    chat_id=CHANNEL_ID,
                    text=(
                        f"🔥 *RESTOCK DISPONIBILE!*\n\n"
                        f"💰 Prezzo attuale: *{price}€*\n"
                        f"🎯 Sotto il target impostato: {p['target']}€\n\n"
                        f"🏪 Venduto da: *Amazon*\n\n"
                        f"👇 Acquista subito con i pulsanti lampo qui sotto 👇"
                    ),
                    parse_mode="Markdown",
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

    # Job queue ogni 5 secondi
    job_queue = application.job_queue
    job_queue.run_repeating(price_checker, interval=5, first=5)

    application.run_polling()


if __name__ == "__main__":
    main()