# логика бота
import logging
import os
import sys
import time
import requests
import re
import io
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
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# OCR API (external service)
OCR_API_URL = "https://api.ocr.space/parse/image"
OCR_API_KEY_ENV = "OCR_SPACE_API_KEY"

# Состояния разговора
PHOTO, CONFIRM_COUNTRY, CONFIRM_PLANTATION, CONFIRM_PROCESSING, CONFIRM_ROASTER, COUNTRY, PLANTATION, PROCESSING, ROASTER, Q_GRADE, MY_RATING = range(11)


class CoffeeBot:
    def __init__(self, token: str):
        logger.info("Initializing CoffeeBot...")
        self.db = Database()
        logger.info("Database initialized")
        self.app = Application.builder().token(token).build()
        logger.info("Application created")
        self._setup_handlers()
        logger.info("CoffeeBot initialized successfully")

    def _call_ocr_api(self, image_bytes: bytes) -> Optional[str]:
        """Call external OCR API and return extracted text or None on failure."""
        api_key = os.getenv(OCR_API_KEY_ENV)
        if not api_key:
            logger.warning("OCR API key not set; skipping OCR.")
            return None
        try:
            # Compress image if too large
            from PIL import Image
            import io
            try:
                img = Image.open(io.BytesIO(image_bytes))
                # Resize if too large (max 2000px on longest side)
                max_size = 2000
                if max(img.size) > max_size:
                    ratio = max_size / max(img.size)
                    new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
                    img = img.resize(new_size, Image.Resampling.LANCZOS)
                
                # Convert to bytes
                output = io.BytesIO()
                img.save(output, format='JPEG', quality=85, optimize=True)
                image_bytes = output.getvalue()
            except Exception as e:
                logger.warning(f"Image compression failed, using original: {e}")
            
            response = requests.post(
                OCR_API_URL,
                files={"file": ("image.jpg", image_bytes, "image/jpeg")},
                data={
                    "apikey": api_key,
                    "language": "eng",
                    "scale": "true",
                    "OCREngine": "2",  # Use engine 2 for better accuracy
                },
                timeout=30,  # Increased timeout
            )
            response.raise_for_status()
            data = response.json()
            if data.get("IsErroredOnProcessing"):
                error_msg = data.get('ErrorMessage', 'Unknown error')
                logger.warning(f"OCR API error: {error_msg}")
                return None
            results = data.get("ParsedResults")
            if not results:
                logger.warning("OCR API returned no results")
                return None
            # Concatenate all parsed text parts
            text = " ".join((r.get("ParsedText", "") or "") for r in results)
            if not text.strip():
                logger.warning("OCR API returned empty text")
                return None
            return text
        except requests.exceptions.Timeout:
            logger.error("OCR API request timeout")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"OCR API request failed: {e}", exc_info=True)
            return None
        except Exception as e:
            logger.error(f"OCR API unexpected error: {e}", exc_info=True)
            return None
    
    def _setup_handlers(self):
        """Настройка обработчиков команд и сообщений"""
        # Обработчик добавления кофе
        add_coffee_handler = ConversationHandler(
            entry_points=[CommandHandler("add", self.start_add_coffee)],
            states={
                PHOTO: [
                    MessageHandler(filters.PHOTO, self.get_photo),
                    MessageHandler(filters.TEXT & ~filters.COMMAND & filters.Regex("^(Skip|skip|SKIP)$"), self.skip_photo)
                ],
                CONFIRM_COUNTRY: [
                    CallbackQueryHandler(self.confirm_country, pattern="^(confirm_country_|confirm_db_data_)(yes|no)$")
                ],
                CONFIRM_PLANTATION: [
                    CallbackQueryHandler(self.confirm_plantation, pattern="^confirm_plantation_(yes|no)$")
                ],
                CONFIRM_PROCESSING: [
                    CallbackQueryHandler(self.confirm_processing, pattern="^confirm_processing_(yes|no)$")
                ],
                CONFIRM_ROASTER: [
                    CallbackQueryHandler(self.confirm_roaster, pattern="^confirm_roaster_(yes|no)$")
                ],
                COUNTRY: [
                    CallbackQueryHandler(self.get_country_callback, pattern="^country_"),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_country)
                ],
                PLANTATION: [
                    CallbackQueryHandler(self.get_plantation_callback, pattern="^plantation_"),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_plantation)
                ],
                PROCESSING: [CallbackQueryHandler(self.get_processing_callback, pattern="^processing_")],
                ROASTER: [
                    CallbackQueryHandler(self.get_roaster_callback, pattern="^roaster_"),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_roaster)
                ],
                Q_GRADE: [CallbackQueryHandler(self.get_q_grade_callback, pattern="^qgrade_")],
                MY_RATING: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_my_rating)],
            },
            fallbacks=[CommandHandler("cancel", self.cancel)],
        )
        
        # Добавляем обработчики в правильном порядке
        # Сначала команды, потом ConversationHandler, потом общий обработчик
        self.app.add_handler(CommandHandler("start", self.start))
        self.app.add_handler(CommandHandler("help", self.help))
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
/my_list - Your coffee grouped by plantation+processing+q_grade+roaster, sorted by rating
/top - Top coffee grouped by plantation+processing+q_grade+roaster, sorted by average rating
/cancel - Cancel current operation
        """
        await update.message.reply_text(help_text)
    
    def _rating_to_stars(self, rating: Optional[int]) -> str:
        """Convert rating to stars"""
        if rating is None:
            return ""
        return "⭐" * rating
    
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
                q_grade_text = "Q: No"
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
                q_grade_text = "Q: No"
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
        await update.message.reply_text(
            "📸 Send a photo of the coffee package (or type 'Skip' to skip this step).\n\n"
            "I'll try to extract information from the photo automatically!"
        )
        return PHOTO
    
    async def get_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle photo upload and extract text using OCR"""
        if not update.message or not update.message.photo:
            await update.message.reply_text("Please send a photo or type 'Skip' to continue.")
            return PHOTO
        
        photo = update.message.photo[-1]  # Get highest resolution
        
        # Save photo IDs to context
        context.user_data['photo_file_id'] = photo.file_id
        context.user_data['photo_file_unique_id'] = photo.file_unique_id
        
        await update.message.reply_text("📸 Processing photo... This may take a moment.")
        
        # First, check if we have this photo in database
        existing_coffee = self.db.find_coffee_by_photo(photo.file_unique_id)
        
        if existing_coffee:
            # Found matching photo - suggest data from database
            avg_rating = existing_coffee.get('avg_rating')
            count = existing_coffee.get('count', 0)
            rating_text = f"{avg_rating:.2f}" if avg_rating else "—"
            
            keyboard = [
                [InlineKeyboardButton("✅ Yes, use this data", callback_data="confirm_db_data_yes")],
                [InlineKeyboardButton("❌ No, fill manually", callback_data="confirm_db_data_no")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                f"🎯 I found this coffee in the database!\n\n"
                f"Country: {existing_coffee.get('country', 'Not found')}\n"
                f"Plantation: {existing_coffee.get('plantation', 'Not found')}\n"
                f"Processing: {existing_coffee.get('processing', 'Not found')}\n"
                f"Roaster: {existing_coffee.get('roaster', 'Not found')}\n"
                f"Q-grade: {existing_coffee.get('q_grade') if existing_coffee.get('q_grade') is not None else 'No'}\n"
                f"Average rating: {rating_text} ({count} ratings)\n\n"
                f"Should I use this information?",
                reply_markup=reply_markup
            )
            
            # Fill context with database data (mark as extracted for confirmation)
            if existing_coffee.get('country'):
                context.user_data['country'] = existing_coffee['country']
                context.user_data['country_extracted'] = True
            if existing_coffee.get('plantation'):
                context.user_data['plantation'] = existing_coffee['plantation']
                context.user_data['plantation_extracted'] = True
            if existing_coffee.get('processing'):
                context.user_data['processing'] = existing_coffee['processing']
                context.user_data['processing_extracted'] = True
            if existing_coffee.get('roaster'):
                context.user_data['roaster'] = existing_coffee['roaster']
                context.user_data['roaster_extracted'] = True
            if existing_coffee.get('q_grade') is not None:
                context.user_data['q_grade'] = existing_coffee['q_grade']
                context.user_data['q_grade_extracted'] = True
            
            # Store flag to indicate we're in database data confirmation
            context.user_data['db_data_confirmation'] = True
            return CONFIRM_COUNTRY
        
        # Photo not found in database - try OCR
        extracted_data = {}
        try:
            # Download photo with timeout
            try:
                file = await context.bot.get_file(photo.file_id)
                # Use asyncio.wait_for for timeout on download
                import asyncio
                photo_bytes = await asyncio.wait_for(
                    file.download_as_bytearray(),
                    timeout=30.0
                )
            except asyncio.TimeoutError:
                logger.error("Photo download timeout")
                await update.message.reply_text("⚠️ Photo download timeout. Please try again or fill the form manually.")
                return await self._start_confirmation_flow(update, context)
            except Exception as e:
                logger.error(f"Photo download error: {e}", exc_info=True)
                await update.message.reply_text("⚠️ Error downloading photo. Please fill the form manually.")
                return await self._start_confirmation_flow(update, context)
            
            # Extract text using external OCR API (fast, no heavy libs in build)
            # Run OCR in executor to avoid blocking
            import asyncio
            loop = asyncio.get_event_loop()
            full_text = await loop.run_in_executor(
                None,
                self._call_ocr_api,
                photo_bytes
            )
            
            if full_text:
                try:
                    extracted_data = self._parse_coffee_info(full_text)
                    if extracted_data:
                        await update.message.reply_text(
                            f"✅ Found information on the package:\n\n"
                            f"Country: {extracted_data.get('country', 'Not found')}\n"
                            f"Plantation: {extracted_data.get('plantation', 'Not found')}\n"
                            f"Processing: {extracted_data.get('processing', 'Not found')}\n"
                            f"Roaster: {extracted_data.get('roaster', 'Not found')}\n\n"
                            f"I'll use this information to fill the form. You can edit it if needed."
                        )
                    else:
                        await update.message.reply_text(
                            "⚠️ Text extracted, but no specific coffee details found. Please fill the form manually."
                        )
                except Exception as e:
                    logger.error(f"OCR parse error: {e}", exc_info=True)
                    await update.message.reply_text(
                        "⚠️ Error processing extracted text. Please fill the form manually."
                    )
            else:
                await update.message.reply_text(
                    "⚠️ OCR failed or not configured. Please fill the form manually."
                )
            
            # Fill context with extracted data (mark as extracted for confirmation)
            if extracted_data.get('country'):
                context.user_data['country'] = extracted_data['country']
                context.user_data['country_extracted'] = True
            if extracted_data.get('plantation'):
                context.user_data['plantation'] = extracted_data['plantation']
                context.user_data['plantation_extracted'] = True
            if extracted_data.get('processing'):
                context.user_data['processing'] = extracted_data['processing']
                context.user_data['processing_extracted'] = True
            if extracted_data.get('roaster'):
                context.user_data['roaster'] = extracted_data['roaster']
                context.user_data['roaster_extracted'] = True
            
        except Exception as e:
            logger.error(f"Error processing photo: {e}", exc_info=True)
            await update.message.reply_text("⚠️ Error processing photo. Please fill the form manually.")
        
        # Start confirmation flow for extracted data
        return await self._start_confirmation_flow(update, context)
    
    async def skip_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Skip photo upload"""
        await update.message.reply_text("Skipping photo upload. Let's fill the form manually.")
        return await self._start_confirmation_flow(update, context)
    
    async def _start_confirmation_flow(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start confirmation flow for extracted data or go to manual input"""
        # Check country first
        if context.user_data.get('country_extracted'):
            country = context.user_data.get('country')
            keyboard = [
                [InlineKeyboardButton("✅ Yes", callback_data="confirm_country_yes")],
                [InlineKeyboardButton("❌ No", callback_data="confirm_country_no")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(f"Country: {country}\n\nCorrect?", reply_markup=reply_markup)
            return CONFIRM_COUNTRY
        else:
            return await self._continue_to_country(update, context)
    
    async def confirm_country(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle country confirmation"""
        query = update.callback_query
        await query.answer()
        
        # Check if this is database data confirmation
        if query.data == "confirm_db_data_yes":
            # User confirmed database data - skip all confirmations and go to rating
            context.user_data.pop('db_data_confirmation', None)
            context.user_data.pop('country_extracted', None)
            context.user_data.pop('plantation_extracted', None)
            context.user_data.pop('processing_extracted', None)
            context.user_data.pop('roaster_extracted', None)
            context.user_data.pop('q_grade_extracted', None)
            
            # Show summary
            country = context.user_data.get('country', '')
            plantation = context.user_data.get('plantation', '')
            processing = context.user_data.get('processing', '')
            roaster = context.user_data.get('roaster', '')
            q_grade = context.user_data.get('q_grade')
            if q_grade is None:
                q_grade_display = "No"
            elif q_grade == 91:
                q_grade_display = "90+"
            else:
                q_grade_display = str(q_grade)
            
            await query.edit_message_text(
                f"✅ Using data from database:\n\n"
                f"Country: {country}\n"
                f"Plantation: {plantation}\n"
                f"Processing: {processing}\n"
                f"Roaster: {roaster}\n"
                f"Q-grade: {q_grade_display}"
            )
            await query.message.reply_text("Your rating (1–5)")
            return MY_RATING
        
        if query.data == "confirm_db_data_no":
            # User wants to fill manually - clear all extracted data
            context.user_data.pop('db_data_confirmation', None)
            context.user_data.pop('country', None)
            context.user_data.pop('country_extracted', None)
            context.user_data.pop('plantation', None)
            context.user_data.pop('plantation_extracted', None)
            context.user_data.pop('processing', None)
            context.user_data.pop('processing_extracted', None)
            context.user_data.pop('roaster', None)
            context.user_data.pop('roaster_extracted', None)
            context.user_data.pop('q_grade', None)
            context.user_data.pop('q_grade_extracted', None)
            
            await query.edit_message_text("I'll help you fill the form manually.")
            from telegram import Update as UpdateType
            fake_update = UpdateType(update_id=0, message=query.message)
            return await self._continue_to_country(fake_update, context)
        
        if query.data == "confirm_country_no":
            # User wants to enter country manually - clear all extracted data
            context.user_data.pop('country', None)
            context.user_data.pop('country_extracted', None)
            context.user_data.pop('plantation', None)
            context.user_data.pop('plantation_extracted', None)
            context.user_data.pop('processing', None)
            context.user_data.pop('processing_extracted', None)
            context.user_data.pop('roaster', None)
            context.user_data.pop('roaster_extracted', None)
            # Create a fake Update object with message
            from telegram import Update as UpdateType
            fake_update = UpdateType(update_id=0, message=query.message)
            return await self._continue_to_country(fake_update, context)
        else:
            # Country confirmed, check plantation
            context.user_data.pop('country_extracted', None)
            if context.user_data.get('plantation_extracted'):
                plantation = context.user_data.get('plantation')
                keyboard = [
                    [InlineKeyboardButton("✅ Yes", callback_data="confirm_plantation_yes")],
                    [InlineKeyboardButton("❌ No", callback_data="confirm_plantation_no")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text(f"Country: {context.user_data.get('country')}")
                await query.message.reply_text(f"Plantation: {plantation}\n\nCorrect?", reply_markup=reply_markup)
                return CONFIRM_PLANTATION
            else:
                await query.edit_message_text(f"Country: {context.user_data.get('country')}")
                from telegram import Update as UpdateType
                fake_update = UpdateType(update_id=0, message=query.message)
                return await self._continue_to_plantation(fake_update, context)
    
    async def confirm_plantation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle plantation confirmation"""
        query = update.callback_query
        await query.answer()
        
        if query.data == "confirm_plantation_no":
            # User wants to enter plantation manually - clear subsequent extracted data
            context.user_data.pop('plantation', None)
            context.user_data.pop('plantation_extracted', None)
            context.user_data.pop('processing', None)
            context.user_data.pop('processing_extracted', None)
            context.user_data.pop('roaster', None)
            context.user_data.pop('roaster_extracted', None)
            await query.edit_message_text(f"Plantation: (will be entered manually)")
            from telegram import Update as UpdateType
            fake_update = UpdateType(update_id=0, message=query.message)
            return await self._continue_to_plantation(fake_update, context)
        else:
            # Plantation confirmed, check processing
            context.user_data.pop('plantation_extracted', None)
            plantation = context.user_data.get('plantation', '')
            await query.edit_message_text(f"Plantation: {plantation}")
            
            if context.user_data.get('processing_extracted'):
                processing = context.user_data.get('processing')
                keyboard = [
                    [InlineKeyboardButton("✅ Yes", callback_data="confirm_processing_yes")],
                    [InlineKeyboardButton("❌ No", callback_data="confirm_processing_no")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.message.reply_text(f"Processing: {processing}\n\nCorrect?", reply_markup=reply_markup)
                return CONFIRM_PROCESSING
            else:
                from telegram import Update as UpdateType
                fake_update = UpdateType(update_id=0, message=query.message)
                return await self._continue_to_processing(fake_update, context)
    
    async def confirm_processing(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle processing confirmation"""
        query = update.callback_query
        await query.answer()
        
        if query.data == "confirm_processing_no":
            # User wants to enter processing manually - clear subsequent extracted data
            context.user_data.pop('processing', None)
            context.user_data.pop('processing_extracted', None)
            context.user_data.pop('roaster', None)
            context.user_data.pop('roaster_extracted', None)
            await query.edit_message_text(f"Processing: (will be entered manually)")
            from telegram import Update as UpdateType
            fake_update = UpdateType(update_id=0, message=query.message)
            return await self._continue_to_processing(fake_update, context)
        else:
            # Processing confirmed, check roaster
            context.user_data.pop('processing_extracted', None)
            if context.user_data.get('roaster_extracted'):
                roaster = context.user_data.get('roaster')
                keyboard = [
                    [InlineKeyboardButton("✅ Yes", callback_data="confirm_roaster_yes")],
                    [InlineKeyboardButton("❌ No", callback_data="confirm_roaster_no")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text(f"Processing: {context.user_data.get('processing')}")
                await query.message.reply_text(f"Roaster: {roaster}\n\nCorrect?", reply_markup=reply_markup)
                return CONFIRM_ROASTER
            else:
                await query.edit_message_text(f"Processing: {context.user_data.get('processing')}")
                from telegram import Update as UpdateType
                fake_update = UpdateType(update_id=0, message=query.message)
                return await self._continue_to_roaster(fake_update, context)
    
    async def confirm_roaster(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle roaster confirmation"""
        query = update.callback_query
        await query.answer()
        
        if query.data == "confirm_roaster_no":
            # User wants to enter roaster manually
            context.user_data.pop('roaster', None)
            context.user_data.pop('roaster_extracted', None)
            await query.edit_message_text(f"Roaster: (will be entered manually)")
            from telegram import Update as UpdateType
            fake_update = UpdateType(update_id=0, message=query.message)
            return await self._continue_to_roaster(fake_update, context)
        else:
            # Roaster confirmed, check Q-grade
            context.user_data.pop('roaster_extracted', None)
            await query.edit_message_text(f"Roaster: {context.user_data.get('roaster')}")
            
            # If Q-grade was extracted from database, skip to rating
            if context.user_data.get('q_grade_extracted'):
                q_grade = context.user_data.get('q_grade')
                if q_grade is None:
                    q_grade_display = "No"
                elif q_grade == 91:
                    q_grade_display = "90+"
                else:
                    q_grade_display = str(q_grade)
                await query.message.reply_text(f"Q-grader score: {q_grade_display}")
                context.user_data.pop('q_grade_extracted', None)
                await query.message.reply_text("Your rating (1–5)")
                return MY_RATING
            
            # Create buttons for Q-grade selection
            keyboard = [
                [InlineKeyboardButton("No", callback_data="qgrade_No")],
                [
                    InlineKeyboardButton("84", callback_data="qgrade_84"),
                    InlineKeyboardButton("85", callback_data="qgrade_85"),
                    InlineKeyboardButton("86", callback_data="qgrade_86"),
                ],
                [
                    InlineKeyboardButton("87", callback_data="qgrade_87"),
                    InlineKeyboardButton("88", callback_data="qgrade_88"),
                    InlineKeyboardButton("89", callback_data="qgrade_89"),
                ],
                [InlineKeyboardButton("90+", callback_data="qgrade_90+")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.message.reply_text("Q-grader score", reply_markup=reply_markup)
            return Q_GRADE
    
    async def _continue_to_country(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Continue to country selection (shared logic)"""
        # Get message object (could be from Update or Message)
        message = update.message if hasattr(update, 'message') and update.message else update
        
        # Clear any extracted country data if we're doing manual input
        if not context.user_data.get('country_extracted'):
            context.user_data.pop('country', None)
        
        # Get list of existing countries
        countries = self.db.get_all_countries()
        
        if countries:
            keyboard = []
            for i in range(0, len(countries), 2):
                row = []
                row.append(InlineKeyboardButton(countries[i], callback_data=f"country_{countries[i]}"))
                if i + 1 < len(countries):
                    row.append(InlineKeyboardButton(countries[i + 1], callback_data=f"country_{countries[i + 1]}"))
                keyboard.append(row)
            keyboard.append([InlineKeyboardButton("✏️ Enter new country", callback_data="country_new")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await message.reply_text("Country (select from list or enter new)", reply_markup=reply_markup)
        else:
            await message.reply_text("Country")
        return COUNTRY
    
    async def _continue_to_plantation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Continue to plantation selection"""
        # Get message object (could be from Update or Message)
        message = update.message if hasattr(update, 'message') and update.message else update
        
        country = context.user_data.get('country')
        if not country:
            # Should not happen, but fallback
            return await self._continue_to_country(update, context)
        
        # Clear any extracted plantation data if we're doing manual input
        if not context.user_data.get('plantation_extracted'):
            context.user_data.pop('plantation', None)
        
        plantations = self.db.get_plantations_by_country(country)
        
        if plantations:
            keyboard = []
            for i in range(0, len(plantations), 2):
                row = []
                row.append(InlineKeyboardButton(plantations[i], callback_data=f"plantation_{plantations[i]}"))
                if i + 1 < len(plantations):
                    row.append(InlineKeyboardButton(plantations[i + 1], callback_data=f"plantation_{plantations[i + 1]}"))
                keyboard.append(row)
            keyboard.append([InlineKeyboardButton("✏️ Enter new plantation", callback_data="plantation_new")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await message.reply_text(f"Plantation for {country} (select from list or enter new)", reply_markup=reply_markup)
        else:
            await message.reply_text("Plantation")
        return PLANTATION
    
    async def _continue_to_processing(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Continue to processing selection"""
        # Get message object (could be from Update or Message)
        message = update.message if hasattr(update, 'message') and update.message else update
        
        # Clear any extracted processing data if we're doing manual input
        if not context.user_data.get('processing_extracted'):
            context.user_data.pop('processing', None)
        
        keyboard = [
            [InlineKeyboardButton("Washed", callback_data="processing_Washed")],
            [InlineKeyboardButton("Natural", callback_data="processing_Natural")],
            [InlineKeyboardButton("Anaerobic", callback_data="processing_Anaerobic")],
            [InlineKeyboardButton("Honey", callback_data="processing_Honey")],
            [InlineKeyboardButton("Infused", callback_data="processing_Infused")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await message.reply_text("Processing type", reply_markup=reply_markup)
        return PROCESSING
    
    async def _continue_to_roaster(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Continue to roaster selection"""
        # Get message object (could be from Update or Message)
        message = update.message if hasattr(update, 'message') and update.message else update
        
        # Clear any extracted roaster data if we're doing manual input
        if not context.user_data.get('roaster_extracted'):
            context.user_data.pop('roaster', None)
        
        roasters = self.db.get_all_roasters()
        
        if roasters:
            keyboard = []
            for i in range(0, len(roasters), 2):
                row = []
                row.append(InlineKeyboardButton(roasters[i], callback_data=f"roaster_{roasters[i]}"))
                if i + 1 < len(roasters):
                    row.append(InlineKeyboardButton(roasters[i + 1], callback_data=f"roaster_{roasters[i + 1]}"))
                keyboard.append(row)
            keyboard.append([InlineKeyboardButton("✏️ Enter new roaster", callback_data="roaster_new")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await message.reply_text("Roaster (select from list or enter new)", reply_markup=reply_markup)
        else:
            await message.reply_text("Roaster")
        return ROASTER
    
    def _parse_coffee_info(self, text: str) -> dict:
        """Parse coffee information from OCR text"""
        text_upper = text.upper()
        result = {}
        
        # Common country names
        countries = ['ETHIOPIA', 'COLOMBIA', 'BRAZIL', 'GUATEMALA', 'COSTA RICA', 'KENYA', 
                     'TANZANIA', 'YEMEN', 'PANAMA', 'EL SALVADOR', 'HONDURAS', 'NICARAGUA',
                     'PERU', 'BOLIVIA', 'ECUADOR', 'RWANDA', 'BURUNDI', 'UGANDA', 'INDIA',
                     'INDONESIA', 'VIETNAM', 'THAILAND', 'PHILIPPINES', 'PAPUA NEW GUINEA']
        
        # Find country
        for country in countries:
            if country in text_upper:
                # Try to get original case from text
                pattern = re.compile(re.escape(country), re.IGNORECASE)
                match = pattern.search(text)
                if match:
                    result['country'] = match.group()
                    break
        
        # Processing types
        processing_types = {
            'WASHED': 'Washed',
            'NATURAL': 'Natural',
            'ANAEROBIC': 'Anaerobic',
            'HONEY': 'Honey',
            'INFUSED': 'Infused',
            'PULPED NATURAL': 'Honey',
            'YELLOW HONEY': 'Honey',
            'RED HONEY': 'Honey',
            'BLACK HONEY': 'Honey'
        }
        
        for key, value in processing_types.items():
            if key in text_upper:
                result['processing'] = value
                break
        
        # Try to find plantation (usually after "FROM", "FINCA", "ESTATE", etc.)
        plantation_patterns = [
            r'(?:FROM|FINCA|ESTATE|FARM|PLANTATION)[\s:]+([A-Z][A-Z\s&]+?)(?:\n|$|,|PROCESS|ROAST)',
            r'([A-Z][A-Z\s&]{3,20}?)\s+(?:PROCESS|PROCESSING|ROAST|ROASTED)',
        ]
        
        for pattern in plantation_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                plantation = match.group(1).strip()
                if len(plantation) > 2 and plantation.upper() not in countries:
                    result['plantation'] = plantation
                    break
        
        # Try to find roaster (usually before "ROASTED", "ROAST", or company name patterns)
        roaster_patterns = [
            r'([A-Z][A-Z\s&]{2,25}?)\s+(?:ROASTED|ROAST|ROASTER)',
            r'ROASTED\s+BY\s+([A-Z][A-Z\s&]+?)(?:\n|$)',
        ]
        
        for pattern in roaster_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                roaster = match.group(1).strip()
                if len(roaster) > 2:
                    result['roaster'] = roaster
                    break
        
        return result
    
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
        
        # Get list of existing roasters
        roasters = self.db.get_all_roasters()
        
        if roasters:
            # Create buttons with existing roasters
            keyboard = []
            # Split into rows of 2 buttons
            for i in range(0, len(roasters), 2):
                row = []
                row.append(InlineKeyboardButton(roasters[i], callback_data=f"roaster_{roasters[i]}"))
                if i + 1 < len(roasters):
                    row.append(InlineKeyboardButton(roasters[i + 1], callback_data=f"roaster_{roasters[i + 1]}"))
                keyboard.append(row)
            keyboard.append([InlineKeyboardButton("✏️ Enter new roaster", callback_data="roaster_new")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.message.reply_text("Roaster (select from list or enter new)", reply_markup=reply_markup)
        else:
            await query.message.reply_text("Roaster")
        return ROASTER
    
    async def get_roaster_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle roaster selection via button"""
        query = update.callback_query
        await query.answer()
        
        if query.data == "roaster_new":
            # User wants to enter a new roaster
            await query.edit_message_text("Enter roaster name:")
            return ROASTER
        
        roaster = query.data.replace("roaster_", "")
        # Roaster from button is already normalized (from database)
        context.user_data['roaster'] = roaster
        
        # Create buttons for Q-grade selection
        keyboard = [
            [InlineKeyboardButton("No", callback_data="qgrade_No")],
            [
                InlineKeyboardButton("84", callback_data="qgrade_84"),
                InlineKeyboardButton("85", callback_data="qgrade_85"),
                InlineKeyboardButton("86", callback_data="qgrade_86"),
            ],
            [
                InlineKeyboardButton("87", callback_data="qgrade_87"),
                InlineKeyboardButton("88", callback_data="qgrade_88"),
                InlineKeyboardButton("89", callback_data="qgrade_89"),
            ],
            [InlineKeyboardButton("90+", callback_data="qgrade_90+")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(f"Roaster: {roaster}")
        await query.message.reply_text("Q-grader score", reply_markup=reply_markup)
        return Q_GRADE
    
    async def get_roaster(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Get roaster (text input)"""
        roaster = update.message.text.strip()
        # Normalize: find existing roaster with same name (case-insensitive) or use as is
        existing_roasters = self.db.get_all_roasters(limit=1000)  # Get all to find match
        for existing in existing_roasters:
            if existing.lower() == roaster.lower():
                roaster = existing  # Use the existing version (preserves original case)
                break
        context.user_data['roaster'] = roaster
        
        # Get list of existing roasters to show buttons
        roasters = self.db.get_all_roasters()
        
        if roasters:
            # Create buttons with existing roasters
            keyboard = []
            # Split into rows of 2 buttons
            for i in range(0, len(roasters), 2):
                row = []
                row.append(InlineKeyboardButton(roasters[i], callback_data=f"roaster_{roasters[i]}"))
                if i + 1 < len(roasters):
                    row.append(InlineKeyboardButton(roasters[i + 1], callback_data=f"roaster_{roasters[i + 1]}"))
                keyboard.append(row)
            keyboard.append([InlineKeyboardButton("✏️ Enter new roaster", callback_data="roaster_new")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(f"Roaster: {roaster}\n\nOr select from existing roasters:", reply_markup=reply_markup)
            return ROASTER
        
        # Create buttons for Q-grade selection
        keyboard = [
            [InlineKeyboardButton("No", callback_data="qgrade_No")],
            [
                InlineKeyboardButton("84", callback_data="qgrade_84"),
                InlineKeyboardButton("85", callback_data="qgrade_85"),
                InlineKeyboardButton("86", callback_data="qgrade_86"),
            ],
            [
                InlineKeyboardButton("87", callback_data="qgrade_87"),
                InlineKeyboardButton("88", callback_data="qgrade_88"),
                InlineKeyboardButton("89", callback_data="qgrade_89"),
            ],
            [InlineKeyboardButton("90+", callback_data="qgrade_90+")],
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
        if q_grade_str == "No":
            context.user_data['q_grade'] = None  # Store as None for "No"
            q_grade_display = "No"
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
            
            # Normalize roaster name before saving (find existing case-insensitive match)
            roaster = context.user_data.get('roaster', '')
            if roaster:
                existing_roasters = self.db.get_all_roasters(limit=1000)
                for existing in existing_roasters:
                    if existing.lower() == roaster.lower():
                        roaster = existing  # Use existing version to preserve original case
                        break
            
            # Create coffee object
            coffee = Coffee(
                user_id=update.effective_user.id,
                country=context.user_data.get('country', ''),
                plantation=context.user_data.get('plantation', ''),
                processing=context.user_data.get('processing', ''),
                roaster=roaster,
                q_grade=context.user_data.get('q_grade'),
                my_rating=rating,
                created_at=datetime.now(),
                photo_file_id=context.user_data.get('photo_file_id'),
                photo_file_unique_id=context.user_data.get('photo_file_unique_id')
            )
            
            # Save to database
            self.db.add_coffee(coffee)
            
            # Clear user data
            context.user_data.clear()
            
            await update.message.reply_text("☕ Coffee added!")
            
            # Show user's coffee list after adding
            user_id = update.effective_user.id
            grouped_coffee = self.db.get_grouped_coffee_by_user(user_id)
            
            if grouped_coffee:
                message_parts = []
                for i, item in enumerate(grouped_coffee, 1):
                    stars = self._rating_to_stars(item['max_rating'])
                    roaster = item['roaster'] if item['roaster'] else "Not specified"
                    processing = item['processing'] if item['processing'] else "Not specified"
                    # Format Q-grader for display
                    if item['q_grade'] is None:
                        q_grade_text = "Q: No"
                    elif item['q_grade'] == 91:
                        q_grade_text = "Q: 90+"
                    else:
                        q_grade_text = f"Q: {item['q_grade']}"
                    message_parts.append(f"{i}. {item['country']} | {item['plantation']} | {processing} | {roaster} | {q_grade_text} — {stars}")
                
                message = "\n".join(message_parts)
                await update.message.reply_text(f"📋 Your coffee list:\n\n{message}")
            
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
