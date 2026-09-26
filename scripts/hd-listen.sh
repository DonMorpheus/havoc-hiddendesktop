#!/usr/bin/env bash
# Operator-side HVNC listener (Linux + Wine64). Do NOT copy the .exe to the implant.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PORT="${HD_PORT:-1337}"

log() { printf '%s\n' "$*"; }
ok()  { log "[+] $*"; }
err() { log "[-] $*" >&2; }
inf() { log "[*] $*"; }

find_exe() {
  local cand
  if [[ -n "${HAVOC_HD_EXE:-}" && -f "${HAVOC_HD_EXE}" ]]; then
    printf '%s\n' "$HAVOC_HD_EXE"
    return 0
  fi
  for cand in \
    "$ROOT/op/hd-op.exe" \
    "$ROOT/bin/hd-op.exe" \
    "$ROOT/bin/HVNC Server.exe" \
    "$ROOT/bin/HVNCServer.exe" \
    "${HOME}/github/havoc-hiddendesktop/bin/HVNC Server.exe" \
    "${HOME}/tools/havoc-hiddendesktop/bin/HVNC Server.exe" \
    "${HOME}/tools/HiddenDesktop/bin/HVNC Server.exe"
  do
    if [[ -f "$cand" ]]; then
      printf '%s\n' "$cand"
      return 0
    fi
  done
  return 1
}

find_wine64() {
  local cand real
  if [[ -n "${WINE64:-}" && -x "${WINE64}" ]]; then
    printf '%s\n' "$WINE64"
    return 0
  fi
  if [[ -n "${WINELOADER:-}" && -x "${WINELOADER}" ]]; then
    printf '%s\n' "$WINELOADER"
    return 0
  fi
  for cand in \
    "$(command -v wine64 2>/dev/null || true)" \
    /usr/lib/wine/wine64 \
    /usr/lib64/wine/wine64 \
    /opt/wine-stable/bin/wine64 \
    /opt/wine-devel/bin/wine64
  do
    if [[ -n "$cand" && -x "$cand" ]]; then
      printf '%s\n' "$cand"
      return 0
    fi
  done
  cand="$(command -v wine 2>/dev/null || true)"
  if [[ -n "$cand" && -x "$cand" ]]; then
    real="$(readlink -f "$cand" 2>/dev/null || printf '%s' "$cand")"
    if grep -q 'wine32=' "$cand" 2>/dev/null || grep -q 'wine32=' "$real" 2>/dev/null; then
      err "found $cand but it is the Debian 32-bit-preferring wrapper"
      err "use wine64 (Debian/Kali: apt install wine64)"
      return 1
    fi
    printf '%s\n' "$cand"
    return 0
  fi
  return 1
}

listening() {
  if [[ -r /proc/net/tcp ]] && awk -v p=$(printf '%04X' "$PORT") '
    NR>1 && $4=="0A" && toupper($2) ~ p"$" { found=1 }
    END { exit found?0:1 }
  ' /proc/net/tcp /proc/net/tcp6 2>/dev/null; then
    return 0
  fi
  ss -lnt 2>/dev/null | grep -qE ":${PORT}\\b" && return 0
  netstat -lnt 2>/dev/null | grep -qE ":${PORT}\\b" && return 0
  return 1
}

inf "probing operator kit"
inf "repo $ROOT"

EXE=""
if EXE="$(find_exe)"; then
  ok "HVNC exe  $EXE"
else
  err "missing HVNC Server.exe"
  err "  looked  $ROOT/bin/HVNC Server.exe"
  err "  looked  $ROOT/op/hd-op.exe"
  err "build: make server    or set HAVOC_HD_EXE="
  exit 1
fi

WINE64_BIN=""
if WINE64_BIN="$(find_wine64)"; then
  ok "wine64    $WINE64_BIN"
else
  err "wine64 not found in PATH"
  err "install:  Debian/Kali  apt install wine64"
  err "          Arch         pacman -S wine"
  err "          Fedora       dnf install wine"
  exit 1
fi

export WINEARCH=win64
export WINEPREFIX="${WINEPREFIX:-$HOME/.wine-hvnc}"
export WINELOADER="$WINE64_BIN"
export WINEDEBUG="${WINEDEBUG:--all}"
export DISPLAY="${DISPLAY:-:0.0}"
mkdir -p "$WINEPREFIX"
ok "DISPLAY   $DISPLAY"
inf "WINEPREFIX $WINEPREFIX"

if listening; then
  ok "already listening on :$PORT"
  exit 0
fi

ok "starting  $WINE64_BIN \"$EXE\""
inf "expect: Starting HVNC Server on Port: $PORT"
cd "$(dirname "$EXE")"
exec "$WINE64_BIN" "$(basename "$EXE")"
