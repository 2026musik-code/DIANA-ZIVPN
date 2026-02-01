import sqlite3
import datetime
import logging
from config import Config
from utils.system import delete_user

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def get_db_connection():
    conn = sqlite3.connect(Config.DATABASE_URI)
    conn.row_factory = sqlite3.Row
    return conn

def cleanup_expired_users():
    conn = get_db_connection()
    now = datetime.datetime.now()

    # Find active users who have expired
    users = conn.execute("SELECT * FROM users WHERE status = 'active' AND expiry_date < ?", (now,)).fetchall()

    if not users:
        logger.info("No expired users found.")
        conn.close()
        return

    logger.info(f"Found {len(users)} expired users. Processing cleanup...")

    for user in users:
        username = user['username']
        logger.info(f"Deleting user: {username}")

        # Delete from System
        success, msg = delete_user(username)

        if success:
            # Update DB status
            conn.execute("UPDATE users SET status = 'expired' WHERE id = ?", (user['id'],))
            logger.info(f"User {username} marked as expired.")
        else:
            logger.error(f"Failed to delete system user {username}: {msg}")

    conn.commit()
    conn.close()
    logger.info("Cleanup complete.")

if __name__ == "__main__":
    cleanup_expired_users()
