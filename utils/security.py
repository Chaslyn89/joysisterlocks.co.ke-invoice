# utils/security.py
"""Security utilities: login decorator, rate limiting"""

from functools import wraps
from datetime import datetime, timedelta
from flask import session, redirect, url_for, request

# Rate limiting storage (in-memory, resets on server restart)
login_attempts = {}

def login_required(f):
    """Decorator to require login for routes"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def is_rate_limited(ip, max_attempts=5, lockout_time=900):
    """Check if an IP is rate limited"""
    if ip in login_attempts:
        attempts, lockout_until = login_attempts[ip]
        if lockout_until and datetime.now() < lockout_until:
            return True
        if lockout_until and datetime.now() >= lockout_until:
            del login_attempts[ip]
    return False

def record_failed_attempt(ip, max_attempts=5, lockout_time=900):
    """Record a failed login attempt"""
    now = datetime.now()
    if ip in login_attempts:
        attempts, lockout_until = login_attempts[ip]
        attempts += 1
        if attempts >= max_attempts:
            lockout_until = now + timedelta(seconds=lockout_time)
        login_attempts[ip] = (attempts, lockout_until)
    else:
        login_attempts[ip] = (1, None)

def clear_login_attempts(ip):
    """Clear successful login attempts"""
    if ip in login_attempts:
        del login_attempts[ip]

def get_remaining_attempts(ip, max_attempts=5):
    """Get remaining login attempts for an IP"""
    if ip in login_attempts:
        attempts, lockout_until = login_attempts[ip]
        if lockout_until and datetime.now() < lockout_until:
            return 0
        return max(0, max_attempts - attempts)
    return max_attempts