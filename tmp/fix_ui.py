import re

with open('c:/Users/danya/Downloads/baron-main/server.py', 'r', encoding='utf-8') as f:
    server_py = f.read()

# Fix Uninstall State Online persistence
old_uninstall = """                elif action == 'uninstall':
                    cmd_uninstall(cid)
"""
new_uninstall = """                elif action == 'uninstall':
                    cmd_uninstall(cid)
                    agents = state.get('agents') or {}
                    if cid in agents:
                        del agents[cid]
                    state.set('agents', agents)
                    socketio.emit('disconnect', {'cid': cid}, namespace='/')
"""
if old_uninstall in server_py:
    server_py = server_py.replace(old_uninstall, new_uninstall)
    with open('c:/Users/danya/Downloads/baron-main/server.py', 'w', encoding='utf-8') as f:
        f.write(server_py)
    print("SERVER PATCHED")

with open('c:/Users/danya/Downloads/baron-main/templates/index.html', 'r', encoding='utf-8') as f:
    html = f.read()

# Fix Context Menu CSS max-height
old_css = """#context-menu {
            position: fixed; z-index: 10000; width: 240px;
            background: rgba(10, 10, 15, 0.85); backdrop-filter: blur(30px);
            border: 1px solid var(--glass-border); border-radius: 12px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.8), 0 0 0 1px rgba(255,255,255,0.05) inset;
            padding: 8px; display: none; opacity: 0; transform: scale(0.95);
            transition: opacity 0.1s, transform 0.1s;
        }"""
new_css = """#context-menu {
            position: fixed; z-index: 10000; width: 240px; max-height: 40vh; overflow-y: auto;
            background: rgba(10, 10, 15, 0.85); backdrop-filter: blur(30px);
            border: 1px solid var(--glass-border); border-radius: 12px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.8), 0 0 0 1px rgba(255,255,255,0.05) inset;
            padding: 8px; display: none; opacity: 0; transform: scale(0.95);
            transition: opacity 0.1s, transform 0.1s;
        }"""
if old_css in html:
    html = html.replace(old_css, new_css)
    with open('c:/Users/danya/Downloads/baron-main/templates/index.html', 'w', encoding='utf-8') as f:
        f.write(html)
    print("CSS PATCHED")
