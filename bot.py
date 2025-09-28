import os
import logging
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)
import asyncio

# ======================
# CONFIGURAZIONE BASE
# ======================
TOKEN = os.getenv("TELEGRAM_TOKEN")  # Impostato su Railway
CHAT_ID = os.getenv("CHAT_ID")       # ID chat opzionale (per notifiche automatiche)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

products = []  # Lista prodotti monitorati


# ======================
# FUNZIONI AMAZON
# ======================
def extract_asin(url: str) -> str:
    """Estrae l'ASIN da un link Amazon"""
    try:
        parts = url.split("/dp/")
        if len(parts) > 1:
            return parts[1].split("/")[0].split("?")[0]
    except:
        return None
    return None


def get_price(url: str) -> float:
    """Ottiene il prezzo dal link Amazon (mock semplice con requests)"""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        }
        r = requests.get(url, headers=headers, timeout=10)
        text = r.text

        # ⚠️ MOCK: qui dovresti fare scraping con regex o libreria parsing HTML
        # Per esempio ora restituiamo prezzo fittizio
        import random
        return round(random.uniform(10, 200), 2)

    except Exception as e:
        logging.error(f"Errore nel recupero prezzo: {e}")
        return None


async def notify_price_drop(application, chat_id, info, price):
    """Invia la notifica con i bottoni checkout"""
    asin = extract_asin(info["url"])
    if not asin:
        return

    link1 = f"https://www.amazon.it/gp/aws/cart/add.html?ASIN.1={asin}&Quantity.1=1"
    link2 = f"https://www.amazon.it/gp/aws/cart/add.html?ASIN.1={asin}&Quantity.1=2"

    keyboard = [
        [
            InlineKeyboardButton("x1 Acquisto ⚡", url=link1),
            InlineKeyboardButton("x2 Acquisto ⚡", url=link2),
        ]
    ]

    await application.bot.send_message(
        chat_id=chat_id,
        text=(
            f"🔥 RESTOCK o prezzo in calo!\n\n"
            f"{info['title']}\n"
            f"💰 Prezzo attuale: {price}€\n"
            f"🎯 Target: {info['target']}€\n\n"
            f"🔗 {info['url']}"
        ),
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


# ======================
# COMANDI TELEGRAM
# ======================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Ciao! Sono il bot MonitorPikemonPanda.\n"
        "Usa /help per vedere i comandi disponibili."
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📌 Comandi disponibili:\n\n"
        "/start - Avvia il bot\n"
        "/add <url> <prezzo> - Aggiungi prodotto da monitorare\n"
        "/list - Mostra i prodotti monitorati\n"
        "/help - Mostra questo messaggio"
    )


async def add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("❌ Usa: /add <url> <prezzo>")
        return

    url = context.args[0]
    try:
        target = float(context.args[1])
    except:
        await update.message.reply_text("❌ Prezzo non valido.")
        return

    title = f"Prodotto {len(products)+1}"
    products.append({"url": url, "target": target, "title": title})

    await update.message.reply_text(
        f"✅ Prodotto aggiunto:\n{title}\n🎯 Target: {target}€"
    )


async def list_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not products:
        await update.message.reply_text("📭 Nessun prodotto monitorato.")
        return

    msg = "📋 Prodotti monitorati:\n\n"
    for i, p in enumerate(products, 1):
        msg += f"{i}. {p['title']} - Target: {p['target']}€\n{p['url']}\n\n"

    await update.message.reply_text(msg)


# ======================
# TASK AUTOMATICO
# ======================
async def price_checker(application):
    while True:
        logging.info("🔎 Controllo prezzi...")
        for info in products:
            price = get_price(info["url"])
            if price and price <= info["target"]:
                await notify_price_drop(application, CHAT_ID, info, price)
        await asyncio.sleep(300)  # ogni 5 minuti


# ======================
# MAIN
# ======================
def main():
    application = Application.builder().token(TOKEN).build()

    # Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_cmd))
    application.add_handler(CommandHandler("add", add))
    application.add_handler(CommandHandler("list", list_products))

    # Avvio del controllo prezzi in background
    application.job_queue.run_once(lambda ctx: asyncio.create_task(price_checker(application)), 1)

    # Avvio bot
    application.run_polling()


if __name__ == "__main__":
    main()