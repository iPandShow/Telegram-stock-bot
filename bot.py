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
def get_product_info(url):
    """Ritorna (disponibile, prezzo, titolo, immagine) da una pagina Amazon (molto base)."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }
    try:
        r = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")

        # Titolo
        title_tag = soup.find("span", {"id": "productTitle"})
        title = title_tag.get_text(strip=True) if title_tag else "Prodotto sconosciuto"

        # Prezzo
        price_tag = soup.find("span", {"class": "a-price-whole"})
        if not price_tag:
            return False, None, title, None
        price = int(price_tag.get_text().replace(".", "").replace(",", "").strip())

        # Immagine
        img_tag = soup.find("img", {"id": "landingImage"})
        image = img_tag["src"] if img_tag else None

        return True, price, title, image
    except Exception as e:
        logger.error(f"Errore scraping {url}: {e}")
        return False, None, "Errore", None


# --- COMANDI TELEGRAM ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Ciao! Usa /help per vedere i comandi disponibili.")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📋 Comandi disponibili:\n"
        "/add <link> <prezzo> - Aggiungi un prodotto\n"
        "/list - Mostra prodotti salvati\n"
        "/remove <id> - Elimina prodotto\n"
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

    await update.message.reply_text(f"✅ Prodotto aggiunto!\n{url}\nTarget: {target_price}€")


async def list_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    products = load_products()
    if not products:
        await update.message.reply_text("📦 Nessun prodotto salvato.")
        return

    msg = "📋 Prodotti monitorati:\n\n"
    for i, p in enumerate(products, start=1):
        msg += f"{i}. {p['url']} → {p['target']}€\n"
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


# --- JOB AUTOMATICO ---
async def price_checker(context: ContextTypes.DEFAULT_TYPE):
    products = load_products()
    if not products:
        return

    for p in products:
        available, price, title, image = get_product_info(p["url"])
        if available and price is not None and price <= p["target"]:
            text = (
                f"🔥 <b>RESTOCK!</b>\n\n"
                f"<b>{title}</b>\n\n"
                f"💶 Prezzo attuale: <b>{price}€</b>\n"
                f"🎯 Prezzo target: {p['target']}€\n"
                f"🏬 Venduto da: Amazon\n\n"
                f"🔗 Per acquistare durante un restock:\n"
                f"⬇️ Clicca sui pulsanti Acquisto Lampo (x1 o x2) qui sotto"
            )

            keyboard = [
                [InlineKeyboardButton("x1 Acquisto ⚡", url=f"{p['url']}?quantity=1&buy-now=1")],
                [InlineKeyboardButton("x2 Acquisto ⚡", url=f"{p['url']}?quantity=2&buy-now=1")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            if image:
                await context.bot.send_photo(
                    chat_id=CHANNEL_ID,
                    photo=image,
                    caption=text,
                    parse_mode="HTML",
                    reply_markup=reply_markup
                )
            else:
                await context.bot.send_message(
                    chat_id=CHANNEL_ID,
                    text=text,
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

    # Job queue ogni 5 secondi
    job_queue = application.job_queue
    job_queue.run_repeating(price_checker, interval=5, first=5)

    application.run_polling()


if __name__ == "__main__":
    main()