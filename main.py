import os
import logging
import random
import re
from telegram import Update, InputFile, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from dotenv import load_dotenv
from telegram.error import BadRequest

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Load verification questions from environment variables
def load_verification_questions():
    questions = []
    for i in range(1, 12):  # Assuming we have 11 questions
        env_key = f"VERIFICATION_Q{i}"
        question_data = os.getenv(env_key)
        if question_data:
            question, answer, image_url = question_data.split("|")
            questions.append((question, answer, image_url))
    return questions

# Load questions at startup
VERIFICATION_QUESTIONS = load_verification_questions()

# List of vulgar words (example)
VULGAR_WORDS = ["fuck", "shit", "cunt", "bitch", "asshole", "dickhead", "motherfucker", "cocksucker", "pussy", "tits", "nipples", "dick", "pussy", "whore", "jerk off", "fuck buddy", "handjob", "blowjob", "slut", "nigger", "chink", "spic", "kike", "retard", "fag", "tranny", "pussy-whipped", "whore", "bimbos", "gold digger", "fag", "queer", "tranny", "dyke", "shitcoin", "ruggers", "scammer", "ponzi", "dump", "pump and dump", "scam", "shiller", "idiot", "loser", "moron", "dumbass", "retard", "cuck", "fatass", "snowflake", "degenerate", "neckbeard", "kill yourself", "go die", "burn in hell", "eat shit", "get fucked", "weed", "cocaine", "meth", "heroin", "acid", "ecstasy", "pothead", "crackhead", "I'll kill you", "I'm going to hurt you", "cut you", "stab you", "shoot you", "bomb", "1000x gains", "mooning", "fake news", "shilling", "guaranteed profits", "get rich quick"]

# User state dictionary
user_states = {}

def contains_vulgar_word(text: str) -> bool:
    pattern = r'\b(' + '|'.join(map(re.escape, VULGAR_WORDS)) + r')\b'
    result = bool(re.search(pattern, text, re.IGNORECASE))
    logger.info(f"Checking text: '{text}', Contains vulgar word: {result}")
    return result

async def start_verification(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    if not VERIFICATION_QUESTIONS:
        logger.error("No verification questions loaded from environment variables")
        await context.bot.send_message(chat_id, "Verification system is currently unavailable. Please contact the administrator.")
        return

    if user_id not in user_states or not user_states[user_id]['verified']:
        # Send a loading message first
        loading_message = await context.bot.send_message(chat_id, "Please wait, fetching verification image...")

        question, answer, image_url = random.choice(VERIFICATION_QUESTIONS)
        user_states[user_id] = {
            'verified': False,
            'current_question': (question, answer, image_url),
            'message_ids': [loading_message.message_id],
            'stored_messages': [],
        }

        try:
            # Create keyboard with multiple rows (each row containing 3 buttons)
            keyboard = [[InlineKeyboardButton(str(i), callback_data=f"verify_{i}") for i in range(j, min(j+3, 11))] for j in range(0, 11, 3)]
            reply_markup = InlineKeyboardMarkup(keyboard)
            sent_msg = await context.bot.send_photo(
                chat_id,
                photo=image_url,
                caption=f"Please answer this question: {question}",
                reply_markup=reply_markup
            )
            user_states[user_id]['message_ids'].append(sent_msg.message_id)

            # Edit the loading message
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=loading_message.message_id,
                text="Image fetched successfully, please answer the question above."
            )
        except Exception as e:
            logger.error(f"Failed to send photo: {e}")
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=loading_message.message_id,
                text="Failed to fetch the verification image. Please try again."
            )
    else:
        await context.bot.send_message(chat_id, "You are already verified!")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    if user_id in user_states and not user_states[user_id]['verified']:
        _, answer, _ = user_states[user_id]['current_question']
        if query.data == f"verify_{answer}":
            user_states[user_id]['verified'] = True
            user_states[user_id]['current_question'] = None

            # Delete all stored messages from the user
            for msg_id, _ in user_states[user_id]['stored_messages']:
                await delete_message_safe(context, chat_id, msg_id)
            user_states[user_id]['stored_messages'].clear()

            # Delete all verification-related messages (sent by the bot)
            for msg_id in user_states[user_id]['message_ids']:
                await delete_message_safe(context, chat_id, msg_id)
            user_states[user_id]['message_ids'].clear()

            # Delete the welcome message
            if 'welcome_message_id' in user_states[user_id]:
                await delete_message_safe(context, chat_id, user_states[user_id]['welcome_message_id'])
                user_states[user_id]['welcome_message_id'] = None

            # Send a success message
            await context.bot.send_message(chat_id, f"🎉 Congratulations, {update.effective_user.first_name}! You are now verified.")
        else:
            # If the answer is incorrect, prompt the user to try again
            await query.edit_message_caption(caption="Incorrect answer. Please try again.")

async def delete_message_safe(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int) -> None:
    try:
        await context.bot.delete_message(chat_id, message_id)
        logger.info(f"Successfully deleted message {message_id} in chat {chat_id}")
    except BadRequest as e:
        logger.error(f"Failed to delete message {message_id} in chat {chat_id}: {e}")

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    message = update.message

    # Check if the user exists in user_states, otherwise assume they are new and unverified
    if user_id not in user_states or not user_states[user_id]['verified']:
        # Initialize user state if they don't exist in user_states
        if user_id not in user_states:
            # Send a welcome message with a verification button if this is the user's first interaction
            keyboard = [[InlineKeyboardButton("Verify", callback_data="start_verification")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            welcome_msg = await context.bot.send_message(
                chat_id,
                f"👋 Hello {update.effective_user.first_name}! Please verify yourself to continue.",
                reply_markup=reply_markup
            )
            user_states[user_id] = {
                'verified': False,
                'current_question': None,
                'message_ids': [],
                'stored_messages': [],
                'welcome_message_id': welcome_msg.message_id  # Store welcome message ID
            }
            logger.info(f"Welcome message sent to user {user_id} with message ID {welcome_msg.message_id}")

        # Store the user's messages until they are verified
        user_states[user_id]['stored_messages'].append((message.message_id, message.text))

        # Delete the user's message (to keep the chat clean if desired)
        await delete_message_safe(context, chat_id, message.message_id)

    elif contains_vulgar_word(message.text):
        # Delete the message if it contains inappropriate content
        await delete_message_safe(context, chat_id, message.message_id)
        await context.bot.send_message(chat_id, "A message containing inappropriate content has been deleted.")

def main() -> None:
    # Get the bot token from environment variable
    token = os.getenv("TELOXIDE_TOKEN")
    if not token:
        logger.error("TELOXIDE_TOKEN must be set")
        return

    # Create the Application and pass it your bot's token
    application = Application.builder().token(token).build()

    # Add handlers
    application.add_handler(CallbackQueryHandler(button_callback, pattern="^verify_"))
    application.add_handler(CallbackQueryHandler(start_verification, pattern="^start_verification$"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    # Run the bot until the user presses Ctrl-C
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()