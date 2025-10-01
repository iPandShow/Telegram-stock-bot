import os
import json
import logging
import requests
import html
import re
from bs4 import BeautifulSoup
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes

# Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- VARIABILI PRINCIPALI ---
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")  # variabile unica
CHANNEL_ID = -1002224497186              # ID canale numerico
CHAT_LINK = "https://t.me/pokemonmonitorpandachat"
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
def scrape_amazon(url):
    """Estrae titolo, prezzo, ASIN, offeringID, immagine e venditore"""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")

        # Titolo
        title = None
        title_el = soup.select_one("#productTitle")
        if title_el:
            title = title_el.get_text(strip=True)

        # Prezzo
        price = None
        selectors = [
            ("span", {"class": "a-price-whole"}),
            ("span", {"class": "a-offscreen"}),
            ("span", {"data-a-color": "price"})
        ]
        for tag, attrs in selectors:
            el = soup.find(tag, attrs=attrs)
            if el:
                price_text = el.get_text().replace("€", "").replace(".", "").replace(",", ".").strip()
                try:
                    price = float(price_text)
                    break
                except ValueError:
                    continue

        # ASIN
        asin = None
        if "/dp/" in url:
            asin = url.split("/dp/")[1].split("/")[0]
        elif "/d/" in url:
            asin = url.split("/d/")[1].split("?")[0]

        # OfferingID
        offeringID = None
        if "offeringID" in r.text:
            match = re.search(r"offeringID=([A-Za-z0-9%]+)", r.text)
            if match:
                offeringID = match.group(1)

        # Immagine
        image = None
        img_el = soup.select_one("#landingImage")
        if img_el and img_el.get("src"):
            image = img_el["src"]

        # Venduto da
        sold_by = None
        seller_el = soup.select_one("#merchant-info")
        if seller_el:
            sold_by = seller_el.get_text(strip=True)
        else:
            seller_el = soup.select_one("#tabular-buybox .tabular-buybox-text")
            if seller_el:
                sold_by = seller_el.get_text(strip=True)

        return {
            "url": url,
            "title": title or "Prodotto",
            "price": price,
            "asin": asin,
            "offeringID": offeringID,
            "image": image,
            "sold_by": sold_by or "Amazon"
        }
    except Exception as e:
        logger.error(f"Errore scraping {url}: {e}")
        return {}


def build_checkout_links(asin, offeringID, tag="romoloepicc00-21"):
    """Costruisce i link checkout rapidi"""
    base = "https://www.amazon.it/gp/checkoutportal/enter-checkout.html/ref=dp_mw_buy_now"
    return [
        f"{base}?asin={asin}&offeringID={offeringID}&buyNow=1&quantity=1&tag={tag}",
        f"{base}?asin={asin}&offeringID={offeringID}&buyNow=1&quantity=2&tag={tag}"
    ]


# --- MESSAGGIO CANALE ---
async def send_to_channel(context: ContextTypes.DEFAULT_TYPE, p, test=False):
    asin = p.get("asin")
    offeringID = p.get("offeringID")

    # Pulsanti Amazon
    buttons = []
    if asin and offeringID:
        links = build_checkout_links(asin, offeringID)
        buttons.append([
            InlineKeyboardButton("⚡ x1 Acquisto", url=links[0]),
            InlineKeyboardButton("⚡ x2 Acquisto", url=links[1])
        ])
    else:
        buttons.append([InlineKeyboardButton("🔗 Vai al prodotto", url=p["url"])])

    # Pulsante invito amici
    share_url = "https://t.me/share/url?url=https://t.me/pokemonmonitorpanda&text=🔥 Unisciti a Pokémon Monitor Panda 🔥"
    buttons.append([InlineKeyboardButton("👥 Condividi / Invita amici", url=share_url)])
    reply_markup = InlineKeyboardMarkup(buttons)

    # Testo messaggio elegante
    caption = "🐼 <b>POKÉMON MONITOR PANDA</b>\n"
    caption += "🔥 <b>RESTOCK!</b> 🔥\n\n" if not test else "🛠 <b>TEST RESTOCK</b>\n\n"
    caption += f"📦 <b>Prodotto:</b> {html.escape(p.get('title','Prodotto'))}\n"
    if p.get("price"):
        caption += f"💶 <b>Prezzo:</b> {p['price']}€\n"
    if p.get("sold_by"):
        caption += f"🏷 <b>Venduto da:</b> {p['sold_by']}\n"
    caption += f"\n🔗 <a href=\"{html.escape(p['url'])}\">Apri su Amazon</a>\n\n"
    caption += "🛒 <i>Acquista subito cliccando i pulsanti qui sotto!</i>\n\n"
    caption += f"💬 <a href=\"{html.escape(CHAT_LINK)}\">Unisciti alla chat</a>"

    # Invia con immagine se disponibile
    if p.get("image"):
        await context.bot.send_photo(
            chat_id=CHANNEL_ID,
            photo=p["image"],
            caption=caption,
            reply_markup=reply_markup,
            parse_mode="HTML"
        )
    else:
        await context.bot.send_message(
            chat_id=CHANNEL_ID,
            text=caption,
            reply_markup=reply_markup,
            parse_mode="HTML"
        )


# --- COMANDI ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Ciao! Usa /help per i comandi.")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📋 Comandi:\n"
        "/add <link> - Aggiungi un prodotto\n"
        "/list - Lista prodotti\n"
        "/remove <id> - Rimuovi prodotto\n"
        "/test <id> - Pubblica test nel canale"
    )


async def add_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ Usa: /add <link>")
        return

    url = context.args[0]
    data = scrape_amazon(url)
    if not data:
        await update.message.reply_text("❌ Errore durante scraping.")
        return

    products = load_products()
    products.append(data)
    save_products(products)

    await update.message.reply_text(f"✅ Prodotto aggiunto:\n{data['title']}")


async def list_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    products = load_products()
    if not products:
        await update.message.reply_text("📦 Nessun prodotto salvato.")
        return

    msg = "📋 Prodotti monitorati:\n\n"
    for i, p in enumerate(products, start=1):
        msg += f"{i}. {p['title']} → {p['url']}\n"
    await update.message.reply_text(msg)


async def remove_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ Usa: /remove <id>")
        return

    try:
        idx = int(context.args[0]) - 1
    except ValueError:
        await update.message.reply_text("⚠️ ID non valido.")
        return

    products = load_products()
    if idx < 0 or idx >= len(products):
        await update.message.reply_text("❌ ID non valido.")
        return

    removed = products.pop(idx)
    save_products(products)
    await update.message.reply_text(f"✅ Rimosso: {removed['title']}")


async def test_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ Usa: /test <id>")
        return

    try:
        idx = int(context.args[0]) - 1
    except ValueError:
        await update.message.reply_text("⚠️ ID non valido.")
        return

    products = load_products()
    if idx < 0 or idx >= len(products):
        await update.message.reply_text("❌ ID non valido.")
        return

    p = products[idx]
    await send_to_channel(context, p, test=True)
    await update.message.reply_text("✅ Test inviato nel canale!")


# --- JOB AUTOMATICO ---
async def price_checker(context: ContextTypes.DEFAULT_TYPE):
    products = load_products()
    if not products:
        return

    for p in products:
        data = scrape_amazon(p["url"])
        if not data or not data.get("price"):
            continue

        # Aggiorna info
        p.update(data)
        save_products(products)

        # Pubblica se prezzo trovato
        await send_to_channel(context, p)


# --- MAIN ---
def main():
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("add", add_product))
    application.add_handler(CommandHandler("list", list_products))
    application.add_handler(CommandHandler("remove", remove_product))
    application.add_handler(CommandHandler("test", test_product))

    job_queue = application.job_queue
    job_queue.run_repeating(price_checker, interval=300, first=10)  # ogni 5 min

    application.run_polling()


if __name__ == "__main__":
    main()