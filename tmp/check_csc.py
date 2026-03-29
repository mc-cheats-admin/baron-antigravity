with open('c:/Users/danya/Downloads/baron-main/server.py', 'r', encoding='utf-8') as f:
    text = f.read()
import re
m = re.search(r'csc\.exe(?:.|\n)*?\"', text, re.IGNORECASE)
if m: print(m.group(0))
