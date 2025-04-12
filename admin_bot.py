from typing import Final, Dict
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, ChatMemberAdministrator, ChatPermissions
from telegram.ext import (
    Application, CommandHandler, ContextTypes, MessageHandler, 
    filters, ConversationHandler, CallbackContext
)
import logging
import os
import re
import json
import os.path
from database import Database
import asyncio
from datetime import datetime, timedelta
import dotenv

dotenv.load_dotenv()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN: Final[str] = os.getenv("ADMIN_BOT_TOKEN")
BOT_USERNAME: Final[str] = os.getenv("ADMIN_BOT_USERNAME")

# File to store admin mappings
MAPPINGS_FILE = "admin_mappings.json"

# Initialize database
db = Database()

# Load admin mappings from file
def load_admin_mappings():
    if os.path.exists(MAPPINGS_FILE):
        try:
            with open(MAPPINGS_FILE, 'r') as f:
                # Convert string keys back to integers
                data = json.load(f)
                mappings = {}
                for chat_id_str, users in data.items():
                    chat_id = int(chat_id_str)
                    mappings[chat_id] = {}
                    for user_id_str, player_index in users.items():
                        user_id = int(user_id_str)
                        mappings[chat_id][user_id] = player_index
                return mappings
        except Exception as e:
            logger.error(f"Error loading admin mappings: {e}")
    return {}

# Save admin mappings to file
def save_admin_mappings():
    try:
        # Convert all keys to strings for JSON serialization
        data = {}
        for chat_id, users in admin_mappings.items():
            data[str(chat_id)] = {}
            for user_id, player_index in users.items():
                data[str(chat_id)][str(user_id)] = player_index
                
        with open(MAPPINGS_FILE, 'w') as f:
            json.dump(data, f)
        logger.info("Admin mappings saved successfully")
    except Exception as e:
        logger.error(f"Error saving admin mappings: {e}")

# Dictionary to store user_id to player_index mapping for admins
# Format: {chat_id: {user_id: player_index}}
admin_mappings = load_admin_mappings()

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /start is issued."""
    await update.message.reply_text(
        "Hi! I'm the Admin Bot. I can promote users to admin with restricted rights.\n"
        "Use /tie_id 123456 to promote a user with their 6-digit player ID."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /help is issued."""
    await update.message.reply_text(
        "Available commands:\n"
        "/start - Start the bot\n"
        "/help - Show this help message\n"
        "/tie_id 123456 - Promote a user with their 6-digit player ID"
    )

async def promote_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Promote a user to admin with restricted rights based on their player ID."""
    # Get the player ID from context.args
    if not context.args or len(context.args) != 1 or not context.args[0].isdigit() or len(context.args[0]) != 6:
        await update.message.reply_text("Invalid command format. Use /tie_id 123456 where 123456 is a 6-digit number.")
        return
    
    player_index = context.args[0]
    
    # Check if the player exists in the database
    user = db.get_user_by_index(player_index)
    if not user:
        await update.message.reply_text(f"No player found with ID {player_index}.")
        return
    
    # Get the user who sent the command
    sender = update.effective_user
    
    # Get the chat where the command was sent
    chat = update.effective_chat
    
    # Get the user to promote (the user who sent the command)
    user_id = sender.id
    user_name = user[1]  # Name from database
    user_surname = user[2]  # Surname from database
    user_elo = user[4]  # ELO rating from database
    
    try:
        # Promote the user to admin with restricted rights
        await context.bot.promote_chat_member(
            chat_id=chat.id,
            user_id=user_id,
            can_change_info=False,
            can_post_messages=False,
            can_edit_messages=False,
            can_delete_messages=False,
            can_invite_users=True,
            can_restrict_members=False,
            can_pin_messages=False,
            can_promote_members=False,
            can_manage_chat=False,
            can_manage_video_chats=False
        )
        
        # Set custom title based on ELO rating
        custom_title = f"ELO: {user_elo}"
        await context.bot.set_chat_administrator_custom_title(
            chat_id=chat.id,
            user_id=user_id,
            custom_title=custom_title
        )
        
        # Store the mapping for periodic updates
        if chat.id not in admin_mappings:
            admin_mappings[chat.id] = {}
        admin_mappings[chat.id][user_id] = player_index
        
        # Save the updated mappings
        save_admin_mappings()
        
        await update.message.reply_text(
            f"User {user_name} {user_surname} has been promoted to admin with restricted rights.\n"
            f"Custom title set to: {custom_title}"
        )
        
    except Exception as e:
        logger.error(f"Error promoting user: {e}")
        await update.message.reply_text(f"Failed to promote user: {e}")

async def update_admin_titles(context: CallbackContext):
    """Periodically update the custom titles of all admins with tied IDs."""
    logger.info("Running scheduled update of admin titles")
    
    for chat_id, users in admin_mappings.items():
        for user_id, player_index in users.items():
            try:
                # Get updated user data from database
                user = db.get_user_by_index(player_index)
                if not user:
                    logger.warning(f"User with player_index {player_index} no longer exists in database")
                    continue
                
                user_elo = user[4]  # ELO rating from database
                
                # Update custom title
                custom_title = f"ELO: {user_elo}"
                await context.bot.set_chat_administrator_custom_title(
                    chat_id=chat_id,
                    user_id=user_id,
                    custom_title=custom_title
                )
                
                logger.info(f"Updated title for user {user_id} in chat {chat_id} to {custom_title}")
                
            except Exception as e:
                logger.error(f"Error updating title for user {user_id} in chat {chat_id}: {e}")

async def update_titles_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manually update all admin titles."""
    await update.message.reply_text("Updating all admin titles...")
    
    # Create a context-like object with a bot attribute
    class DummyContext:
        def __init__(self, bot):
            self.bot = bot
    
    dummy_context = DummyContext(context.bot)
    
    # Call the update function
    await update_admin_titles(dummy_context)
    
    await update.message.reply_text("Admin titles updated successfully!")

def main():
    """Start the bot."""
    # Create the Application
    application = Application.builder().token(TOKEN).build()
    
    # Add command handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    
    # Add handler for tie_id command
    application.add_handler(CommandHandler("tie_id", promote_user))
    
    # Add handler for update_titles command
    application.add_handler(CommandHandler("update_titles", update_titles_command))
    
    # Schedule periodic updates (every minute)
    try:
        job_queue = application.job_queue
        if job_queue is None:
            logger.warning("JobQueue is not available. Please install python-telegram-bot[job-queue]")
            logger.warning("Run: pip install 'python-telegram-bot[job-queue]'")
            logger.warning("Title updates will not run automatically")
        else:
            job_queue.run_repeating(update_admin_titles, interval=60, first=10)
            logger.info("Scheduled automatic title updates every 60 seconds")
    except Exception as e:
        logger.error(f"Error setting up job queue: {e}")
        logger.warning("Title updates will not run automatically")
    
    # Start the Bot
    application.run_polling()
    
    logger.info("Bot started")

if __name__ == '__main__':
    main()


