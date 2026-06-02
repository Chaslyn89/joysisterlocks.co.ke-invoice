# app.py
"""Main application factory for Joy Sisterlocks Invoice System"""

from flask import Flask, render_template, session, redirect, url_for
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
import os

from config import Config
from database import init_db
from blueprints import invoices_bp, clients_bp, expenses_bp

# Import for auth routes (kept here for simplicity, can move to blueprint later)
from utils.security import is_rate_limited, record_failed_attempt, clear_login_attempts

def create_app():
    """Application factory"""
    app = Flask(__name__)
    
    # Configuration
    app.secret_key = Config.SECRET_KEY
    app.permanent_session_lifetime = Config.PERMANENT_SESSION_LIFETIME
    
    # Register blueprints
    app.register_blueprint(invoices_bp)
    app.register_blueprint(clients_bp)
    app.register_blueprint(expenses_bp)
    
    # ============ AUTH ROUTES (keep here for now) ============
    ADMIN_PASSWORD_HASH = generate_password_hash(Config.ADMIN_PASSWORD)
    
    @app.route('/login', methods=['GET', 'POST'])
    def login():
        client_ip = request.remote_addr
        
        if request.method == 'POST':
            if is_rate_limited(client_ip, Config.MAX_LOGIN_ATTEMPTS, Config.LOGIN_LOCKOUT_TIME):
                return render_template('login.html', error='Too many attempts. Please wait 15 minutes.')
            
            password = request.form.get('password')
            if check_password_hash(ADMIN_PASSWORD_HASH, password):
                session.permanent = True
                session['logged_in'] = True
                session['login_time'] = datetime.now().isoformat()
                clear_login_attempts(client_ip)
                return redirect(url_for('invoices.index'))
            else:
                record_failed_attempt(client_ip, Config.MAX_LOGIN_ATTEMPTS, Config.LOGIN_LOCKOUT_TIME)
                return render_template('login.html', error='Invalid password.')
        
        return render_template('login.html')
    
    @app.route('/logout')
    def logout():
        session.clear()
        return redirect(url_for('login'))
    
    # ============ DASHBOARD ROUTES ============
    @app.route("/dashboard")
    def dashboard():
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return render_template("dashboard.html")
    
    @app.route("/api/dashboard-stats")
    def api_dashboard_stats():
        if not session.get('logged_in'):
            return jsonify({"error": "Unauthorized"}), 401
        
        from database import get_dashboard_stats, get_client_stats
        stats = get_dashboard_stats()
        client_stats = get_client_stats()
        
        return jsonify({
            'today_revenue': stats['today_revenue'],
            'today_appointments': stats['today_appointments'],
            'total_balance': stats['total_outstanding'],
            'total_revenue': stats['gross_revenue'],
            'total_expenses': stats['total_expenses'],
            'profit': stats['profit'],
            'revenue_data': stats['revenue_data'],
            'revenue_dates': stats['revenue_dates'],
            'total_clients': client_stats['total_clients'],
            'vip_count': client_stats['vip_count'],
            'new_this_month': client_stats['new_this_month'],
            'avg_visit': client_stats['avg_visit']
        })
    
    @app.route("/api/today-appointments")
    def api_today_appointments():
        if not session.get('logged_in'):
            return jsonify({"error": "Unauthorized"}), 401
        
        from database import get_today_appointments
        appointments = get_today_appointments()
        return jsonify([dict(row) for row in appointments])
    
    @app.route("/api/outstanding-balances")
    def api_outstanding_balances():
        if not session.get('logged_in'):
            return jsonify({"error": "Unauthorized"}), 401
        
        from database import get_outstanding_balances
        balances = get_outstanding_balances()
        return jsonify([dict(row) for row in balances])
    
    # Initialize database
    with app.app_context():
        init_db()
        print("Database initialized successfully")
    
    return app

# For direct running (python app.py)
from flask import request, jsonify

app = create_app()

if __name__ == "__main__":
    app.run(debug=True)