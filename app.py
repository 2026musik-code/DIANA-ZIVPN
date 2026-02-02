from flask import Flask, render_template, request, redirect, url_for, flash, session, g, jsonify
from config import Config
from database import get_db_connection
from werkzeug.security import check_password_hash, generate_password_hash
import functools
import uuid
import datetime
import logging
import random
import string
import subprocess
from utils.paymenku import PaymenkuClient
from utils.system import create_user, check_user_exists, kill_user_session, delete_user

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

# --- Public Routes (One Page) ---

@app.route('/')
def index():
    conn = get_db_connection()
    packages = conn.execute('SELECT * FROM packages').fetchall()
    conn.close()
    return render_template('public/index.html', packages=packages)

@app.route('/api/create_order', methods=['POST'])
def create_order():
    """
    AJAX Endpoint to create order and return QR + PIN
    """
    data = request.json
    package_id = data.get('package_id')
    username = data.get('username')
    password = data.get('password')

    conn = get_db_connection()
    package = conn.execute('SELECT * FROM packages WHERE id = ?', (package_id,)).fetchone()

    if not package:
        conn.close()
        return jsonify({'success': False, 'message': 'Package not found'}), 404

    # Check Username
    existing_user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
    if existing_user or check_user_exists(username):
        conn.close()
        return jsonify({'success': False, 'message': 'Username already exists'}), 400

    # Payment Config
    merchant_id_row = conn.execute("SELECT value FROM settings WHERE key='merchant_id'").fetchone()
    api_key_row = conn.execute("SELECT value FROM settings WHERE key='api_key'").fetchone()

    if not merchant_id_row or not api_key_row:
        conn.close()
        return jsonify({'success': False, 'message': 'Payment gateway not configured'}), 500

    merchant_id = merchant_id_row['value']
    api_key = api_key_row['value']

    # Generate Data
    ref_id = f"TRX-{uuid.uuid4().hex[:8].upper()}"
    pin = ''.join(random.choices(string.digits, k=6)) # 6 Digit PIN
    amount = package['price']

    # Save Pending Transaction
    conn.execute('''
        INSERT INTO transactions (reference_id, pin, username, password, package_id, amount, status)
        VALUES (?, ?, ?, ?, ?, ?, 'pending')
    ''', (ref_id, pin, username, password, package_id, amount))
    conn.commit()
    conn.close()

    # Call Paymenku
    client = PaymenkuClient(merchant_id, api_key, Config.PAYMENKU_BASE_URL)
    resp = client.create_transaction(ref_id, amount)

    if resp.get('success', True) and 'data' in resp:
        return jsonify({
            'success': True,
            'pin': pin,
            'amount': amount,
            'reference_id': ref_id,
            'qr_content': resp['data'].get('qr_content'),
            'checkout_url': resp['data'].get('checkout_url')
        })
    else:
        return jsonify({'success': False, 'message': resp.get('message', 'Payment Error')}), 500

@app.route('/api/check_order', methods=['POST'])
def check_order():
    """
    Check order status by PIN
    """
    pin = request.json.get('pin')
    conn = get_db_connection()
    # Find all transactions for this PIN (usually one, but pin could technically collide or be reused? No, randomly generated. Assume 1:1 for now or list all)
    # Actually, user might buy multiple times with different PINs.
    # But if they want to see "List User yg sudah dibeli" using A PIN?
    # The requirement: "Diberikan PIN untuk melihat akun".
    # So PIN is specific to that purchase.

    trx = conn.execute('''
        SELECT t.*, p.name as package_name, p.duration
        FROM transactions t
        JOIN packages p ON t.package_id = p.id
        WHERE t.pin = ?
    ''', (pin,)).fetchone()

    conn.close()

    if trx:
        data = {
            'found': True,
            'reference_id': trx['reference_id'],
            'status': trx['status'],
            'amount': trx['amount'],
            'username': trx['username'],
            'package': trx['package_name']
        }
        if trx['status'] == 'paid':
            data['password'] = trx['password']
            # Calculate expiry based on created_at + duration (Approximation, real expiry is in users table)
            # Better: fetch from users table if active
            conn = get_db_connection()
            user = conn.execute("SELECT * FROM users WHERE username = ?", (trx['username'],)).fetchone()
            conn.close()
            if user:
                data['expiry_date'] = user['expiry_date']
                data['user_status'] = user['status']

        return jsonify(data)
    else:
        return jsonify({'found': False, 'message': 'PIN not found'})

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

    if not client.verify_callback_signature(data):
        logger.warning("Invalid signature in webhook")
        if merchant_id_row['value'] != 'mock':
             conn.close()
             return {"success": False, "message": "Invalid signature"}, 400

    ref_id = data.get('ref_id')
    status = data.get('status')

    if status.lower() in ['paid', 'success']:
        trx = conn.execute('SELECT * FROM transactions WHERE reference_id = ?', (ref_id,)).fetchone()

        if trx and trx['status'] == 'pending':
            conn.execute("UPDATE transactions SET status = 'paid' WHERE id = ?", (trx['id'],))
            pkg = conn.execute('SELECT * FROM packages WHERE id = ?', (trx['package_id'],)).fetchone()
            duration = pkg['duration']
            expiry_date = datetime.datetime.now() + datetime.timedelta(days=duration)

            success, msg = create_user(trx['username'], trx['password'], expiry_date)

            if success:
                conn.execute('''
                    INSERT INTO users (username, password, expiry_date, status)
                    VALUES (?, ?, ?, 'active')
                ''', (trx['username'], trx['password'], expiry_date))
                conn.commit()
                logger.info(f"User {trx['username']} created successfully.")
            else:
                logger.error(f"Failed to create system user: {msg}")

    conn.close()
    return {"success": True}

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
    total_sales_res = conn.execute("SELECT SUM(amount) as total FROM transactions WHERE status='paid'").fetchone()
    total_sales = total_sales_res['total'] if total_sales_res['total'] else 0
    active_users_count = conn.execute("SELECT COUNT(*) as count FROM users WHERE status='active'").fetchone()['count']
    transaction_count = conn.execute("SELECT COUNT(*) as count FROM transactions").fetchone()['count']
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

@app.route('/admin/change_password', methods=['GET', 'POST'])
@login_required
def admin_change_password():
    if request.method == 'POST':
        new_password = request.form['new_password']
        if new_password:
            hashed = generate_password_hash(new_password)
            conn = get_db_connection()
            conn.execute('UPDATE admins SET password_hash = ? WHERE username = ?', (hashed, session['admin_username']))
            conn.commit()
            conn.close()
            flash('Password updated successfully.', 'success')
        return redirect(url_for('admin_settings'))
    return redirect(url_for('admin_settings'))

@app.route('/admin/update_system', methods=['POST'])
@login_required
def admin_update_system():
    # Only works if running with sufficient permissions and inside git repo
    try:
        # git pull
        subprocess.run(['git', 'pull'], check=True)
        # restart service (assumes systemd service name is known, e.g. diana-zivpn)
        # Requires sudoers or root. Since we run as root in this context:
        subprocess.run(['systemctl', 'restart', 'diana-zivpn'], check=True)
        flash('System updated and restarted.', 'success')
    except Exception as e:
        flash(f'Update failed: {e}', 'danger')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/packages')
@login_required
def admin_packages():
    conn = get_db_connection()
    packages = conn.execute('SELECT * FROM packages').fetchall()
    conn.close()
    return render_template('admin/packages.html', packages=packages)

@app.route('/admin/packages/add', methods=['GET', 'POST'])
@login_required
def admin_add_package():
    if request.method == 'POST':
        name = request.form['name']
        duration = request.form['duration']
        price = request.form['price']
        conn = get_db_connection()
        conn.execute('INSERT INTO packages (name, duration, price) VALUES (?, ?, ?)', (name, duration, price))
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
        conn.execute('UPDATE packages SET name = ?, duration = ?, price = ? WHERE id = ?', (name, duration, price, pkg_id))
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
        if conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone():
            flash('Username already exists.', 'danger')
            conn.close()
            return redirect(url_for('admin_add_user'))

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

@app.route('/admin/users/edit/<int:user_id>', methods=['GET', 'POST'])
@login_required
def admin_edit_user(user_id):
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()

    if request.method == 'POST':
        # Typically we just edit password or duration (expiry)
        # Editing username is complex (needs system user rename), keeping it simple for now (Password & Expiry)
        new_password = request.form.get('password')
        extend_days = request.form.get('extend_days', type=int)

        # Update System
        current_expiry = datetime.datetime.strptime(user['expiry_date'], '%Y-%m-%d %H:%M:%S.%f') if isinstance(user['expiry_date'], str) else user['expiry_date']

        if extend_days:
            current_expiry += datetime.timedelta(days=extend_days)

        # Re-create user (update password/expiry in zivpn config)
        # Zivpn config just holds username:password. It doesn't enforce expiry natively (cron job does).
        # So we update password in config.
        if new_password:
             create_user(user['username'], new_password, current_expiry)
             conn.execute('UPDATE users SET password = ? WHERE id = ?', (new_password, user_id))

        if extend_days:
             conn.execute('UPDATE users SET expiry_date = ? WHERE id = ?', (current_expiry, user_id))
             # Also ensure expiry in system user logic if applicable (in Zivpn mode, it's just DB + Cron)

        conn.commit()
        conn.close()
        flash('User updated successfully.', 'success')
        return redirect(url_for('admin_users'))

    conn.close()
    return render_template('admin/edit_user.html', user=user)

@app.route('/admin/users/delete/<string:username>')
@login_required
def admin_delete_user(username):
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()

    if user:
         delete_user(username) # Remove from Zivpn
         conn.execute('DELETE FROM users WHERE username = ?', (username,))
         conn.commit()
         flash('User deleted.', 'success')
    else:
        flash('User not found.', 'danger')
    conn.close()
    return redirect(url_for('admin_users'))

@app.route('/admin/users/kill/<string:username>')
@login_required
def admin_kill_user(username):
    success, msg = kill_user_session(username)
    if success:
        flash(f'Session for {username} killed successfully.', 'success')
    else:
        flash(f'Failed to kill session: {msg}', 'danger')
    return redirect(url_for('admin_users'))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
