# ☕ Telegram Coffee Bot

Telegram-бот для отслеживания и оценки кофе. Позволяет добавлять записи о кофе с информацией о стране, плантации, обработке, обжарщике, оценке Q-грейдера и личной оценке.

## 🚀 Быстрый старт

### Локальный запуск

1. Клонируйте репозиторий или скачайте файлы
2. Установите зависимости:
   ```bash
   pip install -r requirements.txt
   ```
3. Создайте файл `.env` с токеном бота и опционально ключом OCR API:
   ```
   TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
   OCR_SPACE_API_KEY=your_ocr_api_key_here  # Опционально, для распознавания текста с фото
   ```
4. Запустите бота:
   ```bash
   python3 main.py
   ```

## 📋 Команды бота

- `/start` - Начать работу с ботом
- `/help` - Показать список команд
- `/add` - Добавить новый кофе (можно загрузить фото для автоматического распознавания)
- `/my_list` - Ваш список кофе, сгруппированный по плантации+обработка+обжарщик
- `/top` - Топ кофе всех пользователей, сгруппированный по плантации+обработка+обжарщик, отсортированный по средней оценке
- `/cancel` - Отменить текущую операцию

## 🌐 Деплой на облачные платформы

### ⚡ Railway.app (РЕКОМЕНДУЕТСЯ - самый простой!)

**Самый простой способ деплоя:**

1. Зайдите на https://railway.app и войдите через GitHub
2. Создайте новый проект → Deploy from GitHub repo
3. Подключите ваш репозиторий
4. Добавьте переменные окружения (см. инструкцию ниже):
   - `TELEGRAM_BOT_TOKEN` = `ваш_токен` (обязательно)
   - `OCR_SPACE_API_KEY` = `ваш_ocr_ключ` (опционально, для распознавания текста с фото)
   - `DB_PATH` = `/data/coffee.db` (для постоянного хранения БД)
5. **ВАЖНО: Создайте Volume для базы данных:**
   - В Railway перейдите в ваш проект
   - Нажмите "+ New" → "Volume"
   - Назовите volume (например, "coffee-db")
   - Подключите volume к вашему сервису
   - Установите Mount Path: `/data`
6. **Готово!** Бот автоматически задеплоится и будет работать 24/7
   
**Примечание:** Без Volume база данных будет теряться при каждом перезапуске контейнера!

### 📝 Как добавить переменные окружения в Railway:

1. Откройте ваш проект в Railway
2. Нажмите на ваш сервис (service)
3. В правой панели найдите раздел **"Variables"** или перейдите во вкладку **"Variables"** в верхней панели
4. Нажмите **"+ New Variable"** или **"+ Add Variable"**
5. Для каждой переменной:
   - Введите **Name** (например: `TELEGRAM_BOT_TOKEN`)
   - Введите **Value** (ваш токен или значение)
   - Нажмите **"Add"** или **"Save"**
6. Railway автоматически перезапустит сервис после добавления переменных

Подробная инструкция в файле `RAILWAY_VARIABLES.md`

**Плюсы:**
- ✅ Автоматический деплой из GitHub
- ✅ Бесплатный план с $5 кредитом
- ✅ Работает 24/7
- ✅ Автоматические обновления при push

Подробные инструкции в файле `DEPLOY.md`

### 🎨 Render.com (альтернатива)

1. Зайдите на https://render.com
2. New → Web Service → подключите GitHub
3. Настройки:
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `python3 main.py`
4. Добавьте переменную: `TELEGRAM_BOT_TOKEN`
5. **Готово!**

### 🚁 Fly.io (хороший бесплатный вариант)

```bash
fly launch
fly secrets set TELEGRAM_BOT_TOKEN=ваш_токен
fly deploy
```

Подробные инструкции в файле `DEPLOY.md`

---

## 🌐 Деплой на AWS EC2 (Free Tier) - если нужен полный контроль

### Шаг 1: Создание EC2 инстанса

1. Войдите в [AWS Console](https://console.aws.amazon.com)
2. Перейдите в **EC2** → **Launch Instance**
3. Настройте инстанс:
   - **Name**: `telegram-coffee-bot`
   - **OS**: Ubuntu 22.04 LTS (Free Tier eligible)
   - **Instance type**: `t2.micro` (Free Tier eligible)
   - **Key pair**: Создайте новый или используйте существующий
   - **Security Group**: Разрешите SSH (port 22) из вашего IP
4. Нажмите **Launch Instance**

### Шаг 2: Подключение к серверу

```bash
ssh -i your-key.pem ubuntu@YOUR_EC2_PUBLIC_IP
```

### Шаг 3: Загрузка файлов проекта

**Вариант A: Через SCP (с вашего компьютера)**
```bash
scp -i your-key.pem -r /path/to/Telegram_coffee ubuntu@YOUR_EC2_IP:~/telegram_coffee
```

**Вариант B: Через Git (если проект в репозитории)**
```bash
cd ~
git clone YOUR_REPO_URL telegram_coffee
cd telegram_coffee
```

**Вариант C: Вручную (скопируйте все файлы)**

### Шаг 4: Автоматическая настройка

На сервере выполните:
```bash
cd ~/telegram_coffee
chmod +x setup_aws.sh
./setup_aws.sh
```

Скрипт автоматически:
- Обновит систему
- Установит Python и зависимости
- Создаст виртуальное окружение
- Установит зависимости проекта
- Создаст systemd service для автозапуска

### Шаг 5: Настройка токена

Создайте файл `.env`:
```bash
nano ~/telegram_coffee/.env
```

Добавьте:
```
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
```

Сохраните (Ctrl+O, Enter, Ctrl+X)

### Шаг 6: Запуск бота

```bash
sudo systemctl start telegram-coffee-bot
sudo systemctl status telegram-coffee-bot
```

### Управление ботом

```bash
# Просмотр логов
sudo journalctl -u telegram-coffee-bot -f

# Остановить
sudo systemctl stop telegram-coffee-bot

# Запустить
sudo systemctl start telegram-coffee-bot

# Перезапустить
sudo systemctl restart telegram-coffee-bot

# Статус
sudo systemctl status telegram-coffee-bot
```

## 📁 Структура проекта

```
telegram_coffee/
├── main.py              # Логика бота
├── db.py                # Работа с базой данных (с системой миграций)
├── models.py            # Модель данных Coffee
├── requirements.txt     # Зависимости Python
├── .env                 # Токен бота и OCR API ключ (не коммитится)
├── coffee.db            # База данных SQLite
├── coffee.db.backup     # Резервная копия БД
├── Dockerfile           # Docker конфигурация для деплоя
├── nixpacks.toml        # Nixpacks конфигурация для Railway
├── railway.json          # Railway конфигурация
├── Procfile              # Procfile для деплоя
├── install_and_run.sh    # Скрипт установки и запуска
├── run_bot.sh            # Скрипт запуска бота
└── README.md            # Документация
```

## 🔧 Технические детали

- **Язык**: Python 3.9+
- **Библиотека**: python-telegram-bot 20.0+
- **База данных**: SQLite с системой миграций
- **OCR**: Внешний API (ocr.space) для распознавания текста с фото
- **Оптимизации**: Индексы БД для быстрых запросов, оптимизированные SQL-запросы
- **Требования**: Минимум 512 MB RAM, 1 vCPU

## ✨ Особенности

- 📸 **OCR распознавание**: Загрузите фото пачки кофе, бот автоматически извлечет информацию
- 🔄 **Система миграций БД**: Автоматическое обновление схемы БД без потери данных
- ⚡ **Оптимизированные запросы**: Индексы для быстрой работы с большими объемами данных
- 🎯 **Умная группировка**: Автоматическое объединение похожих названий (с учетом опечаток)
- 📊 **Статистика**: Просмотр личного списка и общего топа кофе

## 💰 AWS Free Tier

AWS Free Tier включает:
- **750 часов** EC2 t2.micro в месяц (достаточно для работы 24/7)
- **30 GB** хранилища EBS
- **2 миллиона** запросов I/O

**Важно**: Free Tier действует 12 месяцев с момента регистрации AWS аккаунта.

## 🐛 Решение проблем

### Бот не отвечает

1. Проверьте логи: `sudo journalctl -u telegram-coffee-bot -f`
2. Убедитесь, что токен правильный в `.env`
3. Проверьте статус: `sudo systemctl status telegram-coffee-bot`

### Ошибки при установке

```bash
# Обновите pip
pip install --upgrade pip

# Переустановите зависимости
pip install -r requirements.txt --force-reinstall
```

### Проблемы с правами доступа

```bash
# Убедитесь, что файлы принадлежат правильному пользователю
sudo chown -R ubuntu:ubuntu ~/telegram_coffee
```

## 📝 Лицензия

Этот проект создан для личного использования.

## 🤝 Поддержка

Если возникли проблемы:
1. Проверьте логи бота
2. Убедитесь, что все зависимости установлены
3. Проверьте правильность токена в `.env`
