import re

with open('c:/Users/danya/Downloads/baron-main/server.py', 'r', encoding='utf-8') as f:
    text = f.read()

text = text.replace(
    '[DllImport("ntdll.dll", SetLastError = true)] static extern int NtSuspendProcess(IntPtr processHandle);\\n"',
    '        "        [DllImport(\\"ntdll.dll\\", SetLastError = true)] static extern int NtSuspendProcess(IntPtr processHandle);\\n"'
)

with open('c:/Users/danya/Downloads/baron-main/server.py', 'w', encoding='utf-8') as f:
    f.write(text)
print("FIXED NTDLL syntax")
