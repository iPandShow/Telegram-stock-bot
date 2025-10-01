# bot.py
import os
import json
import logging
import re
import requests
from urllib.parse import quote_plus
from bs4 import BeautifulSoup
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

# ──────────────────────────────────────────────────────────────────────────────
# Logging
# ──────────────────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("panda-bot")

# ──────────────────────────────────────────────────────────────────────────────
# Config (SOLO TOKEN in env)
# ──────────────────────────────────────────────────────────────────────────────
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")  # <-- unica variabile richiesta

# Username del canale (il bot invierà SOLO qui)
CHANNEL_USERNAME = "pokemonmonitorpanda"
CHANNEL_ID = None  # risolto a runtime

# Link testuale alla chat
CHAT_LINK = "https://t.me/pokemonmonitorpandachat"

# File prodotti
PRODUCTS_FILE = "products.json"

# Immagine di fallback
PLACEHOLDER_IMG = "https://i.imgur.com/8fKQZt6.png"

# ──────────────────────────────────────────────────────────────────────────────
# Utilità: storage
# ──────────────────────────────────────────────────────────────────────────────
def load_products():
    if not os.path.exists(PRODUCTS_FILE):
        return []
    try:
        with open(PRODUCTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_products(products):
    with open(PRODUCTS_FILE, "w", encoding="utf-8") as f:
        json.dump(products, f, indent=2, ensure_ascii=False)


# ──────────────────────────────────────────────────────────────────────────────
# Scraping Amazon (best effort, senza login)
# ──────────────────────────────────────────────────────────────────────────────
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0 Safari/537.36"
    )
}


def extract_asin(url: str) -> str | None:
    if "/dp/" in url:
        return url.split("/dp/")[1].split("/")[0].split("?")[0]
    if "/d/" in url:
        return url.split("/d/")[1].split("/")[0].split("?")[0]
    m = re.search(r"[?&]asin=([A-Z0-9]{10})", url)
    return m.group(1) if m else None


def scrape_amazon(url: str) -> dict:
    """Ritorna dict: title, price (float|None), image, asin, offeringID."""
    data = {"title": None, "price": None, "image": PLACEHOLDER_IMG, "asin": extract_asin(url), "offeringID": None}
    try:
        r = requests.get(url, headers=HEADERS, timeout=12)
        r.raise_for_status()
        html = r.text
        soup = BeautifulSoup(html, "html.parser")

        # Titolo
        title = soup.find("span", {"id": "productTitle"})
        if not title:
            ogt = soup.find("meta", {"property": "og:title"})
            title = ogt["content"] if ogt and ogt.get("content") else None
        else:
            title = title.get_text(strip=True)
        if title:
            data["title"] = title

        # Prezzo
        candidates = [
            ("span", {"class": "a-price-whole"}),
            ("span", {"class": "a-offscreen"}),
            ("span", {"data-a-size": "l"}),
            ("span", {"data-a-color": "price"}),
        ]
        for tag, attrs in candidates:
            el = soup.find(tag, attrs=attrs)
            if el:
                txt = el.get_text().replace("€", "").replace(".", "").replace(",", ".").strip()
                try:
                    price = float(txt)
                    data["price"] = price
                    break
                except Exception:
                    pass

        # Immagine
        img = soup.find("img", {"id": "landingImage"})
        if not img:
            ogimg = soup.find("meta", {"property": "og:image"})
            if ogimg and ogimg.get("content"):
                data["image"] = ogimg["content"]
        else:
            data["image"] = img.get("src", PLACEHOLDER_IMG)

        # offeringID (se visibile in pagina)
        m = re.search(r"offeringID=([A-Za-z0-9%]+)", html)
        if m:
            data["offeringID"] = m.group(1)

    except Exception as e:
        logger.warning(f"Scraping fallito: {e}")

    return data


def build_checkout_links(asin: str, offering_id: str, tag: str = "romoloepicc00-21") -> tuple[str, str]:
    base = "https://www.amazon.it/gp/checkoutportal/enter-checkout.html/ref=dp_mw_buy_now"
    x1 = f"{base}?asin={asin}&offeringID={offering_id}&buyNow=1&quantity=1&tag={tag}"
    x2 = f"{base}?asin={asin}&offeringID={offering_id}&buyNow=1&quantity=2&tag={tag}"
    return x1, x2


def share_button() -> InlineKeyboardButton:
    share_url = "https://t.me/share/url?url=" + quote_plus("https://t.me/pokemonmonitorpanda") + \
                "&text=" + quote_plus("🔥 Unisciti a Pokémon Monitor Panda! Restock e offerte in tempo reale.")
    return InlineKeyboardButton("👥 Condividi / Invita amici", url=share_url)


# ──────────────────────────────────────────────────────────────────────────────
# Testo messaggio (HTML)
# ──────────────────────────────────────────────────────────────────────────────
def render_caption(url: str, title: str | None, price: float | None) -> str:
    title_line = title if title else "Prodotto Amazon"
    price_line = f"\n💶 <b>Prezzo attuale:</b> {price:.2f}€" if price is not None else ""
    caption = (
        "🐼 <b>POKÉMON MONITOR PANDA</b>\n"
        "🔥 <b>RESTOCK!</b>\n\n"
        f"📦 <b>Prodotto:</b> {title_line}\n"
        "🏪 <b>Venduto da:</b> Amazon"
        f"{price_line}\n\n"
        f"🔗 <a href=\"{url}\">Apri su Amazon</a>\n\n"
        "🛒 <i>Per acquistare durante un restock usa i pulsanti qui sotto.</i>\n\n"
        f"💬 <a href=\"{CHAT_LINK}\">Unisciti alla chat</a>"
    )
    return caption


# ──────────────────────────────────────────────────────────────────────────────
# Invio nel canale (unico posto dove il bot pubblica)
# ──────────────────────────────────────────────────────────────────────────────
async def post_to_channel(context: ContextTypes.DEFAULT_TYPE, url: str, test: bool = False):
    # Dati live dal prodotto (titolo, immagine, prezzo, asin/offering)
    info = scrape_amazon(url)
    asin = info.get("asin")
    offering = info.get("offeringID")

    # Pulsanti acquisto
    rows = []
    if asin and offering:
        x1, x2 = build_checkout_links(asin, offering)
        rows.append([
            InlineKeyboardButton("⚡ x1 Acquisto", url=x1),
            InlineKeyboardButton("⚡ x2 Acquisto", url=x2),
        ])
    else:
        rows.append([InlineKeyboardButton("🔗 Vai al prodotto", url=url)])

    # Pulsante condividi
    rows.append([share_button()])
    markup = InlineKeyboardMarkup(rows)

    # Testo/Caption
    caption = render_caption(url=url, title=info.get("title"), price=info.get("price"))

    # Identifica canale
    chat_id = CHANNEL_ID if CHANNEL_ID is not None else f"@{CHANNEL_USERNAME}"

    # Invio come foto (se disponibile) così i pulsanti stanno sotto l’immagine
    photo_url = info.get("image") or PLACEHOLDER_IMG
    try:
        await context.bot.send_photo(
            chat_id=chat_id,
            photo=photo_url,
            caption=caption,
            parse_mode="HTML",
            reply_markup=markup,
        )
    except Exception as e:
        logger.warning(f"send_photo fallito ({e}), provo send_message…")
        await context.bot.send_message(
            chat_id=chat_id,
            text=caption,
            parse_mode="HTML",
            reply_markup=markup,
        )


# ──────────────────────────────────────────────────────────────────────────────
# Comandi
# ──────────────────────────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Ciao! Sono il bot di 🐼 Pokémon Monitor Panda.\n"
        "Usa /help per i comandi."
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📋 <b>Comandi</b>\n"
        "/add &lt;link&gt; &lt;prezzo&gt; – Aggiungi un prodotto\n"
        "/list – Elenco prodotti salvati\n"
        "/remove &lt;id&gt; – Rimuovi prodotto\n"
        "/test &lt;id&gt; – Invio di prova al canale",
        parse_mode="HTML",
    )


async def add_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("⚠️ Usa: /add <link> <prezzo>")
        return

    url = context.args[0]
    try:
        target = float(context.args[1])
    except ValueError:
        await update.message.reply_text("⚠️ Il prezzo deve essere un numero (es. 149.99).")
        return

    # Scrape veloce per salvare asin/offering (se disponibili ora)
    info = scrape_amazon(url)

    products = load_products()
    products.append({
        "url": url,
        "target": target,             # non verrà mostrato nei post
        "asin": info.get("asin"),
        "offeringID": info.get("offeringID"),
    })
    save_products(products)

    await update.message.reply_text(
        f"✅ Prodotto aggiunto!\n{url}\n"
        f"ASIN: {info.get('asin') or '—'} | offeringID: {info.get('offeringID') or '—'}"
    )


async def list_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    items = load_products()
    if not items:
        await update.message.reply_text("📦 Nessun prodotto salvato.")
        return

    msg = ["📋 <b>Prodotti monitorati</b>\n"]
    for i, p in enumerate(items, start=1):
        msg.append(f"{i}. <a href=\"{p['url']}\">link</a>  (🎯 {p['target']}€)")
    await update.message.reply_text("\n".join(msg), parse_mode="HTML", disable_web_page_preview=True)


async def remove_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ Usa: /remove <id>")
        return
    try:
        idx = int(context.args[0]) - 1
    except ValueError:
        await update.message.reply_text("⚠️ L'ID deve essere un numero.")
        return

    items = load_products()
    if idx < 0 or idx >= len(items):
        await update.message.reply_text("❌ ID non valido.")
        return

    removed = items.pop(idx)
    save_products(items)
    await update.message.reply_text(f"✅ Prodotto rimosso:\n{removed['url']}")


async def test_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Invia al canale il prodotto in posizione <id> (sempre e comunque)."""
    if not context.args:
        await update.message.reply_text("⚠️ Usa: /test <id>")
        return
    try:
        idx = int(context.args[0]) - 1
    except ValueError:
        await update.message.reply_text("⚠️ L'ID deve essere un numero.")
        return

    items = load_products()
    if idx < 0 or idx >= len(items):
        await update.message.reply_text("❌ ID non valido.")
        return

    url = items[idx]["url"]
    await post_to_channel(context, url, test=True)
    await update.message.reply_text("✅ Messaggio di test inviato al canale.")


# ──────────────────────────────────────────────────────────────────────────────
# Job periodico: controlla prezzi e pubblica
# ──────────────────────────────────────────────────────────────────────────────
async def price_checker(context: ContextTypes.DEFAULT_TYPE):
    items = load_products()
    if not items:
        return

    for p in items:
        try:
            info = scrape_amazon(p["url"])
            price = info.get("price")
            target = p.get("target")
            if price is not None and target is not None and price <= float(target):
                await post_to_channel(context, p["url"], test=False)
        except Exception as e:
            logger.warning(f"Errore checker su {p.get('url')}: {e}")


# ──────────────────────────────────────────────────────────────────────────────
# Inizializzazione: risolviamo l'ID numerico del canale
# ──────────────────────────────────────────────────────────────────────────────
async def _post_init(app: Application):
    global CHANNEL_ID
    try:
        chat = await app.bot.get_chat(f"@{CHANNEL_USERNAME}")
        CHANNEL_ID = chat.id
        logger.info(f"Canale risolto: @{CHANNEL_USERNAME} -> {CHANNEL_ID}")
    except Exception as e:
        CHANNEL_ID = None
        logger.warning(f"Impossibile risolvere ID canale, userò @{CHANNEL_USERNAME}. Dettagli: {e}")


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────
def main():
    if not TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN non impostato.")

    app = Application.builder().token(TOKEN).post_init(_post_init).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("add", add_cmd))
    app.add_handler(CommandHandler("list", list_cmd))
    app.add_handler(CommandHandler("remove", remove_cmd))
    app.add_handler(CommandHandler("test", test_cmd))

    app.job_queue.run_repeating(price_checker, interval=60, first=10)

    app.run_polling(allowed_updates=["message", "edited_message"])

if __name__ == "__main__":
    main()