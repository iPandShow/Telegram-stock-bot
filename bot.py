import logging
import requests
from bs4 import BeautifulSoup
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)
import os

# =====================
# Logging
# =====================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")

# Placeholder se non troviamo immagine
PLACEHOLDER_IMG = "https://i.imgur.com/8fKQZt6.png"

# Dizionario prodotti {url: {max_price, title}}
products = {}

# =====================
# Funzione scraping Amazon
# =====================
def scrape_amazon(url: str):
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            logging.warning(f"Amazon risposta {response.status_code}")
            return None

        soup = BeautifulSoup(response.text, "lxml")

        # Titolo
        title = soup.find("span", {"id": "productTitle"})
        title = title.get_text(strip=True) if title else "Prodotto sconosciuto"

        # Prezzo
        price_whole = soup.find("span", {"class": "a-price-whole"})
        price_frac = soup.find("span", {"class": "a-price-fraction"})
        if price_whole:
            price_str = price_whole.get_text().replace(".", "").replace(",", ".")
            price = float(price_str + (price_frac.get_text() if price_frac else "0"))
        else:
            price = None

        # Immagine
        img_tag = soup.find("img", {"id": "landingImage"})
        image_url = img_tag["src"] if img_tag else PLACEHOLDER_IMG

        return {"title": title, "price": price, "image": image_url}
    except Exception as e:
        logging.error(f"Errore scraping: {e}")
        return None

# =====================
# Aggiungi prodotto
# =====================
async def add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("Usa: /add <url> <prezzo_max>")
        return

    url = context.args[0]
    try:
        max_price = float(context.args[1])
    except ValueError:
        await update.message.reply_text("Prezzo non valido.")
        return

    data = scrape_amazon(url)
    if not data:
        await update.message.reply_text("Errore durante lo scraping.")
        return

    products[url] = {"max_price": max_price, "title": data["title"]}
    await update.message.reply_text(
        f"✅ Aggiunto:\n<b>{data['title']}</b>\n💶 Prezzo max: {max_price}€",
        parse_mode="HTML"
    )

# =====================
# Rimuovi prodotto
# =====================
async def remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usa: /remove <url>")
        return
    url = context.args[0]
    if url in products:
        del products[url]
        await update.message.reply_text("🗑️ Prodotto rimosso.")
    else:
        await update.message.reply_text("Prodotto non trovato.")

# =====================
# Lista prodotti
# =====================
async def list_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not products:
        await update.message.reply_text("Nessun prodotto monitorato.")
        return
    msg = "📋 <b>Prodotti monitorati:</b>\n\n"
    for url, data in products.items():
        msg += f"🔗 {data['title']}\n💶 max {data['max_price']}€\n{url}\n\n"
    await update.message.reply_text(msg, parse_mode="HTML")

# =====================
# Comandi disponibili
# =====================
async def commands(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "🤖 <b>Comandi disponibili</b>\n\n"
        "/add <url> <prezzo> → aggiungi prodotto\n"
        "/remove <url> → rimuovi prodotto\n"
        "/list → lista prodotti monitorati\n"
        "/commands → mostra questo messaggio"
    )
    await update.message.reply_text(msg, parse_mode="HTML")

# =====================
# Check prezzi periodici
# =====================
async def check_prices(context: ContextTypes.DEFAULT_TYPE):
    for url, data in products.items():
        scraped = scrape_amazon(url)
        if not scraped or not scraped["price"]:
            continue

        if scraped["price"] <= data["max_price"]:
            text = (
                f"🔥 <b>RESTOCK!</b>\n\n"
                f"{scraped['title']}\n"
                f"💶 Prezzo: <b>{scraped['price']}€</b>\n"
                f"🏬 Venduto da: Amazon\n\n"
                f"🔗 Per acquistare durante un Restock:\n"
                f"⬇️ Clicca sui pulsanti qui sotto 👇"
            )

            keyboard = [
                [InlineKeyboardButton("⚡ x1 Acquisto", url=f"{url}?quantity=1&buy-now=1")],
                [InlineKeyboardButton("⚡ x2 Acquisto", url=f"{url}?quantity=2&buy-now=1")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            try:
                await context.bot.send_photo(
                    chat_id=CHANNEL_ID,
                    photo=scraped["image"],
                    caption=text,
                    parse_mode="HTML",
                    reply_markup=reply_markup
                )
            except Exception as e:
                logging.error(f"Errore invio messaggio: {e}")

# =====================
# Main
# =====================
def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("add", add))
    app.add_handler(CommandHandler("remove", remove))
    app.add_handler(CommandHandler("list", list_products))
    app.add_handler(CommandHandler("commands", commands))

    # Controlla prezzi ogni 5 secondi
    app.job_queue.run_repeating(check_prices, interval=5, first=5)

    app.run_polling()

if __name__ == "__main__":
    main()