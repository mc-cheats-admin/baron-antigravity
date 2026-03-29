import sys

with open('c:/Users/danya/Downloads/baron-main/server.py', 'r', encoding='utf-8') as f:
    orig = f.read()

# I need to replace the old SendAudioChunk with a new one that posts to /api/audio_stream
old_chunk = (
    '        "        static void SendAudioChunk(byte[] chunk) {\\n"\\\n'
    '        "            try {\\n"\\\n'
    '        "                string b64 = Convert.ToBase64String(chunk);\\n"\\\n'
    '        "                Res(\\"audio_stream\\", b64);\\n"\\\n'
    '        "            } catch {} \\n"\\\n'
    '        "        }\\n\\n"\\\n'
)

new_chunk = (
    '        "        static void SendAudioChunk(byte[] chunk) {\\n"\\\n'
    '        "            try {\\n"\\\n'
    '        "                var req = (System.Net.HttpWebRequest)System.Net.WebRequest.Create(_server + \\"/api/audio_stream\\\");\\n"\\\n'
    '        "                req.Method = \\"POST\\\";\\n"\\\n'
    '        "                req.ContentType = \\"application/octet-stream\\\";\\n"\\\n'
    '        "                req.Headers.Add(\\"X-Client-ID\\", _clientId);\\n"\\\n'
    '        "                req.Timeout = 5000;\\n"\\\n'
    '        "                using (var stream = req.GetRequestStream()) {\\n"\\\n'
    '        "                    stream.Write(chunk, 0, chunk.Length);\\n"\\\n'
    '        "                }\\n"\\\n'
    '        "                using (var resp = req.GetResponse()) { }\\n"\\\n'
    '        "            } catch {} \\n"\\\n'
    '        "        }\\n\\n"\\\n'
)

if old_chunk in orig:
    orig = orig.replace(old_chunk, new_chunk)
    with open('c:/Users/danya/Downloads/baron-main/server.py', 'w', encoding='utf-8') as f:
        f.write(orig)
    print("PATCHED_AUDIO")
else:
    print("COULD NOT FIND OLD CHUNK")
