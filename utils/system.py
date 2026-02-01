import logging
from utils.zivpn_config import ZivpnConfig

# Set this to False in production
MOCK_MODE = True

logger = logging.getLogger(__name__)

def create_user(username, password, expiry_date):
    """
    Creates a VPN user by adding to Zivpn config.
    """
    try:
        zivpn = ZivpnConfig()
        # Add user to config (username:password)
        if zivpn.add_user(username, password):
            # Restart service
            success, msg = zivpn.reload_service()
            if success:
                logger.info(f"User {username} created and Zivpn restarted.")
                return True, "User created successfully"
            else:
                logger.error(f"User added to config but service restart failed: {msg}")
                return False, f"Service restart failed: {msg}"
        else:
            return False, "Failed to write config"
    except Exception as e:
        logger.error(f"Error creating user: {e}")
        return False, str(e)

def delete_user(username):
    """
    Deletes a VPN user from Zivpn config.
    """
    try:
        zivpn = ZivpnConfig()
        if zivpn.remove_user(username):
            success, msg = zivpn.reload_service()
            return success, msg
        return False, "Failed to save config"
    except Exception as e:
        return False, str(e)

def kill_user_session(username):
    """
    Kills user session.
    For Zivpn, we strictly speaking can't kill a single session easily without API.
    We will restart the service which disconnects everyone.
    """
    # In a real Zivpn setup, maybe removing the user and restarting is the way to kick them.
    # Since we don't have a separate "disconnect" command, we reuse reload.
    zivpn = ZivpnConfig()
    return zivpn.reload_service()

def check_user_exists(username):
    """
    Checks if a user exists in the Zivpn config.
    """
    zivpn = ZivpnConfig()
    # Check if any token starts with "username:"
    if "auth" in zivpn.data and "config" in zivpn.data["auth"]:
        for token in zivpn.data["auth"]["config"]:
            if token.startswith(f"{username}:") or token == username:
                return True
    return False
