FROM python:3.11-slim

WORKDIR /app

# Устанавливаем системные зависимости для EasyOCR
RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Копируем requirements и устанавливаем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Предзагружаем модели EasyOCR (опционально, но ускоряет первый запуск)
RUN python3 -c "import easyocr; easyocr.Reader(['en'], gpu=False)" || true

# Копируем все файлы проекта
COPY main.py .
COPY db.py .
COPY models.py .

# Запускаем бота
CMD ["python3", "main.py"]
