import subprocess
import os
import logging

# Set this to False in production
MOCK_MODE = True

logger = logging.getLogger(__name__)

def run_command(command, input_text=None):
    """
    Executes a shell command safely without shell=True.
    Args:
        command (list): The command and arguments as a list.
        input_text (str): Optional input to pipe to stdin.
    """
    if MOCK_MODE:
        logger.info(f"[MOCK SYSTEM] Executing: {command} | Input: {input_text}")
        return True, "Mock success"

    try:
        # shell=False is default, which is safer (prevents injection)
        result = subprocess.run(command, input=input_text, text=True, capture_output=True, check=True)
        return True, result.stdout
    except subprocess.CalledProcessError as e:
        logger.error(f"Command failed: {command}. Error: {e.stderr}")
        return False, e.stderr
    except FileNotFoundError:
        logger.error(f"Command not found: {command[0]}")
        return False, "Command not found"

def create_user(username, password, expiry_date):
    """
    Creates a system user for VPN.
    """
    expiry_str = expiry_date.strftime('%Y-%m-%d')

    # 1. Create user
    # useradd -M -s /bin/false -e YYYY-MM-DD username
    cmd_add = ["useradd", "-M", "-s", "/bin/false", "-e", expiry_str, username]
    success, msg = run_command(cmd_add)
    if not success:
        return False, msg

    # 2. Set password
    # chpasswd expects "user:password" on stdin
    cmd_pass = ["chpasswd"]
    input_pass = f"{username}:{password}"
    success, msg = run_command(cmd_pass, input_text=input_pass)

    return success, msg

def delete_user(username):
    """
    Deletes a system user.
    """
    cmd = ["userdel", "-f", username]
    return run_command(cmd)

def kill_user_session(username):
    """
    Kills the user's connection.
    """
    cmd = ["pkill", "-u", username]
    return run_command(cmd)

def check_user_exists(username):
    """
    Checks if a user exists in the system.
    """
    cmd = ["id", username]
    if MOCK_MODE:
        logger.info(f"[MOCK SYSTEM] Checking user: {username}")
        return False # Simulate user does NOT exist so we can create it

    try:
        subprocess.run(cmd, capture_output=True, check=True)
        return True
    except subprocess.CalledProcessError:
        return False
