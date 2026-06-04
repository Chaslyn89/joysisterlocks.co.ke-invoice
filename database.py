import os
from datetime import datetime, timedelta
import uuid
from functools import wraps
import time
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2.pool import SimpleConnectionPool

# Database connection pool
db_pool = None

def init_db_pool():
    """Initialize connection pool for PostgreSQL"""
    global db_pool
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        raise ValueError("DATABASE_URL environment variable not set")
    
    db_pool = SimpleConnectionPool(
        minconn=1,
        maxconn=10,
        dsn=database_url
    )
    return db_pool

def get_db():
    """Get database connection from pool"""
    global db_pool
    if db_pool is None:
        init_db_pool()
    return db_pool.getconn()

def return_db(conn):
    """Return connection to pool"""
    global db_pool
    if db_pool:
        db_pool.putconn(conn)

# Simple in-memory cache for dashboard stats
_cache = {}
CACHE_TTL = 60  # seconds

def cache_result(ttl=CACHE_TTL):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            cache_key = f"{func.__name__}:{args}:{kwargs}"
            now = time.time()
            if cache_key in _cache:
                result, timestamp = _cache[cache_key]
                if now - timestamp < ttl:
                    return result
            result = func(*args, **kwargs)
            _cache[cache_key] = (result, now)
            return result
        return wrapper
    return decorator

def get_current_date():
    """Get current date in consistent YYYY-MM-DD format"""
    return datetime.now().strftime('%Y-%m-%d')

def init_db():
    """Initialize database with all tables and indexes"""
    conn = get_db()
    try:
        cursor = conn.cursor()
        
        # Main clients table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS clients (
                id SERIAL PRIMARY KEY,
                client_name TEXT NOT NULL,
                client_phone TEXT UNIQUE NOT NULL,
                client_email TEXT,
                join_date TEXT,
                total_visits INTEGER DEFAULT 0,
                gross_spent INTEGER DEFAULT 0,
                total_paid INTEGER DEFAULT 0,
                last_visit TEXT,
                category TEXT DEFAULT 'New',
                retention_status TEXT DEFAULT 'Active',
                notes TEXT,
                preferred_stylist TEXT DEFAULT 'Joy',
                preferred_contact TEXT DEFAULT 'WhatsApp',
                birthday TEXT,
                referrer TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        ''')
        
        # Services catalog table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS services (
                id SERIAL PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                price INTEGER NOT NULL,
                category TEXT,
                is_active INTEGER DEFAULT 1,
                created_at TEXT
            )
        ''')
        
        # Insert default services (only if table is empty)
        cursor.execute("SELECT COUNT(*) FROM services")
        count = cursor.fetchone()[0]
        if count == 0:
            default_services = [
                ('Sister Locs Retie', 3500, 'Retie'),
                ('Micro Locs Retie', 3500, 'Retie'),
                ('Sister Locs Full Installation', 15000, 'Installation'),
                ('Sister Locs Colour & Styling', 4500, 'Colour'),
                ('Sister Locs Colour + Retie', 5500, 'Combo'),
                ('Wash, Retie, Massage & Styling', 3000, 'Package')
            ]
            for name, price, category in default_services:
                cursor.execute('''
                    INSERT INTO services (name, price, category, is_active, created_at)
                    VALUES (%s, %s, %s, 1, %s)
                    ON CONFLICT (name) DO NOTHING
                ''', (name, price, category, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        
        # Service history table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS service_history (
                id SERIAL PRIMARY KEY,
                client_id INTEGER REFERENCES clients(id) ON DELETE CASCADE,
                invoice_number TEXT,
                service_date TEXT,
                service_name TEXT,
                service_details TEXT,
                amount INTEGER,
                amount_paid INTEGER,
                balance INTEGER,
                payment_method TEXT,
                stylist_name TEXT,
                notes TEXT,
                mpesa_code TEXT
            )
        ''')
        
        # Appointments table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS appointments (
                id SERIAL PRIMARY KEY,
                client_id INTEGER REFERENCES clients(id) ON DELETE CASCADE,
                appointment_date TEXT,
                appointment_time TEXT,
                service_name TEXT,
                status TEXT DEFAULT 'scheduled',
                reminder_sent INTEGER DEFAULT 0,
                created_at TEXT
            )
        ''')
        
        # Expenses table with deleted_at for soft delete
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS expenses (
                id SERIAL PRIMARY KEY,
                category TEXT,
                amount INTEGER,
                description TEXT,
                expense_date TEXT,
                created_at TEXT,
                deleted_at TEXT
            )
        ''')
        
        # Client health/allergies table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS client_health (
                id SERIAL PRIMARY KEY,
                client_id INTEGER REFERENCES clients(id) ON DELETE CASCADE,
                allergy_type TEXT,
                allergy_description TEXT,
                severity TEXT DEFAULT 'Medium',
                recorded_date TEXT
            )
        ''')
        
        # Communications table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS communications (
                id SERIAL PRIMARY KEY,
                client_id INTEGER REFERENCES clients(id) ON DELETE CASCADE,
                comm_date TEXT,
                comm_type TEXT,
                message TEXT,
                sent_by TEXT
            )
        ''')
        
        # INDEXES for performance
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_phone ON clients(client_phone)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_name ON clients(client_name)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_last_visit ON clients(last_visit)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_service_client ON service_history(client_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_appointment_date ON appointments(appointment_date)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_expense_date ON expenses(expense_date)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_expense_deleted ON expenses(deleted_at)')
        
        conn.commit()
    finally:
        return_db(conn)

def get_or_create_client(client_data):
    """Get existing client by phone or create new one"""
    conn = get_db()
    try:
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM clients WHERE client_phone = %s', (client_data['client_phone'],))
        client = cursor.fetchone()
        
        if client:
            cursor.execute('''
                UPDATE clients 
                SET client_name = %s, client_email = %s, updated_at = %s
                WHERE client_phone = %s
            ''', (client_data['client_name'], client_data.get('client_email', ''), 
                  get_current_date(), client_data['client_phone']))
            client_id = client[0]
        else:
            cursor.execute('''
                INSERT INTO clients (
                    client_name, client_phone, client_email, join_date, 
                    category, retention_status, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            ''', (client_data['client_name'], client_data['client_phone'], 
                  client_data.get('client_email', ''), get_current_date(),
                  'New', 'Active', get_current_date(), get_current_date()))
            client_id = cursor.fetchone()[0]
        
        conn.commit()
        return client_id
    finally:
        return_db(conn)

def generate_invoice_number():
    """Generate unique invoice number using UUID"""
    return f"JSL-{uuid.uuid4().hex[:8].upper()}"

def get_client_visits(client_id):
    """Get total visits count for a client"""
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute('SELECT total_visits FROM clients WHERE id = %s', (client_id,))
        result = cursor.fetchone()
        return result[0] if result else 0
    finally:
        return_db(conn)

def save_service_record(client_id, invoice_data):
    """Save service history after invoice - wrapped in transaction"""
    conn = get_db()
    try:
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO service_history (
                client_id, invoice_number, service_date, service_name, 
                service_details, amount, amount_paid, balance, 
                payment_method, stylist_name, notes, mpesa_code
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ''', (client_id, invoice_data['invoice_number'], invoice_data['date'],
              invoice_data['service_name'], invoice_data.get('service_details', ''),
              invoice_data['total'], invoice_data['amount_paid'], invoice_data['balance'],
              invoice_data['payment_method'], invoice_data.get('stylist_name', 'Joy'),
              invoice_data.get('notes', ''), invoice_data.get('mpesa_code', '')))
        
        cursor.execute('''
            UPDATE clients 
            SET total_visits = total_visits + 1,
                gross_spent = gross_spent + %s,
                total_paid = total_paid + %s,
                last_visit = %s,
                category = CASE 
                    WHEN total_visits + 1 >= 10 THEN 'VIP'
                    WHEN total_visits + 1 >= 5 THEN 'Regular'
                    ELSE category
                END,
                retention_status = 'Active',
                updated_at = %s
            WHERE id = %s
        ''', (invoice_data['total'], invoice_data['amount_paid'], invoice_data['date'], 
              get_current_date(), client_id))
        
        _cache.clear()
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        return_db(conn)

def update_retention_status():
    """Update client retention status based on last visit"""
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE clients 
            SET retention_status = CASE
                WHEN (DATE(%s) - DATE(last_visit)) <= 30 THEN 'Active'
                WHEN (DATE(%s) - DATE(last_visit)) <= 60 THEN 'At Risk'
                WHEN (DATE(%s) - DATE(last_visit)) <= 90 THEN 'Inactive'
                ELSE 'Lost'
            END
            WHERE last_visit IS NOT NULL
        ''', (get_current_date(), get_current_date(), get_current_date()))
        conn.commit()
    finally:
        return_db(conn)

def search_clients(search_term, request_count=1):
    """Search clients by name or phone with rate limiting protection"""
    if len(search_term) > 50:
        return []
    if request_count > 100:
        return []
    
    conn = get_db()
    try:
        cursor = conn.cursor()
        search_pattern = f'%{search_term}%'
        cursor.execute('''
            SELECT id, client_name, client_phone, total_visits, gross_spent, 
                   last_visit, category, retention_status
            FROM clients 
            WHERE client_name ILIKE %s OR client_phone ILIKE %s
            ORDER BY gross_spent DESC, last_visit DESC
            LIMIT 50
        ''', (search_pattern, search_pattern))
        
        columns = ['id', 'client_name', 'client_phone', 'total_visits', 'gross_spent', 
                   'last_visit', 'category', 'retention_status']
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    finally:
        return_db(conn)

def get_recent_clients(limit=10):
    """Get most recent clients"""
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, client_name, client_phone, total_visits, gross_spent, 
                   last_visit, category, retention_status, join_date
            FROM clients 
            ORDER BY created_at DESC
            LIMIT %s
        ''', (limit,))
        
        columns = ['id', 'client_name', 'client_phone', 'total_visits', 'gross_spent', 
                   'last_visit', 'category', 'retention_status', 'join_date']
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    finally:
        return_db(conn)

def get_top_clients(limit=10):
    """Get top spending clients by gross_spent"""
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, client_name, client_phone, total_visits, gross_spent, 
                   last_visit, category, retention_status
            FROM clients 
            ORDER BY gross_spent DESC
            LIMIT %s
        ''', (limit,))
        
        columns = ['id', 'client_name', 'client_phone', 'total_visits', 'gross_spent', 
                   'last_visit', 'category', 'retention_status']
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    finally:
        return_db(conn)

def get_at_risk_clients():
    """Get clients who are At Risk or Inactive or Lost"""
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, client_name, client_phone, last_visit, retention_status
            FROM clients 
            WHERE retention_status IN ('At Risk', 'Inactive', 'Lost')
            ORDER BY last_visit ASC
        ''')
        
        columns = ['id', 'client_name', 'client_phone', 'last_visit', 'retention_status']
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    finally:
        return_db(conn)

def get_client_by_id(client_id):
    """Get complete client profile"""
    conn = get_db()
    try:
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM clients WHERE id = %s', (client_id,))
        client_row = cursor.fetchone()
        if not client_row:
            return None
        
        client_columns = ['id', 'client_name', 'client_phone', 'client_email', 'join_date', 
                          'total_visits', 'gross_spent', 'total_paid', 'last_visit', 
                          'category', 'retention_status', 'notes', 'preferred_stylist', 
                          'preferred_contact', 'birthday', 'referrer', 'created_at', 'updated_at']
        client = dict(zip(client_columns, client_row))
        
        cursor.execute('SELECT * FROM service_history WHERE client_id = %s ORDER BY service_date DESC', (client_id,))
        service_columns = ['id', 'client_id', 'invoice_number', 'service_date', 'service_name', 
                           'service_details', 'amount', 'amount_paid', 'balance', 
                           'payment_method', 'stylist_name', 'notes', 'mpesa_code']
        services = [dict(zip(service_columns, row)) for row in cursor.fetchall()]
        
        cursor.execute('SELECT * FROM client_health WHERE client_id = %s', (client_id,))
        health_columns = ['id', 'client_id', 'allergy_type', 'allergy_description', 'severity', 'recorded_date']
        health = [dict(zip(health_columns, row)) for row in cursor.fetchall()]
        
        cursor.execute('SELECT * FROM communications WHERE client_id = %s ORDER BY comm_date DESC LIMIT 10', (client_id,))
        comm_columns = ['id', 'client_id', 'comm_date', 'comm_type', 'message', 'sent_by']
        communications = [dict(zip(comm_columns, row)) for row in cursor.fetchall()]
        
        cursor.execute('SELECT * FROM appointments WHERE client_id = %s ORDER BY appointment_date DESC LIMIT 5', (client_id,))
        apt_columns = ['id', 'client_id', 'appointment_date', 'appointment_time', 'service_name', 'status', 'reminder_sent', 'created_at']
        appointments = [dict(zip(apt_columns, row)) for row in cursor.fetchall()]
        
        return {
            'client': client,
            'services': services,
            'health': health,
            'communications': communications,
            'appointments': appointments
        }
    finally:
        return_db(conn)

@cache_result(ttl=CACHE_TTL)
def get_client_stats():
    """Get overall business statistics with caching"""
    conn = get_db()
    try:
        cursor = conn.cursor()
        update_retention_status()
        
        cursor.execute('SELECT COUNT(*) FROM clients')
        total_clients = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM clients WHERE category = 'VIP'")
        vip_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM clients WHERE category = 'Regular'")
        regular_count = cursor.fetchone()[0]
        
        current_month = get_current_date()[:7]
        cursor.execute('SELECT COUNT(*) FROM clients WHERE join_date LIKE %s', (f'{current_month}%',))
        new_this_month = cursor.fetchone()[0]
        
        cursor.execute('SELECT COALESCE(SUM(amount), 0) FROM service_history')
        gross_revenue = cursor.fetchone()[0]
        
        cursor.execute('SELECT COALESCE(SUM(amount_paid), 0) FROM service_history')
        cash_collected = cursor.fetchone()[0]
        
        cursor.execute('SELECT COALESCE(SUM(balance), 0) FROM service_history')
        outstanding = cursor.fetchone()[0]
        
        cursor.execute('SELECT COALESCE(AVG(amount), 0) FROM service_history')
        avg_visit = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM clients WHERE retention_status = 'At Risk'")
        at_risk = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM clients WHERE retention_status = 'Lost'")
        lost = cursor.fetchone()[0]
        
        return {
            'total_clients': total_clients,
            'vip_count': vip_count,
            'regular_count': regular_count,
            'new_this_month': new_this_month,
            'gross_revenue': gross_revenue,
            'cash_collected': cash_collected,
            'outstanding': outstanding,
            'avg_visit': avg_visit,
            'at_risk': at_risk,
            'lost': lost
        }
    finally:
        return_db(conn)

@cache_result(ttl=CACHE_TTL)
def get_dashboard_stats():
    """Get statistics for dashboard with revenue data for chart"""
    conn = get_db()
    try:
        cursor = conn.cursor()
        today = get_current_date()
        
        cursor.execute('SELECT COALESCE(SUM(amount_paid), 0) FROM service_history WHERE service_date = %s', (today,))
        today_revenue = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM appointments WHERE appointment_date = %s AND status != %s', (today, 'cancelled'))
        today_appointments = cursor.fetchone()[0]
        
        cursor.execute('SELECT COALESCE(SUM(balance), 0) FROM service_history')
        total_outstanding = cursor.fetchone()[0]
        
        cursor.execute('SELECT COALESCE(SUM(amount), 0) FROM service_history')
        gross_revenue = cursor.fetchone()[0]
        
        cursor.execute('SELECT COALESCE(SUM(amount), 0) FROM expenses WHERE deleted_at IS NULL')
        total_expenses = cursor.fetchone()[0]
        
        thirty_days_ago = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
        cursor.execute('''
            SELECT service_date, COALESCE(SUM(amount_paid), 0) as daily_revenue
            FROM service_history
            WHERE service_date >= %s
            GROUP BY service_date
            ORDER BY service_date
        ''', (thirty_days_ago,))
        revenue_data_rows = cursor.fetchall()
        
        revenue_data = [row[1] for row in revenue_data_rows]
        revenue_dates = [row[0] for row in revenue_data_rows]
        
        return {
            'today_revenue': today_revenue,
            'today_appointments': today_appointments,
            'total_outstanding': total_outstanding,
            'gross_revenue': gross_revenue,
            'total_expenses': total_expenses,
            'profit': gross_revenue - total_expenses,
            'revenue_data': revenue_data,
            'revenue_dates': revenue_dates
        }
    finally:
        return_db(conn)

def create_appointment(client_id, appointment_date, appointment_time, service_name):
    """Create a new appointment"""
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO appointments (client_id, appointment_date, appointment_time, service_name, created_at)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
        ''', (client_id, appointment_date, appointment_time, service_name, get_current_date()))
        appointment_id = cursor.fetchone()[0]
        conn.commit()
        _cache.clear()
        return appointment_id
    finally:
        return_db(conn)

def get_today_appointments():
    """Get today's appointments"""
    conn = get_db()
    try:
        cursor = conn.cursor()
        today = get_current_date()
        cursor.execute('''
            SELECT a.*, c.client_name, c.client_phone 
            FROM appointments a
            JOIN clients c ON a.client_id = c.id
            WHERE a.appointment_date = %s AND a.status != %s
            ORDER BY a.appointment_time
        ''', (today, 'cancelled'))
        
        columns = ['id', 'client_id', 'appointment_date', 'appointment_time', 'service_name', 
                   'status', 'reminder_sent', 'created_at', 'client_name', 'client_phone']
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    finally:
        return_db(conn)

def get_outstanding_balances():
    """Get clients with outstanding balances"""
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT c.id, c.client_name, c.client_phone, SUM(s.balance) as total_balance
            FROM service_history s
            JOIN clients c ON s.client_id = c.id
            WHERE s.balance > 0
            GROUP BY c.id, c.client_name, c.client_phone
            ORDER BY total_balance DESC
            LIMIT 10
        ''')
        
        columns = ['id', 'client_name', 'client_phone', 'total_balance']
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    finally:
        return_db(conn)

def add_expense(category, amount, description, expense_date):
    """Add an expense record with soft delete support"""
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO expenses (category, amount, description, expense_date, created_at, deleted_at)
            VALUES (%s, %s, %s, %s, %s, NULL)
        ''', (category, amount, description, expense_date, get_current_date()))
        conn.commit()
        _cache.clear()
    finally:
        return_db(conn)

def soft_delete_expense(expense_id):
    """Soft delete an expense by setting deleted_at timestamp"""
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute('UPDATE expenses SET deleted_at = %s WHERE id = %s', (get_current_date(), expense_id))
        conn.commit()
        _cache.clear()
    finally:
        return_db(conn)

def get_expenses(limit=50):
    """Get expense records (non-deleted only)"""
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM expenses 
            WHERE deleted_at IS NULL
            ORDER BY expense_date DESC 
            LIMIT %s
        ''', (limit,))
        
        columns = ['id', 'category', 'amount', 'description', 'expense_date', 'created_at', 'deleted_at']
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    finally:
        return_db(conn)

def get_expenses_by_category():
    """Get expenses grouped by category (non-deleted only)"""
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
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    finally:
        return_db(conn)

def add_client_note(client_id, note):
    """Add a note to client profile"""
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute('SELECT notes FROM clients WHERE id = %s', (client_id,))
        current = cursor.fetchone()
        current_notes = current[0] if current and current[0] else ''
        
        timestamp = get_current_date()
        new_note = f"{current_notes}\n\n[{timestamp}] {note}" if current_notes else f"[{timestamp}] {note}"
        
        cursor.execute('UPDATE clients SET notes = %s, updated_at = %s WHERE id = %s', 
                      (new_note.strip(), get_current_date(), client_id))
        conn.commit()
        _cache.clear()
    finally:
        return_db(conn)

def add_allergy(client_id, allergy_type, description, severity='Medium'):
    """Add allergy/sensitivity record"""
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO client_health (client_id, allergy_type, allergy_description, severity, recorded_date)
            VALUES (%s, %s, %s, %s, %s)
        ''', (client_id, allergy_type, description, severity, get_current_date()))
        conn.commit()
    finally:
        return_db(conn)

def log_communication(client_id, comm_type, message, sent_by='System'):
    """Log communication with client"""
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO communications (client_id, comm_date, comm_type, message, sent_by)
            VALUES (%s, %s, %s, %s, %s)
        ''', (client_id, get_current_date(), comm_type, message, sent_by))
        conn.commit()
    finally:
        return_db(conn)
