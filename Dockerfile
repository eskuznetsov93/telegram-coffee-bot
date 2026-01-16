FROM python:3.11-slim

WORKDIR /app

# Копируем requirements и устанавливаем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем все файлы проекта
COPY main.py .
COPY db.py .
COPY models.py .

# Запускаем бота
CMD ["python3", "main.py"]
