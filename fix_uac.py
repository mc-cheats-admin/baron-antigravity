"""Generate the actual C# file and analyze line 606 for CS1009"""
import os, sys, re

path = r"c:\Users\danya\Downloads\baron-main\server.py"

# Read the whole server.py  
with open(path, 'r', encoding='utf-8') as f:
    server_code = f.read()

# We need to call generate_agent_source but that requires Flask etc.
# Instead, let's extract just the function and its dependencies, 
# and mock what we need.

# Extract all _generate_* functions and the main function
# and evaluate them

# Simpler approach: use exec with mocks
import hashlib, secrets, time

def encrypt_string(s, key):
    """XOR encrypt and base64 encode"""
    import base64
    enc = bytes([ord(c) ^ key[i % len(key)] for i, c in enumerate(s)])
    return base64.b64encode(enc).decode()

# Extract the function code
func_pattern = re.compile(r'^def (generate_agent_source|_generate_\w+)\(.*?\):\s*\n(.*?)(?=\ndef |\Z)', re.MULTILINE | re.DOTALL)
funcs = func_pattern.findall(server_code)

# Build executable code
code_parts = []
code_parts.append("import hashlib, secrets, time, re, base64, os\n")
code_parts.append("""
def encrypt_string(s, key):
    enc = bytes([ord(c) ^ key[i % len(key)] for i, c in enumerate(s)])
    return base64.b64encode(enc).decode()
""")

# Extract all functions from generate_agent_source line to end of file
func_start_idx = server_code.index('def generate_agent_source(bc):')
# Get all code from there to end
func_code = server_code[func_start_idx:]

# Write to a temp file and exec it 
temp_path = os.path.join(os.path.dirname(path), '_temp_gen.py')
with open(temp_path, 'w', encoding='utf-8') as f:
    f.write("import hashlib, secrets, time, re, base64, os\n\n")
    f.write("""
def encrypt_string(s, key):
    enc = bytes([ord(c) ^ key[i % len(key)] for i, c in enumerate(s)])
    return base64.b64encode(enc).decode()
\n""")
    f.write(func_code)
    f.write("""
\n
if __name__ == '__main__':
    bc = {
        'server': 'https://example.com',
        'name': 'svchost',
        'id': 'test123456',
        'beacon': 5000,
        'hidden': True,
        'persistence': True, 
        'anti_kill': True,
        'disable_defender': True,
        'fake_error': False,
        'fake_error_msg': '',
        'anti_analysis': True,
        'debug': False,
    }
    source = generate_agent_source(bc)
    # Write to file
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '_test_output.cs')
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(source)
    
    lines = source.split('\\n')
    print(f"Total C# lines: {len(lines)}")
    
    # Show line 606
    if len(lines) >= 606:
        line606 = lines[605]
        print(f"Line 606 ({len(line606)} chars): {line606}")
        if len(line606) >= 89:
            print(f"Char at pos 89: {repr(line606[88])}")
            print(f"Context around pos 89: {repr(line606[80:100])}")
    
    # Search for backslash-space in entire output
    for i, line in enumerate(lines):
        if '\\\\ ' in line:
            print(f"FOUND '\\\\ ' at C# line {i+1}: {line[:120]}")
        # Also check for raw backslash followed by non-escape chars
        bad = re.findall(r'(?<!@)\"[^\"]*\\\\([^\\\\nrt0\"abfvux\\'\\\\])', line)
        if bad:
            print(f"BAD ESCAPE at C# line {i+1}: {bad} -> {line[:120]}")
""")

print("Generated test file. Running...")
os.system(f'python {temp_path}')
