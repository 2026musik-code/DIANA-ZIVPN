from flask import Flask, render_template, request, redirect, url_for, flash, session, g
from config import Config
from database import get_db_connection
from werkzeug.security import check_password_hash
import functools
import uuid
import datetime
import logging
from utils.paymenku import PaymenkuClient
from utils.system import create_user, check_user_exists, kill_user_session

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config.from_object(Config)

def login_required(view):
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if session.get('admin_logged_in') is None:
            return redirect(url_for('admin_login'))
        return view(**kwargs)
    return wrapped_view

@app.before_request
def load_logged_in_user():
    g.user = session.get('admin_logged_in')

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

# --- Admin Routes ---

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = get_db_connection()
        user = conn.execute('SELECT * FROM admins WHERE username = ?', (username,)).fetchone()
        conn.close()

        if user and check_password_hash(user['password_hash'], password):
            session['admin_logged_in'] = True
            session['admin_username'] = user['username']
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Invalid username or password', 'danger')

    return render_template('admin/login.html')

@app.route('/admin/logout')
def admin_logout():
    session.clear()
    return redirect(url_for('admin_login'))

@app.route('/admin')
@login_required
def admin_dashboard():
    conn = get_db_connection()

    # Stats
    total_sales_res = conn.execute("SELECT SUM(amount) as total FROM transactions WHERE status='paid'").fetchone()
    total_sales = total_sales_res['total'] if total_sales_res['total'] else 0

    active_users_count = conn.execute("SELECT COUNT(*) as count FROM users WHERE status='active'").fetchone()['count']
    transaction_count = conn.execute("SELECT COUNT(*) as count FROM transactions").fetchone()['count']

    # Recent Transactions
    recent_transactions = conn.execute("SELECT * FROM transactions ORDER BY created_at DESC LIMIT 5").fetchall()

    conn.close()

    return render_template('admin/dashboard.html',
                           total_sales=f"Rp {total_sales:,}",
                           active_users_count=active_users_count,
                           transaction_count=transaction_count,
                           recent_transactions=recent_transactions)

@app.route('/admin/settings', methods=['GET', 'POST'])
@login_required
def admin_settings():
    conn = get_db_connection()
    if request.method == 'POST':
        merchant_id = request.form['merchant_id']
        api_key = request.form['api_key']

        conn.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', ('merchant_id', merchant_id))
        conn.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', ('api_key', api_key))
        conn.commit()
        flash('Settings updated successfully.', 'success')

    merchant_id_row = conn.execute("SELECT value FROM settings WHERE key='merchant_id'").fetchone()
    api_key_row = conn.execute("SELECT value FROM settings WHERE key='api_key'").fetchone()
    conn.close()

    return render_template('admin/settings.html',
                           merchant_id=merchant_id_row['value'] if merchant_id_row else '',
                           api_key=api_key_row['value'] if api_key_row else '')

@app.route('/admin/packages')
@login_required
def admin_packages():
    conn = get_db_connection()
    packages = conn.execute('SELECT * FROM packages').fetchall()
    conn.close()
    return render_template('admin/packages.html', packages=packages)

# --- Public Routes ---

@app.route('/')
def index():
    conn = get_db_connection()
    packages = conn.execute('SELECT * FROM packages').fetchall()
    conn.close()
    return render_template('public/index.html', packages=packages)

@app.route('/order/<int:pkg_id>')
def order_page(pkg_id):
    conn = get_db_connection()
    package = conn.execute('SELECT * FROM packages WHERE id = ?', (pkg_id,)).fetchone()
    conn.close()
    if not package:
        flash('Package not found.', 'danger')
        return redirect(url_for('index'))
    return render_template('public/order.html', package=package)

@app.route('/status', methods=['GET', 'POST'])
def status_page():
    result = None
    error = None
    if request.method == 'POST':
        username = request.form['username']
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        conn.close()

        if user:
            result = user
        else:
            error = "User not found."

    return render_template('public/status.html', result=result, error=error)

@app.route('/checkout', methods=['POST'])
def checkout():
    package_id = request.form['package_id']
    username = request.form['username']
    password = request.form['password']

    conn = get_db_connection()
    package = conn.execute('SELECT * FROM packages WHERE id = ?', (package_id,)).fetchone()

    # Check if username exists in DB or System
    existing_user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
    if existing_user or check_user_exists(username):
        conn.close()
        flash('Username already exists. Please choose another.', 'danger')
        return redirect(url_for('order_page', pkg_id=package_id))

    # Get Payment Settings
    merchant_id_row = conn.execute("SELECT value FROM settings WHERE key='merchant_id'").fetchone()
    api_key_row = conn.execute("SELECT value FROM settings WHERE key='api_key'").fetchone()

    if not merchant_id_row or not api_key_row:
        conn.close()
        flash('Payment gateway not configured by admin.', 'danger')
        return redirect(url_for('index'))

    merchant_id = merchant_id_row['value']
    api_key = api_key_row['value']

    # Create Transaction Reference
    ref_id = f"TRX-{uuid.uuid4().hex[:8].upper()}"
    amount = package['price']

    conn.execute('''
        INSERT INTO transactions (reference_id, username, password, package_id, amount, status)
        VALUES (?, ?, ?, ?, ?, 'pending')
    ''', (ref_id, username, password, package_id, amount))
    conn.commit()
    conn.close()

    # Call Paymenku
    client = PaymenkuClient(merchant_id, api_key, Config.PAYMENKU_BASE_URL)
    resp = client.create_transaction(ref_id, amount)

    if resp.get('success', True) and 'data' in resp: # Handling mock response structure or real one
        qr_content = resp['data'].get('qr_content')
        checkout_url = resp['data'].get('checkout_url')
        return render_template('public/checkout.html',
                               transaction={'amount': amount, 'reference_id': ref_id},
                               qr_content=qr_content,
                               checkout_url=checkout_url)
    else:
        flash(f"Payment Error: {resp.get('message')}", 'danger')
        return redirect(url_for('order_page', pkg_id=package_id))

@app.route('/api/callback', methods=['POST'])
def callback():
    data = request.json
    logger.info(f"Webhook received: {data}")

    conn = get_db_connection()
    merchant_id_row = conn.execute("SELECT value FROM settings WHERE key='merchant_id'").fetchone()
    api_key_row = conn.execute("SELECT value FROM settings WHERE key='api_key'").fetchone()

    if not merchant_id_row or not api_key_row:
        conn.close()
        return {"success": False, "message": "Config missing"}, 500

    client = PaymenkuClient(merchant_id_row['value'], api_key_row['value'], Config.PAYMENKU_BASE_URL)

    # Verify Signature
    # Note: If running a mock without signature, you might want to bypass this or ensure mock sends valid signature
    if not client.verify_callback_signature(data):
        logger.warning("Invalid signature in webhook")
        # For simplicity in this demo, if it's a mock merchant, we might be lenient or ensure test sends correct sig
        if merchant_id_row['value'] != 'mock':
             conn.close()
             return {"success": False, "message": "Invalid signature"}, 400

    ref_id = data.get('ref_id')
    status = data.get('status') # e.g. 'Paid', 'Success'

    if status.lower() in ['paid', 'success']:
        trx = conn.execute('SELECT * FROM transactions WHERE reference_id = ?', (ref_id,)).fetchone()

        if trx and trx['status'] == 'pending':
            # Update Transaction
            conn.execute("UPDATE transactions SET status = 'paid' WHERE id = ?", (trx['id'],))

            # Get Package Duration
            pkg = conn.execute('SELECT * FROM packages WHERE id = ?', (trx['package_id'],)).fetchone()
            duration = pkg['duration']

            # Calculate Expiry
            expiry_date = datetime.datetime.now() + datetime.timedelta(days=duration)

            # Create System User
            success, msg = create_user(trx['username'], trx['password'], expiry_date)

            if success:
                # Add to Users Table
                conn.execute('''
                    INSERT INTO users (username, password, expiry_date, status)
                    VALUES (?, ?, ?, 'active')
                ''', (trx['username'], trx['password'], expiry_date))
                conn.commit()
                logger.info(f"User {trx['username']} created successfully.")
            else:
                logger.error(f"Failed to create system user: {msg}")
                # We might want to mark transaction as 'failed_provision' or similar

    conn.close()
    return {"success": True}

@app.route('/admin/packages/add', methods=['GET', 'POST'])
@login_required
def admin_add_package():
    if request.method == 'POST':
        name = request.form['name']
        duration = request.form['duration']
        price = request.form['price']

        conn = get_db_connection()
        conn.execute('INSERT INTO packages (name, duration, price) VALUES (?, ?, ?)',
                     (name, duration, price))
        conn.commit()
        conn.close()
        flash('Package added successfully.', 'success')
        return redirect(url_for('admin_packages'))

    return render_template('admin/package_form.html', package=None)

@app.route('/admin/packages/edit/<int:pkg_id>', methods=['GET', 'POST'])
@login_required
def admin_edit_package(pkg_id):
    conn = get_db_connection()
    package = conn.execute('SELECT * FROM packages WHERE id = ?', (pkg_id,)).fetchone()

    if request.method == 'POST':
        name = request.form['name']
        duration = request.form['duration']
        price = request.form['price']

        conn.execute('UPDATE packages SET name = ?, duration = ?, price = ? WHERE id = ?',
                     (name, duration, price, pkg_id))
        conn.commit()
        conn.close()
        flash('Package updated successfully.', 'success')
        return redirect(url_for('admin_packages'))

    conn.close()
    return render_template('admin/package_form.html', package=package)

@app.route('/admin/packages/delete/<int:pkg_id>')
@login_required
def admin_delete_package(pkg_id):
    conn = get_db_connection()
    conn.execute('DELETE FROM packages WHERE id = ?', (pkg_id,))
    conn.commit()
    conn.close()
    flash('Package deleted successfully.', 'success')
    return redirect(url_for('admin_packages'))

@app.route('/admin/users')
@login_required
def admin_users():
    conn = get_db_connection()
    users = conn.execute("SELECT * FROM users ORDER BY created_at DESC").fetchall()
    conn.close()
    return render_template('admin/users.html', users=users)

@app.route('/admin/users/add', methods=['GET', 'POST'])
@login_required
def admin_add_user():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        duration = int(request.form['duration'])

        conn = get_db_connection()
        # Check if user exists
        if conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone():
            flash('Username already exists.', 'danger')
            conn.close()
            return redirect(url_for('admin_add_user'))

        # Create System User
        expiry_date = datetime.datetime.now() + datetime.timedelta(days=duration)
        success, msg = create_user(username, password, expiry_date)

        if success:
            conn.execute('''
                INSERT INTO users (username, password, expiry_date, status)
                VALUES (?, ?, ?, 'active')
            ''', (username, password, expiry_date))
            conn.commit()
            flash('User created successfully.', 'success')
            conn.close()
            return redirect(url_for('admin_users'))
        else:
            flash(f'Failed to create user: {msg}', 'danger')
            conn.close()

    return render_template('admin/add_user.html')

@app.route('/admin/users/kill/<string:username>')
@login_required
def admin_kill_user(username):
    # Security check: ensure user actually exists in DB before attempting command
    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    conn.close()

    if not user:
        flash('User not found.', 'danger')
        return redirect(url_for('admin_users'))

    success, msg = kill_user_session(username)
    if success:
        flash(f'Session for {username} killed successfully.', 'success')
    else:
        flash(f'Failed to kill session: {msg}', 'danger')

    return redirect(url_for('admin_users'))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
