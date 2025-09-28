import os
import asyncio
import logging
import requests
from bs4 import BeautifulSoup
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Token del bot
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHANNEL_ID = "@pokemonmonitorpanda"  # canale dove inviare le notifiche

# Dizionario prodotti: {ASIN: {"url": ..., "price": ..., "title": ..., "image": ...}}
products = {}

# Funzione per ottenere dati prodotto da Amazon
def get_amazon_data(url):
    headers = {"User-Agent": "Mozilla/5.0"}
    r = requests.get(url, headers=headers)
    soup = BeautifulSoup(r.text, "html.parser")

    # Titolo
    title = soup.find("span", {"id": "productTitle"})
    title = title.get_text(strip=True) if title else "Prodotto sconosciuto"

    # Prezzo
    price_tag = soup.find("span", {"class": "a-price-whole"})
    price = None
    if price_tag:
        try:
            price = float(price_tag.get_text(strip=True).replace(".", "").replace(",", "."))
        except:
            price = None

    # Immagine
    img_tag = soup.find("img", {"id": "landingImage"})
    image = img_tag["src"] if img_tag else None

    return title, price, image

# Funzione add prodotto
async def add_product(update, context):
    try:
        url = context.args[0]
        price_limit = float(context.args[1])
    except:
        await update.message.reply_text("❌ Usa: /add <link_amazon> <prezzo_max>")
        return

    if "/dp/" not in url:
        await update.message.reply_text("❌ Link Amazon non valido")
        return

    asin = url.split("/dp/")[1].split("/")[0]
    title, price, image = get_amazon_data(url)

    products[asin] = {"url": url, "price": price_limit, "title": title, "image": image}
    await update.message.reply_text(f"✅ Prodotto aggiunto:\n{title}\n💶 Soglia: {price_limit}€")

# Funzione remove prodotto
async def remove_product(update, context):
    try:
        asin = context.args[0]
    except:
        await update.message.reply_text("❌ Usa: /remove <ASIN>")
        return

    if asin in products:
        del products[asin]
        await update.message.reply_text(f"🗑 Prodotto {asin} rimosso")
    else:
        await update.message.reply_text("❌ ASIN non trovato")

# Lista prodotti
async def list_products(update, context):
    if not products:
        await update.message.reply_text("📭 Nessun prodotto monitorato")
        return

    msg = "📋 Prodotti monitorati:\n\n"
    for asin, data in products.items():
        msg += f"- {data['title']} (ASIN: {asin}) → {data['price']}€\n"
    await update.message.reply_text(msg)

# Monitoraggio prezzi
async def check_products(bot):
    while True:
        for asin, data in list(products.items()):
            title, price, image = get_amazon_data(data["url"])
            if price and price <= data["price"]:
                logger.info(f"RESTOCK trovato: {title} a {price}€")

                # Link checkout diretto
                link_x1 = f"https://www.amazon.it/gp/aws/cart/add.html?ASIN.1={asin}&Quantity.1=1"
                link_x2 = f"https://www.amazon.it/gp/aws/cart/add.html?ASIN.1={asin}&Quantity.1=2"

                buttons = [
                    [InlineKeyboardButton("⚡ x1 Acquisto", url=link_x1)],
                    [InlineKeyboardButton("⚡ x2 Acquisto", url=link_x2)]
                ]
                reply_markup = InlineKeyboardMarkup(buttons)

                text = (
                    f"🔥 <b>RESTOCK!</b>\n\n"
                    f"📦 {title}\n"
                    f"🏷 Prezzo: <b>{price}€</b>\n"
                    f"🛒 Venduto da: Amazon\n\n"
                    f"⬇️ Per acquistare clicca sui pulsanti qui sotto"
                )

                try:
                    await bot.send_photo(
                        chat_id=CHANNEL_ID,
                        photo=image if image else "https://i.imgur.com/placeholder.png",
                        caption=text,
                        parse_mode="HTML",
                        reply_markup=reply_markup
                    )
                except Exception as e:
                    logger.error(f"Errore invio messaggio: {e}")

        await asyncio.sleep(5)  # ogni 5 secondi

# Comando help
async def help_cmd(update, context):
    msg = (
        "📌 <b>Comandi disponibili</b>\n\n"
        "/add <link_amazon> <prezzo> → aggiunge un prodotto da monitorare\n"
        "/remove <ASIN> → rimuove un prodotto\n"
        "/list → mostra i prodotti monitorati\n"
        "/help → mostra questo messaggio"
    )
    await update.message.reply_text(msg, parse_mode="HTML")

# Avvio bot
def main():
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("add", add_product))
    application.add_handler(CommandHandler("remove", remove_product))
    application.add_handler(CommandHandler("list", list_products))
    application.add_handler(CommandHandler("help", help_cmd))

    bot = Bot(TOKEN)
    application.job_queue.run_once(lambda _: asyncio.create_task(check_products(bot)), when=1)

    application.run_polling()

if __name__ == "__main__":
    main()