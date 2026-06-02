# utils/qrcode.py
"""QR code generation utilities"""

import qrcode
from io import BytesIO
import base64

def generate_qr_code(url, box_size=2, border=2, fill_color="#2d1b4e", back_color="white"):
    """
    Generate QR code as base64 image for embedding in HTML/PDF
    
    Args:
        url: The URL to encode in the QR code
        box_size: Size of each QR box in pixels
        border: Border size in boxes
        fill_color: Color of QR code (default: dark purple)
        back_color: Background color
    
    Returns:
        Base64 encoded image string or None if error
    """
    try:
        qr = qrcode.QRCode(
            version=1,
            box_size=box_size,
            border=border
        )
        qr.add_data(url)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color=fill_color, back_color=back_color)
        
        buffered = BytesIO()
        img.save(buffered, format="PNG")
        img_str = base64.b64encode(buffered.getvalue()).decode()
        
        return f"data:image/png;base64,{img_str}"
    except Exception as e:
        print(f"QR code generation error: {e}")
        return None

def generate_whatsapp_qr(whatsapp_number):
    """Generate WhatsApp QR code for business"""
    whatsapp_url = f"https://wa.me/{whatsapp_number}"
    return generate_qr_code(whatsapp_url)