import time
import secrets
import hashlib
import re
import logging
import threading
from flask import request, jsonify, Response
from .config import Config
from .db import db

logger = logging.getLogger('BARON.GUARD')

try:
    from argon2 import PasswordHasher
    ph = PasswordHasher()
    HAS_ARGON2 = True
except ImportError:
    logger.warning("Argon2 not found. Falling back to PBKDF2.")
    HAS_ARGON2 = False

class SecurityGuard:
    """Authentication, authorization, rate limiting, banning"""

    def __init__(self):
        self._rate_limits = {}
        self._rate_lock = threading.Lock()
        self._failed_logins = {} # IP -> count
        self._fim_thread = None
        self._file_hashes = {}
        self.whitelisted_ips = [] # Loaded from config
        self.honeypot_users = ['admin', 'root', 'administrator', 'system', 'test']

    def hash_password(self, password: str) -> str:
        if HAS_ARGON2:
            return ph.hash(password)
        else:
            # PBKDF2 Fallback
            salt = secrets.token_bytes(16)
            dk = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 100000)
            return f"pbkdf2:sha256:100000${salt.hex()}${dk.hex()}"

    def verify_password(self, password: str, hashed: str) -> bool:
        if hashed.startswith('$argon2id$'):
            if not HAS_ARGON2: return False
            try: return ph.verify(hashed, password)
            except: return False
        elif hashed.startswith('pbkdf2:sha256:'):
            try:
                method, hash_name, iterations, salt_hex, dk_hex = hashed.split('$')[0].split(':') + hashed.split('$')[1:]
                salt = bytes.fromhex(salt_hex)
                expected = bytes.fromhex(dk_hex)
                actual = hashlib.pbkdf2_hmac(hash_name, password.encode(), salt, int(iterations))
                return secrets.compare_digest(actual, expected)
            except: return False
        else:
            # Legacy SHA256 (for migration)
            actual = hashlib.sha256(password.encode()).hexdigest()
            # Timing attack mitigation: fake sleep
            time.sleep(secrets.randbelow(50) / 1000.0)
            return secrets.compare_digest(actual, hashed)

    def get_client_ip(self):
        """Get real client IP — with Render.com support"""
        forwarded = request.headers.get('X-Forwarded-For', '')
        if forwarded:
            ip = forwarded.split(',')[0].strip()
            if re.match(r'^[\d.:a-fA-F]+$', ip):
                return ip
        return request.remote_addr or '0.0.0.0'

    def check_ban(self, ip):
        bans = db.get_state('bans', {})
        ban = bans.get(ip)
        if not ban: return None
        if ban.get('until', 0) > 0 and time.time() > ban.get('until', 0):
            del bans[ip]
            db.set_state('bans', bans)
            return None
        return ban

    def ban_ip(self, ip, duration_min=0, reason=''):
        bans = db.get_state('bans', {})
        until = time.time() + (duration_min * 60) if duration_min > 0 else 0
        bans[ip] = {'until': until, 'reason': reason, 'at': time.time()}
        db.set_state('bans', bans)
        db.log('WARN', f"Banned IP {ip} — {reason}")

    def check_rate_limit(self, key, max_req=60, window=60):
        now = time.time()
        with self._rate_lock:
            hits = self._rate_limits.get(key, [])
            hits = [t for t in hits if now - t < window]
            if len(hits) >= max_req: return False
            hits.append(now)
            self._rate_limits[key] = hits
            return True

    def register_failed_login(self, ip):
        with self._rate_lock:
            count = self._failed_logins.get(ip, 0) + 1
            self._failed_logins[ip] = count
            # Exponential tarpit: 1s, 2s, 4s, 8s...
            delay = min(2 ** (count - 1), 30)
            time.sleep(delay)
            if count >= 5:
                # Ban after 5 fails
                self.ban_ip(ip, duration_min=60, reason="Brute-force protection")

    def register_success_login(self, ip):
        with self._rate_lock:
            if ip in self._failed_logins:
                del self._failed_logins[ip]

    def check_whitelist(self, ip):
        if not self.whitelisted_ips: return True
        return ip in self.whitelisted_ips

    def handle_honeypot(self, user, ip):
        if user.lower() in self.honeypot_users:
            self.ban_ip(ip, duration_min=1440, reason=f"Honeypot trap triggered for user {user}")
            logger.critical(f"HONEYPOT TRIGGERED! IP {ip} tried to login as {user}. Banned for 24h.")
            return True
        return False

    def start_fim(self, paths):
        """File Integrity Monitoring for critical components"""
        import os
        for p in paths:
            if os.path.exists(p):
                with open(p, 'rb') as f:
                    self._file_hashes[p] = hashlib.sha256(f.read()).hexdigest()

        def fim_loop():
            while True:
                time.sleep(60)
                for p, expected_hash in self._file_hashes.items():
                    if os.path.exists(p):
                        with open(p, 'rb') as f:
                            actual = hashlib.sha256(f.read()).hexdigest()
                            if actual != expected_hash:
                                logger.critical(f"FIM ALERT: File {p} was modified! Shutting down to prevent compromise.")
                                os._exit(1) # Hard kill
        
        self._fim_thread = threading.Thread(target=fim_loop, daemon=True)
        self._fim_thread.start()

    def create_session(self, user, ip, is_admin=False):
        token = secrets.token_hex(48)
        sessions = db.get_state('sessions', {})
        sessions[token] = {
            'user': user, 'ip': ip, 'admin': is_admin,
            'at': time.time(), 'last': time.time()
        }
        db.set_state('sessions', sessions)
        return token

    def validate_session(self, token):
        if not token: return None
        sessions = db.get_state('sessions', {})
        session = sessions.get(token)
        if not session: return None
        if time.time() - session['at'] > Config.TOKEN_LIFETIME:
            del sessions[token]
            db.set_state('sessions', sessions)
            return None
        session['last'] = time.time()
        db.set_state('sessions', sessions)
        return session

def require_auth(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('X-Token')
        session = guard.validate_session(token)
        if not session:
            return jsonify({'ok': False, 'error': 'Unauthorized'}), 401
        request.session = session
        return f(*args, **kwargs)
    return decorated

def require_admin(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('X-Token')
        session = guard.validate_session(token)
        if not session or not session.get('admin'):
            return jsonify({'ok': False, 'error': 'Admin required'}), 401
        request.session = session
        return f(*args, **kwargs)
    return decorated

guard = SecurityGuard()
