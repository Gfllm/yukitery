import os
import sqlite3
from datetime import datetime
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory, session
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

# ── Config ────────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'k-pavely-secret-key-2024')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(__file__), 'static', 'uploads')

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
    
    # Таблица настроек (для времени звонков)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            call_time_from TEXT DEFAULT '09:00',
            call_time_to TEXT DEFAULT '21:00',
            owner_name TEXT DEFAULT 'K.Pavely',
            owner_phone TEXT DEFAULT '+375XXXXXXXXX'
        )
    ''')
    
    # Таблица объявлений
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS listings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            price REAL NOT NULL,
            photo TEXT,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Вставляем настройки по умолчанию, если нет
    cursor.execute('SELECT COUNT(*) FROM settings')
    if cursor.fetchone()[0] == 0:
        cursor.execute('INSERT INTO settings (call_time_from, call_time_to) VALUES (?, ?)', 
                       ('09:00', '21:00'))
    
    conn.commit()
    conn.close()


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    conn = get_db()
    cursor = conn.cursor()
    
    # Получаем все объявления
    cursor.execute('SELECT id, name, price, photo, description, created_at FROM listings ORDER BY created_at DESC')
    rows = cursor.fetchall()
    
    # Преобразуем строки в словари с правильным форматом даты
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
    cursor.execute('SELECT * FROM settings LIMIT 1')
    settings = cursor.fetchone()
    
    conn.close()
    
    return render_template('index.html', listings=listings, settings=settings)


@app.route('/listing/<int:listing_id>')
def listing_detail(listing_id):
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT id, name, price, photo, description, created_at FROM listings WHERE id = ?', (listing_id,))
    row = cursor.fetchone()
    
    cursor.execute('SELECT * FROM settings LIMIT 1')
    settings = cursor.fetchone()
    
    conn.close()
    
    if row is None:
        return render_template('404.html'), 404
    
    # Преобразуем дату
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
    
    return render_template('listing.html', listing=listing, settings=settings)


@app.route('/add', methods=['GET', 'POST'])
def add_listing():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        price = request.form.get('price', '').strip()
        description = request.form.get('description', '').strip()
        photo = None
        
        # Проверка загрузки файла
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
        cursor.execute('INSERT INTO listings (name, price, description, photo) VALUES (?, ?, ?, ?)',
                       (name, price, description, photo))
        conn.commit()
        conn.close()
        
        flash('Объявление успешно добавлено!', 'success')
        return redirect(url_for('index'))
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT call_time_from, call_time_to, owner_name, owner_phone FROM settings LIMIT 1')
    row = cursor.fetchone()
    conn.close()
    
    if row:
        settings = dict(row)
    else:
        settings = {
            'call_time_from': '09:00',
            'call_time_to': '21:00',
            'owner_name': 'K.Pavely',
            'owner_phone': ''
        }
    
    return render_template('add.html', settings=settings)


@app.route('/delete/<int:listing_id>')
def delete_listing(listing_id):
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
def settings():
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
    conn.close()
    
    # Преобразуем в словарь с значениями по умолчанию
    if row:
        settings = dict(row)
    else:
        settings = {
            'call_time_from': '09:00',
            'call_time_to': '21:00',
            'owner_name': 'K.Pavely',
            'owner_phone': ''
        }
    
    return render_template('settings.html', settings=settings)


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


# ── Init & Run ──────────────────────────────────────────────────────────────
if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5003, debug=True)
