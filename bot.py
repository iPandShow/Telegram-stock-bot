import requests
import time
import json
import threading
from bs4 import BeautifulSoup
import telebot

# 🔑 CONFIGURAZIONE BOT
TOKEN = "8439643050:AAFDDtpLXRMlFL26RUdTio-SgctR0BvHdMc"
CHAT_ID = "@pokemonmonitorpanda"

bot = telebot.TeleBot(TOKEN)
DATA_FILE = "prodotti.json"

# Carica i prodotti salvati o crea file vuoto
try:
    with open(DATA_FILE, "r") as f:
        prodotti = json.load(f)
except:
    prodotti = {}
    with open(DATA_FILE, "w") as f:
        json.dump(prodotti, f)

def salva_prodotti():
    with open(DATA_FILE, "w") as f:
        json.dump(prodotti, f, indent=2)

def check_prodotto(url, prezzo_max):
    """Controlla disponibilità e prezzo di un prodotto"""
    headers = {"User-Agent": "Mozilla/5.0"}
    r = requests.get(url, headers=headers)
    soup = BeautifulSoup(r.text, "html.parser")

    prezzo_elem = soup.select_one("span.a-price-whole")
    if not prezzo_elem:
        return None, False

    prezzo_str = prezzo_elem.get_text().replace(".", "").replace(",", ".")
    try:
        prezzo = float(prezzo_str)
    except:
        return None, False

    disponibile = "Aggiungi al carrello" in r.text or "Disponibile" in r.text
    return prezzo, disponibile and prezzo <= prezzo_max

def worker():
    """Loop che controlla i prodotti ogni minuto"""
    while True:
        for url, prezzo_max in prodotti.items():
            prezzo, ok = check_prodotto(url, prezzo_max)
            if ok:
                keyboard = {
                    "inline_keyboard": [
                        [{"text": "x1 Acquisto ⚡", "url": url}],
                        [{"text": "x2 Acquisto ⚡", "url": url}]
                    ]
                }
                bot.send_message(
                    CHAT_ID,
                    f"🔥 RESTOCK!\n\nDisponibile a {prezzo}€ 🚀\n{url}",
                    reply_markup=keyboard
                )
        time.sleep(60)  # ricontrolla ogni minuto

# -------------------- COMANDI --------------------

@bot.message_handler(commands=["start"])
def start(message):
    bot.reply_to(message, "Ciao 👋 Usa /aggiungi <link> <prezzo>, /lista o /rimuovi <link>.")

@bot.message_handler(commands=["aggiungi"])
def aggiungi(message):
    try:
        _, url, prezzo = message.text.split()
        prezzo = float(prezzo)
        prodotti[url] = prezzo
        salva_prodotti()
        bot.reply_to(message, f"✅ Aggiunto:\n{url}\nPrezzo max: {prezzo}€")
    except:
        bot.reply_to(message, "❌ Usa il formato: /aggiungi <link> <prezzo>")

@bot.message_handler(commands=["lista"])
def lista(message):
    if not prodotti:
        bot.reply_to(message, "📭 Nessun prodotto in lista.")
        return
    risposta = "📌 Prodotti monitorati:\n\n"
    for url, prezzo in prodotti.items():
        risposta += f"- {url} (max {prezzo}€)\n"
    bot.reply_to(message, risposta)

@bot.message_handler(commands=["rimuovi"])
def rimuovi(message):
    try:
        _, url = message.text.split()
        if url in prodotti:
            del prodotti[url]
            salva_prodotti()
            bot.reply_to(message, f"🗑️ Rimosso: {url}")
        else:
            bot.reply_to(message, "❌ Link non trovato in lista.")
    except:
        bot.reply_to(message, "❌ Usa il formato: /rimuovi <link>")

# -------------------- AVVIO --------------------
threading.Thread(target=worker, daemon=True).start()
bot.polling()