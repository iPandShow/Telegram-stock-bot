import os
from telegram.ext import Application, CommandHandler

# Legge il token da Railway (variabile TELEGRAM_TOKEN)
TOKEN = os.getenv("TELEGRAM_TOKEN")

async def start(update, context):
    await update.message.reply_text("Ciao! Sono MonitorPikemonPanda 🐼")

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    print("Bot avviato...")
    app.run_polling()

if __name__ == "__main__":
    main()