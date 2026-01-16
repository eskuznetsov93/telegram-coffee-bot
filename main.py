# логика бота
import logging
import os
import sys
import time
import requests
from typing import Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)
from db import Database
from models import Coffee
from datetime import datetime
from dotenv import load_dotenv

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Состояния разговора
COUNTRY, PLANTATION, PROCESSING, ROASTER, Q_GRADE, MY_RATING = range(6)


class CoffeeBot:
    def __init__(self, token: str):
        logger.info("Initializing CoffeeBot...")
        self.db = Database()
        logger.info("Database initialized")
        self.app = Application.builder().token(token).build()
        logger.info("Application created")
        self._setup_handlers()
        logger.info("CoffeeBot initialized successfully")
    
    def _setup_handlers(self):
        """Настройка обработчиков команд и сообщений"""
        # Обработчик добавления кофе
        add_coffee_handler = ConversationHandler(
            entry_points=[CommandHandler("add", self.start_add_coffee)],
            states={
                COUNTRY: [
                    CallbackQueryHandler(self.get_country_callback, pattern="^country_"),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_country)
                ],
                PLANTATION: [
                    CallbackQueryHandler(self.get_plantation_callback, pattern="^plantation_"),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_plantation)
                ],
                PROCESSING: [CallbackQueryHandler(self.get_processing_callback, pattern="^processing_")],
                ROASTER: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_roaster)],
                Q_GRADE: [CallbackQueryHandler(self.get_q_grade_callback, pattern="^qgrade_")],
                MY_RATING: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_my_rating)],
            },
            fallbacks=[CommandHandler("cancel", self.cancel)],
        )
        
        # Добавляем обработчики в правильном порядке
        # Сначала команды, потом ConversationHandler, потом общий обработчик
        self.app.add_handler(CommandHandler("start", self.start))
        self.app.add_handler(CommandHandler("help", self.help))
        self.app.add_handler(CommandHandler("list", self.list_coffee))
        self.app.add_handler(CommandHandler("my_list", self.my_list_coffee))
        self.app.add_handler(CommandHandler("top", self.top_coffee))
        self.app.add_handler(add_coffee_handler)
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        
        # Обработчик ошибок
        self.app.add_error_handler(self.error_handler)
        
        logger.info("Handlers successfully configured")
    
    async def error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик ошибок"""
        logger.error(f"Exception while handling an update: {context.error}", exc_info=context.error)
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler for /start command"""
        user = update.effective_user
        logger.info(f"Received /start command from user {user.id} (@{user.username})")
        
        if not update.message:
            logger.warning("update.message is None")
            return
            
        try:
            text = (
                "☕ Welcome to Coffee Bot!\n\n"
                "Use /help for a list of commands."
            )
            await update.message.reply_text(text)
            logger.info(f"Response to /start sent to user {user.id}")
        except Exception as e:
            logger.error(f"Error sending response to /start: {e}", exc_info=True)
            raise
    
    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler for /help command"""
        help_text = """
☕ Available commands:

/start - Start working with the bot
/help - Show this message
/add - Add new coffee
/list - List all your coffee
/my_list - Your coffee grouped by plantation+processing+q_grade+roaster, sorted by rating
/top - Top coffee grouped by plantation+processing+q_grade+roaster, sorted by average rating
/cancel - Cancel current operation
        """
        await update.message.reply_text(help_text)
    
    def _rating_to_stars(self, rating: Optional[int]) -> str:
        """Конвертация оценки в звездочки"""
        if rating is None:
            return ""
        return "⭐" * rating
    
    async def list_coffee(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler for /list command"""
        user_id = update.effective_user.id
        coffee_list = self.db.get_coffee_by_user(user_id)
        
        if not coffee_list:
            await update.message.reply_text("You don't have any coffee entries yet. Use /add to add one.")
            return
        
        message_parts = []
        for i, coffee in enumerate(coffee_list, 1):
            stars = self._rating_to_stars(coffee.my_rating)
            message_parts.append(
                f"{i}. {coffee.country} | {coffee.plantation}\n"
                f"   Roaster: {coffee.roaster}\n"
                f"   My rating: {stars}"
            )
        
        message = "\n\n".join(message_parts)
        await update.message.reply_text(message)
    
    async def my_list_coffee(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler for /my_list - grouped by plantation+processing+q_grade+roaster, sorted by user's rating"""
        user_id = update.effective_user.id
        grouped_coffee = self.db.get_grouped_coffee_by_user(user_id)
        
        if not grouped_coffee:
            await update.message.reply_text("You don't have any coffee entries yet. Use /add to add one.")
            return
        
        message_parts = []
        for i, item in enumerate(grouped_coffee, 1):
            stars = self._rating_to_stars(item['max_rating'])
            roaster = item['roaster'] if item['roaster'] else "Not specified"
            processing = item['processing'] if item['processing'] else "Not specified"
            # Format Q-grader for display
            if item['q_grade'] is None:
                q_grade_text = "Q: —"
            elif item['q_grade'] == 79:
                q_grade_text = "Q: <80"
            elif item['q_grade'] == 86:
                q_grade_text = "Q: 85+"
            elif item['q_grade'] == 91:
                q_grade_text = "Q: 90+"
            else:
                q_grade_text = f"Q: {item['q_grade']}"
            message_parts.append(f"{i}. {item['country']} | {item['plantation']} | {processing} | {roaster} | {q_grade_text} — {stars}")
        
        message = "\n".join(message_parts)
        await update.message.reply_text(message)
    
    async def top_coffee(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler for /top - grouped by plantation+processing+q_grade+roaster, sorted by average rating"""
        grouped_coffee = self.db.get_grouped_coffee_average_rating()
        
        if not grouped_coffee:
            await update.message.reply_text("No coffee entries yet.")
            return
        
        message_parts = []
        for i, item in enumerate(grouped_coffee, 1):
            avg_rating = item['avg_rating']
            stars = self._rating_to_stars(int(avg_rating) if avg_rating else None)
            roaster = item['roaster'] if item['roaster'] else "Not specified"
            processing = item['processing'] if item['processing'] else "Not specified"
            # Format Q-grader for display
            if item['q_grade'] is None:
                q_grade_text = "Q: —"
            elif item['q_grade'] == 79:
                q_grade_text = "Q: <80"
            elif item['q_grade'] == 86:
                q_grade_text = "Q: 85+"
            elif item['q_grade'] == 91:
                q_grade_text = "Q: 90+"
            else:
                q_grade_text = f"Q: {item['q_grade']}"
            
            rating_text = f"{avg_rating:.2f}" if avg_rating else "—"
            message_parts.append(
                f"{i}. {item['country']} | {item['plantation']} | {processing} | {roaster} | {q_grade_text} — {stars} (avg: {rating_text}, {item['count']} ratings)"
            )
        
        message = "\n".join(message_parts)
        
        # Telegram has a message length limit (4096 characters)
        if len(message) > 4000:
            # Split into multiple messages
            chunks = []
            current_chunk = []
            current_length = 0
            
            for part in message_parts:
                part_length = len(part) + 1  # +1 for "\n"
                if current_length + part_length > 4000:
                    chunks.append("\n".join(current_chunk))
                    current_chunk = [part]
                    current_length = part_length
                else:
                    current_chunk.append(part)
                    current_length += part_length
            
            if current_chunk:
                chunks.append("\n".join(current_chunk))
            
            for chunk in chunks:
                await update.message.reply_text(chunk)
        else:
            await update.message.reply_text(message)
    
    async def start_add_coffee(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start the coffee addition process"""
        # Get list of existing countries
        countries = self.db.get_all_countries()
        
        if countries:
            # Create buttons with existing countries
            keyboard = []
            # Split into rows of 2 buttons
            for i in range(0, len(countries), 2):
                row = []
                row.append(InlineKeyboardButton(countries[i], callback_data=f"country_{countries[i]}"))
                if i + 1 < len(countries):
                    row.append(InlineKeyboardButton(countries[i + 1], callback_data=f"country_{countries[i + 1]}"))
                keyboard.append(row)
            keyboard.append([InlineKeyboardButton("✏️ Enter new country", callback_data="country_new")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text("Country (select from list or enter new)", reply_markup=reply_markup)
        else:
            await update.message.reply_text("Country")
        return COUNTRY
    
    async def get_country_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle country selection via button"""
        query = update.callback_query
        await query.answer()
        
        if query.data == "country_new":
            # User wants to enter a new country
            await query.edit_message_text("Enter country name:")
            return COUNTRY
        
        country = query.data.replace("country_", "")
        context.user_data['country'] = country
        
        # Get list of existing plantations for this country
        plantations = self.db.get_plantations_by_country(country)
        
        if plantations:
            # Create buttons with existing plantations
            keyboard = []
            # Split into rows of 2 buttons
            for i in range(0, len(plantations), 2):
                row = []
                row.append(InlineKeyboardButton(plantations[i], callback_data=f"plantation_{plantations[i]}"))
                if i + 1 < len(plantations):
                    row.append(InlineKeyboardButton(plantations[i + 1], callback_data=f"plantation_{plantations[i + 1]}"))
                keyboard.append(row)
            keyboard.append([InlineKeyboardButton("✏️ Enter new plantation", callback_data="plantation_new")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(f"Country: {country}")
            await query.message.reply_text(f"Plantation for {country} (select from list or enter new)", reply_markup=reply_markup)
        else:
            await query.edit_message_text(f"Country: {country}")
            await query.message.reply_text("Plantation")
        return PLANTATION
    
    async def get_country(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Get country (text input)"""
        country = update.message.text.strip()
        context.user_data['country'] = country
        
        # Get list of existing plantations for this country
        plantations = self.db.get_plantations_by_country(country)
        
        if plantations:
            # Create buttons with existing plantations
            keyboard = []
            # Split into rows of 2 buttons
            for i in range(0, len(plantations), 2):
                row = []
                row.append(InlineKeyboardButton(plantations[i], callback_data=f"plantation_{plantations[i]}"))
                if i + 1 < len(plantations):
                    row.append(InlineKeyboardButton(plantations[i + 1], callback_data=f"plantation_{plantations[i + 1]}"))
                keyboard.append(row)
            keyboard.append([InlineKeyboardButton("✏️ Enter new plantation", callback_data="plantation_new")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(f"Plantation for {country} (select from list or enter new)", reply_markup=reply_markup)
        else:
            await update.message.reply_text("Plantation")
        return PLANTATION
    
    async def get_plantation_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle plantation selection via button"""
        query = update.callback_query
        await query.answer()
        
        if query.data == "plantation_new":
            # User wants to enter a new plantation
            await query.edit_message_text(f"Enter plantation name for {context.user_data.get('country', '')}:")
            return PLANTATION
        
        plantation = query.data.replace("plantation_", "")
        context.user_data['plantation'] = plantation
        
        # Create buttons for processing selection
        keyboard = [
            [InlineKeyboardButton("Washed", callback_data="processing_Washed")],
            [InlineKeyboardButton("Natural", callback_data="processing_Natural")],
            [InlineKeyboardButton("Anaerobic", callback_data="processing_Anaerobic")],
            [InlineKeyboardButton("Honey", callback_data="processing_Honey")],
            [InlineKeyboardButton("Infused", callback_data="processing_Infused")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(f"Plantation: {plantation}")
        await query.message.reply_text("Processing type", reply_markup=reply_markup)
        return PROCESSING
    
    async def get_plantation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Get plantation (text input)"""
        plantation = update.message.text.strip()
        context.user_data['plantation'] = plantation
        
        # Create buttons for processing selection
        keyboard = [
            [InlineKeyboardButton("Washed", callback_data="processing_Washed")],
            [InlineKeyboardButton("Natural", callback_data="processing_Natural")],
            [InlineKeyboardButton("Anaerobic", callback_data="processing_Anaerobic")],
            [InlineKeyboardButton("Honey", callback_data="processing_Honey")],
            [InlineKeyboardButton("Infused", callback_data="processing_Infused")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text("Processing type", reply_markup=reply_markup)
        return PROCESSING
    
    async def get_processing_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle processing type selection via button"""
        query = update.callback_query
        await query.answer()
        
        processing = query.data.replace("processing_", "")
        context.user_data['processing'] = processing
        
        await query.edit_message_text(f"Processing type: {processing}")
        await query.message.reply_text("Roaster")
        return ROASTER
    
    async def get_roaster(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Get roaster"""
        context.user_data['roaster'] = update.message.text
        
        # Create buttons for Q-grade selection
        keyboard = [
            [InlineKeyboardButton("<80", callback_data="qgrade_<80")],
            [
                InlineKeyboardButton("80", callback_data="qgrade_80"),
                InlineKeyboardButton("81", callback_data="qgrade_81"),
                InlineKeyboardButton("82", callback_data="qgrade_82"),
            ],
            [
                InlineKeyboardButton("83", callback_data="qgrade_83"),
                InlineKeyboardButton("84", callback_data="qgrade_84"),
                InlineKeyboardButton("85", callback_data="qgrade_85"),
            ],
            [
                InlineKeyboardButton("85+", callback_data="qgrade_85+"),
                InlineKeyboardButton("90+", callback_data="qgrade_90+"),
            ],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text("Q-grader score", reply_markup=reply_markup)
        return Q_GRADE
    
    async def get_q_grade_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка выбора Q-грейдера через кнопку"""
        query = update.callback_query
        await query.answer()
        
        q_grade_str = query.data.replace("qgrade_", "")
        
        # Convert string to number for storage
        if q_grade_str == "<80":
            context.user_data['q_grade'] = 79  # Store as 79 for sorting
            q_grade_display = "<80"
        elif q_grade_str == "85+":
            context.user_data['q_grade'] = 86  # Store as 86 for sorting
            q_grade_display = "85+"
        elif q_grade_str == "90+":
            context.user_data['q_grade'] = 91  # Store as 91 for sorting
            q_grade_display = "90+"
        else:
            context.user_data['q_grade'] = int(q_grade_str)
            q_grade_display = q_grade_str
        
        await query.edit_message_text(f"Q-grader score: {q_grade_display}")
        await query.message.reply_text("Your rating (1–5)")
        return MY_RATING
    
    async def get_my_rating(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Get user rating and save coffee"""
        try:
            rating = int(update.message.text)
            if rating < 1 or rating > 5:
                await update.message.reply_text("Please enter a rating from 1 to 5.")
                return MY_RATING
            
            context.user_data['my_rating'] = rating
            
            # Create coffee object
            coffee = Coffee(
                user_id=update.effective_user.id,
                country=context.user_data.get('country', ''),
                plantation=context.user_data.get('plantation', ''),
                processing=context.user_data.get('processing', ''),
                roaster=context.user_data.get('roaster', ''),
                q_grade=context.user_data.get('q_grade'),
                my_rating=rating,
                created_at=datetime.now()
            )
            
            # Save to database
            self.db.add_coffee(coffee)
            
            # Clear user data
            context.user_data.clear()
            
            await update.message.reply_text("☕ Coffee added!")
            return ConversationHandler.END
        except ValueError:
            await update.message.reply_text("Please enter a number from 1 to 5.")
            return MY_RATING
    
    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Cancel operation"""
        context.user_data.clear()
        await update.message.reply_text("Operation cancelled.")
        return ConversationHandler.END
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler for regular messages"""
        await update.message.reply_text(
            "I don't understand this message. Use /help for a list of commands."
        )
    
    def run(self):
        """Start the bot"""
        # Remove webhook and wait before starting polling
        try:
            token = os.getenv("TELEGRAM_BOT_TOKEN")
            if token:
                # Удаляем webhook несколько раз для надежности
                for attempt in range(3):
                    try:
                        response = requests.post(
                            f"https://api.telegram.org/bot{token}/deleteWebhook",
                            params={"drop_pending_updates": True},
                            timeout=5
                        )
                        if response.status_code == 200:
                            logger.info("Webhook удален, используется polling")
                            break
                    except Exception as e:
                        logger.warning(f"Попытка {attempt + 1} удаления webhook: {e}")
                        if attempt < 2:
                            time.sleep(2)
        except Exception as e:
            logger.warning(f"Не удалось удалить webhook: {e}")
        
        # Ждем немного перед запуском polling
        logger.info("Ожидание 5 секунд перед запуском polling...")
        time.sleep(5)
        
        # Пытаемся запустить с обработкой конфликтов
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                logger.info("Запуск бота...")
                logger.info("Ожидание сообщений...")
                
                self.app.run_polling(
                    allowed_updates=Update.ALL_TYPES,
                    drop_pending_updates=True
                )
                break  # Если успешно запустился, выходим из цикла
            except Exception as e:
                error_str = str(e)
                logger.error(f"Ошибка при запуске бота: {e}", exc_info=True)
                
                # Если конфликт - ждем и повторяем
                if "Conflict" in error_str and retry_count < max_retries - 1:
                    wait_time = (retry_count + 1) * 10
                    logger.warning(f"Обнаружен конфликт. Ожидание {wait_time} секунд перед повторной попыткой...")
                    time.sleep(wait_time)
                    retry_count += 1
                    logger.info(f"Повторная попытка запуска ({retry_count}/{max_retries})...")
                    
                    # Снова удаляем webhook перед повторной попыткой
                    try:
                        token = os.getenv("TELEGRAM_BOT_TOKEN")
                        if token:
                            requests.post(
                                f"https://api.telegram.org/bot{token}/deleteWebhook",
                                params={"drop_pending_updates": True},
                                timeout=5
                            )
                    except:
                        pass
                else:
                    # Если не конфликт или исчерпаны попытки - поднимаем исключение
                    raise


if __name__ == "__main__":
    try:
        load_dotenv()
        TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
        
        if not TOKEN:
            logger.error("TELEGRAM_BOT_TOKEN not found in environment variables!")
            print("ERROR: TELEGRAM_BOT_TOKEN not found in environment variables!")
            print("Make sure the .env file exists and contains TELEGRAM_BOT_TOKEN")
            sys.exit(1)
        
        logger.info("Token loaded successfully")
        print("Initializing bot...")
        bot = CoffeeBot(TOKEN)
        print("Bot started! Press Ctrl+C to stop.")
        bot.run()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
        print("\nBot stopped.")
    except Exception as e:
        logger.error(f"Critical error: {e}", exc_info=True)
        print(f"ERROR: {e}")
        sys.exit(1)
