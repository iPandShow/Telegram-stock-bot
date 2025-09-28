import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler

# Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Token e Chat ID
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID", "@pokemonmonitorpanda")


# --- COMANDI ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Messaggio di benvenuto"""
    await update.message.reply_text(
        "👋 Ciao! Sono MonitorPokemonPanda.\n"
        "Usa /help per vedere i comandi disponibili."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostra i comandi disponibili"""
    await update.message.reply_text(
        "📋 Lista comandi disponibili:\n\n"
        "/start - Avvia il bot\n"
        "/help - Mostra i comandi\n"
        "/add <nome prodotto> <link amazon> <prezzo> - Aggiungi un prodotto\n"
        "/list - Mostra i prodotti monitorati\n"
        "/send <messaggio> - Invia un messaggio al canale\n"
    )


async def add_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Aggiunge un prodotto al monitoraggio"""
    try:
        text = " ".join(context.args)
        if not text:
            await update.message.reply_text("⚠️ Usa il formato:\n/add NomeProdotto link prezzo")
            return

        await update.message.reply_text(f"✅ Prodotto aggiunto: {text}")
    except Exception as e:
        logger.error(f"Errore add_product: {e}")
        await update.message.reply_text("❌ Errore durante l'aggiunta del prodotto.")


async def list_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lista prodotti (placeholder, puoi collegarlo al DB più avanti)"""
    await update.message.reply_text("📦 Al momento non ci sono prodotti salvati.")


async def send_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Invia un messaggio al canale"""
    if not context.args:
        await update.message.reply_text("⚠️ Usa il formato:\n/send messaggio da inviare")
        return

    text = " ".join(context.args)

    # Bottoni Acquisto x1 e x2
    keyboard = [
        [
            InlineKeyboardButton("x1 Acquisto ⚡", url="https://www.amazon.it/gp/aws/cart/add.html?ASIN.1=B0XXXXXX&Quantity.1=1"),
            InlineKeyboardButton("x2 Acquisto ⚡", url="https://www.amazon.it/gp/aws/cart/add.html?ASIN.1=B0XXXXXX&Quantity.1=2"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await context.bot.send_message(
        chat_id=CHANNEL_ID,
        text=f"🔥 RESTOCK!\n\n{text}",
        reply_markup=reply_markup
    )

    await update.message.reply_text("✅ Messaggio inviato al canale!")


# --- SCHEDULER (job_queue) ---

async def price_checker(context: ContextTypes.DEFAULT_TYPE):
    """Controlla prezzi (placeholder)"""
    logger.info("Eseguo controllo prezzi...")
    # Qui più avanti metti scraping o API Amazon


# --- MAIN ---

def main():
    application = Application.builder().token(TOKEN).build()

    # Comandi
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("add", add_product))
    application.add_handler(CommandHandler("list", list_products))
    application.add_handler(CommandHandler("send", send_message))

    # Job queue ogni 60 secondi
    job_queue = application.job_queue
    job_queue.run_repeating(price_checker, interval=60, first=5)

    # Avvia il bot
    application.run_polling()


if __name__ == "__main__":
    main()