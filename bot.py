import os
import json
import logging
import requests
from bs4 import BeautifulSoup
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes

# Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Token e ID canale dal Railway
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID", "@pokemonmonitorpanda")

# Link collegati
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
def get_price_asin_offering(url):
    """Estrae prezzo, asin e offeringID se disponibile"""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")

        # Prezzo
        price = None
        selectors = [
            ("span", {"class": "a-price-whole"}),
            ("span", {"class": "a-offscreen"}),
            ("span", {"data-a-size": "l"}),
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

        # offeringID
        offeringID = None
        html = r.text
        if "offeringID" in html:
            import re
            match = re.search(r"offeringID=([A-Za-z0-9%]+)", html)
            if match:
                offeringID = match.group(1)

        return price, asin, offeringID
    except Exception as e:
        logger.error(f"Errore scraping {url}: {e}")
        return None, None, None


def build_checkout_links(asin, offeringID, tag="romoloepicc00-21"):
    """Costruisce i due link checkout rapidi"""
    base = "https://www.amazon.it/gp/checkoutportal/enter-checkout.html/ref=dp_mw_buy_now"
    return [
        f"{base}?asin={asin}&offeringID={offeringID}&buyNow=1&quantity=1&tag={tag}",
        f"{base}?asin={asin}&offeringID={offeringID}&buyNow=1&quantity=2&tag={tag}"
    ]


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

    price, asin, offeringID = get_price_asin_offering(url)

    products = load_products()
    products.append({
        "url": url,
        "target": target_price,
        "asin": asin,
        "offeringID": offeringID
    })
    save_products(products)

    await update.message.reply_text(
        f"✅ Prodotto aggiunto!\n{url}\n🎯 Target: {target_price}€\n"
        f"ASIN: {asin}\nOfferingID: {offeringID if offeringID else '❌ non trovato'}"
    )


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


async def send_to_channel(p, test=False, price=None):
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

    # Pulsante invito amici (inoltro del canale)
    buttons.append([
        InlineKeyboardButton("👥 Invita amici", switch_inline_query="Unisciti a @pokemonmonitorpanda 🔥")
    ])
    reply_markup = InlineKeyboardMarkup(buttons)

    text = "🐼 **Pokémon Monitor Panda** 🐼\n\n"
    text += "🔥 **RESTOCK TROVATO!** 🔥\n\n" if not test else "🛠 **TEST RESTOCK**\n\n"
    text += f"📦 *Prodotto:* [Link Amazon]({p['url']})\n"
    text += f"🎯 *Prezzo target:* {p['target']}€\n"
    if price:
        text += f"💶 *Prezzo attuale:* {price}€\n\n"

    text += "🛒 *Per acquistare durante il restock clicca i pulsanti qui sotto!*\n\n"
    text += f"💬 [Unisciti alla chat]({CHAT_LINK})"

    return text, reply_markup


async def test_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    text, reply_markup = await send_to_channel(p, test=True)

    # ✅ invia SOLO nel canale
    await context.bot.send_message(chat_id=CHANNEL_ID, text=text, reply_markup=reply_markup, parse_mode="Markdown")
    await update.message.reply_text("✅ Messaggio test inviato al canale!")


# --- JOB AUTOMATICO ---
async def price_checker(context: ContextTypes.DEFAULT_TYPE):
    products = load_products()
    if not products:
        return

    for p in products:
        price, asin, offeringID = get_price_asin_offering(p["url"])
        if price is None:
            continue

        if price <= p["target"]:
            if asin:
                p["asin"] = asin
            if offeringID:
                p["offeringID"] = offeringID
            save_products(products)

            text, reply_markup = await send_to_channel(p, price=price)
            # ✅ invia SOLO nel canale
            await context.bot.send_message(chat_id=CHANNEL_ID, text=text, reply_markup=reply_markup, parse_mode="Markdown")


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
    job_queue.run_repeating(price_checker, interval=60, first=10)

    application.run_polling()


if __name__ == "__main__":
    main()