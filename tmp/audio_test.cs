
using System;
using System.IO;
using System.Runtime.InteropServices;
using System.Threading;

class Program {
    [DllImport("winmm.dll")]
    public static extern int waveInOpen(out IntPtr hWaveIn, int uDeviceID, ref WAVEFORMATEX lpFormat, waveInProc dwCallback, IntPtr dwInstance, int dwFlags);
    [DllImport("winmm.dll")]
    public static extern int waveInPrepareHeader(IntPtr hWaveIn, IntPtr lpWaveInHdr, int uSize);
    [DllImport("winmm.dll")]
    public static extern int waveInAddBuffer(IntPtr hWaveIn, IntPtr lpWaveInHdr, int uSize);
    [DllImport("winmm.dll")]
    public static extern int waveInStart(IntPtr hWaveIn);
    [DllImport("winmm.dll")]
    public static extern int waveInStop(IntPtr hWaveIn);
    [DllImport("winmm.dll")]
    public static extern int waveInUnprepareHeader(IntPtr hWaveIn, IntPtr lpWaveInHdr, int uSize);
    [DllImport("winmm.dll")]
    public static extern int waveInClose(IntPtr hWaveIn);

    public delegate void waveInProc(IntPtr hWaveIn, int uMsg, IntPtr dwInstance, IntPtr wavhdr, IntPtr dwParam2);

    [StructLayout(LayoutKind.Sequential)]
    public struct WAVEFORMATEX {
        public short wFormatTag;
        public short nChannels;
        public int nSamplesPerSec;
        public int nAvgBytesPerSec;
        public short nBlockAlign;
        public short wBitsPerSample;
        public short cbSize;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct WAVEHDR {
        public IntPtr lpData;
        public int dwBufferLength;
        public int dwBytesRecorded;
        public IntPtr dwUser;
        public int dwFlags;
        public int dwLoops;
        public IntPtr lpNext;
        public IntPtr reserved;
    }

    static waveInProc _waveInCallback;
    static IntPtr _hWaveIn;
    static bool rtAudioRunning = false;

    static void Main() {
        Console.WriteLine("STARTING RECORD");
        Start();
        Thread.Sleep(5000);
        rtAudioRunning = false;
        Console.WriteLine("STOP");
    }

    static void Start() {
        rtAudioRunning = true;
        WAVEFORMATEX format = new WAVEFORMATEX();
        format.wFormatTag = 1; 
        format.nChannels = 1;
        format.nSamplesPerSec = 8000;
        format.wBitsPerSample = 16;
        format.nBlockAlign = (short)(format.nChannels * format.wBitsPerSample / 8);
        format.nAvgBytesPerSec = format.nSamplesPerSec * format.nBlockAlign;
        format.cbSize = 0;

        _waveInCallback = new waveInProc(WaveInCallbackPtr);

        int res = waveInOpen(out _hWaveIn, -1, ref format, _waveInCallback, IntPtr.Zero, 0x30000);
        if (res != 0) {
            Console.WriteLine("ERR: " + res);
            return;
        }

        for (int i=0; i<3; i++) {
            IntPtr headerPtr = Marshal.AllocHGlobal(Marshal.SizeOf(typeof(WAVEHDR)));
            WAVEHDR header = new WAVEHDR();
            header.dwBufferLength = format.nAvgBytesPerSec / 2; // 0.5 sec
            header.lpData = Marshal.AllocHGlobal(header.dwBufferLength);
            Marshal.StructureToPtr(header, headerPtr, false);

            waveInPrepareHeader(_hWaveIn, headerPtr, Marshal.SizeOf(typeof(WAVEHDR)));
            waveInAddBuffer(_hWaveIn, headerPtr, Marshal.SizeOf(typeof(WAVEHDR)));
        }
        waveInStart(_hWaveIn);
    }

    static void WaveInCallbackPtr(IntPtr hwi, int uMsg, IntPtr dwInstance, IntPtr wavhdrPtr, IntPtr dwParam2) {
        if (uMsg == 0x3BF) { // 0x3BF = MM_WIM_DATA
            WAVEHDR header = (WAVEHDR)Marshal.PtrToStructure(wavhdrPtr, typeof(WAVEHDR));
            if (header.dwBytesRecorded > 0 && rtAudioRunning) {
                Console.WriteLine("RECORDED: " + header.dwBytesRecorded + " bytes");
                // REQUEUE
                waveInAddBuffer(hwi, wavhdrPtr, Marshal.SizeOf(typeof(WAVEHDR)));
            }
        }
    }
}

