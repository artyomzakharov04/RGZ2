from functools import wraps  # Добавляем этот импорт

import psycopg2
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash, current_app
from psycopg2.extras import RealDictCursor
from werkzeug.security import generate_password_hash, check_password_hash
import os
import sqlite3  # Импортируем sqlite3 для работы с SQLite

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'секретно-секретный секрет')
app.config['DB_TYPE'] = os.getenv('DB_TYPE', 'postgres')  # Определяем тип базы данных (Postgres или SQLite)

# Функция для получения соединения с базой данных (PostgreSQL или SQLite)
def get_db_connection():
    if current_app.config['DB_TYPE'] == 'postgres':
        try:
            # Для PostgreSQL
            conn = psycopg2.connect(
                host='127.0.0.1',
                database='rgz_zaxarov22',
                user='rgz_zaxarov22',
                password='12345',
                cursor_factory=RealDictCursor  # Используем RealDictCursor для PostgreSQL
            )
            return conn
        except psycopg2.Error as e:
            print(f"Ошибка подключения к базе данных: {e}")
            flash('Не удается подключиться к базе данных. Проверьте настройки.', 'error')
            return None
    else:
        # Для SQLite
        db_path = os.path.join(os.path.dirname(__file__), 'database.db')
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row  # Используем Row factory для SQLite, аналогично RealDictCursor
        return conn

# Функции для авторизации и маршруты приложения
def login_required(f):
    @wraps(f)  # Используем импортированную функцию wraps
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        if username == "admin" and password == "admin":
            session['user_id'] = 'admin'
            return redirect(url_for('admin'))

        if not username or not password:
            flash('Введены неверные логин и/или пароль!', 'error')
            return redirect(url_for('login'))

        conn = get_db_connection()
        if conn is None:
            return redirect(url_for('login'))  # если не удалось подключиться, вернемся на страницу входа
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE username = %s", (username,))
        user = cur.fetchone()
        cur.close()
        conn.close()

        if user and check_password_hash(user[2], password):
            session['user_id'] = user[0]
            return redirect(url_for('index'))
        
        flash('Введены неверные логин и/или пароль!', 'error')
        return redirect(url_for('login'))
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect(url_for('index'))

@app.route('/')
def index():
    page = request.args.get('page', 1, type=int)
    offset = (page - 1) * 20
    conn = get_db_connection()
    if conn is None:
        return render_template('error.html', message="Не удается подключиться к базе данных.")
    cur = conn.cursor()
    
    # Правильный запрос для SQLite
    cur.execute("SELECT * FROM initiative ORDER BY date_created DESC LIMIT 20 OFFSET ?", (offset,))
    initiatives = cur.fetchall()

    # Для каждой инициативы получаем количество лайков и дизлайков
    initiative_likes = {}
    initiative_dislikes = {}
    for initiative in initiatives:
        initiative_id = initiative['id']
        
        # Подсчитываем количество лайков
        cur.execute("SELECT COUNT(*) FROM vote WHERE initiative_id = ? AND vote_value = 1", (initiative_id,))
        likes_result = cur.fetchone()
        likes = likes_result['count'] if likes_result else 0
        
        # Подсчитываем количество дизлайков
        cur.execute("SELECT COUNT(*) FROM vote WHERE initiative_id = ? AND vote_value = -1", (initiative_id,))
        dislikes_result = cur.fetchone()
        dislikes = dislikes_result['count'] if dislikes_result else 0
        
        initiative_likes[initiative_id] = likes
        initiative_dislikes[initiative_id] = dislikes

    # Получаем общее количество инициатив для пагинации
    cur.execute("SELECT COUNT(*) FROM initiative")
    total_initiatives_result = cur.fetchone()
    total_initiatives = total_initiatives_result.get('count', 0) if total_initiatives_result else 0

    cur.close()
    conn.close()
    return render_template('index.html', initiatives=initiatives, initiative_likes=initiative_likes, initiative_dislikes=initiative_dislikes, total_initiatives=total_initiatives)


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        if username == "admin":
            flash('Этот логин недоступен!', 'error')
            return redirect(url_for('register'))

        if not username or not password:
            flash('Введены неверные данные!', 'error')
            return redirect(url_for('register'))

        password_hash = generate_password_hash(password)

        conn = get_db_connection()
        if conn is None:
            return redirect(url_for('register'))  # если не удалось подключиться, вернемся на страницу регистрации
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE username = %s", (username,))
        if cur.fetchone():
            flash('Введены неверные данные!', 'error')
            return redirect(url_for('register'))

        cur.execute("INSERT INTO users (username, password) VALUES (%s, %s)", (username, password_hash))
        conn.commit()
        cur.close()
        conn.close()
        return redirect(url_for('login'))
    return render_template('register.html')

# Дополнительные маршруты для создания, удаления инициатив и голосования
@app.route('/create', methods=['GET', 'POST'])
@login_required
def create_initiative():
    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content']

        if not title or not content:
            flash('Введены неверные данные!', 'error')
            return redirect(url_for('create_initiative'))

        user_id = session['user_id']

        conn = get_db_connection()
        if conn is None:
            return redirect(url_for('create_initiative'))  # если не удалось подключиться, вернемся на страницу создания инициативы
        cur = conn.cursor()
        cur.execute("INSERT INTO initiative (title, content, user_id) VALUES (%s, %s, %s)", (title, content, user_id))
        conn.commit()
        cur.close()
        conn.close()
        return redirect(url_for('index'))
    return render_template('create_initiative.html')

@app.route('/delete/<int:initiative_id>')
@login_required
def delete_initiative(initiative_id):
    conn = get_db_connection()
    if conn is None:
        return redirect(url_for('index'))  # если не удалось подключиться, возвращаемся на главную страницу
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM initiative WHERE id = %s", (initiative_id,))
    initiative = cur.fetchone()
    if initiative and initiative['user_id'] != session['user_id']:
        flash('Введены неверные данные!', 'error')
        return redirect(url_for('index'))

    cur.execute("DELETE FROM initiative WHERE id = %s", (initiative_id,))
    conn.commit()
    cur.close()
    conn.close()
    return redirect(url_for('index'))

@app.route('/vote', methods=['POST'])
@login_required
def vote():
    data = request.get_json()
    initiative_id = data['initiative_id']
    vote_value = data['vote_value']
    user_id = session['user_id']

    conn = get_db_connection()
    if conn is None:
        return jsonify({'error': 'Не удалось подключиться к базе данных'}), 500

    cur = conn.cursor()
    cur.execute("SELECT * FROM vote WHERE user_id = %s AND initiative_id = %s", (user_id, initiative_id))
    existing_vote = cur.fetchone()

    if existing_vote:
        cur.execute("UPDATE vote SET vote_value = %s WHERE id = %s", (vote_value, existing_vote['id']))
    else:
        cur.execute("INSERT INTO vote (user_id, initiative_id, vote_value) VALUES (%s, %s, %s)", (user_id, initiative_id, vote_value))

    conn.commit()

    # Обновляем количество лайков и дизлайков
    cur.execute("SELECT COUNT(*) FROM vote WHERE initiative_id = %s AND vote_value = 1", (initiative_id,))
    likes_result = cur.fetchone()
    likes = likes_result['count'] if likes_result else 0
    
    cur.execute("SELECT COUNT(*) FROM vote WHERE initiative_id = %s AND vote_value = -1", (initiative_id,))
    dislikes_result = cur.fetchone()
    dislikes = dislikes_result['count'] if dislikes_result else 0

    # Если количество дизлайков >= 10, удаляем инициативу с сайта
    if dislikes >= 10:
        cur.execute("DELETE FROM initiative WHERE id = %s", (initiative_id,))
        conn.commit()

    cur.close()
    conn.close()

    return jsonify({'likes': likes, 'dislikes': dislikes})

# Оставшиеся маршруты и администрирование
@app.route('/admin', methods=['GET', 'POST'])
@login_required
def admin():
    if session['user_id'] != 'admin':
        flash('У вас нет прав доступа к этому разделу!', 'error')
        return redirect(url_for('index'))

    conn = get_db_connection()
    if conn is None:
        return redirect(url_for('index'))  # если не удалось подключиться, возвращаемся на страницу администрирования
    cur = conn.cursor()
    cur.execute("SELECT * FROM users")
    users = cur.fetchall()
    cur.execute("SELECT * FROM initiative")
    initiatives = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('admin.html', users=users, initiatives=initiatives)

# Удаление пользователя и инициативы
@app.route('/admin/delete_user/<int:user_id>')
@login_required
def delete_user(user_id):
    if session['user_id'] != 'admin':
        flash('У вас нет прав доступа к этому разделу!', 'error')
        return redirect(url_for('index'))

    conn = get_db_connection()
    if conn is None:
        return redirect(url_for('admin'))  # если не удалось подключиться, возвращаемся на страницу администрирования
    cur = conn.cursor()
    cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
    conn.commit()
    cur.close()
    conn.close()
    return redirect(url_for('admin'))

@app.route('/admin/delete_initiative/<int:initiative_id>')
@login_required
def delete_admin_initiative(initiative_id):
    if session['user_id'] != 'admin':
        flash('У вас нет прав доступа к этому разделу!', 'error')
        return redirect(url_for('index'))

    conn = get_db_connection()
    if conn is None:
        return redirect(url_for('admin'))  # если не удалось подключиться, возвращаемся на страницу администрирования
    cur = conn.cursor()
    cur.execute("DELETE FROM initiative WHERE id = %s", (initiative_id,))
    conn.commit()
    cur.close()
    conn.close()
    return redirect(url_for('admin'))

# Обработчик загрузки дополнительных инициатив
@app.route('/load_more_initiatives')
def load_more_initiatives():
    page = request.args.get('page', 1, type=int)
    offset = (page - 1) * 20

    conn = get_db_connection()
    if conn is None:
        return jsonify({'error': 'Не удалось подключиться к базе данных'}), 500
    cur = conn.cursor()
    cur.execute("SELECT * FROM initiative ORDER BY date_created DESC LIMIT 20 OFFSET %s", (offset,))
    initiatives = cur.fetchall()

    initiative_likes = {}
    initiative_dislikes = {}
    for initiative in initiatives:
        initiative_id = initiative['id']
        cur.execute("SELECT COUNT(*) FROM vote WHERE initiative_id = %s AND vote_value = 1", (initiative_id,))
        likes_result = cur.fetchone()
        likes = likes_result['count'] if likes_result else 0
        
        cur.execute("SELECT COUNT(*) FROM vote WHERE initiative_id = %s AND vote_value = -1", (initiative_id,))
        dislikes_result = cur.fetchone()
        dislikes = dislikes_result['count'] if dislikes_result else 0
        
        initiative_likes[initiative_id] = likes
        initiative_dislikes[initiative_id] = dislikes

    cur.close()
    conn.close()

    return jsonify({
        'initiatives': [dict(initiative) for initiative in initiatives],
        'initiative_likes': initiative_likes,
        'initiative_dislikes': initiative_dislikes
    })

if __name__ == '__main__':
    app.run(debug=True)




