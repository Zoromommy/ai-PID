# Лёгкий базовый образ Python
FROM python:3.11-slim

WORKDIR /app

# Системные зависимости
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Сначала устанавливаем PyTorch CPU (отдельно, чтобы кэшировалось)
RUN pip install --no-cache-dir \
    torch==2.3.0+cpu \
    --extra-index-url https://download.pytorch.org/whl/cpu

# Остальные зависимости
RUN pip install --no-cache-dir \
    fastapi==0.111.0 \
    uvicorn==0.29.0 \
    numpy==1.26.4 \
    joblib==1.4.2 \
    scikit-learn==1.4.2 \
    pydantic==2.7.1

# Копируем файлы проекта
COPY . .

# Открываем порт
EXPOSE 8000

# Запуск (PORT берётся из переменной окружения)
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
