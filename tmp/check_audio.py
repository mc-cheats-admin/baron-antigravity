import re

with open('c:/Users/danya/Downloads/baron-main/server.py', 'r', encoding='utf-8') as f:
    text = f.read()

m = re.search(r'elif data\.get\("type"\) == "(\w+)".*?emit', text, re.IGNORECASE)
if m: print("Audio socket io emit is present?", m.group(0))

print("All lines handling audio:")
for line in text.split('\n'):
    if 'audio' in line.lower() and 'emit' in line.lower():
        print(line)
