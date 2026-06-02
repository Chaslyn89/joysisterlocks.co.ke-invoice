# utils/formatters.py
"""Formatting utilities: money, phone numbers, VAT calculations"""

import re

def format_money(amount):
    """Format money safely"""
    return f"KES {amount:,.0f}" if amount else "KES 0"

def calculate_vat_inclusive(total_inclusive, vat_rate=0.16):
    """Calculate subtotal and VAT from VAT-inclusive total"""
    subtotal = total_inclusive / (1 + vat_rate)
    vat_amount = total_inclusive - subtotal
    return round(subtotal, 2), round(vat_amount, 2)

def validate_kenyan_phone(phone):
    """Validate Kenyan phone number format"""
    phone_pattern = r'^(07|01|\+254|254)[0-9]{8,9}$'
    return bool(re.match(phone_pattern, phone))

def format_phone(phone):
    """Format phone number to international format with +"""
    phone = re.sub(r'\D', '', phone)
    if phone.startswith('0'):
        phone = '254' + phone[1:]
    elif phone.startswith('+'):
        phone = phone[1:]
    return '+' + phone

def format_phone_display(phone):
    """Format phone number for display (obfuscated)"""
    if not phone:
        return ''
    clean = re.sub(r'\D', '', phone)
    if len(clean) >= 10:
        return clean[:4] + '****' + clean[-4:]
    return phone

def validate_email(email):
    """Basic email validation"""
    if not email:
        return True
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(email_pattern, email))