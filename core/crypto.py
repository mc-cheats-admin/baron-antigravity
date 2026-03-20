import base64
import hashlib
import secrets
import logging
from .config import Config

logger = logging.getLogger('BARON.CRYPTO')

try:
    from Crypto.Cipher import AES
    from Crypto.Protocol.KDF import PBKDF2
    HAS_AES = True
except ImportError:
    logger.warning("PyCryptodome not found. Crypto operations will fail securely.")
    HAS_AES = False

class CryptoEngine:
    """Strong AES-256-GCM encryption engine"""

    def __init__(self, key=None):
        self.key = key or Config.MASTER_KEY
        if len(self.key) != 32:
            self.key = hashlib.sha256(self.key).digest()

    def encrypt(self, data: bytes) -> str:
        if not HAS_AES:
            raise RuntimeError("PyCryptodome required for encryption")
            
        nonce = secrets.token_bytes(12)
        cipher = AES.new(self.key, AES.MODE_GCM, nonce=nonce)
        ciphertext, tag = cipher.encrypt_and_digest(data)
        
        # Format: nonce (12) + tag (16) + ciphertext
        return base64.b64encode(nonce + tag + ciphertext).decode()

    def decrypt(self, data_b64: str) -> bytes:
        if not HAS_AES:
            raise RuntimeError("PyCryptodome required for decryption")
            
        try:
            raw = base64.b64decode(data_b64)
            nonce, tag, ciphertext = raw[:12], raw[12:28], raw[28:]
            cipher = AES.new(self.key, AES.MODE_GCM, nonce=nonce)
            return cipher.decrypt_and_verify(ciphertext, tag)
        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            raise ValueError("Invalid ciphertext or key")

    @staticmethod
    def generate_key(length=32) -> bytes:
        return secrets.token_bytes(length)

crypto = CryptoEngine()
