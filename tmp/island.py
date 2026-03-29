import re
with open('c:/Users/danya/Downloads/baron-main/templates/index.html', 'r', encoding='utf-8') as f:
    text = f.read()

island_html = '''<!-- Dynamic Island -->
<div id="dynamic-island" class="dynamic-island">
    <div class="island-content">
        <div class="island-icon">
            <i id="island-icon-class" class="fa-solid fa-info-circle"></i>
        </div>
        <div class="island-text" id="island-text">Notification</div>
    </div>
</div>
'''

island_css = '''<style>
.dynamic-island {
    position: fixed;
    top: 20px;
    left: 50%;
    transform: translateX(-50%) translateY(-20px) scale(0.9);
    min-width: 50px;
    width: auto;
    height: 40px;
    background: rgba(10, 10, 10, 0.4);
    backdrop-filter: blur(25px);
    -webkit-backdrop-filter: blur(25px);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 30px;
    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5), inset 0 0 15px rgba(255, 255, 255, 0.05);
    z-index: 10000;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 0 15px;
    opacity: 0;
    transition: all 0.5s cubic-bezier(0.8, -0.2, 0.2, 1.4);
    pointer-events: none;
    overflow: hidden;
}

.dynamic-island.show {
    opacity: 1;
    transform: translateX(-50%) translateY(0) scale(1);
    height: 45px;
    pointer-events: auto;
    min-width: 250px;
}

.island-content {
    display: flex;
    align-items: center;
    gap: 12px;
    width: 100%;
    color: #fff;
    white-space: nowrap;
}

.island-icon {
    font-size: 1.1rem;
    color: #fff;
    text-shadow: 0 0 15px currentColor;
    flex-shrink: 0;
}

.island-icon.success { color: #00ff88; }
.island-icon.error { color: #ff3366; }
.island-icon.info { color: #00eeff; }

.island-text {
    font-size: 0.95rem;
    font-weight: 500;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    opacity: 0;
    transform: translateX(10px);
    transition: all 0.3s ease 0.1s;
    flex-grow: 1;
}

.dynamic-island.show .island-text {
    opacity: 1;
    transform: translateX(0);
}
</style>
'''

island_js = '''<script>
function showIsland(text, type='info', duration=4000) {
    const island = document.getElementById('dynamic-island');
    const txt = document.getElementById('island-text');
    const iconWrapper = document.querySelector('.island-icon');
    const icon = document.getElementById('island-icon-class');
    
    txt.innerText = text;
    
    iconWrapper.className = 'island-icon ' + type;
    if (type === 'success') {
        icon.className = 'fa-solid fa-check-circle fa-beat';
    } else if (type === 'error') {
        icon.className = 'fa-solid fa-triangle-exclamation fa-shake';
    } else {
        icon.className = 'fa-solid fa-info-circle fa-fade';
    }
    
    island.classList.remove('show');
    void island.offsetWidth;
    island.classList.add('show');
    
    if (island.hideTimeout) clearTimeout(island.hideTimeout);
    
    island.hideTimeout = setTimeout(() => {
        island.classList.remove('show');
    }, duration);
}

// Override showResult to use Dynamic Island for simple short messages and Modal ONLY for huge text
const originalShowResult = window.showResult;
window.showResult = function(title, content) {
    if (!content) return;
    
    // Check if it's a huge block of text (e.g. keylogger, net scanner, or raw token dump)
    if (content.length > 150 || content.includes('\\n')) {
        originalShowResult(title, content);
        // also pop island
        showIsland(title + " received", "success");
    } else {
        // Just dynamic island for small stuff
        let type = 'info';
        if (content.toLowerCase().includes('started') || content.toLowerCase().includes('success')) type = 'success';
        if (content.toLowerCase().includes('error') || content.toLowerCase().includes('failed')) type = 'error';
        showIsland(title + ': ' + content, type);
    }
};
</script>
'''

if 'dynamic-island' not in text:
    text = text.replace('</head>', island_css + '</head>')
    text = text.replace('<body>', '<body>\n' + island_html)
    text = text.replace('</body>', island_js + '</body>')
    with open('c:/Users/danya/Downloads/baron-main/templates/index.html', 'w', encoding='utf-8') as f:
        f.write(text)
    print("UI INJECTED")
