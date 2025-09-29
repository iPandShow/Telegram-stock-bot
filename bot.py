import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import Application, MessageHandler, filters
import re
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID")

# 🔗 Funzione per creare link checkout rapidi
def build_checkout_links(asin, offeringID):
    base_url = "https://www.amazon.it/gp/aws/cart/add.html"
    x1 = f"{base_url}?ASIN.{asin}=1&OfferListingId.{asin}={offeringID}&Quantity.{asin}=1"
    x2 = f"{base_url}?ASIN.{asin}=1&OfferListingId.{asin}={offeringID}&Quantity.{asin}=2"
    return [x1, x2]

# 🎨 Funzione per formattare il messaggio
async def send_to_channel(p, test=False, price=None):
    asin = p.get("asin")
    offeringID = p.get("offeringID")
    buttons = []

    # ✅ Pulsanti acquisto
    if asin and offeringID:
        links = build_checkout_links(asin, offeringID)
        buttons.append([
            InlineKeyboardButton("⚡ x1 Acquisto Lampo", url=links[0]),
            InlineKeyboardButton("⚡ x2 Acquisto Lampo", url=links[1])
        ])
    else:
        buttons.append([
            InlineKeyboardButton("🔗 Vai al prodotto", url=p["url"])
        ])

    reply_markup = InlineKeyboardMarkup(buttons)

    # 📝 Testo accattivante con link testuali
    text = "🚨 **RESTOCK LAMPO!** 🚨\n\n"
    text += f"🎁 **Prodotto:** {p['url']}\n"
    text += "📦 **Venduto da:** Amazon\n"
    text += f"🎯 **Target:** {p['target']}€\n"
    if price:
        text += f"💶 **Prezzo attuale:** {price}€\n"

    text += "\n⚡ Non lasciartelo scappare!\n"
    text += "👉 Usa i pulsanti qui sotto per un acquisto lampo!\n\n"

    # 🔗 Link testuali per la community
    text += "💬 Vuoi commentare insieme a noi? [Unisciti alla Chat](https://t.me/pokemonmonitorpandachat)\n"
    text += "📢 Porta un amico nel canale: [Invita qui](https://t.me/pokemonmonitorpanda)\n"

    return text, reply_markup

# 🛠 Gestore messaggi
async def handle_message(update, context):
    message = update.message.text
    logger.info(f"Messaggio ricevuto: {message}")

    amazon_url_pattern = r"(https?://(?:www\.)?amazon\.[a-z]{2,3}/[^\s]+)"
    match = re.search(amazon_url_pattern, message)

    if match:
        url = match.group(1)
        p = {
            "asin": "FAKEASIN123",  # 👉 qui in futuro da estrarre davvero
            "offeringID": "FAKEOFFER456",  # 👉 idem sopra
            "url": url,
            "target": "29.99"
        }

        text, reply_markup = await send_to_channel(p, price="29.99")
        bot: Bot = context.bot
        await bot.send_message(
            chat_id=CHANNEL_ID,
            text=text,
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )

# 🚀 Avvio bot
def main():
    application = Application.builder().token(TOKEN).build()
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.run_polling()

if __name__ == "__main__":
    main()