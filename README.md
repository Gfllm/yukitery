# ❄ Yukitery — Платформа объявлений

Полноценная платформа для подачи и просмотра объявлений с чатом в реальном времени.

## Возможности

- **Регистрация и вход** — двухэтапная регистрация с подтверждением по email (6-значный код)
- **Личный кабинет** — аватар, биография, город, телефон
- **Объявления** — создание, редактирование, удаление, загрузка до 5 фото
- **Категории** — 10 предустановленных + свободные
- **Поиск и фильтры** — по тексту, категории, сортировка по цене/дате/популярности
- **Избранное** — сохранение понравившихся объявлений
- **Чат** — реалтайм WebSocket между покупателем и продавцом
- **Защита** — хеширование паролей (werkzeug), CSRF через session, валидация
- **Адаптивный дизайн** — тёмная тема, мобильное меню

## Быстрый старт

```bash
# 1. Установить зависимости
pip install -r requirements.txt

# 2. Настроить SMTP для отправки кодов (опционально)
export SMTP_HOST=smtp.gmail.com
export SMTP_PORT=587
export SMTP_USER=your@gmail.com
export SMTP_PASS=your_app_password
export SECRET_KEY=your_random_secret_key

# 3. Запустить
python app.py
```

Сайт будет доступен на `http://localhost:5000`

## SMTP настройка (Gmail)

1. Включите двухфакторную аутентификацию в Google аккаунте
2. Перейдите в Настройки → Безопасность → Пароли приложений
3. Создайте пароль для "Почта"
4. Используйте его как `SMTP_PASS`

Без SMTP коды будут выводиться в консоль (режим разработки).

## Деплой на VPS (Debian/Ubuntu)

```bash
# Установить Python и pip
sudo apt update && sudo apt install python3 python3-pip python3-venv -y

# Клонировать / загрузить проект
cd /opt
# ... скопировать yukitery/ сюда

# Виртуальное окружение
cd yukitery
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install gunicorn

# Systemd сервис
sudo tee /etc/systemd/system/yukitery.service << 'EOF'
[Unit]
Description=Yukitery Platform
After=network.target

[Service]
User=www-data
WorkingDirectory=/opt/yukitery
Environment=SMTP_HOST=smtp.gmail.com
Environment=SMTP_PORT=587
Environment=SMTP_USER=your@gmail.com
Environment=SMTP_PASS=your_app_password
Environment=SECRET_KEY=change_me_to_random_string
ExecStart=/opt/yukitery/venv/bin/gunicorn --worker-class eventlet -w 1 -b 0.0.0.0:5000 app:app
Restart=always

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl enable yukitery
sudo systemctl start yukitery
```

> **Важно:** для WebSocket нужен `eventlet`:
> ```bash
> pip install eventlet
> ```
> и gunicorn запускается с `--worker-class eventlet -w 1`

## Структура

```
yukitery/
├── app.py              # Основное приложение (Flask + SocketIO)
├── requirements.txt    # Зависимости
├── yukitery.db         # SQLite база (создаётся автоматически)
├── static/
│   ├── css/style.css   # Стили
│   └── uploads/        # Загруженные фото
└── templates/          # HTML шаблоны
    ├── base.html
    ├── index.html
    ├── register.html
    ├── login.html
    ├── profile.html
    ├── edit_profile.html
    ├── public_profile.html
    ├── new_listing.html
    ├── edit_listing.html
    ├── listing_detail.html
    ├── messages.html
    ├── chat.html
    ├── favorites.html
    └── 404.html
```
