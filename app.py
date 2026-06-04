# app.py
"""Main application factory for Joy Sisterlocks Invoice System"""

from flask import Flask, render_template, session, redirect, url_for, request, jsonify
from datetime import datetime
import os

from config import Config
from database import init_db, get_db, return_db, add_expense, soft_delete_expense
from blueprints import invoices_bp, clients_bp, expenses_bp
from auth import verify_password, get_user_by_username, update_user_password

# Import for auth routes
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
    
    # ============ AUTH ROUTES ============
    
    @app.route('/login', methods=['GET', 'POST'])
    def login():
        client_ip = request.remote_addr
        
        if request.method == 'POST':
            if is_rate_limited(client_ip, Config.MAX_LOGIN_ATTEMPTS, Config.LOGIN_LOCKOUT_TIME):
                return render_template('login.html', error='Too many attempts. Please wait 15 minutes.')
            
            username = request.form.get('username', '').strip()
            password = request.form.get('password', '')
            
            if not username or not password:
                return render_template('login.html', error='Username and password required')
            
            user = get_user_by_username(username)
            
            if user and verify_password(password, user['password_hash']):
                session.permanent = True
                session['logged_in'] = True
                session['username'] = user['username']
                session['login_time'] = datetime.now().isoformat()
                clear_login_attempts(client_ip)
                return redirect(url_for('dashboard'))
            else:
                record_failed_attempt(client_ip, Config.MAX_LOGIN_ATTEMPTS, Config.LOGIN_LOCKOUT_TIME)
                return render_template('login.html', error='Invalid username or password')
        
        return render_template('login.html')
    
    @app.route('/change-password', methods=['GET', 'POST'])
    def change_password():
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        
        if request.method == 'POST':
            current_password = request.form.get('current_password', '')
            new_password = request.form.get('new_password', '')
            confirm_password = request.form.get('confirm_password', '')
            
            if not current_password or not new_password:
                return render_template('change_password.html', error='All fields required')
            
            if new_password != confirm_password:
                return render_template('change_password.html', error='New passwords do not match')
            
            if len(new_password) < 6:
                return render_template('change_password.html', error='Password must be at least 6 characters')
            
            user = get_user_by_username(session['username'])
            
            if not verify_password(current_password, user['password_hash']):
                return render_template('change_password.html', error='Current password is incorrect')
            
            update_user_password(session['username'], new_password)
            
            session.clear()
            return render_template('change_password.html', success='Password changed successfully! Please login again.')
        
        return render_template('change_password.html')
    
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
    
    @app.route("/api/at-risk-clients")
    def api_at_risk_clients():
        if not session.get('logged_in'):
            return jsonify({"error": "Unauthorized"}), 401
        
        from database import get_at_risk_clients
        clients = get_at_risk_clients()
        return jsonify([dict(row) for row in clients])
    
    @app.route("/api/recent-expenses")
    def api_recent_expenses():
        if not session.get('logged_in'):
            return jsonify({"error": "Unauthorized"}), 401
        
        from database import get_expenses
        expenses = get_expenses(limit=10)
        return jsonify([dict(row) for row in expenses])
    
    # ============ DELETE CLIENT ROUTE ============
    
    @app.route("/api/client/<int:client_id>", methods=["DELETE"])
    def delete_client(client_id):
        if not session.get('logged_in'):
            return jsonify({"error": "Unauthorized"}), 401
        
        from database import get_db, return_db, log_communication
        conn = get_db()
        try:
            cursor = conn.cursor()
            
            cursor.execute("SELECT id, client_name FROM clients WHERE id = %s", (client_id,))
            client = cursor.fetchone()
            if not client:
                return jsonify({"error": "Client not found"}), 404
            
            client_name = client[1]
            
            log_communication(client_id, 'Client Deleted', f'Client {client_name} was deleted', 'System')
            
            cursor.execute("DELETE FROM clients WHERE id = %s", (client_id,))
            conn.commit()
            
            from database import _cache
            _cache.clear()
            
            return jsonify({"success": True, "message": f"Client {client_name} deleted successfully"})
        except Exception as e:
            return jsonify({"error": str(e)}), 500
        finally:
            return_db(conn)
    
    # ============ EXPENSE API ROUTES ============
    
    @app.route("/api/expenses")
    def api_get_expenses():
        if not session.get('logged_in'):
            return jsonify({"error": "Unauthorized"}), 401
        
        page = request.args.get('page', 1, type=int)
        limit = min(request.args.get('limit', 50, type=int), 100)
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        offset = (page - 1) * limit
        
        conn = get_db()
        cursor = conn.cursor()
        
        where_clauses = []
        params = []
        
        if start_date:
            where_clauses.append("expense_date >= %s")
            params.append(start_date)
        if end_date:
            where_clauses.append("expense_date <= %s")
            params.append(end_date)
        
        where_sql = ""
        if where_clauses:
            where_sql = " AND " + " AND ".join(where_clauses)
        
        count_query = f"SELECT COUNT(*) FROM expenses WHERE deleted_at IS NULL{where_sql}"
        cursor.execute(count_query, params)
        total = cursor.fetchone()[0]
        
        query = f"SELECT * FROM expenses WHERE deleted_at IS NULL{where_sql} ORDER BY expense_date DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])
        cursor.execute(query, params)
        
        columns = [desc[0] for desc in cursor.description]
        expenses = [dict(zip(columns, row)) for row in cursor.fetchall()]
        
        return_db(conn)
        
        return jsonify({
            'expenses': expenses,
            'total': total,
            'page': page,
            'limit': limit,
            'total_pages': (total + limit - 1) // limit
        })
    
    @app.route("/api/expense", methods=["POST"])
    def add_expense_record():
        if not session.get('logged_in'):
            return jsonify({"error": "Unauthorized"}), 401
        
        data = request.get_json()
        category = data.get('category')
        amount = data.get('amount')
        description = data.get('description', '')
        expense_date = data.get('date')
        
        if not category or not amount or not expense_date:
            return jsonify({"error": "Category, amount, and date are required"}), 400
        
        if amount <= 0:
            return jsonify({"error": "Invalid amount"}), 400
        
        add_expense(category, amount, description, expense_date)
        
        return jsonify({"success": True})
    
    @app.route("/api/expense/<int:expense_id>", methods=["DELETE"])
    def delete_expense(expense_id):
        if not session.get('logged_in'):
            return jsonify({"error": "Unauthorized"}), 401
        
        soft_delete_expense(expense_id)
        return jsonify({"success": True})
    
    @app.route("/api/expense-categories")
    def get_expense_categories():
        if not session.get('logged_in'):
            return jsonify({"error": "Unauthorized"}), 401
        
        conn = get_db()
        try:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT category, SUM(amount) as total
                FROM expenses
                WHERE deleted_at IS NULL
                GROUP BY category
                ORDER BY total DESC
            ''')
            
            columns = ['category', 'total']
            categories = [dict(zip(columns, row)) for row in cursor.fetchall()]
            return jsonify(categories)
        finally:
            return_db(conn)
    
    @app.route("/api/revenue-summary")
    def get_revenue_summary():
        if not session.get('logged_in'):
            return jsonify({"error": "Unauthorized"}), 401
        
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        if not start_date or not end_date:
            return jsonify({"error": "Missing date range"}), 400
        
        conn = get_db()
        try:
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT COALESCE(SUM(amount_paid), 0) as total_revenue 
                FROM service_history 
                WHERE service_date BETWEEN %s AND %s
            ''', (start_date, end_date))
            revenue = cursor.fetchone()[0]
            
            cursor.execute('''
                SELECT COALESCE(SUM(amount), 0) as total_expenses 
                FROM expenses 
                WHERE expense_date BETWEEN %s AND %s AND deleted_at IS NULL
            ''', (start_date, end_date))
            expenses = cursor.fetchone()[0]
            
            return jsonify({
                'revenue': revenue,
                'expenses': expenses
            })
        finally:
            return_db(conn)
    
    # Initialize database
    with app.app_context():
        init_db()
        print("Database initialized successfully")
    
    return app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
