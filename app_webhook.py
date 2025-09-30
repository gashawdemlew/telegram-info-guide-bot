import os
import logging
import asyncio
from flask import Flask, request

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from google import genai
from google.genai.errors import APIError

# ----------------------------
# Logging configuration
# ----------------------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ----------------------------
# Environment Variables / Config
# ----------------------------
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # e.g., https://<your-service>.onrender.com/webhook
CHAT_SESSION_KEY = "gemini_chat_session"

GEMINI_MODEL = "gemini-2.0-flash-lite"
SYSTEM_PROMPT = (
    "You are a helpful and friendly Telegram bot. "
    "You remember the conversation history. "
    "Provide concise and informative responses."
)

# ----------------------------
# Initialize Gemini Client
# ----------------------------
ai_client = None
try:
    if not GEMINI_API_KEY:
        logger.warning("GEMINI_API_KEY is not set. AI responses may fail.")
    ai_client = genai.Client(api_key=GEMINI_API_KEY)
    logger.info("Gemini client initialized.")
except Exception as e:
    logger.critical(f"Failed to initialize Gemini client: {e}")

# ----------------------------
# Helper: Manage Gemini chat sessions
# ----------------------------
def get_or_create_chat(context: ContextTypes.DEFAULT_TYPE, user_id: int):
    if ai_client is None:
        return None
    if CHAT_SESSION_KEY not in context.user_data:
        chat = ai_client.chats.create(
            model=GEMINI_MODEL,
            config=genai.types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT),
        )
        context.user_data[CHAT_SESSION_KEY] = chat
    return context.user_data[CHAT_SESSION_KEY]

# ----------------------------
# Telegram Handlers
# ----------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_name = update.effective_user.first_name
    await update.message.reply_text(
        f"Hello, {user_name}! I am an AI bot powered by Gemini (webhook mode)."
    )

async def new_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if CHAT_SESSION_KEY in context.user_data:
        del context.user_data[CHAT_SESSION_KEY]
        await update.message.reply_text("Conversation memory has been reset!")
    else:
        await update.message.reply_text("You are already starting a new chat!")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_message = update.message.text
    user_id = update.effective_user.id
    chat_id = update.message.chat_id

    if ai_client is None:
        await update.message.reply_text("AI service not configured.")
        return

    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    try:
        chat_session = get_or_create_chat(context, user_id)
        response = chat_session.send_message(user_message)
        reply_text = response.text or "🤖 (Empty response from Gemini.)"
        await update.message.reply_text(reply_text)
    except APIError as e:
        logger.error(f"Gemini API Error: {e}")
        await update.message.reply_text(
            "⚠️ Gemini is a bit tired right now. Please try again shortly!"
        )
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        await update.message.reply_text(
            "😅 Something went wrong, but I’m still here! Try again?"
        )

# ----------------------------
# Telegram Application
# ----------------------------
application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("new_chat", new_chat))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

# ----------------------------
# Flask App for Render
# ----------------------------
flask_app = Flask(__name__)

@flask_app.route("/")
def index():
    return "Bot is running (webhook mode)."

@flask_app.route("/health")
def health():
    return {"status": "ok"}

@flask_app.route("/webhook", methods=["POST"])
def webhook():
    """Handle incoming Telegram updates from webhook."""
    update = Update.de_json(request.get_json(force=True), application.bot)
    application.update_queue.put_nowait(update)
    return {"status": "ok"}

# ----------------------------
# Start the bot in webhook mode
# ----------------------------
async def start_webhook():
    if not WEBHOOK_URL:
        logger.error("WEBHOOK_URL is not set. Please configure it in Render.")
        return

    await application.initialize()
    await application.bot.set_webhook(url=WEBHOOK_URL, drop_pending_updates=True)
    logger.info(f"Webhook set to {WEBHOOK_URL}")

    # Start the background task to process updates
    await application.start()
    logger.info("Telegram bot application started in webhook mode.")

# ----------------------------
# Entrypoint
# ----------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))

    # Start Telegram bot in background asyncio task
    loop = asyncio.get_event_loop()
    loop.create_task(start_webhook())

    # Start Flask server
    flask_app.run(host="0.0.0.0", port=port)
