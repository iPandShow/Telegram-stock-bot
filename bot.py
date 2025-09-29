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
    """Estrae titolo, prezzo e immagine da una pagina Amazon"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }
    try:
        r = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")

        # Titolo
        title = soup.find("span", {"id": "productTitle"})
        title = title.get_text(strip=True) if title else "Prodotto Amazon"

        # Prezzo
        price = None
        selectors = [
            ("span", {"class": "a-price-whole"}),
            ("span", {"class": "a-offscreen"}),
        ]
        for tag, attrs in selectors:
            el = soup.find(tag, attrs=attrs)
            if el:
                price_text = el.get_text().replace("€", "").replace(".", "").replace(",", ".").strip()
                try:
                    price = int(float(price_text))
                    break
                except ValueError:
                    continue

        # Immagine
        img = None
        img_tag = soup.find("img", {"id": "landingImage"})
        if img_tag and img_tag.get("src"):
            img = img_tag["src"]

        return title, price, img
    except Exception as e:
        logger.error(f"Errore scraping {url}: {e}")
        return None, None, None


def build_checkout_links(asin, tag="romoloepicc00-21"):
    """Costruisce link checkout alternativi senza offeringID"""
    return [
        f"https://www.amazon.it/dp/{asin}?tag={tag}&quantity=1",
        f"https://www.amazon.it/dp/{asin}?tag={tag}&quantity=2",
    ]


def extract_asin(url: str):
    """Estrae ASIN da link Amazon"""
    if "/dp/" in url:
        return url.split("/dp/")[1].split("/")[0]
    if "/d/" in url:
        return url.split("/d/")[1].split("?")[0]
    return None


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


async def send_product_message(bot, product, price, img_url):
    """Invia il messaggio al canale con immagine e bottoni"""
    asin = extract_asin(product["url"])
    if not asin:
        return

    links = build_checkout_links(asin)
    keyboard = [
        [InlineKeyboardButton("x1 Acquisto ⚡", url=links[0]),
         InlineKeyboardButton("x2 Acquisto ⚡", url=links[1])]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    caption = (
        f"🔥 RESTOCK disponibile!\n\n"
        f"📌 <b>{product['url']}</b>\n\n"
        f"💶 Prezzo attuale: <b>{price}€</b>\n"
        f"🎯 Prezzo target: <b>{product['target']}€</b>\n"
        f"🏬 Venduto da: Amazon\n\n"
        f"➡️ Clicca sui pulsanti per acquisto lampo!"
    )

    try:
        if img_url:
            await bot.send_photo(
                chat_id=CHANNEL_ID,
                photo=img_url,
                caption=caption,
                parse_mode="HTML",
                reply_markup=reply_markup
            )
        else:
            await bot.send_message(
                chat_id=CHANNEL_ID,
                text=caption,
                parse_mode="HTML",
                reply_markup=reply_markup
            )
    except Exception as e:
        logger.error(f"Errore invio messaggio: {e}")


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
    title, price, img = get_product_info(p["url"])
    await send_product_message(context.bot, p, price or 0, img)
    await update.message.reply_text("✅ Messaggio test inviato al canale!")


# --- JOB AUTOMATICO ---
async def price_checker(context: ContextTypes.DEFAULT_TYPE):
    products = load_products()
    if not products:
        return

    for p in products:
        title, price, img = get_product_info(p["url"])
        if price is not None and price <= p["target"]:
            await send_product_message(context.bot, p, price, img)


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

    # Job queue ogni 5 secondi
    job_queue = application.job_queue
    job_queue.run_repeating(price_checker, interval=5, first=5)

    application.run_polling()


if __name__ == "__main__":
    main()