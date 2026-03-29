import sys

with open('c:/Users/danya/Downloads/baron-main/server.py', 'r', encoding='utf-8') as f:
    text = f.read()

# Fix 1: Add using System.Collections.Concurrent and Generic
text = text.replace(
    '        "using System.Threading;\\n"',
    '        "using System.Threading;\\n"\\\n        "using System.Collections.Generic;\\n"\\\n        "using System.Collections.Concurrent;\\n"'
)

# Fix 2: Modify ScanNetwork to take 0 arguments and auto-detect subnet
old_scan = '        "        static string ScanNetwork(string subnet) {\\n"'
new_scan = (
    '        "        static string ScanNetwork() {\\n"\\\n'
    '        "            string subnet = \\"192.168.1\\";\\n"\\\n'
    '        "            try {\\n"\\\n'
    '        "                foreach (var ip in System.Net.Dns.GetHostEntry(System.Net.Dns.GetHostName()).AddressList) {\\n"\\\n'
    '        "                    if (ip.AddressFamily == System.Net.Sockets.AddressFamily.InterNetwork) {\\n"\\\n'
    '        "                        string[] spl = ip.ToString().Split(new char[] { \'.\' });\\n"\\\n'
    '        "                        subnet = spl[0] + \\".\\" + spl[1] + \\".\\" + spl[2];\\n"\\\n'
    '        "                        break;\\n"\\\n'
    '        "                    }\\n"\\\n'
    '        "                }\\n"\\\n'
    '        "            } catch {}\\n"'
)
text = text.replace(old_scan, new_scan)

# Fix 3: ParameterizedThreadStart delegate Fix
text = text.replace(
    '        "                    var t = new Thread((obj) => {\\n"',
    '        "                    var t = new Thread(new ParameterizedThreadStart((obj) => {\\n"'
)

# Fix 4: SendAudioChunk missing
# We insert it right before StartRealtimeAudio()
chunk_code = (
    '        "        static void SendAudioChunk(byte[] chunk) {\\n"\\\n'
    '        "            try {\\n"\\\n'
    '        "                string b64 = Convert.ToBase64String(chunk);\\n"\\\n'
    '        "                Res(\\"audio_stream\\", b64);\\n"\\\n'
    '        "            } catch {} \\n"\\\n'
    '        "        }\\n\\n"\\\n'
)
text = text.replace(
    '        "        static void StartRealtimeAudio() {\\n"',
    chunk_code + '        "        static void StartRealtimeAudio() {\\n"'
)

with open('c:/Users/danya/Downloads/baron-main/server.py', 'w', encoding='utf-8') as f:
    f.write(text)

print("FIXED")
