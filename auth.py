import os
import jwt
import datetime
import sqlite3
from functools import wraps
from flask import request, jsonify
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

# Configuration
DB_PATH = os.path.join(os.path.dirname(__file__), 'auth.db')
JWT_SECRET = "super-secret-key-replace-in-prod" # Ideally from env
GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID', 'your_google_client_id_here')
ADMIN_EMAIL = "nitansh.bareja@gmail.com"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  email TEXT UNIQUE,
                  role TEXT,
                  created_at DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    conn.close()

def get_user(email):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT email, role, created_at FROM users WHERE email=?", (email,))
    user = c.fetchone()
    conn.close()
    if user:
        return {"email": user[0], "role": user[1], "created_at": user[2]}
    return None

def create_user(email, role='user'):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute("INSERT INTO users (email, role) VALUES (?, ?)", (email, role))
        conn.commit()
    except sqlite3.IntegrityError:
        pass # User already exists
    conn.close()

def verify_google_token(token):
    try:
        idinfo = id_token.verify_oauth2_token(token, google_requests.Request(), GOOGLE_CLIENT_ID)
        return idinfo
    except Exception as e:
        print(f"Token verification failed: {e}")
        return None

def generate_jwt(user_data):
    payload = {
        **user_data,
        "exp": datetime.datetime.utcnow() + datetime.timedelta(days=7)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token:
            return jsonify({"message": "Token is missing"}), 401
        try:
            token = token.split(" ")[1]
            data = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
            request.user = data
        except Exception as e:
            return jsonify({"message": "Token is invalid"}), 401
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token:
            return jsonify({"message": "Token is missing"}), 401
        try:
            token = token.split(" ")[1]
            data = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
            if data.get('role') != 'admin':
                return jsonify({"message": "Admin access required"}), 403
            request.user = data
        except Exception as e:
            return jsonify({"message": "Token is invalid"}), 401
        return f(*args, **kwargs)
    return decorated

def check_trial_status(email):
    user = get_user(email)
    if not user:
        return False
    if user['role'] == 'admin':
        return True
    
    created_at = datetime.datetime.strptime(user['created_at'], '%Y-%m-%d %H:%M:%S')
    days_diff = (datetime.datetime.now() - created_at).days
    return days_diff < 5

# Initialize database on import
init_db()
