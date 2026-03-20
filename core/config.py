import os
import secrets
import hashlib
from pathlib import Path

class Config:
    VERSION = "5.0.0-SOVEREIGN"
    
    # Network
    PORT = int(os.environ.get('PORT', 5000))
    DEBUG = os.environ.get('DEBUG', 'False').lower() == 'true'
    
    # Secrets
    SECRET_KEY = os.environ.get('BARON_SECRET', secrets.token_hex(32))
    MASTER_KEY = hashlib.sha256(SECRET_KEY.encode()).digest()
    
    # Paths
    BASE_DIR = Path(__file__).parent.parent
    UPLOADS_DIR = BASE_DIR / "uploads"
    BUILDS_DIR = BASE_DIR / "builds"
    DATABASE_PATH = os.environ.get('DATABASE_URL', str(BASE_DIR / "baron_v5.db"))
    
    # Security Policy
    TOKEN_LIFETIME = 86400  # 24h
    NONCE_WINDOW = 300      # 5m
    LOGIN_MAX_ATTEMPTS = 5
    LOGIN_LOCKOUT_TIME = 900 # 15m
    RATE_LIMIT_WINDOW = 60
    
    # Render.com specific
    TRUST_PROXY = True
    
    @classmethod
    def init_dirs(cls):
        cls.UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
        cls.BUILDS_DIR.mkdir(parents=True, exist_ok=True)

# Pre-obfuscated standard credentials (example)
# In production, these should be in ENV
class DefaultCreds:
    _CRED_KEY = b'\x4f\x7a\x2b\x91\xde\x33\xc7\x58\xa2\x1d\xe6\x0b\x74\xf9\x8c\x40'
    
    @staticmethod
    def decode(data_hex):
        raw = bytes.fromhex(data_hex)
        key = DefaultCreds._CRED_KEY
        return bytes(b ^ key[i % len(key)] for i, b in enumerate(raw)).decode('utf-8')
