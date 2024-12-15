import psycopg2
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'

def get_db_connection():
    return psycopg2.connect(database="rgz_zaxarov22", user="rgz_zaxarov22", password="12345", host="localhost")

# Helper functions
def login_required(f):
    @wraps(f)
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
    cur = conn.cursor()
    cur.execute("SELECT * FROM initiative ORDER BY date_created DESC LIMIT 20 OFFSET %s", (offset,))
    initiatives = cur.fetchall()

    # Для каждой инициативы получаем количество лайков и дизлайков
    initiative_likes = {}
    initiative_dislikes = {}
    for initiative in initiatives:
        initiative_id = initiative[0]
        
        # Подсчитываем количество лайков
        cur.execute("SELECT COUNT(*) FROM vote WHERE initiative_id = %s AND vote_value = 1", (initiative_id,))
        likes = cur.fetchone()[0]
        
        # Подсчитываем количество дизлайков
        cur.execute("SELECT COUNT(*) FROM vote WHERE initiative_id = %s AND vote_value = -1", (initiative_id,))
        dislikes = cur.fetchone()[0]
        
        initiative_likes[initiative_id] = likes
        initiative_dislikes[initiative_id] = dislikes

    # Получаем общее количество инициатив для пагинации
    cur.execute("SELECT COUNT(*) FROM initiative")
    total_initiatives = cur.fetchone()[0]

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
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM initiative WHERE id = %s", (initiative_id,))
    initiative = cur.fetchone()
    if initiative and initiative[0] != session['user_id']:
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
    cur = conn.cursor()
    cur.execute("SELECT * FROM vote WHERE user_id = %s AND initiative_id = %s", (user_id, initiative_id))
    existing_vote = cur.fetchone()

    if existing_vote:
        cur.execute("UPDATE vote SET vote_value = %s WHERE id = %s", (vote_value, existing_vote[0]))
    else:
        cur.execute("INSERT INTO vote (user_id, initiative_id, vote_value) VALUES (%s, %s, %s)", (user_id, initiative_id, vote_value))

    conn.commit()

    # Обновляем количество лайков и дизлайков
    cur.execute("SELECT COUNT(*) FROM vote WHERE initiative_id = %s AND vote_value = 1", (initiative_id,))
    likes = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM vote WHERE initiative_id = %s AND vote_value = -1", (initiative_id,))
    dislikes = cur.fetchone()[0]

    # Если количество дизлайков >= 10, удаляем инициативу с сайта
    if dislikes >= 10:
        cur.execute("DELETE FROM initiative WHERE id = %s", (initiative_id,))
        conn.commit()

    cur.close()
    conn.close()

    return jsonify({'likes': likes, 'dislikes': dislikes})

@app.route('/admin', methods=['GET', 'POST'])
@login_required
def admin():
    if session['user_id'] != 'admin':
        flash('У вас нет прав доступа к этому разделу!', 'error')
        return redirect(url_for('index'))

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users")
    users = cur.fetchall()
    cur.execute("SELECT * FROM initiative")
    initiatives = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('admin.html', users=users, initiatives=initiatives)

@app.route('/admin/delete_user/<int:user_id>')
@login_required
def delete_user(user_id):
    if session['user_id'] != 'admin':
        flash('У вас нет прав доступа к этому разделу!', 'error')
        return redirect(url_for('index'))

    conn = get_db_connection()
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
    cur = conn.cursor()

    # Получаем инициативы для текущей страницы
    cur.execute("SELECT * FROM initiative ORDER BY date_created DESC LIMIT 20 OFFSET %s", (offset,))
    initiatives = cur.fetchall()

    # Для каждой инициативы получаем количество лайков и дизлайков
    initiative_likes = {}
    initiative_dislikes = {}
    for initiative in initiatives:
        initiative_id = initiative[0]

        # Подсчитываем количество лайков
        cur.execute("SELECT COUNT(*) FROM vote WHERE initiative_id = %s AND vote_value = 1", (initiative_id,))
        likes = cur.fetchone()[0]

        # Подсчитываем количество дизлайков
        cur.execute("SELECT COUNT(*) FROM vote WHERE initiative_id = %s AND vote_value = -1", (initiative_id,))
        dislikes = cur.fetchone()[0]

        initiative_likes[initiative_id] = likes
        initiative_dislikes[initiative_id] = dislikes

    # Получаем общее количество инициатив для пагинации
    cur.execute("SELECT COUNT(*) FROM initiative")
    total_initiatives = cur.fetchone()[0]

    cur.close()
    conn.close()

    return jsonify({
        'initiatives': [{
            'id': initiative[0],
            'title': initiative[1],
            'content': initiative[2],
            'date_created': initiative[3],
            'likes': initiative_likes[initiative[0]],
            'dislikes': initiative_dislikes[initiative[0]]
        } for initiative in initiatives],
        'total_initiatives': total_initiatives
    })



















