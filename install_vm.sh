#!/bin/bash

# Скрипт установки Yukitery на VM (Ubuntu/Linux)
# Скопируйте этот текст и вставьте в терминал VM

echo "Установка Yukitery..."

# 1. Обновление системы
apt update && apt upgrade -y

# 2. Установка Python
apt install -y python3 python3-pip python3-venv git

# 3. Запрос URL репозитория
echo "Введите URL GitHub репозитория (пример: https://github.com/ВАШ_НИК/yukitery):"
read REPO_URL

# 4. Клонирование репозитория
git clone "$REPO_URL" ~/yukitery

# 5. Установка зависимостей
cd ~/yukitery
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 6. Открытие порта
ufw allow 5003/tcp

echo "Готово! Сайт будет доступен по адресу: http://IP_VM:5003"
echo "Для запуска: cd ~/yukitery && source venv/bin/activate && python3 app.py"

# 7. Запуск
echo "Запускаем сайт..."
source venv/bin/activate
python3 app.py
