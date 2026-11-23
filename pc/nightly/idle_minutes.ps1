# Minutes since Kevin last touched keyboard or mouse in this session (EATP-037).
# Prints a number, or -1 if Windows cannot say (callers must then treat him as "present").
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class RoveIdle {
  [StructLayout(LayoutKind.Sequential)] struct LASTINPUTINFO { public uint cbSize; public uint dwTime; }
  [DllImport("user32.dll")] static extern bool GetLastInputInfo(ref LASTINPUTINFO p);
  public static double Minutes() {
    LASTINPUTINFO i = new LASTINPUTINFO(); i.cbSize = (uint)Marshal.SizeOf(i);
    if (!GetLastInputInfo(ref i)) return -1;
    return ((uint)Environment.TickCount - i.dwTime) / 60000.0;
  }
}
"@
[math]::Round([RoveIdle]::Minutes(), 1)
