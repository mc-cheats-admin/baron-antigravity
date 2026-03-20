import sqlite3
import threading
import json
import time
import logging
from .config import Config

logger = logging.getLogger('BARON.DB')

class Database:
    """Thread-safe SQLite wrapper for persistent state"""
    
    def __init__(self, db_path=None):
        self.db_path = db_path or Config.DATABASE_PATH
        self._lock = threading.RLock()
        self._init_db()

    def _get_conn(self):
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._lock:
            conn = self._get_conn()
            cursor = conn.cursor()
            
            # Key-Value store for global state
            cursor.execute('''CREATE TABLE IF NOT EXISTS state 
                             (key TEXT PRIMARY KEY, value TEXT)''')
            
            # Audit Logs
            cursor.execute('''CREATE TABLE IF NOT EXISTS logs 
                             (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                              time REAL, level TEXT, msg TEXT)''')
            
            # Clients
            cursor.execute('''CREATE TABLE IF NOT EXISTS clients 
                             (cid TEXT PRIMARY KEY, data TEXT, last_seen REAL)''')
            
            # Tasks
            cursor.execute('''CREATE TABLE IF NOT EXISTS tasks 
                             (tid TEXT PRIMARY KEY, cid TEXT, data TEXT, status TEXT)''')
            
            conn.commit()
            conn.close()

    def set_state(self, key, value):
        with self._lock:
            conn = self._get_conn()
            val_json = json.dumps(value)
            conn.execute("INSERT OR REPLACE INTO state (key, value) VALUES (?, ?)", (key, val_json))
            conn.commit()
            conn.close()

    def get_state(self, key, default=None):
        with self._lock:
            conn = self._get_conn()
            res = conn.execute("SELECT value FROM state WHERE key = ?", (key,)).fetchone()
            conn.close()
            return json.loads(res['value']) if res else default

    def log(self, level, msg):
        with self._lock:
            conn = self._get_conn()
            conn.execute("INSERT INTO logs (time, level, msg) VALUES (?, ?, ?)", 
                         (time.time(), level, msg))
            conn.commit()
            conn.close()

    def get_logs(self, limit=100):
        with self._lock:
            conn = self._get_conn()
            res = conn.execute("SELECT * FROM logs ORDER BY time DESC LIMIT ?", (limit,)).fetchall()
            conn.close()
            return [dict(r) for r in res]

db = Database()
