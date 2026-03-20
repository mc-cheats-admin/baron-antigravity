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

    if not guard.check_rate_limit(f"login:{ip}", max_req=10, window=60):
        return jsonify({'ok': False, 'error': 'Rate limit exceeded'}), 429

    # Migration: checking legacy admin/admin
    if user == "admin" and password == "admin":
        is_admin = True
    else:
        # Here we would check real DB users
        return jsonify({'ok': False, 'error': 'Invalid credentials'}), 401

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
