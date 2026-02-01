import json
import os
import subprocess
import logging

# Config path
CONFIG_PATH = "/etc/zivpn/config.json"
MOCK_MODE = True # Will be imported/controlled from config usually, but hardcoding for safety in utils

logger = logging.getLogger(__name__)

class ZivpnConfig:
    def __init__(self, path=CONFIG_PATH):
        self.path = path
        self.data = self._load()

    def _load(self):
        if MOCK_MODE and not os.path.exists(self.path):
            # Return mock data structure
            return {
                "listen": ":5667",
                "auth": {
                    "mode": "passwords",
                    "config": []
                }
            }

        try:
            with open(self.path, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.error(f"Failed to load config: {e}")
            return {"auth": {"config": []}}

    def save(self):
        if MOCK_MODE:
            logger.info(f"[MOCK ZIVPN] Saving config: {json.dumps(self.data)}")
            return True

        try:
            with open(self.path, 'w') as f:
                json.dump(self.data, f, indent=4)
            return True
        except Exception as e:
            logger.error(f"Failed to save config: {e}")
            return False

    def add_user(self, username, password):
        # We store as "username:password" string
        token = f"{username}:{password}"

        # Check if already exists (to avoid duplicates)
        if "auth" not in self.data:
             self.data["auth"] = {"mode": "passwords", "config": []}

        if "config" not in self.data["auth"]:
            self.data["auth"]["config"] = []

        # Remove existing if any (update)
        self.remove_user(username)

        self.data["auth"]["config"].append(token)
        return self.save()

    def remove_user(self, username):
        if "auth" in self.data and "config" in self.data["auth"]:
            # Filter out entries that start with "username:"
            # OR if it matches exactly (in case of legacy data)
            new_config = [
                token for token in self.data["auth"]["config"]
                if not token.startswith(f"{username}:") and token != username
            ]
            self.data["auth"]["config"] = new_config
            return self.save()
        return True

    def reload_service(self):
        cmd = ["systemctl", "restart", "zivpn"]
        if MOCK_MODE:
            logger.info(f"[MOCK ZIVPN] Restarting service: {' '.join(cmd)}")
            return True, "Mock restart success"

        try:
            subprocess.run(cmd, check=True, capture_output=True)
            return True, "Service restarted"
        except subprocess.CalledProcessError as e:
            return False, str(e)
