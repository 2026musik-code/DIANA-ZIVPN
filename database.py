import sqlite3
import datetime
from config import Config
from werkzeug.security import generate_password_hash

def get_db_connection():
    conn = sqlite3.connect(Config.DATABASE_URI)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    c = conn.cursor()

    # Admin Table
    c.execute('''
        CREATE TABLE IF NOT EXISTS admins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL
        )
    ''')

    # Settings Table
    c.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')

    # Packages Table
    c.execute('''
        CREATE TABLE IF NOT EXISTS packages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            price INTEGER NOT NULL,
            duration INTEGER NOT NULL
        )
    ''')

    # Users Table (VPN Accounts)
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            expiry_date TIMESTAMP,
            status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Transactions Table (Added 'pin')
    c.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reference_id TEXT NOT NULL UNIQUE,
            pin TEXT NOT NULL,
            username TEXT NOT NULL,
            password TEXT NOT NULL,
            package_id INTEGER,
            amount INTEGER NOT NULL,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (package_id) REFERENCES packages (id)
        )
    ''')

    conn.commit()
    conn.close()

def seed_admin(username, password):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT * FROM admins WHERE username = ?', (username,))
    if c.fetchone() is None:
        c.execute('INSERT INTO admins (username, password_hash) VALUES (?, ?)',
                  (username, generate_password_hash(password)))
        conn.commit()
        print(f"Admin user '{username}' created.")
    else:
        print(f"Admin user '{username}' already exists.")
    conn.close()
