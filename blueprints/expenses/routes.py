# blueprints/expenses/routes.py
"""Expense routes - management, API endpoints"""

from flask import Blueprint, render_template, request, jsonify
from datetime import datetime
from services.expense_service import (
    create_expense, get_expense_list, delete_expense,
    get_category_breakdown
)
from database import get_db, get_dashboard_stats
from utils.security import login_required

expenses_bp = Blueprint('expenses', __name__, url_prefix='/')

@expenses_bp.route("/expenses")
@login_required
def expenses_page():
    """Expense management page"""
    return render_template("expenses.html")

# ============ API ENDPOINTS ============

@expenses_bp.route("/api/expenses")
@login_required
def api_get_expenses():
    """Get expenses with pagination and filters"""
    page = request.args.get('page', 1, type=int)
    limit = min(request.args.get('limit', 50, type=int), 100)
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    offset = (page - 1) * limit
    
    conn = get_db()
    cursor = conn.cursor()
    
    query = "SELECT * FROM expenses WHERE deleted_at IS NULL"
    params = []
    
    if start_date:
        query += " AND expense_date >= ?"
        params.append(start_date)
    if end_date:
        query += " AND expense_date <= ?"
        params.append(end_date)
    
    # Get total count
    count_query = query.replace("SELECT *", "SELECT COUNT(*) as total")
    cursor.execute(count_query, params)
    total = cursor.fetchone()['total']
    
    # Get paginated results
    query += " ORDER BY expense_date DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    cursor.execute(query, params)
    expenses = cursor.fetchall()
    
    conn.close()
    
    return jsonify({
        'expenses': [dict(row) for row in expenses],
        'total': total,
        'page': page,
        'limit': limit,
        'total_pages': (total + limit - 1) // limit if total > 0 else 1
    })

@expenses_bp.route("/api/expense", methods=["POST"])
@login_required
def add_expense_record():
    """Add a new expense"""
    data = request.get_json()
    amount = data.get('amount', 0)
    
    success, error = create_expense(
        data.get('category'),
        amount,
        data.get('description'),
        data.get('date', datetime.now().strftime('%Y-%m-%d'))
    )
    
    if success:
        return jsonify({"success": True})
    return jsonify({"error": error}), 400

@expenses_bp.route("/api/expense/<int:expense_id>", methods=["DELETE"])
@login_required
def api_delete_expense(expense_id):
    """Soft delete an expense"""
    delete_expense(expense_id)
    return jsonify({"success": True})

@expenses_bp.route("/api/expense-categories")
@login_required
def api_expense_categories():
    """Get expenses grouped by category"""
    categories = get_category_breakdown()
    return jsonify([dict(row) for row in categories])

@expenses_bp.route("/api/revenue-summary")
@login_required
def api_revenue_summary():
    """Get revenue vs expenses for a date range"""
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    if not start_date or not end_date:
        return jsonify({"error": "Missing date range"}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT COALESCE(SUM(amount_paid), 0) as total_revenue 
        FROM service_history 
        WHERE service_date BETWEEN ? AND ?
    ''', (start_date, end_date))
    revenue = cursor.fetchone()['total_revenue'] or 0
    
    cursor.execute('''
        SELECT COALESCE(SUM(amount), 0) as total_expenses 
        FROM expenses 
        WHERE expense_date BETWEEN ? AND ? AND deleted_at IS NULL
    ''', (start_date, end_date))
    expenses = cursor.fetchone()['total_expenses'] or 0
    
    conn.close()
    
    return jsonify({
        'revenue': revenue,
        'expenses': expenses
    })

@expenses_bp.route("/api/recent-expenses")
@login_required
def api_recent_expenses():
    """Get recent expenses for dashboard"""
    expenses = get_expense_list(limit=10)
    return jsonify([dict(row) for row in expenses])