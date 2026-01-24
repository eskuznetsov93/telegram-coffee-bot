FROM python:3.11-slim

WORKDIR /app

# Устанавливаем системные зависимости для EasyOCR
RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Копируем requirements и устанавливаем зависимости
# Устанавливаем без предзагрузки моделей EasyOCR (они загрузятся при первом использовании)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем все файлы проекта
COPY main.py .
COPY db.py .
COPY models.py .

# Запускаем бота
CMD ["python3", "main.py"]
