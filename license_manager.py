import json
import os
import hashlib
import time

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")

# ---------------------------------------------
# Helper functions
# ---------------------------------------------
def _hash(text: str) -> str:
    """Simple SHA1 hash for license key"""
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]

def get_hash(email: str) -> str:
    """Generate a deterministic license key from email"""
    return _hash(email.lower().strip())

# ---------------------------------------------
# License Configuration Management
# ---------------------------------------------
def init_license():
    """Create config file if not exists"""
    if not os.path.exists(CONFIG_PATH):
        data = {
            "premium": False,
            "email": "",
            "key": "",
            "activated_at": 0,
            "expires_at": 0
        }
        with open(CONFIG_PATH, "w") as f:
            json.dump(data, f, indent=2)

def get_license_info():
    if not os.path.exists(CONFIG_PATH):
        init_license()
    try:
        with open(CONFIG_PATH, "r") as f:
            return json.load(f)
    except Exception:
        return {"premium": False}

def save_license_info(info):
    with open(CONFIG_PATH, "w") as f:
        json.dump(info, f, indent=2)

# ---------------------------------------------
# Activation Logic
# ---------------------------------------------
def activate_license(email: str, key: str) -> bool:
    """Check license key and activate if valid"""
    expected = get_hash(email)
    if key.strip().lower() == expected.lower():
        info = get_license_info()
        info.update({
            "premium": True,
            "email": email,
            "key": key,
            "activated_at": int(time.time()),
            "expires_at": int(time.time()) + (365 * 24 * 3600)  # 1 year license
        })
        save_license_info(info)
        print(f"\n✅ License activated successfully for {email}")
        print("🚀 Premium mode enabled for 1 year.")
        return True
    else:
        print("\n❌ Invalid license key. Please check and try again.")
        return False

def is_premium() -> bool:
    info = get_license_info()
    if not info.get("premium"):
        return False
    # check expiration
    if int(time.time()) > info.get("expires_at", 0):
        print("\n⚠️ License expired. Please renew.")
        info["premium"] = False
        save_license_info(info)
        return Fa
