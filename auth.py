import os
import hashlib
import secrets
from datetime import datetime, timedelta

# Simple password hashing (can upgrade to bcrypt later)
def hash_password(password):
    salt = secrets.token_hex(16)
    hash_obj = hashlib.sha256((password + salt).encode())
    return f"{salt}:{hash_obj.hexdigest()}"

def verify_password(password, stored_hash):
    salt, hash_value = stored_hash.split(':')
    hash_obj = hashlib.sha256((password + salt).encode())
    return hash_obj.hexdigest() == hash_value

def get_user_by_username(username):
    from database import get_db
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute('SELECT id, username, password_hash, email FROM users WHERE username = %s', (username,))
        user = cursor.fetchone()
        if user:
            return {
                'id': user[0],
                'username': user[1],
                'password_hash': user[2],
                'email': user[3]
            }
        return None
    finally:
        from database import return_db
        return_db(conn)

def create_user(username, password, email):
    from database import get_db
    conn = get_db()
    try:
        cursor = conn.cursor()
        password_hash = hash_password(password)
        cursor.execute('''
            INSERT INTO users (username, password_hash, email, created_at)
            VALUES (%s, %s, %s, %s)
        ''', (username, password_hash, email, datetime.now().isoformat()))
        conn.commit()
        return True
    except Exception as e:
        print(f"Error creating user: {e}")
        return False
    finally:
        from database import return_db
        return_db(conn)

def update_user_password(username, new_password):
    from database import get_db
    conn = get_db()
    try:
        cursor = conn.cursor()
        password_hash = hash_password(new_password)
        cursor.execute('UPDATE users SET password_hash = %s, updated_at = %s WHERE username = %s',
                      (password_hash, datetime.now().isoformat(), username))
        conn.commit()
        return True
    finally:
        from database import return_db
        return_db(conn)
