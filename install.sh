#!/bin/bash

# Скрипт установки Yukitery на VM (Ubuntu/Linux)
# Запуск: bash install.sh https://github.com/ВАШ_НИК/РЕПОЗИТОРИЙ

set -e

REPO_URL="https://github.com/Gfllm/yukitery"

echo "════════════════════════════════════════"
echo "  Установка Yukitery"
echo "════════════════════════════════════════"

# Проверка URL
if [ -z "$REPO_URL" ]; then
    echo "ОШИБКА: Укажите URL репозитория!"
    echo "Пример: bash install.sh https://github.com/ваш_ник/yukitery"
    exit 1
fi

echo "URL репозитория: $REPO_URL"

# 1. Обновление системы
echo "[1/6] Обновление системы..."
apt update && apt upgrade -y

# 2. Установка Python
echo "[2/6] Установка Python..."
apt install -y python3 python3-pip python3-venv git

# 3. Клонирование репозитория
echo "[3/6] Клонирование репозитория..."
git clone "$REPO_URL" ~/yukitery

# 4. Установка зависимостей
echo "[4/6] Установка зависимостей..."
cd ~/yukitery
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 5. Открытие порта
echo "[5/6] Настройка firewall..."
ufw allow 5003/tcp || true

# 6. Запуск
echo "[6/6] Запуск сайта..."
echo "════════════════════════════════════════"
source venv/bin/activate
python3 app.py
