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
            processing = coffee.processing if coffee.processing else "Не указан"
            # Форматируем Q-грейдер для отображения
            if coffee.q_grade is None:
                q_grade_text = "Q: —"
            elif coffee.q_grade == 86:
                q_grade_text = "Q: 85+"
            elif coffee.q_grade == 91:
                q_grade_text = "Q: 90+"
            else:
                q_grade_text = f"Q: {coffee.q_grade}"
            message_parts.append(f"{i}. {coffee.country} | {coffee.plantation} | {processing} | {roaster} | {q_grade_text} — {stars}")
        
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
            # Форматируем Q-грейдер для отображения
            if coffee.q_grade is None:
                q_grade_text = "Q: —"
            elif coffee.q_grade == 86:
                q_grade_text = "Q: 85+"
            elif coffee.q_grade == 91:
                q_grade_text = "Q: 90+"
            else:
                q_grade_text = f"Q: {coffee.q_grade}"
            
            # Пытаемся получить username пользователя
            try:
                chat = await context.bot.get_chat(coffee.user_id)
                user_info = f"@{chat.username}" if chat.username else f"ID: {coffee.user_id}"
            except Exception:
                user_info = f"ID: {coffee.user_id}"
            
            processing = coffee.processing if coffee.processing else "Не указан"
            message_parts.append(
                f"{i}. {coffee.country} | {coffee.plantation} | {processing} | {roaster} | {q_grade_text} — {stars}\n"
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
        # Получаем список существующих стран
        countries = self.db.get_all_countries()
        
        if countries:
            # Создаем кнопки с существующими странами
            keyboard = []
            # Разбиваем на ряды по 2 кнопки
            for i in range(0, len(countries), 2):
                row = []
                row.append(InlineKeyboardButton(countries[i], callback_data=f"country_{countries[i]}"))
                if i + 1 < len(countries):
                    row.append(InlineKeyboardButton(countries[i + 1], callback_data=f"country_{countries[i + 1]}"))
                keyboard.append(row)
            keyboard.append([InlineKeyboardButton("✏️ Ввести новую страну", callback_data="country_new")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text("Страна (выберите из списка или введите новую)", reply_markup=reply_markup)
        else:
            await update.message.reply_text("Страна")
        return COUNTRY
    
    async def get_country_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка выбора страны через кнопку"""
        query = update.callback_query
        await query.answer()
        
        if query.data == "country_new":
            # Пользователь хочет ввести новую страну
            await query.edit_message_text("Введите название страны:")
            return COUNTRY
        
        country = query.data.replace("country_", "")
        context.user_data['country'] = country
        
        # Получаем список существующих плантаций для этой страны
        plantations = self.db.get_plantations_by_country(country)
        
        if plantations:
            # Создаем кнопки с существующими плантациями
            keyboard = []
            # Разбиваем на ряды по 2 кнопки
            for i in range(0, len(plantations), 2):
                row = []
                row.append(InlineKeyboardButton(plantations[i], callback_data=f"plantation_{plantations[i]}"))
                if i + 1 < len(plantations):
                    row.append(InlineKeyboardButton(plantations[i + 1], callback_data=f"plantation_{plantations[i + 1]}"))
                keyboard.append(row)
            keyboard.append([InlineKeyboardButton("✏️ Ввести новую плантацию", callback_data="plantation_new")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(f"Страна: {country}")
            await query.message.reply_text(f"Плантация для {country} (выберите из списка или введите новую)", reply_markup=reply_markup)
        else:
            await query.edit_message_text(f"Страна: {country}")
            await query.message.reply_text("Плантация")
        return PLANTATION
    
    async def get_country(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Получение страны (текстовый ввод)"""
        country = update.message.text.strip()
        context.user_data['country'] = country
        
        # Получаем список существующих плантаций для этой страны
        plantations = self.db.get_plantations_by_country(country)
        
        if plantations:
            # Создаем кнопки с существующими плантациями
            keyboard = []
            # Разбиваем на ряды по 2 кнопки
            for i in range(0, len(plantations), 2):
                row = []
                row.append(InlineKeyboardButton(plantations[i], callback_data=f"plantation_{plantations[i]}"))
                if i + 1 < len(plantations):
                    row.append(InlineKeyboardButton(plantations[i + 1], callback_data=f"plantation_{plantations[i + 1]}"))
                keyboard.append(row)
            keyboard.append([InlineKeyboardButton("✏️ Ввести новую плантацию", callback_data="plantation_new")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(f"Плантация для {country} (выберите из списка или введите новую)", reply_markup=reply_markup)
        else:
            await update.message.reply_text("Плантация")
        return PLANTATION
    
    async def get_plantation_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка выбора плантации через кнопку"""
        query = update.callback_query
        await query.answer()
        
        if query.data == "plantation_new":
            # Пользователь хочет ввести новую плантацию
            await query.edit_message_text(f"Введите название плантации для {context.user_data.get('country', '')}:")
            return PLANTATION
        
        plantation = query.data.replace("plantation_", "")
        context.user_data['plantation'] = plantation
        
        # Создаем кнопки для выбора обработки
        keyboard = [
            [InlineKeyboardButton("Washed", callback_data="processing_Washed")],
            [InlineKeyboardButton("Natural", callback_data="processing_Natural")],
            [InlineKeyboardButton("Anaerobic", callback_data="processing_Anaerobic")],
            [InlineKeyboardButton("Honey", callback_data="processing_Honey")],
            [InlineKeyboardButton("Infused", callback_data="processing_Infused")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(f"Плантация: {plantation}")
        await query.message.reply_text("Тип обработки", reply_markup=reply_markup)
        return PROCESSING
    
    async def get_plantation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Получение плантации (текстовый ввод)"""
        plantation = update.message.text.strip()
        context.user_data['plantation'] = plantation
        
        # Создаем кнопки для выбора обработки
        keyboard = [
            [InlineKeyboardButton("Washed", callback_data="processing_Washed")],
            [InlineKeyboardButton("Natural", callback_data="processing_Natural")],
            [InlineKeyboardButton("Anaerobic", callback_data="processing_Anaerobic")],
            [InlineKeyboardButton("Honey", callback_data="processing_Honey")],
            [InlineKeyboardButton("Infused", callback_data="processing_Infused")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text("Тип обработки", reply_markup=reply_markup)
        return PROCESSING
    
    async def get_processing_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка выбора типа обработки через кнопку"""
        query = update.callback_query
        await query.answer()
        
        processing = query.data.replace("processing_", "")
        context.user_data['processing'] = processing
        
        await query.edit_message_text(f"Тип обработки: {processing}")
        await query.message.reply_text("Обжарщик")
        return ROASTER
    
    async def get_roaster(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Получение обжарщика"""
        context.user_data['roaster'] = update.message.text
        
        # Создаем кнопки для выбора Q-грейдера
        keyboard = [
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
        
        await update.message.reply_text("Оценка Q-грейдера", reply_markup=reply_markup)
        return Q_GRADE
    
    async def get_q_grade_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка выбора Q-грейдера через кнопку"""
        query = update.callback_query
        await query.answer()
        
        q_grade_str = query.data.replace("qgrade_", "")
        
        # Преобразуем строку в число для сохранения
        if q_grade_str == "85+":
            context.user_data['q_grade'] = 86  # Сохраняем как 86 для сортировки
            q_grade_display = "85+"
        elif q_grade_str == "90+":
            context.user_data['q_grade'] = 91  # Сохраняем как 91 для сортировки
            q_grade_display = "90+"
        else:
            context.user_data['q_grade'] = int(q_grade_str)
            q_grade_display = q_grade_str
        
        await query.edit_message_text(f"Оценка Q-грейдера: {q_grade_display}")
        await query.message.reply_text("Твоя оценка (1–5)")
        return MY_RATING
    
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
        # Удаляем webhook и ждем перед запуском polling
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
