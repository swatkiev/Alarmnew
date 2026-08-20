FROM python:3.9-alpine

# Устанавливаем системные зависимости для работы с SQLite и сетевыми библиотеками
RUN apk add --no-cache gcc musl-dev sqlite-dev

# Рабочая директория
WORKDIR /opt/alarmnew/

# Установка необходимых Python-пакетов
RUN pip install --no-cache-dir aiogram==2.25.2 python_http_client

# Запуск бота
CMD ["python", "alarmnew.py"]
