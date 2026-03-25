import os
import re
import random
import string
import time
import uuid
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from functools import wraps

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, jsonify, abort, send_from_directory
)
from flask_socketio import SocketIO, emit, join_room, leave_room
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import sqlite3

# ── Config ────────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', os.urandom(32).hex())
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(__file__), 'static', 'uploads')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)

# SMTP config — set these env vars on your server
SMTP_HOST = 'smtp.gmail.com'
SMTP_PORT = 587
SMTP_USER = 'heelpeers@gmail.com'
SMTP_PASS = 'cmthypytlhplzuig'
SMTP_FROM = 'heelpeers@gmail.com'

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# ── Database ──────────────────────────────────────────────────────────────────
DB_PATH = os.path.join(os.path.dirname(__file__), 'yukitery.db')


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    conn = get_db()
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            avatar TEXT DEFAULT '',
            bio TEXT DEFAULT '',
            phone TEXT DEFAULT '',
            city TEXT DEFAULT '',
            verified INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS email_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            code TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            used INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            slug TEXT UNIQUE NOT NULL,
            icon TEXT DEFAULT '📦'
        );

        CREATE TABLE IF NOT EXISTS listings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            category_id INTEGER,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            price REAL DEFAULT 0,
            currency TEXT DEFAULT 'RUB',
            city TEXT DEFAULT '',
            images TEXT DEFAULT '',
            status TEXT DEFAULT 'active',
            views INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (category_id) REFERENCES categories(id)
        );

        CREATE TABLE IF NOT EXISTS favorites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            listing_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, listing_id),
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (listing_id) REFERENCES listings(id)
        );

        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            listing_id INTEGER NOT NULL,
            buyer_id INTEGER NOT NULL,
            seller_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(listing_id, buyer_id),
            FOREIGN KEY (listing_id) REFERENCES listings(id),
            FOREIGN KEY (buyer_id) REFERENCES users(id),
            FOREIGN KEY (seller_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL,
            sender_id INTEGER NOT NULL,
            text TEXT NOT NULL,
            read INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (conversation_id) REFERENCES conversations(id),
            FOREIGN KEY (sender_id) REFERENCES users(id)
        );

        CREATE INDEX IF NOT EXISTS idx_listings_user ON listings(user_id);
        CREATE INDEX IF NOT EXISTS idx_listings_category ON listings(category_id);
        CREATE INDEX IF NOT EXISTS idx_listings_status ON listings(status);
        CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id);
        CREATE INDEX IF NOT EXISTS idx_favorites_user ON favorites(user_id);
    ''')
    # Seed default categories
    default_cats = [
        ('Электроника', 'electronics', '💻'),
        ('Авто', 'auto', '🚗'),
        ('Недвижимость', 'realty', '🏠'),
        ('Одежда', 'clothing', '👕'),
        ('Мебель', 'furniture', '🪑'),
        ('Услуги', 'services', '🔧'),
        ('Хобби', 'hobby', '🎨'),
        ('Животные', 'pets', '🐾'),
        ('Работа', 'jobs', '💼'),
        ('Другое', 'other', '📦'),
    ]
    for name, slug, icon in default_cats:
        conn.execute(
            'INSERT OR IGNORE INTO categories (name, slug, icon) VALUES (?, ?, ?)',
            (name, slug, icon)
        )
    conn.commit()
    conn.close()


init_db()

# ── Helpers ───────────────────────────────────────────────────────────────────

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Войдите в аккаунт', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


def get_current_user():
    if 'user_id' in session:
        db = get_db()
        user = db.execute('SELECT * FROM users WHERE id=?', (session['user_id'],)).fetchone()
        db.close()
        return user
    return None


def send_verification_email(to_email, code):
    """Send verification code via SMTP."""
    if not SMTP_USER or not SMTP_PASS:
        print(f"[DEV MODE] Verification code for {to_email}: {code}")
        return True
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f'Yukitery — код подтверждения: {code}'
        msg['From'] = SMTP_FROM
        msg['To'] = to_email
        html = f"""
        <div style="font-family:sans-serif;max-width:480px;margin:0 auto;padding:32px;background:#0f0f14;color:#e0e0e0;border-radius:12px;">
            <h2 style="color:#a78bfa;margin:0 0 16px;">Yukitery</h2>
            <p>Ваш код подтверждения:</p>
            <div style="font-size:32px;font-weight:bold;letter-spacing:8px;color:#fff;background:#1a1a2e;padding:16px 24px;border-radius:8px;text-align:center;margin:16px 0;">
                {code}
            </div>
            <p style="color:#888;font-size:13px;">Код действителен 10 минут. Если вы не регистрировались — проигнорируйте это письмо.</p>
        </div>
        """
        msg.attach(MIMEText(html, 'html'))
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SMTP_FROM, to_email, msg.as_string())
        return True
    except Exception as e:
        print(f"Email error: {e}")
        return False


def generate_code(length=6):
    return ''.join(random.choices(string.digits, k=length))


def unread_count(user_id):
    db = get_db()
    count = db.execute('''
        SELECT COUNT(*) FROM messages m
        JOIN conversations c ON m.conversation_id = c.id
        WHERE (c.buyer_id=? OR c.seller_id=?) AND m.sender_id!=? AND m.read=0
    ''', (user_id, user_id, user_id)).fetchone()[0]
    db.close()
    return count


@app.context_processor
def inject_globals():
    user = get_current_user()
    unread = unread_count(user['id']) if user else 0
    return dict(current_user=user, unread_messages=unread)


# ── Auth Routes ───────────────────────────────────────────────────────────────

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        step = request.form.get('step', '1')

        if step == '1':
            username = request.form.get('username', '').strip()
            email = request.form.get('email', '').strip().lower()
            password = request.form.get('password', '')

            errors = []
            if len(username) < 3:
                errors.append('Имя пользователя: минимум 3 символа')
            if not re.match(r'^[a-zA-Z0-9_]+$', username):
                errors.append('Имя: только латиница, цифры, _')
            if not re.match(r'^[^@]+@[^@]+\.[^@]+$', email):
                errors.append('Некорректный email')
            if len(password) < 6:
                errors.append('Пароль: минимум 6 символов')

            db = get_db()
            if db.execute('SELECT id FROM users WHERE username=?', (username,)).fetchone():
                errors.append('Имя пользователя занято')
            if db.execute('SELECT id FROM users WHERE email=?', (email,)).fetchone():
                errors.append('Email уже зарегистрирован')
            db.close()

            if errors:
                for e in errors:
                    flash(e, 'error')
                return render_template('register.html', step='1',
                                       username=username, email=email)

            code = generate_code()
            db = get_db()
            db.execute('INSERT INTO email_codes (email, code) VALUES (?, ?)', (email, code))
            db.commit()
            db.close()

            send_verification_email(email, code)

            session['reg_data'] = {
                'username': username,
                'email': email,
                'password': password,
            }
            return render_template('register.html', step='2', email=email)

        elif step == '2':
            code = request.form.get('code', '').strip()
            reg = session.get('reg_data')
            if not reg:
                flash('Сессия истекла, начните заново', 'error')
                return redirect(url_for('register'))

            db = get_db()
            row = db.execute('''
                SELECT * FROM email_codes
                WHERE email=? AND code=? AND used=0
                ORDER BY created_at DESC LIMIT 1
            ''', (reg['email'], code)).fetchone()

            if not row:
                flash('Неверный код', 'error')
                db.close()
                return render_template('register.html', step='2', email=reg['email'])

            # Check expiry (10 min)
            created = datetime.strptime(row['created_at'], '%Y-%m-%d %H:%M:%S')
            if datetime.utcnow() - created > timedelta(minutes=10):
                flash('Код истёк, запросите новый', 'error')
                db.close()
                return render_template('register.html', step='2', email=reg['email'])

            db.execute('UPDATE email_codes SET used=1 WHERE id=?', (row['id'],))
            db.execute(
                'INSERT INTO users (username, email, password_hash, verified) VALUES (?, ?, ?, 1)',
                (reg['username'], reg['email'], generate_password_hash(reg['password']))
            )
            db.commit()
            user = db.execute('SELECT id FROM users WHERE email=?', (reg['email'],)).fetchone()
            db.close()

            session.pop('reg_data', None)
            session['user_id'] = user['id']
            session.permanent = True
            flash('Добро пожаловать в Yukitery!', 'success')
            return redirect(url_for('index'))

    return render_template('register.html', step='1')


@app.route('/resend-code', methods=['POST'])
def resend_code():
    reg = session.get('reg_data')
    if not reg:
        return jsonify({'ok': False, 'msg': 'Сессия истекла'})
    code = generate_code()
    db = get_db()
    db.execute('INSERT INTO email_codes (email, code) VALUES (?, ?)', (reg['email'], code))
    db.commit()
    db.close()
    send_verification_email(reg['email'], code)
    return jsonify({'ok': True, 'msg': 'Код отправлен повторно'})


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        login_val = request.form.get('login', '').strip()
        password = request.form.get('password', '')

        db = get_db()
        user = db.execute(
            'SELECT * FROM users WHERE username=? OR email=?',
            (login_val, login_val.lower())
        ).fetchone()
        db.close()

        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            session.permanent = True
            flash(f'С возвращением, {user["username"]}!', 'success')
            return redirect(url_for('index'))
        flash('Неверный логин или пароль', 'error')

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('Вы вышли из аккаунта', 'info')
    return redirect(url_for('index'))


# ── Profile ───────────────────────────────────────────────────────────────────

@app.route('/profile')
@login_required
def profile():
    db = get_db()
    listings = db.execute(
        'SELECT * FROM listings WHERE user_id=? ORDER BY created_at DESC',
        (session['user_id'],)
    ).fetchall()
    db.close()
    return render_template('profile.html', listings=listings)


@app.route('/profile/edit', methods=['GET', 'POST'])
@login_required
def edit_profile():
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE id=?', (session['user_id'],)).fetchone()

    if request.method == 'POST':
        bio = request.form.get('bio', '').strip()[:500]
        phone = request.form.get('phone', '').strip()[:20]
        city = request.form.get('city', '').strip()[:100]
        avatar_path = user['avatar']

        if 'avatar' in request.files:
            file = request.files['avatar']
            if file and file.filename and allowed_file(file.filename):
                ext = file.filename.rsplit('.', 1)[1].lower()
                fname = f"avatar_{session['user_id']}_{uuid.uuid4().hex[:8]}.{ext}"
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], fname))
                avatar_path = fname

        db.execute(
            'UPDATE users SET bio=?, phone=?, city=?, avatar=? WHERE id=?',
            (bio, phone, city, avatar_path, session['user_id'])
        )
        db.commit()
        flash('Профиль обновлён', 'success')
        db.close()
        return redirect(url_for('profile'))

    db.close()
    return render_template('edit_profile.html', user=user)


@app.route('/user/<int:user_id>')
def public_profile(user_id):
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE id=?', (user_id,)).fetchone()
    if not user:
        abort(404)
    listings = db.execute(
        'SELECT * FROM listings WHERE user_id=? AND status="active" ORDER BY created_at DESC',
        (user_id,)
    ).fetchall()
    db.close()
    return render_template('public_profile.html', user=user, listings=listings)


# ── Listings ──────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    db = get_db()
    categories = db.execute('SELECT * FROM categories ORDER BY name').fetchall()
    q = request.args.get('q', '').strip()
    cat_slug = request.args.get('cat', '')
    sort = request.args.get('sort', 'new')
    page = max(1, int(request.args.get('page', 1)))
    per_page = 20

    sql = 'SELECT l.*, c.name as cat_name, c.icon as cat_icon, u.username FROM listings l LEFT JOIN categories c ON l.category_id=c.id JOIN users u ON l.user_id=u.id WHERE l.status="active"'
    params = []

    if q:
        sql += ' AND (l.title LIKE ? OR l.description LIKE ?)'
        params += [f'%{q}%', f'%{q}%']
    if cat_slug:
        sql += ' AND c.slug=?'
        params.append(cat_slug)

    if sort == 'price_asc':
        sql += ' ORDER BY l.price ASC'
    elif sort == 'price_desc':
        sql += ' ORDER BY l.price DESC'
    elif sort == 'popular':
        sql += ' ORDER BY l.views DESC'
    else:
        sql += ' ORDER BY l.created_at DESC'

    total = db.execute(sql.replace('SELECT l.*, c.name as cat_name, c.icon as cat_icon, u.username', 'SELECT COUNT(*)'), params).fetchone()[0]
    sql += ' LIMIT ? OFFSET ?'
    params += [per_page, (page - 1) * per_page]

    listings = db.execute(sql, params).fetchall()
    pages = max(1, (total + per_page - 1) // per_page)
    db.close()

    return render_template('index.html', listings=listings, categories=categories,
                           q=q, cat=cat_slug, sort=sort, page=page, pages=pages)


@app.route('/listing/new', methods=['GET', 'POST'])
@login_required
def new_listing():
    db = get_db()
    categories = db.execute('SELECT * FROM categories ORDER BY name').fetchall()

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        price = request.form.get('price', '0')
        category_id = request.form.get('category_id')
        city = request.form.get('city', '').strip()

        try:
            price = max(0, float(price))
        except ValueError:
            price = 0

        errors = []
        if len(title) < 3:
            errors.append('Заголовок: минимум 3 символа')
        if len(description) < 10:
            errors.append('Описание: минимум 10 символов')

        # Handle images
        image_names = []
        files = request.files.getlist('images')
        for f in files[:5]:  # max 5 images
            if f and f.filename and allowed_file(f.filename):
                ext = f.filename.rsplit('.', 1)[1].lower()
                fname = f"{uuid.uuid4().hex}.{ext}"
                f.save(os.path.join(app.config['UPLOAD_FOLDER'], fname))
                image_names.append(fname)

        if errors:
            for e in errors:
                flash(e, 'error')
            db.close()
            return render_template('new_listing.html', categories=categories)

        db.execute(
            '''INSERT INTO listings (user_id, category_id, title, description, price, city, images)
               VALUES (?, ?, ?, ?, ?, ?, ?)''',
            (session['user_id'], category_id or None, title, description, price, city,
             ','.join(image_names))
        )
        db.commit()
        listing_id = db.execute('SELECT last_insert_rowid()').fetchone()[0]
        db.close()
        flash('Объявление опубликовано!', 'success')
        return redirect(url_for('listing_detail', listing_id=listing_id))

    db.close()
    return render_template('new_listing.html', categories=categories)


@app.route('/listing/<int:listing_id>')
def listing_detail(listing_id):
    db = get_db()
    listing = db.execute('''
        SELECT l.*, c.name as cat_name, c.icon as cat_icon, u.username, u.avatar as user_avatar, u.city as user_city
        FROM listings l
        LEFT JOIN categories c ON l.category_id=c.id
        JOIN users u ON l.user_id=u.id
        WHERE l.id=?
    ''', (listing_id,)).fetchone()
    if not listing:
        abort(404)

    # Increment views
    db.execute('UPDATE listings SET views=views+1 WHERE id=?', (listing_id,))
    db.commit()

    is_fav = False
    if 'user_id' in session:
        is_fav = db.execute(
            'SELECT id FROM favorites WHERE user_id=? AND listing_id=?',
            (session['user_id'], listing_id)
        ).fetchone() is not None

    db.close()
    return render_template('listing_detail.html', listing=listing, is_fav=is_fav)


@app.route('/listing/<int:listing_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_listing(listing_id):
    db = get_db()
    listing = db.execute('SELECT * FROM listings WHERE id=? AND user_id=?',
                         (listing_id, session['user_id'])).fetchone()
    if not listing:
        abort(404)
    categories = db.execute('SELECT * FROM categories ORDER BY name').fetchall()

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        price = max(0, float(request.form.get('price', '0') or '0'))
        category_id = request.form.get('category_id')
        city = request.form.get('city', '').strip()
        status = request.form.get('status', 'active')

        existing_images = listing['images'].split(',') if listing['images'] else []
        files = request.files.getlist('images')
        for f in files[:5]:
            if f and f.filename and allowed_file(f.filename):
                ext = f.filename.rsplit('.', 1)[1].lower()
                fname = f"{uuid.uuid4().hex}.{ext}"
                f.save(os.path.join(app.config['UPLOAD_FOLDER'], fname))
                existing_images.append(fname)

        db.execute('''
            UPDATE listings SET title=?, description=?, price=?, category_id=?,
            city=?, images=?, status=?, updated_at=CURRENT_TIMESTAMP WHERE id=?
        ''', (title, description, price, category_id or None, city,
              ','.join(existing_images[:5]), status, listing_id))
        db.commit()
        db.close()
        flash('Объявление обновлено', 'success')
        return redirect(url_for('listing_detail', listing_id=listing_id))

    db.close()
    return render_template('edit_listing.html', listing=listing, categories=categories)


@app.route('/listing/<int:listing_id>/delete', methods=['POST'])
@login_required
def delete_listing(listing_id):
    db = get_db()
    db.execute('DELETE FROM listings WHERE id=? AND user_id=?', (listing_id, session['user_id']))
    db.commit()
    db.close()
    flash('Объявление удалено', 'info')
    return redirect(url_for('profile'))


# ── Favorites ─────────────────────────────────────────────────────────────────

@app.route('/favorite/<int:listing_id>', methods=['POST'])
@login_required
def toggle_favorite(listing_id):
    db = get_db()
    existing = db.execute('SELECT id FROM favorites WHERE user_id=? AND listing_id=?',
                          (session['user_id'], listing_id)).fetchone()
    if existing:
        db.execute('DELETE FROM favorites WHERE id=?', (existing['id'],))
        status = 'removed'
    else:
        db.execute('INSERT INTO favorites (user_id, listing_id) VALUES (?, ?)',
                   (session['user_id'], listing_id))
        status = 'added'
    db.commit()
    db.close()
    return jsonify({'status': status})


@app.route('/favorites')
@login_required
def favorites():
    db = get_db()
    listings = db.execute('''
        SELECT l.*, c.name as cat_name, c.icon as cat_icon, u.username
        FROM favorites f
        JOIN listings l ON f.listing_id=l.id
        LEFT JOIN categories c ON l.category_id=c.id
        JOIN users u ON l.user_id=u.id
        WHERE f.user_id=?
        ORDER BY f.created_at DESC
    ''', (session['user_id'],)).fetchall()
    db.close()
    return render_template('favorites.html', listings=listings)


# ── Chat / Messages ──────────────────────────────────────────────────────────

@app.route('/chat/start/<int:listing_id>', methods=['POST'])
@login_required
def start_chat(listing_id):
    db = get_db()
    listing = db.execute('SELECT * FROM listings WHERE id=?', (listing_id,)).fetchone()
    if not listing or listing['user_id'] == session['user_id']:
        abort(400)

    conv = db.execute(
        'SELECT id FROM conversations WHERE listing_id=? AND buyer_id=?',
        (listing_id, session['user_id'])
    ).fetchone()

    if not conv:
        db.execute(
            'INSERT INTO conversations (listing_id, buyer_id, seller_id) VALUES (?, ?, ?)',
            (listing_id, session['user_id'], listing['user_id'])
        )
        db.commit()
        conv = db.execute(
            'SELECT id FROM conversations WHERE listing_id=? AND buyer_id=?',
            (listing_id, session['user_id'])
        ).fetchone()

    db.close()
    return redirect(url_for('chat_room', conv_id=conv['id']))


@app.route('/messages')
@login_required
def messages_list():
    db = get_db()
    convs = db.execute('''
        SELECT c.*, l.title as listing_title, l.images as listing_images,
            u_buyer.username as buyer_name, u_seller.username as seller_name,
            (SELECT text FROM messages WHERE conversation_id=c.id ORDER BY created_at DESC LIMIT 1) as last_msg,
            (SELECT created_at FROM messages WHERE conversation_id=c.id ORDER BY created_at DESC LIMIT 1) as last_msg_time,
            (SELECT COUNT(*) FROM messages WHERE conversation_id=c.id AND sender_id!=? AND read=0) as unread
        FROM conversations c
        JOIN listings l ON c.listing_id=l.id
        JOIN users u_buyer ON c.buyer_id=u_buyer.id
        JOIN users u_seller ON c.seller_id=u_seller.id
        WHERE c.buyer_id=? OR c.seller_id=?
        ORDER BY last_msg_time DESC
    ''', (session['user_id'], session['user_id'], session['user_id'])).fetchall()
    db.close()
    return render_template('messages.html', conversations=convs)


@app.route('/chat/<int:conv_id>')
@login_required
def chat_room(conv_id):
    db = get_db()
    conv = db.execute('''
        SELECT c.*, l.title as listing_title, l.id as listing_id,
            u_buyer.username as buyer_name, u_seller.username as seller_name
        FROM conversations c
        JOIN listings l ON c.listing_id=l.id
        JOIN users u_buyer ON c.buyer_id=u_buyer.id
        JOIN users u_seller ON c.seller_id=u_seller.id
        WHERE c.id=? AND (c.buyer_id=? OR c.seller_id=?)
    ''', (conv_id, session['user_id'], session['user_id'])).fetchone()
    if not conv:
        abort(404)

    msgs = db.execute('''
        SELECT m.*, u.username FROM messages m
        JOIN users u ON m.sender_id=u.id
        WHERE m.conversation_id=? ORDER BY m.created_at ASC
    ''', (conv_id,)).fetchall()

    # Mark as read
    db.execute(
        'UPDATE messages SET read=1 WHERE conversation_id=? AND sender_id!=?',
        (conv_id, session['user_id'])
    )
    db.commit()
    db.close()

    other_name = conv['seller_name'] if conv['buyer_id'] == session['user_id'] else conv['buyer_name']
    return render_template('chat.html', conv=conv, messages=msgs, other_name=other_name)


# ── WebSocket Events ─────────────────────────────────────────────────────────

@socketio.on('join')
def handle_join(data):
    room = f"conv_{data['conv_id']}"
    join_room(room)


@socketio.on('send_message')
def handle_message(data):
    user_id = session.get('user_id')
    if not user_id:
        return

    conv_id = data.get('conv_id')
    text = data.get('text', '').strip()
    if not text or not conv_id:
        return

    db = get_db()
    # Verify user belongs to conversation
    conv = db.execute(
        'SELECT * FROM conversations WHERE id=? AND (buyer_id=? OR seller_id=?)',
        (conv_id, user_id, user_id)
    ).fetchone()
    if not conv:
        db.close()
        return

    db.execute(
        'INSERT INTO messages (conversation_id, sender_id, text) VALUES (?, ?, ?)',
        (conv_id, user_id, text)
    )
    db.commit()

    user = db.execute('SELECT username FROM users WHERE id=?', (user_id,)).fetchone()
    db.close()

    emit('new_message', {
        'sender_id': user_id,
        'username': user['username'],
        'text': text,
        'time': datetime.utcnow().strftime('%H:%M'),
    }, room=f"conv_{conv_id}")


@socketio.on('typing')
def handle_typing(data):
    user_id = session.get('user_id')
    if user_id:
        emit('user_typing', {
            'user_id': user_id
        }, room=f"conv_{data.get('conv_id')}", include_self=False)


# ── Static Files ──────────────────────────────────────────────────────────────

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


# ── Error Handlers ────────────────────────────────────────────────────────────

@app.errorhandler(404)
def not_found(e):
    return render_template('404.html'), 404


@app.errorhandler(413)
def too_large(e):
    flash('Файл слишком большой (макс. 16 МБ)', 'error')
    return redirect(request.url)


# ── Run ───────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5003, debug=True, allow_unsafe_werkzeug=True)
