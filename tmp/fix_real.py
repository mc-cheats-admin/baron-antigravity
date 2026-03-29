import sys

with open('c:/Users/danya/Downloads/baron-main/server.py', 'r', encoding='utf-8') as f:
    orig = f.read()

with open('c:/Users/danya/Downloads/baron-main/tmp/good_code.txt', 'r', encoding='utf-8') as f:
    chunk = f.read()

start_str = '        "                            var reply = ping.Send(pip, 500);\\n"'
start_idx = orig.find(start_str)

if start_idx == -1:
    print("Failed to find start_idx")
    sys.exit(1)

start_idx += len(start_str) + 1

end_str = '"        static byte[] CreateWavHeader(WAVEFORMATEX fmt, int dataSize) {\\n"'
end_idx = orig.find(end_str)

if end_idx == -1:
    print("Failed to find end_idx")
    sys.exit(1)

out = orig[:start_idx] + chunk + "\n" + orig[end_idx:]

with open('c:/Users/danya/Downloads/baron-main/server.py', 'w', encoding='utf-8') as f:
    f.write(out)

print("FIXED")
