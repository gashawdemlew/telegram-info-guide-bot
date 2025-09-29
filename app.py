import logging
import os
from telegram import Update
# Import changes for modern python-telegram-bot (v20+)
from telegram.ext import (
    Application, # New: Import Application
    CommandHandler, 
    MessageHandler, 
    filters, 
    CallbackContext,
    ApplicationBuilder # New: Import ApplicationBuilder
)

# Install this package: pip install google-genai
from google import genai 
from google.genai.errors import APIError 
# FIX: The Chat object is no longer directly available in a consistent location
# across all minor versions of the SDK (1.39.1). To resolve the ImportError, 
# we remove the specific type hint and rely on the runtime object returned 
# by client.chats.create().
# from google.genai.models import Chat # <-- Removed this problematic import

# Set up logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- CONFIGURATION ---

# Key for storing the persistent chat session in user_data
CHAT_SESSION_KEY = 'gemini_chat_session' 

# 💡 Best Practice: Load tokens/keys from environment variables
# To run this script, replace the '' placeholders with your actual keys, or set them as environment variables.
# 1. TELEGRAM_BOT_TOKEN: Get this from BotFather on Telegram.
# 2. GEMINI_API_KEY: Get this from Google AI Studio.

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '8414128717:AAEEZtTG1ImWUt_0_vCY2U20us9aB0xQeGM')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', 'AIzaSyATN8Q9dBAjuJhvZ7mtupwgl_iY0yZ4VG0')

# GEMINI_MODEL = "gemini-2.5-flash" # The recommended model for fast chat interactions
GEMINI_MODEL = "gemini-2.0-flash-lite" # The recommended model for fast chat interactions
SYSTEM_PROMPT = "You are a helpful and friendly Telegram bot. You remember the conversation history. Provide concise and informative responses."

# --- GEMINI CLIENT SETUP ---
ai_client = None

try:
    # Check if the key is empty. If it is, log a warning, but attempt to initialize (it might use other defaults)
    if not GEMINI_API_KEY:
        logger.warning("GEMINI_API_KEY is unset. AI features may fail. Please set the environment variable or replace the placeholder in the code.")
    
    # Initialize the Gemini client using the API key
    ai_client = genai.Client(api_key=GEMINI_API_KEY)
    logger.info("Gemini client initialized for chat sessions.")
    
except Exception as e:
    logger.critical(f"Failed to initialize Gemini Client. AI features will be disabled: {e}")

# --- HELPER FUNCTION FOR CHAT SESSION MANAGEMENT ---

# Now accepts user_id as a parameter
def get_or_create_chat(context: CallbackContext, user_id: int):
    """Retrieves or creates a Gemini chat session for the current user."""
    
    # 1. Check if a chat session already exists in the user's data
    if ai_client is None:
        logger.error("Cannot create chat: AI client not initialized.")
        return None

    if CHAT_SESSION_KEY not in context.user_data:
        # Use the passed user_id for logging
        logger.info(f"Creating new chat session for user {user_id}")
        
        # 2. Initialize the chat with the model and system instruction
        # Note: client.chats.create() returns the Chat object
        chat = ai_client.chats.create(
            model=GEMINI_MODEL,
            config=genai.types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
            )
        )
        context.user_data[CHAT_SESSION_KEY] = chat
    
    return context.user_data[CHAT_SESSION_KEY]

# --- BOT COMMANDS AND HANDLERS ---

# Note: Handlers use the same (update: Update, context: CallbackContext) signature, 
# which is compatible with the Application handler system.

async def start(update: Update, context: CallbackContext) -> None:
    """Handles the /start command."""
    user_name = update.effective_user.first_name
    # Must await the reply function
    await update.message.reply_text(f'Hello, {user_name}! I am an AI bot powered by Gemini and I remember our conversation. Ask me anything!')

async def new_chat(update: Update, context: CallbackContext) -> None:
    """Handles the /new_chat command to reset the conversation memory."""
    if CHAT_SESSION_KEY in context.user_data:
        # Delete the old chat session, forcing get_or_create_chat to make a new one
        del context.user_data[CHAT_SESSION_KEY]
        # Must await the reply function
        await update.message.reply_text("Conversation memory has been reset! Starting a fresh chat now.")
    else:
        # Must await the reply function
        await update.message.reply_text("You are already starting a new chat!")

async def handle_message(update: Update, context: CallbackContext) -> None:
    """Processes user text messages, maintains history, and sends the AI response."""
    user_message = update.message.text
    chat_id = update.message.chat_id
    
    # Retrieve the user ID from the update object
    user_id = update.effective_user.id

    # Check if AI is initialized
    if ai_client is None:
        # Must await the reply function
        await update.message.reply_text("AI service is not configured. Please check the GEMINI_API_KEY.")
        return

    # 1. Send a 'typing' action for a better user experience
    # Must await the action function
    await context.bot.send_chat_action(chat_id=chat_id, action='typing')
    
    logger.info(f"Received message from {update.effective_user.name} ({user_id}): '{user_message}'")
    
    try:
        # 2. Get the user's persistent chat session, passing the user_id
        chat_session = get_or_create_chat(context, user_id)
        
        if chat_session is None:
            # Must await the reply function
            await update.message.reply_text("Could not start a chat session. Please ensure the AI client initialized correctly.")
            return

        # 3. Send the message to the chat session (this automatically includes history)
        # Note: chat_session.send_message is synchronous in the google-genai SDK, no await needed here.
        response = chat_session.send_message(user_message)
        
        # 4. Send the reply back
        bot_reply = response.text
        # Must await the reply function
        await update.message.reply_text(bot_reply)

    except APIError as e:
        logger.error(f"Gemini API Error: {e}")
        # Must await the reply function
        await update.message.reply_text("I apologize, but I received an error from the AI service. The API might be incorrectly configured.")
    except Exception as e:
        logger.error(f"An unexpected error occurred during AI generation: {e}")
        # Must await the reply function
        await update.message.reply_text("Something went wrong while I was thinking. Try asking again!")

def main() -> None:
    """Starts the bot."""
    # If the token is not set (i.e., it's an empty string from os.getenv), exit.
    if not TELEGRAM_BOT_TOKEN:
        logger.error("FATAL: TELEGRAM_BOT_TOKEN not set. Please get your token from BotFather and replace the placeholder/set the environment variable.")
        return

    # --- UPDATED BOT INITIALIZATION (using ApplicationBuilder for python-telegram-bot v20+) ---
    
    # 1. Build the Application instance
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # The Application instance itself is used to add handlers
    # Command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("new_chat", new_chat)) # Handler for resetting history

    # Message handler for all non-command text
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Start the Bot
    logger.info("Starting bot polling...")
    # 2. Run the bot (this is a blocking call)
    application.run_polling(poll_interval=1.0, allowed_updates=Update.ALL_TYPES)
    application.run_polling(drop_pending_updates=True)
    
    # Note: application.run_polling() is the modern replacement for updater.start_polling() and updater.idle()

if __name__ == '__main__':
    main()
