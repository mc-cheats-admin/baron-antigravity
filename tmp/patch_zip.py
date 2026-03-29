import sys

with open('c:/Users/danya/Downloads/baron-main/server.py', 'r', encoding='utf-8') as f:
    text = f.read()

# Add ZIP library to compilation arguments for the new Grabber
old_mcs = "            '-r:System.Security.dll',"
new_mcs = "            '-r:System.Security.dll',\n            '-r:System.IO.Compression.dll',\n            '-r:System.IO.Compression.FileSystem.dll',"
old_csc = "            '/r:System.Security.dll',"
new_csc = "            '/r:System.Security.dll',\n            '/r:System.IO.Compression.dll',\n            '/r:System.IO.Compression.FileSystem.dll',"

if old_mcs in text and old_csc in text:
    text = text.replace(old_mcs, new_mcs)
    text = text.replace(old_csc, new_csc)
    with open('c:/Users/danya/Downloads/baron-main/server.py', 'w', encoding='utf-8') as f:
        f.write(text)
    print("DLL ADDED")
else:
    print("FAILED TO PATCH CSC DLLS")
