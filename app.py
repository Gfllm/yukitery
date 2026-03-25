import os
import sqlite3
import random
import string
from datetime import datetime, timedelta
from functools import wraps
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory, session
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import smtplib

# ── Config ────────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'k-pavely-secret-key-2024')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(__file__), 'static', 'uploads')

# Пользователи с правом публикации объявлений
ADMIN_USERS = ['Kurdun']

# Email настройки
SMTP_HOST = 'smtp.gmail.com'
SMTP_PORT = 587
SMTP_USER = 'heelpeers@gmail.com'
SMTP_PASS = 'ujdt rqws ypbv kyzk'
SMTP_FROM = 'heelpeers@gmail.com'

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# ── Database ──────────────────────────────────────────────────────────────────
DB_PATH = os.path.join(os.path.dirname(__file__), 'kpavely.db')


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    conn = get_db()
    cursor = conn.cursor()
    
    # Таблица пользователей
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            is_verified INTEGER DEFAULT 0,
            verification_code TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Таблица настроек
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            call_time_from TEXT DEFAULT '09:00',
            call_time_to TEXT DEFAULT '21:00',
            owner_name TEXT DEFAULT 'K.Pavely',
            owner_phone TEXT DEFAULT ''
        )
    ''')
    
    # Таблица объявлений
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS listings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            name TEXT NOT NULL,
            price REAL NOT NULL,
            photo TEXT,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    # Таблица сообщений
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            listing_id INTEGER,
            message TEXT NOT NULL,
            is_read INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (listing_id) REFERENCES listings (id)
        )
    ''')
    
    # Вставляем настройки по умолчанию
    cursor.execute('SELECT COUNT(*) FROM settings')
    if cursor.fetchone()[0] == 0:
        cursor.execute('INSERT INTO settings (call_time_from, call_time_to) VALUES (?, ?)', 
                       ('09:00', '21:00'))
    
    conn.commit()
    conn.close()


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def send_email(to_email, subject, body):
    """Отправка email с кодом подтверждения"""
    try:
        msg = MIMEMultipart()
        msg['From'] = SMTP_FROM
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'html', 'utf-8'))
        
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)
        return True
    except Exception as e:
        print(f"Email error: {e}")
        return False


def generate_verification_code(length=6):
    """Генерация кода подтверждения"""
    return ''.join(random.choices(string.digits, k=length))


# ── Auth Decorator ─────────────────────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('user_id'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


def can_post_listings():
    """Проверка, может ли пользователь публиковать объявления"""
    username = session.get('username', '').lower()
    return username in [u.lower() for u in ADMIN_USERS]


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    conn = get_db()
    cursor = conn.cursor()
    
    # Параметры поиска и сортировки
    search = request.args.get('search', '').strip()
    sort = request.args.get('sort', 'newest')
    
    # Базовый запрос
    query = 'SELECT id, name, price, photo, description, created_at FROM listings'
    params = []
    
    # Добавляем поиск
    if search:
        query += ' WHERE name LIKE ? OR description LIKE ?'
        params = [f'%{search}%', f'%{search}%']
    
    # Добавляем сортировку
    if sort == 'price_low':
        query += ' ORDER BY price ASC'
    elif sort == 'price_high':
        query += ' ORDER BY price DESC'
    elif sort == 'name':
        query += ' ORDER BY name ASC'
    else:
        query += ' ORDER BY created_at DESC'
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    
    listings = []
    for row in rows:
        listing = dict(row)
        created_at = listing.get('created_at', '')
        if created_at:
            if isinstance(created_at, str):
                try:
                    listing['created_at'] = datetime.strptime(created_at, '%Y-%m-%d %H:%M:%S')
                except:
                    listing['created_at'] = datetime.now()
            else:
                listing['created_at'] = created_at
        else:
            listing['created_at'] = datetime.now()
        listings.append(listing)
    
    # Получаем настройки
    cursor.execute('SELECT call_time_from, call_time_to, owner_name, owner_phone FROM settings LIMIT 1')
    row = cursor.fetchone()
    if row:
        settings = dict(row)
    else:
        settings = {'call_time_from': '09:00', 'call_time_to': '21:00', 'owner_name': 'K.Pavely', 'owner_phone': ''}
    
    conn.close()
    
    return render_template('index.html', listings=listings, settings=settings, search=search, sort=sort)


@app.route('/listing/<int:listing_id>')
def listing_detail(listing_id):
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT id, name, price, photo, description, created_at, user_id FROM listings WHERE id = ?', (listing_id,))
    row = cursor.fetchone()
    
    cursor.execute('SELECT call_time_from, call_time_to, owner_name, owner_phone FROM settings LIMIT 1')
    settings_row = cursor.fetchone()
    
    conn.close()
    
    if row is None:
        return render_template('404.html'), 404
    
    listing = dict(row)
    created_at = listing.get('created_at', '')
    if created_at:
        if isinstance(created_at, str):
            try:
                listing['created_at'] = datetime.strptime(created_at, '%Y-%m-%d %H:%M:%S')
            except:
                listing['created_at'] = datetime.now()
        else:
            listing['created_at'] = created_at
    else:
        listing['created_at'] = datetime.now()
    
    if settings_row:
        settings = dict(settings_row)
    else:
        settings = {'call_time_from': '09:00', 'call_time_to': '21:00', 'owner_name': 'K.Pavely', 'owner_phone': ''}
    
    return render_template('listing.html', listing=listing, settings=settings)


@app.route('/add', methods=['GET', 'POST'])
@login_required
def add_listing():
    if not can_post_listings():
        flash('У вас нет права публиковать объявления', 'error')
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        price = request.form.get('price', '').strip()
        description = request.form.get('description', '').strip()
        photo = None
        
        if 'photo' in request.files:
            file = request.files['photo']
            if file and file.filename and allowed_file(file.filename):
                filename = secure_filename(f"{datetime.now().timestamp()}_{file.filename}")
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                photo = filename
        
        if not name or not price:
            flash('Пожалуйста, заполните название и цену', 'error')
            return redirect(url_for('add_listing'))
        
        try:
            price = float(price)
        except ValueError:
            flash('Цена должна быть числом', 'error')
            return redirect(url_for('add_listing'))
        
        conn = get_db()
        cursor = conn.cursor()
        user_id = session.get('user_id')
        cursor.execute('INSERT INTO listings (user_id, name, price, description, photo) VALUES (?, ?, ?, ?, ?)',
                       (user_id, name, price, description, photo))
        conn.commit()
        conn.close()
        
        flash('Объявление успешно добавлено!', 'success')
        return redirect(url_for('index'))
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT call_time_from, call_time_to FROM settings LIMIT 1')
    row = cursor.fetchone()
    if row:
        settings = dict(row)
    else:
        settings = {'call_time_from': '09:00', 'call_time_to': '21:00'}
    conn.close()
    
    return render_template('add.html', settings=settings)


@app.route('/delete/<int:listing_id>')
@login_required
def delete_listing(listing_id):
    if not can_post_listings():
        flash('У вас нет права удалять объявления', 'error')
        return redirect(url_for('index'))
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT photo FROM listings WHERE id = ?', (listing_id,))
    listing = cursor.fetchone()
    
    if listing and listing['photo']:
        photo_path = os.path.join(app.config['UPLOAD_FOLDER'], listing['photo'])
        if os.path.exists(photo_path):
            os.remove(photo_path)
    
    cursor.execute('DELETE FROM listings WHERE id = ?', (listing_id,))
    conn.commit()
    conn.close()
    
    flash('Объявление удалено', 'success')
    return redirect(url_for('index'))


@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    if not can_post_listings():
        flash('У вас нет доступа к настройкам', 'error')
        return redirect(url_for('index'))
    
    conn = get_db()
    cursor = conn.cursor()
    
    if request.method == 'POST':
        call_time_from = request.form.get('call_time_from', '09:00')
        call_time_to = request.form.get('call_time_to', '21:00')
        owner_name = request.form.get('owner_name', 'K.Pavely')
        owner_phone = request.form.get('owner_phone', '')
        
        cursor.execute('''
            UPDATE settings 
            SET call_time_from = ?, call_time_to = ?, owner_name = ?, owner_phone = ?
            WHERE id = 1
        ''', (call_time_from, call_time_to, owner_name, owner_phone))
        conn.commit()
        
        flash('Настройки сохранены!', 'success')
        return redirect(url_for('index'))
    
    cursor.execute('SELECT call_time_from, call_time_to, owner_name, owner_phone FROM settings LIMIT 1')
    row = cursor.fetchone()
    if row:
        settings = dict(row)
    else:
        settings = {'call_time_from': '09:00', 'call_time_to': '21:00', 'owner_name': 'K.Pavely', 'owner_phone': ''}
    conn.close()
    
    return render_template('settings.html', settings=settings)


# ── Auth Routes ─────────────────────────────────────────────────────────────

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        
        if not username or not email or not password:
            flash('Заполните все поля', 'error')
            return redirect(url_for('register'))
        
        # Проверка длины пароля
        if len(password) < 4:
            flash('Пароль должен быть не менее 4 символов', 'error')
            return redirect(url_for('register'))
        
        password_hash = generate_password_hash(password)
        verification_code = generate_verification_code()
        
        conn = get_db()
        cursor = conn.cursor()
        
        # Проверка существующего пользователя
        cursor.execute('SELECT id FROM users WHERE username = ? OR email = ?', (username, email))
        if cursor.fetchone():
            flash('Пользователь с таким именем или email уже существует', 'error')
            conn.close()
            return redirect(url_for('register'))
        
        try:
            cursor.execute('''
                INSERT INTO users (username, email, password_hash, verification_code)
                VALUES (?, ?, ?, ?)
            ''', (username, email, password_hash, verification_code))
            conn.commit()
            user_id = cursor.lastrowid
            
            # Отправка email с кодом
            if send_email(email, 'Код подтверждения K.Pavely', 
                        f'<h2>Код подтверждения: {verification_code}</h2><p>Введите этот код на сайте для подтверждения email.</p>'):
                session['pending_user_id'] = user_id
                session['pending_email'] = email
                flash('Код подтверждения отправлен на ваш email!', 'success')
                return redirect(url_for('verify'))
            else:
                # Если email не отправлен - активируем сразу (для теста)
                cursor.execute('UPDATE users SET is_verified = 1 WHERE id = ?', (user_id,))
                conn.commit()
                flash('Регистрация успешна! Теперь вы можете войти.', 'success')
                return redirect(url_for('login'))
                
        except Exception as e:
            flash(f'Ошибка при регистрации: {e}', 'error')
            conn.close()
            return redirect(url_for('register'))
    
    return render_template('register.html')


@app.route('/verify', methods=['GET', 'POST'])
def verify():
    if request.method == 'POST':
        code = request.form.get('code', '').strip()
        
        user_id = session.get('pending_user_id')
        if not user_id:
            flash('Сессия истекла. Зарегистрируйтесь заново.', 'error')
            return redirect(url_for('register'))
        
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('SELECT verification_code FROM users WHERE id = ?', (user_id,))
        row = cursor.fetchone()
        
        if row and row['verification_code'] == code:
            cursor.execute('UPDATE users SET is_verified = 1, verification_code = NULL WHERE id = ?', (user_id,))
            conn.commit()
            session.pop('pending_user_id', None)
            session.pop('pending_email', None)
            flash('Email подтверждён! Теперь вы можете войти.', 'success')
            return redirect(url_for('login'))
        else:
            flash('Неверный код подтверждения', 'error')
            conn.close()
            return redirect(url_for('verify'))
    
    email = session.get('pending_email', '')
    return render_template('verify.html', email=email)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('SELECT id, username, password_hash, is_verified FROM users WHERE username = ?', (username,))
        user = cursor.fetchone()
        conn.close()
        
        if user and check_password_hash(user['password_hash'], password):
            if not user['is_verified']:
                session['pending_user_id'] = user['id']
                session['pending_email'] = user['username']
                flash('Сначала подтвердите email!', 'error')
                return redirect(url_for('verify'))
            
            session['user_id'] = user['id']
            session['username'] = user['username']
            flash(f'Добро пожаловать, {user["username"]}!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Неверное имя пользователя или пароль', 'error')
            return redirect(url_for('login'))
    
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.pop('user_id', None)
    session.pop('username', None)
    flash('Вы вышли из системы', 'success')
    return redirect(url_for('index'))


@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('SELECT id, username FROM users WHERE email = ?', (email,))
        user = cursor.fetchone()
        
        if user:
            # Генерируем новый код сброса
            reset_code = generate_verification_code()
            cursor.execute('UPDATE users SET verification_code = ? WHERE id = ?', (reset_code, user['id']))
            conn.commit()
            
            # Отправляем email
            if send_email(email, 'Код сброса пароля K.Pavely',
                        f'<h2>Код сброса пароля: {reset_code}</h2><p>Введите этот код для сброса пароля.</p>'):
                session['reset_user_id'] = user['id']
                session['reset_email'] = email
                flash('Код сброса отправлен на email!', 'success')
                return redirect(url_for('reset_password'))
            else:
                flash('Ошибка отправки email. Попробуйте позже.', 'error')
        else:
            flash('Email не найден в системе', 'error')
        
        conn.close()
        return redirect(url_for('forgot_password'))
    
    return render_template('forgot_password.html')


@app.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    user_id = session.get('reset_user_id')
    if not user_id:
        flash('Сессия истекла', 'error')
        return redirect(url_for('forgot_password'))
    
    if request.method == 'POST':
        code = request.form.get('code', '').strip()
        new_password = request.form.get('password', '').strip()
        
        if len(new_password) < 4:
            flash('Пароль должен быть не менее 4 символов', 'error')
            return redirect(url_for('reset_password'))
        
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('SELECT verification_code FROM users WHERE id = ?', (user_id,))
        row = cursor.fetchone()
        
        if row and row['verification_code'] == code:
            password_hash = generate_password_hash(new_password)
            cursor.execute('UPDATE users SET password_hash = ?, verification_code = NULL WHERE id = ?', 
                         (password_hash, user_id))
            conn.commit()
            session.pop('reset_user_id', None)
            session.pop('reset_email', None)
            flash('Пароль успешно изменён! Войдите с новым паролем.', 'success')
            return redirect(url_for('login'))
        else:
            flash('Неверный код', 'error')
        
        conn.close()
    
    return render_template('reset_password.html')


# ── Messages Routes ─────────────────────────────────────────────────────

@app.route('/messages')
@login_required
def messages():
    conn = get_db()
    cursor = conn.cursor()
    
    user_id = session.get('user_id')
    
    # Получаем все сообщения для пользователя
    cursor.execute('''
        SELECT m.*, l.name as listing_name, u.username
        FROM messages m
        LEFT JOIN listings l ON m.listing_id = l.id
        LEFT JOIN users u ON m.user_id = u.id
        ORDER BY m.created_at DESC
    ''')
    all_messages = cursor.fetchall()
    
    # Сообщения от пользователей (для админа/Kurdun)
    user_messages = []
    if can_post_listings():
        for msg in all_messages:
            user_messages.append(dict(msg))
    else:
        # Обычный пользователь видит только свои сообщения
        for msg in all_messages:
            if msg['user_id'] == user_id:
                user_messages.append(dict(msg))
    
    conn.close()
    return render_template('messages.html', messages=user_messages)


@app.route('/send_message/<int:listing_id>', methods=['GET', 'POST'])
@login_required
def send_message(listing_id):
    conn = get_db()
    cursor = conn.cursor()
    
    # Получаем объявление
    cursor.execute('SELECT name FROM listings WHERE id = ?', (listing_id,))
    listing = cursor.fetchone()
    
    if not listing:
        conn.close()
        return render_template('404.html'), 404
    
    if request.method == 'POST':
        message_text = request.form.get('message', '').strip()
        
        if message_text:
            user_id = session.get('user_id')
            cursor.execute('INSERT INTO messages (user_id, listing_id, message) VALUES (?, ?, ?)',
                          (user_id, listing_id, message_text))
            conn.commit()
            flash('Сообщение отправлено продавцу!', 'success')
            return redirect(url_for('index'))
    
    conn.close()
    return render_template('send_message.html', listing_name=listing['name'], listing_id=listing_id)


@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


# ── Error Handlers ──────────────────────────────────────────────────────────
@app.errorhandler(404)
def not_found(e):
    return render_template('404.html'), 404


@app.errorhandler(500)
def server_error(e):
    return render_template('500.html'), 500


# ── Context Processor ─────────────────────────────────────────────────────
@app.context_processor
def inject_can_post():
    return dict(can_post_listings=can_post_listings)

# ── Init & Run ──────────────────────────────────────────────────────────────
if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5003, debug=True)
