# логика бота
import logging
import os
import sys
import time
import requests
from typing import Optional
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
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
        logger.info("Инициализация CoffeeBot...")
        self.db = Database()
        logger.info("База данных инициализирована")
        self.app = Application.builder().token(token).build()
        logger.info("Application создан")
        self._setup_handlers()
        logger.info("CoffeeBot инициализирован успешно")
    
    def _setup_handlers(self):
        """Настройка обработчиков команд и сообщений"""
        # Обработчик добавления кофе
        add_coffee_handler = ConversationHandler(
            entry_points=[CommandHandler("add", self.start_add_coffee)],
            states={
                COUNTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_country)],
                PLANTATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_plantation)],
                PROCESSING: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_processing)],
                ROASTER: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_roaster)],
                Q_GRADE: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_q_grade)],
                MY_RATING: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_my_rating)],
            },
            fallbacks=[CommandHandler("cancel", self.cancel)],
        )
        
        # Добавляем обработчики в правильном порядке
        # Сначала команды, потом ConversationHandler, потом общий обработчик
        self.app.add_handler(CommandHandler("start", self.start))
        self.app.add_handler(CommandHandler("help", self.help))
        self.app.add_handler(CommandHandler("list", self.list_coffee))
        self.app.add_handler(CommandHandler("top", self.top_coffee))
        self.app.add_handler(CommandHandler("all", self.all_coffee))
        self.app.add_handler(add_coffee_handler)
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        
        # Обработчик ошибок
        self.app.add_error_handler(self.error_handler)
        
        logger.info("Обработчики успешно настроены")
    
    async def error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик ошибок"""
        logger.error(f"Exception while handling an update: {context.error}", exc_info=context.error)
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /start"""
        user = update.effective_user
        logger.info(f"Получена команда /start от пользователя {user.id} (@{user.username})")
        
        if not update.message:
            logger.warning("update.message is None")
            return
            
        try:
            text = (
                "☕ Добро пожаловать в Coffee Bot!\n\n"
                "Используйте /help для списка команд."
            )
            await update.message.reply_text(text)
            logger.info(f"Ответ на /start отправлен пользователю {user.id}")
        except Exception as e:
            logger.error(f"Ошибка при отправке ответа на /start: {e}", exc_info=True)
            raise
    
    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /help"""
        help_text = """
☕ Доступные команды:

/start - Начать работу с ботом
/help - Показать это сообщение
/add - Добавить новый кофе
/list - Список всех кофе
/top - Топ кофе по твоей оценке
/all - Все записи от всех пользователей
/cancel - Отменить текущую операцию
        """
        await update.message.reply_text(help_text)
    
    def _rating_to_stars(self, rating: Optional[int]) -> str:
        """Конвертация оценки в звездочки"""
        if rating is None:
            return ""
        return "⭐" * rating
    
    async def list_coffee(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /list"""
        user_id = update.effective_user.id
        coffee_list = self.db.get_coffee_by_user(user_id)
        
        if not coffee_list:
            await update.message.reply_text("У тебя пока нет добавленных кофе. Используй /add для добавления.")
            return
        
        message_parts = []
        for i, coffee in enumerate(coffee_list, 1):
            stars = self._rating_to_stars(coffee.my_rating)
            message_parts.append(
                f"{i}. {coffee.country} | {coffee.plantation}\n"
                f"   Обжарщик: {coffee.roaster}\n"
                f"   Моя оценка: {stars}"
            )
        
        message = "\n\n".join(message_parts)
        await update.message.reply_text(message)
    
    async def top_coffee(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /top - сортировка по оценке"""
        user_id = update.effective_user.id
        coffee_list = self.db.get_coffee_by_user_sorted_by_rating(user_id)
        
        if not coffee_list:
            await update.message.reply_text("У тебя пока нет добавленных кофе. Используй /add для добавления.")
            return
        
        message_parts = []
        for i, coffee in enumerate(coffee_list, 1):
            stars = self._rating_to_stars(coffee.my_rating)
            roaster = coffee.roaster if coffee.roaster else "Не указан"
            q_grade_text = f"Q: {coffee.q_grade}" if coffee.q_grade is not None else "Q: —"
            message_parts.append(f"{i}. {coffee.country} | {coffee.plantation} | {roaster} | {q_grade_text} — {stars}")
        
        message = "\n".join(message_parts)
        await update.message.reply_text(message)
    
    async def all_coffee(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /all - все записи от всех пользователей"""
        coffee_list = self.db.get_all_coffee()
        
        if not coffee_list:
            await update.message.reply_text("Пока нет добавленных кофе.")
            return
        
        message_parts = []
        for i, coffee in enumerate(coffee_list, 1):
            stars = self._rating_to_stars(coffee.my_rating)
            roaster = coffee.roaster if coffee.roaster else "Не указан"
            q_grade_text = f"Q: {coffee.q_grade}" if coffee.q_grade is not None else "Q: —"
            
            # Пытаемся получить username пользователя
            try:
                chat = await context.bot.get_chat(coffee.user_id)
                user_info = f"@{chat.username}" if chat.username else f"ID: {coffee.user_id}"
            except Exception:
                user_info = f"ID: {coffee.user_id}"
            
            message_parts.append(
                f"{i}. {coffee.country} | {coffee.plantation} | {roaster} | {q_grade_text} — {stars}\n"
                f"   👤 {user_info}"
            )
        
        message = "\n\n".join(message_parts)
        
        # Telegram имеет лимит на длину сообщения (4096 символов)
        if len(message) > 4000:
            # Разбиваем на несколько сообщений
            chunks = []
            current_chunk = []
            current_length = 0
            
            for part in message_parts:
                part_length = len(part) + 2  # +2 для "\n\n"
                if current_length + part_length > 4000:
                    chunks.append("\n\n".join(current_chunk))
                    current_chunk = [part]
                    current_length = part_length
                else:
                    current_chunk.append(part)
                    current_length += part_length
            
            if current_chunk:
                chunks.append("\n\n".join(current_chunk))
            
            for chunk in chunks:
                await update.message.reply_text(chunk)
        else:
            await update.message.reply_text(message)
    
    async def start_add_coffee(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Начало процесса добавления кофе"""
        await update.message.reply_text("Страна")
        return COUNTRY
    
    async def get_country(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Получение страны"""
        context.user_data['country'] = update.message.text
        await update.message.reply_text("Плантация")
        return PLANTATION
    
    async def get_plantation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Получение плантации"""
        context.user_data['plantation'] = update.message.text
        await update.message.reply_text("Тип обработки")
        return PROCESSING
    
    async def get_processing(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Получение типа обработки"""
        context.user_data['processing'] = update.message.text
        await update.message.reply_text("Обжарщик")
        return ROASTER
    
    async def get_roaster(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Получение обжарщика"""
        context.user_data['roaster'] = update.message.text
        await update.message.reply_text("Оценка Q-грейдера")
        return Q_GRADE
    
    async def get_q_grade(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Получение оценки Q-грейдера"""
        try:
            q_grade = int(update.message.text)
            context.user_data['q_grade'] = q_grade
            await update.message.reply_text("Твоя оценка (1–5)")
            return MY_RATING
        except ValueError:
            await update.message.reply_text("Пожалуйста, введите число для оценки Q-грейдера.")
            return Q_GRADE
    
    async def get_my_rating(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Получение оценки пользователя и сохранение кофе"""
        try:
            rating = int(update.message.text)
            if rating < 1 or rating > 5:
                await update.message.reply_text("Пожалуйста, введите оценку от 1 до 5.")
                return MY_RATING
            
            context.user_data['my_rating'] = rating
            
            # Создание объекта кофе
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
            
            # Сохранение в базу данных
            self.db.add_coffee(coffee)
            
            # Очистка данных пользователя
            context.user_data.clear()
            
            await update.message.reply_text("☕ Кофе добавлен!")
            return ConversationHandler.END
        except ValueError:
            await update.message.reply_text("Пожалуйста, введите число от 1 до 5.")
            return MY_RATING
    
    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Отмена операции"""
        context.user_data.clear()
        await update.message.reply_text("Операция отменена.")
        return ConversationHandler.END
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик обычных сообщений"""
        await update.message.reply_text(
            "Я не понимаю это сообщение. Используйте /help для списка команд."
        )
    
    def run(self):
        """Запуск бота"""
        try:
            logger.info("Запуск бота...")
            logger.info("Ожидание сообщений...")
            
            # Удаляем webhook синхронно перед запуском polling
            try:
                token = os.getenv("TELEGRAM_BOT_TOKEN")
                if token:
                    response = requests.post(
                        f"https://api.telegram.org/bot{token}/deleteWebhook",
                        params={"drop_pending_updates": True},
                        timeout=5
                    )
                    if response.status_code == 200:
                        logger.info("Webhook удален, используется polling")
                    else:
                        logger.warning(f"Не удалось удалить webhook: {response.status_code}")
            except Exception as e:
                logger.warning(f"Не удалось удалить webhook: {e}")
            
            self.app.run_polling(
                allowed_updates=Update.ALL_TYPES,
                drop_pending_updates=True
            )
        except Exception as e:
            logger.error(f"Ошибка при запуске бота: {e}", exc_info=True)
            # Если конфликт - ждем и перезапускаем
            if "Conflict" in str(e):
                logger.warning("Обнаружен конфликт с другим экземпляром бота. Ожидание 10 секунд...")
                time.sleep(10)
                logger.info("Повторная попытка запуска...")
                self.app.run_polling(
                    allowed_updates=Update.ALL_TYPES,
                    drop_pending_updates=True
                )
            else:
                raise


if __name__ == "__main__":
    try:
        load_dotenv()
        TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
        
        if not TOKEN:
            logger.error("TELEGRAM_BOT_TOKEN не найден в переменных окружения!")
            print("ОШИБКА: TELEGRAM_BOT_TOKEN не найден в переменных окружения!")
            print("Убедитесь, что файл .env существует и содержит TELEGRAM_BOT_TOKEN")
            sys.exit(1)
        
        logger.info("Токен загружен успешно")
        print("Инициализация бота...")
        bot = CoffeeBot(TOKEN)
        print("Бот запущен! Нажмите Ctrl+C для остановки.")
        bot.run()
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем")
        print("\nБот остановлен.")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}", exc_info=True)
        print(f"ОШИБКА: {e}")
        sys.exit(1)
