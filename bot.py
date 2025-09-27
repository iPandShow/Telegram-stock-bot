import requests
import time
from bs4 import BeautifulSoup
import telebot

# Configura i tuoi dati
TOKEN = "INSERISCI_IL_TUO_TOKEN"   # <-- da @BotFather
CHAT_ID = "455570062"              # <-- tuo ID
URL = "https://www.amazon.it/dp/XXXXXXXX"  # link prodotto
PREZZO_MIN = 25.0
PREZZO_MAX = 35.0

bot = telebot.TeleBot(TOKEN)

def check_prodotto():
    headers = {"User-Agent": "Mozilla/5.0"}
    r = requests.get(URL, headers=headers)
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
    return prezzo, disponibile

while True:
    prezzo, disponibile = check_prodotto()
    if disponibile and prezzo and PREZZO_MIN <= prezzo <= PREZZO_MAX:
        keyboard = {
            "inline_keyboard": [
                [{"text": "x1 Acquisto ⚡", "url": URL}],
                [{"text": "x2 Acquisto ⚡", "url": URL}]
            ]
        }
        bot.send_message(
            CHAT_ID,
            f"🔥 RESTOCK!\n\nProdotto disponibile a {prezzo}€ 🚀",
            reply_markup=keyboard
        )
        time.sleep(600)  # aspetta 10 min
    else:
        time.sleep(60)   # ricontrolla ogni min
