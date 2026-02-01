import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-this'
    DATABASE_URI = 'vpn_panel.db'
    # Payment settings (defaults)
    PAYMENKU_BASE_URL = "https://paymenku.com/api"
