import os
import base64
import hashlib
from cryptography.fernet import Fernet

API_ID = int(os.environ.get("API_ID", 12345678))
API_HASH = os.environ.get("API_HASH", "your_api_hash_here")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "1234567890:YOUR_BOT_TOKEN_HERE")
ADMIN_ID = int(os.environ.get("ADMIN_ID", 1234567890))
MONGO_URI = os.environ.get("MONGO_URI", "mongodb+srv://username:password@cluster.mongodb.net/?appName=cluster")
WORK_DIR = os.path.abspath(os.environ.get("WORK_DIR", "./downloads"))
LOG_GROUP_ID = None
LOG_CHANNEL_ID = int(os.environ.get("LOG_CHANNEL_ID", -1003820017953))
_raw_fsub = os.environ.get("FSUB_CHANNEL", "desibotz").strip()
if "t.me/" in _raw_fsub:
    _raw_fsub = _raw_fsub.split("t.me/")[-1].strip("/")
if _raw_fsub.startswith("@"):
    _raw_fsub = _raw_fsub[1:]
FSUB_CHANNEL = _raw_fsub

os.makedirs(WORK_DIR, exist_ok=True)

# DONT CHANGE THIS KEY
ENCRYPTION_KEY = os.environ.get("ENCRYPTION_KEY", "SAMRA_SECURE_AES256_ENGINE_KEY_DO_NOT_CHANGE")

def _derive_fernet_key(secret: str) -> bytes:
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)

_FERNET_ENGINE = Fernet(_derive_fernet_key(ENCRYPTION_KEY))

def encrypt_session(session_str: str) -> str:
    if not session_str:
        return ""
    token = _FERNET_ENGINE.encrypt(session_str.encode("utf-8")).decode("utf-8")
    return f"ENC_{token}"

def decrypt_session(stored_session: str) -> str:
    if not stored_session:
        return ""
    if stored_session.startswith("ENC_"):
        cipher_token = stored_session[4:]
        try:
            return _FERNET_ENGINE.decrypt(cipher_token.encode("utf-8")).decode("utf-8")
        except Exception as e:
            raise ValueError(f"Session Decryption Failed! Invalid ENCRYPTION_KEY or corrupt data. Error: {e}")
    return stored_session
