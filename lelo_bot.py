from typing import Final, Dict
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application, CommandHandler, ContextTypes, MessageHandler, 
    filters, ConversationHandler, CallbackContext
)
import logging
import os
from database import Database
from elo import calculate_elo
import dotenv

dotenv.load_dotenv()

TOKEN: Final[str] = os.getenv("LELO_BOT_TOKEN")
BOT_USERNAME: Final[str] = os.getenv("LELO_BOT_USERNAME")

# States for registration conversation
NAME, SURNAME, POSITION, CONFIRM = range(4)

# States for game reporting conversation
OPPONENT_ID, SCORE, WAITING_CONFIRMATION = range(3)

# Initialize database
db = Database()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Store temporary game data
pending_games: Dict[int, dict] = {}

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "It is advised to report scores for SETS, not GAMES. \n"
        "For example, you can report 3-1 or 2-3 for a best of 5 set match.\n"
        "This will count into the ELO as a SINGLE ENCOUNTER, so:\n"
        "a) Reporting 3-0 will have DIFFERENT effect from reporting 1-0 three times.\n"
        "b) Reporting 3-0 will have the SAME effect as reporting 5-0."
    )

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hello! I'm a Table Tennis Rating Bot!\n"
        "Available commands:\n"
        "/register - Register as a player\n"
        "/add_match - Report a game result\n"
        "/my_stats - View your statistics\n"
        "/all_stats - View all players' ratings\n"
        "/help - Get help on how to report scores"
    )

async def register_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if db.get_user(update.effective_user.id):
        await update.message.reply_text("You are already registered!")
        return ConversationHandler.END
    
    await update.message.reply_text("Please enter your name:")
    return NAME

async def register_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['name'] = update.message.text
    await update.message.reply_text("Please enter your surname:")
    return SURNAME

async def register_surname(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['surname'] = update.message.text
    keyboard = [['Student', 'Staff'], ['Professor', 'Other']]
    await update.message.reply_text(
        "Please select your position:",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)
    )
    return POSITION

async def register_position(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['position'] = update.message.text
    await update.message.reply_text(
        f"Please confirm your registration:\n"
        f"Name: {context.user_data['name']}\n"
        f"Surname: {context.user_data['surname']}\n"
        f"Position: {context.user_data['position']}\n"
        f"Type 'confirm' to complete registration or 'cancel' to abort",
        reply_markup=ReplyKeyboardRemove()
    )
    return CONFIRM

async def register_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text.lower() == 'confirm':
        success = db.register_user(
            update.effective_user.id,
            context.user_data['name'],
            context.user_data['surname'],
            context.user_data['position']
        )
        if success:
            # Get the user to retrieve their assigned index
            user = db.get_user(update.effective_user.id)
            await update.message.reply_text(f"Registration successful! Your starting ELO is 1500.\nYour player index is: {user[6]}")
        else:
            await update.message.reply_text("Registration failed. You might be already registered.")
    else:
        await update.message.reply_text("Registration cancelled.")
    
    return ConversationHandler.END

async def report_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = db.get_user(update.effective_user.id)
    if not user:
        await update.message.reply_text("You need to register first! Use /register command.")
        return ConversationHandler.END
    
    await update.message.reply_text("Please enter your opponent's player index (6-digit number) or type 'cancel' to abort:")
    return OPPONENT_ID

async def report_opponent_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    
    # Check for cancel command
    if text.lower() == "cancel":
        await update.message.reply_text("Match reporting cancelled.")
        return ConversationHandler.END
    
    # Validate that the input is a 6-digit number
    if not (text.isdigit() and len(text) == 6):
        await update.message.reply_text("Invalid player index. Please enter a valid 6-digit number or type 'cancel' to abort.")
        return OPPONENT_ID
    
    # Get opponent by player index
    opponent = db.get_user_by_index(text)
    
    if not opponent:
        await update.message.reply_text("Opponent not found. Please check the player index and try again.")
        return OPPONENT_ID
    
    # Check that opponent is not the same as the reporter
    if opponent[0] == update.effective_user.id:
        await update.message.reply_text("You cannot report a game against yourself.")
        return OPPONENT_ID
    
    context.user_data['opponent_id'] = opponent[0]
    context.user_data['opponent_name'] = f"{opponent[1]} {opponent[2]}"
    
    await update.message.reply_text(
        f"Opponent found: {context.user_data['opponent_name']}\n"
        "Please enter the score (number of games) in format: 'your_score-opponent_score'\n"
        "Example: 3-1\n"
        "Or type 'cancel' to abort."
    )
    return SCORE

async def report_score(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    
    # Check for cancel command
    if text.lower() == "cancel":
        await update.message.reply_text("Match reporting cancelled.")
        return ConversationHandler.END
    
    try:
        score1, score2 = map(int, text.split('-'))
        
        # Check for 0-0 score
        if score1 == 0 and score2 == 0:
            await update.message.reply_text("Invalid score: 0-0 is not allowed. Please enter a valid score.")
            return SCORE
            
        game_id = db.create_game(
            update.effective_user.id,
            context.user_data['opponent_id'],
            score1,
            score2
        )
        
        pending_games[game_id] = {
            'player1_id': update.effective_user.id,
            'player2_id': context.user_data['opponent_id'],
            'score1': score1,
            'score2': score2
        }
        
        # Get reporter's name and surname
        reporter = db.get_user(update.effective_user.id)
        reporter_name = f"{reporter[1]} {reporter[2]}"
        
        # Notify opponent
        await context.bot.send_message(
            context.user_data['opponent_id'],
            f"Game report received from @{update.effective_user.username} ({reporter_name})!\n"
            f"Score: {score1}-{score2} ('opponent_score-your_score')\n"
            f"Type /confirm_{game_id} to confirm or /reject_{game_id} to reject"
        )
        
        await update.message.reply_text("Game reported! Waiting for opponent's confirmation.")
        return ConversationHandler.END
    
    except ValueError:
        await update.message.reply_text("Invalid score format. Please use format: 3-1 or type 'cancel' to abort.")
        return SCORE

async def confirm_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        # Extract game_id from the command text (e.g., /confirm_123)
        command_parts = update.message.text.split('_')
        if len(command_parts) != 2:
            await update.message.reply_text("Invalid command format. Use /confirm_<game_id>")
            return
            
        game_id = int(command_parts[1])
        
        if game_id not in pending_games:
            await update.message.reply_text("Game not found or already processed.")
            return
        
        game = pending_games[game_id]
        
        # Check if the user is the opponent who should confirm
        if update.effective_user.id != game['player2_id']:
            await update.message.reply_text("You are not authorized to confirm this game.")
            return
            
        db.confirm_game(game_id)
        
        # Get current ratings
        player1 = db.get_user(game['player1_id'])
        player2 = db.get_user(game['player2_id'])
        
        # Calculate new ratings
        new_rating1, new_rating2 = calculate_elo(
            player1[4], player2[4],  # Current ELO ratings
            game['score1'], game['score2']
        )
        
        # Update ratings
        db.update_elo(game['player1_id'], new_rating1)
        db.update_elo(game['player2_id'], new_rating2)
        
        # Notify both players
        message = f"Game confirmed! New ratings:\n{player1[1]} {player1[2]}: {new_rating1}\n{player2[1]} {player2[2]}: {new_rating2}"
        await context.bot.send_message(game['player1_id'], message)
        await context.bot.send_message(game['player2_id'], message)
        
        del pending_games[game_id]
    except (ValueError, IndexError):
        await update.message.reply_text("Invalid command format. Use /confirm_<game_id>")

async def reject_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        # Extract game_id from the command text (e.g., /reject_123)
        command_parts = update.message.text.split('_')
        if len(command_parts) != 2:
            await update.message.reply_text("Invalid command format. Use /reject_<game_id>")
            return
            
        game_id = int(command_parts[1])
        
        if game_id not in pending_games:
            await update.message.reply_text("Game not found or already processed.")
            return
        
        game = pending_games[game_id]
        
        # Check if the user is the opponent who should confirm/reject
        if update.effective_user.id != game['player2_id']:
            await update.message.reply_text("You are not authorized to reject this game.")
            return
        
        # Delete the game from database
        db.delete_game(game_id)
        
        # Notify both players
        message_to_reporter = "Your opponent rejected the game report."
        message_to_rejecter = "You have rejected the game report."
        await context.bot.send_message(game['player1_id'], message_to_reporter)
        await context.bot.send_message(game['player2_id'], message_to_rejecter)
        
        del pending_games[game_id]
    except (ValueError, IndexError):
        await update.message.reply_text("Invalid command format. Use /reject_<game_id>")

async def my_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = db.get_user(update.effective_user.id)
    if not user:
        await update.message.reply_text("You need to register first! Use /register command.")
        return
    
    await update.message.reply_text(
        f"Your statistics:\n"
        f"Name: {user[1]} {user[2]}\n"
        f"Position: {user[3]}\n"
        f"ELO Rating: {user[4]}\n"
        f"Games played: {user[5]}\n"
        f"Player Index: {user[6]}"
    )

async def all_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = db.get_all_users()
    message = "All players' ratings:\n"
    sorted_users = sorted(users, key=lambda x: x[2], reverse=True)

    for i, (name, surname, elo, player_index) in enumerate(sorted_users, 1):
        message += f"{i}. {name} {surname}: {elo}\n"
    
    await update.message.reply_text(message)

# Add a cancel handler function
async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Operation cancelled.")
    return ConversationHandler.END

def main():
    app = Application.builder().token(TOKEN).build()
    
    # Register conversation handler
    register_handler = ConversationHandler(
        entry_points=[CommandHandler('register', register_start)],
        states={
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_name)],
            SURNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_surname)],
            POSITION: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_position)],
            CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_confirm)],
        },
        fallbacks=[],
    )
    
    # Report game conversation handler
    report_handler = ConversationHandler(
        entry_points=[CommandHandler('add_match', report_start)],
        states={
            OPPONENT_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, report_opponent_id)],
            SCORE: [MessageHandler(filters.TEXT & ~filters.COMMAND, report_score)],
        },
        fallbacks=[CommandHandler('cancel', cancel_command)],
    )
    
    # Add handlers
    app.add_handler(CommandHandler('start', start_command))
    app.add_handler(CommandHandler('help', help_command))
    app.add_handler(register_handler)
    app.add_handler(report_handler)
    app.add_handler(CommandHandler('my_stats', my_stats))
    app.add_handler(CommandHandler('all_stats', all_stats))
    app.add_handler(CommandHandler('confirm', lambda u, c: u.message.reply_text("Use /confirm_<game_id> to confirm a game")))
    app.add_handler(CommandHandler('reject', lambda u, c: u.message.reply_text("Use /reject_<game_id> to reject a game")))
    
    # Use MessageHandler with regex filter instead of CommandHandler for commands with underscore
    app.add_handler(MessageHandler(filters.Regex(r'^/confirm_\d+$'), confirm_game))
    app.add_handler(MessageHandler(filters.Regex(r'^/reject_\d+$'), reject_game))
    
    # Start the bot
    print('Starting bot...')
    app.run_polling(poll_interval=0.5)

if __name__ == '__main__':
    main()
    
