import os
import logging
import asyncio
from flask import Flask, request, jsonify
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
import google.generativeai as genai

# ----------------------------
# Logging setup
# ----------------------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ----------------------------
# Environment variables
# ----------------------------
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")  # Example: https://your-app.onrender.com/webhook

if not TELEGRAM_BOT_TOKEN or not GEMINI_API_KEY or not WEBHOOK_URL:
    raise ValueError("Missing TELEGRAM_BOT_TOKEN, GEMINI_API_KEY, or WEBHOOK_URL env vars")

# ----------------------------
# Gemini setup
# ----------------------------
genai.configure(api_key=GEMINI_API_KEY)
gemini_model = genai.GenerativeModel("gemini-1.5-flash")

# ----------------------------
# Telegram handlers
# ----------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hi! I am your info bot 🤖. Ask me anything!")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text
    logger.info(f"User said: {user_message}")

    try:
        response = gemini_model.generate_content(user_message)
        bot_reply = response.text if response and response.text else "Sorry, I couldn't generate a reply."
        await update.message.reply_text(bot_reply)
    except Exception as e:
        logger.error(f"Gemini error: {e}")
        await update.message.reply_text("⚠️ Error while contacting Gemini API.")

# ----------------------------
# Telegram Application
# ----------------------------
application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
application.add_handler(CommandHandler("start", start))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

# ----------------------------
# Flask app
# ----------------------------
flask_app = Flask(__name__)

@flask_app.route("/")
def index():
    return "Bot is running!", 200

@flask_app.route("/health")
def health():
    return jsonify({"status": "ok"}), 200

@flask_app.route("/webhook", methods=["POST"])
def telegram_webhook():
    try:
        update = Update.de_json(request.get_json(force=True), application.bot)
        asyncio.run(application.process_update(update))
    except Exception as e:
        logger.error(f"Error in webhook processing: {e}")
    return "ok", 200

# ----------------------------
# Register webhook on startup
# ----------------------------
async def setup_webhook():
    await application.bot.set_webhook(url=WEBHOOK_URL, drop_pending_updates=True)
    logger.info(f"Webhook registered with Telegram: {WEBHOOK_URL}")

# Run setup_webhook once when app starts
asyncio.get_event_loop().run_until_complete(setup_webhook())

# ----------------------------
# Run Flask app
# ----------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    flask_app.run(host="0.0.0.0", port=port)
