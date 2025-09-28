import logging
import requests
from bs4 import BeautifulSoup
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler, JobQueue
import os
import asyncio

# Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")

# Placeholder se non troviamo immagine
PLACEHOLDER_IMG = "https://i.imgur.com/8fKQZt6.png"

# Lista prodotti {url, prezzo, titolo}
products = {}

# =====================
# Funzione scraping Amazon
# =====================
def scrape_amazon(url: str):
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, "lxml")

        title = soup.find("span", {"id": "productTitle"})
        title = title.get_text(strip=True) if title else "Prodotto sconosciuto"

        price_whole = soup.find("span", {"class": "a-price-whole"})
        price_frac = soup.find("span", {"class": "a-price-fraction"})
        if price_whole:
            price = float(price_whole.get_text().replace(".", "").replace(",", ".") +
                          (price_frac.get_text() if price_frac else "0"))
        else:
            price = None

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
    await update.message.reply_text(f"✅ Aggiunto:\n{data['title']}\nPrezzo max: {max_price}€")

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
    msg = "📋 Prodotti monitorati:\n"
    for url, data in products.items():
        msg += f"- {data['title']} (max {data['max_price']}€)\n"
    await update.message.reply_text(msg)

# =====================
# Comandi disponibili
# =====================
async def commands(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "🤖 Comandi disponibili:\n\n"
        "/add <url> <prezzo> → aggiungi prodotto\n"
        "/remove <url> → rimuovi prodotto\n"
        "/list → lista prodotti monitorati\n"
        "/commands → mostra questo messaggio"
    )
    await update.message.reply_text(msg)

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
                f"💶 Prezzo: {scraped['price']}€\n"
                f"🏬 Venduto da: Amazon\n\n"
                f"🔗 Per acquistare durante un Restock:\n"
                f"⬇️ Clicca sui pulsanti Acquisto Lampo (x1 o x2) qui sotto"
            )

            keyboard = [
                [InlineKeyboardButton("x1 Acquisto ⚡", url=f"{url}?quantity=1&buy-now=1")],
                [InlineKeyboardButton("x2 Acquisto ⚡", url=f"{url}?quantity=2&buy-now=1")]
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

    app.job_queue.run_repeating(check_prices, interval=5, first=5)

    app.run_polling()

if __name__ == "__main__":
    main()