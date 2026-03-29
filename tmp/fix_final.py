import sys

with open('c:/Users/danya/Downloads/baron-main/server.py', 'r', encoding='utf-8') as f:
    orig = f.read()

with open('c:/Users/danya/Downloads/baron-main/tmp/good_code.txt', 'r', encoding='utf-8') as f:
    chunk = f.read()

# We need to find where the corruption starts and ends.
# I know the text output by my view_file was:
# 2855:         "                            var reply = ping.Send(pip, 500);\n"
# 2856:         "                            if (reply.Status == System.Net.NetworkInformation.IPStatus.Success) {\n"
# So let's split from 2855!

start_str = '        "                            var reply = ping.Send(pip, 500);\\n"'
start_idx = orig.find(start_str)

if start_idx == -1:
    print("Could not find start str")
    sys.exit(1)

start_idx += len(start_str) + 1 # include the \n

# And the end is the python literal "        static byte[] CreateWavHeader"
end_str = '"        static byte[] CreateWavHeader(WAVEFORMATEX fmt, int dataSize) {\\n"'
end_idx = orig.find(end_str)

if end_idx == -1:
    print("Could not find end str")
    sys.exit(1)

out = orig[:start_idx] + chunk + orig[end_idx:]

with open('c:/Users/danya/Downloads/baron-main/server.py', 'w', encoding='utf-8') as f:
    f.write(out)
    
print("FIXED")
