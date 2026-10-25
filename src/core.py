"""VNC/RDP remote desktop sharing planner for SigmaOS-remote-desktop (gliff).

The engine plans desktop-sharing servers (view-only vs interactive), parses a
session store, plans viewer connections and graceful session stops. Passwords
are deliberately never placed on argv (defensive design); spawning servers /
viewers is the thin execute layer that self_test() never runs.
Principles: Defensive Programming, Separation of Concerns, Fail-Fast, KISS.
"""
import argparse, os, re, sys

ENGINE = {
    "name": "sigma-remote",
    "summary": "Plan VNC/RDP desktop sharing sessions and viewer access",
    "language": "python",
    "verbs": ["share-plan", "sessions", "access", "stop-plan"],
    "principles": ["Defensive Programming", "Separation of Concerns",
                   "Fail-Fast", "KISS", "Deterministic Testing"],
}

cli_doc = """\
$ sigma-remote share-plan --port 5901 --mode view-only
x11vnc -display :0 -rfbport 5901 -forever -shared -viewonly -nopw
$ sigma-remote sessions sessions.txt
s1|:0|5901|alice|view-only|1761316800|4242
$ sigma-remote access laptop.local --protocol rdp
xfreerdp /v:laptop.local /port:3389 /cert:ignore
$ sigma-remote stop-plan --pid 4242
kill -INT 4242
"""


class RemoteError(Exception):
    pass


MODES = ("view-only", "interactive")
PROTOCOLS = {"vnc": (5900, "x11vnc", "vncviewer"), "rdp": (3389, "xrdp", "xfreerdp")}
_IFACE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9._-]*$")


# --------------------------------------------------------------------------- #
#  PURE plan / parse layer
# --------------------------------------------------------------------------- #
def _port(value, what="port"):
    try:
        port = int(value)
    except (TypeError, ValueError):
        raise RemoteError(f"{what} must be an integer")
    if not (1 <= port <= 65535):
        raise RemoteError(f"{what} must be 1..65535")
    return port


def share_plan(port=None, display=":0", mode="view-only", protocol="vnc",
               password=False, server=None):
    """Build the sharing-server argv (never embeds the password itself)."""
    if protocol not in PROTOCOLS:
        raise RemoteError(f"unknown protocol {protocol!r} "
                          f"(choose from {', '.join(sorted(PROTOCOLS))})")
    if mode not in MODES:
        raise RemoteError(f"unknown mode {mode!r} (choose from {', '.join(MODES)})")
    if not isinstance(display, str) or not re.match(r"^:\d+(\.\d+)?$", display):
        raise RemoteError(f"bad X display: {display!r} (expected :0)")
    default_port, default_server, _ = PROTOCOLS[protocol]
    port = default_port if port is None else _port(port)
    server = server or default_server
    argv = [server, "-display", display, "-rfbport", str(port),
            "-forever", "-shared"]
    if mode == "view-only":
        argv.append("-viewonly")
    # password auth goes through a file, never through argv
    argv.append("-rfbauth" if password else "-nopw")
    return {"argv": argv, "port": port, "display": display, "mode": mode,
            "protocol": protocol, "password_via": "file" if password else "none"}


def parse_sessions(text):
    """Parse a 'sid|display|port|user|mode|started|pid' session store."""
    sessions, seen = [], set()
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) != 7:
            raise RemoteError(f"line {lineno}: expected 7 |-separated fields")
        sid, display, port, user, mode, started, pid = parts
        if not sid or not re.match(r"^[A-Za-z0-9._-]+$", sid):
            raise RemoteError(f"line {lineno}: bad session id {sid!r}")
        if sid in seen:
            raise RemoteError(f"line {lineno}: duplicate session id {sid!r}")
        seen.add(sid)
        if not display.startswith(":"):
            raise RemoteError(f"line {lineno}: bad display {display!r}")
        if mode not in MODES:
            raise RemoteError(f"line {lineno}: bad mode {mode!r}")
        if not user or not re.match(r"^[A-Za-z0-9._-]+$", user):
            raise RemoteError(f"line {lineno}: bad user {user!r}")
        sessions.append({"sid": sid, "display": display, "port": _port(port),
                         "user": user, "mode": mode,
                         "started": started, "pid": _port(pid, "pid")})
    return sessions


def load_sessions(path):
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as fh:
        return parse_sessions(fh.read())


def save_sessions(path, sessions):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for s in sessions:
            fh.write(f'{s["sid"]}|{s["display"]}|{s["port"]}|{s["user"]}|'
                     f'{s["mode"]}|{s["started"]}|{s["pid"]}\n')


def access_plan(host, port=None, protocol="vnc"):
    """Build the viewer argv to reach a shared desktop."""
    if not isinstance(host, str) or not host.strip() or " " in host:
        raise RemoteError(f"bad host: {host!r}")
    if protocol not in PROTOCOLS:
        raise RemoteError(f"unknown protocol: {protocol!r}")
    default_port, _, viewer = PROTOCOLS[protocol]
    port = default_port if port is None else _port(port)
    if protocol == "vnc":
        argv = [viewer, "-AutoReconnect", f"{host}:{port}"]
    else:
        argv = [viewer, f"/v:{host}", f"/port:{port}", "/cert:ignore",
                "/dynamic-resolution"]
    return {"argv": argv, "host": host, "port": port, "protocol": protocol}


def stop_plan(pid, graceful=True):
    """Plan a session stop: SIGINT by default, SIGTERM when forced."""
    pid = _port(pid, "pid")
    if graceful:
        signal, abbrev = "SIGINT", "INT"
    else:
        signal, abbrev = "SIGTERM", "TERM"
    return {"pid": pid, "signal": signal, "argv": ["kill", f"-{abbrev}", str(pid)]}


# --------------------------------------------------------------------------- #
#  CLI
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog=ENGINE["name"], description=ENGINE["summary"])
    sub = p.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("share-plan", help="build a sharing-server invocation")
    sp.add_argument("--port", type=int, default=None)
    sp.add_argument("--display", default=":0")
    sp.add_argument("--mode", default="view-only", choices=list(MODES))
    sp.add_argument("--protocol", default="vnc", choices=sorted(PROTOCOLS))
    sp.add_argument("--password", action="store_true",
                    help="authenticate via a file (never via argv)")
    ss = sub.add_parser("sessions", help="parse a session store")
    ss.add_argument("file")
    ac = sub.add_parser("access", help="build a viewer invocation")
    ac.add_argument("host")
    ac.add_argument("--port", type=int, default=None)
    ac.add_argument("--protocol", default="vnc", choices=sorted(PROTOCOLS))
    st = sub.add_parser("stop-plan", help="plan a session stop")
    st.add_argument("--pid", type=int, required=True)
    st.add_argument("--force", action="store_true")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.cmd == "share-plan":
            plan = share_plan(args.port, args.display, args.mode,
                              args.protocol, args.password)
            print(" ".join(plan["argv"]))
        elif args.cmd == "sessions":
            for s in load_sessions(args.file):
                print(f'{s["sid"]}  {s["user"]}@{s["display"]} '
                      f'port={s["port"]} {s["mode"]} pid={s["pid"]}')
        elif args.cmd == "access":
            plan = access_plan(args.host, args.port, args.protocol)
            print(" ".join(plan["argv"]))
        elif args.cmd == "stop-plan":
            plan = stop_plan(args.pid, not args.force)
            print(" ".join(plan["argv"]) + f"   # {plan['signal']}")
        return 0
    except (RemoteError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


# --------------------------------------------------------------------------- #
#  Tests (pure plan/parse layer; filesystem use limited to tempfile)
# --------------------------------------------------------------------------- #
SAMPLE_SESSIONS = """\
# active sharing sessions
s1|:0|5901|alice|view-only|1761316800|4242
s2|:1|5902|bob|interactive|1761316900|4300
"""


def self_test() -> None:
    plan = share_plan()
    assert plan["argv"] == ["x11vnc", "-display", ":0", "-rfbport", "5900",
                            "-forever", "-shared", "-viewonly", "-nopw"], plan["argv"]
    assert plan["port"] == 5900
    plan = share_plan(port=5901, mode="interactive", password=True)
    assert "-viewonly" not in plan["argv"] and "-rfbauth" in plan["argv"]
    assert plan["password_via"] == "file"
    plan = share_plan(port=3389, protocol="rdp")
    assert plan["argv"][0] == "xrdp" and "3389" in plan["argv"]
    # defensive: a password must never end up on the argv
    plan = share_plan(password=True)
    assert not any("pass" in a.lower() for a in plan["argv"])
    for bad in ((70000,), (0,), ("x",), (5900, ":0", "root-only"),
                (5900, "0", "view-only"), (5900, ":0", "view-only", "telnet")):
        try:
            share_plan(*bad)
        except RemoteError:
            pass
        else:
            raise AssertionError(f"bad share plan not rejected: {bad!r}")

    sessions = parse_sessions(SAMPLE_SESSIONS)
    assert len(sessions) == 2, sessions
    assert sessions[0]["sid"] == "s1" and sessions[0]["user"] == "alice"
    assert sessions[0]["port"] == 5901 and sessions[0]["pid"] == 4242
    assert sessions[1]["mode"] == "interactive"
    assert parse_sessions("") == []
    for bad in ("s1|:0|5901|alice|view-only|1|1\ns1|:0|5902|bob|view-only|1|2\n",
                "s1|:0|5901|alice|root-only|1|1\n",
                "s1|:0|5901|alice|view-only|1\n",
                "s1|0|5901|alice|view-only|1|1\n",
                "s 1|:0|5901|alice|view-only|1|1\n"):
        try:
            parse_sessions(bad)
        except RemoteError:
            pass
        else:
            raise AssertionError(f"bad session store not rejected: {bad!r}")

    plan = access_plan("laptop.local")
    assert plan["argv"] == ["vncviewer", "-AutoReconnect", "laptop.local:5900"]
    plan = access_plan("work.example.com", 3389, "rdp")
    assert plan["argv"][0] == "xfreerdp" and "/v:work.example.com" in plan["argv"]
    assert "/cert:ignore" in plan["argv"]
    for bad in (("bad host",), ("",), ("h", 70000), ("h", None, "telnet")):
        try:
            access_plan(*bad)
        except RemoteError:
            pass
        else:
            raise AssertionError(f"bad access plan not rejected: {bad!r}")

    assert stop_plan(4242)["argv"] == ["kill", "-INT", "4242"]
    assert stop_plan(4242, graceful=False)["signal"] == "SIGTERM"
    for bad in (0, -1, "abc", 70000):
        try:
            stop_plan(bad)
        except RemoteError:
            pass
        else:
            raise AssertionError(f"bad pid not rejected: {bad!r}")

    import tempfile
    with tempfile.TemporaryDirectory() as d:
        store = os.path.join(d, "sessions")
        assert load_sessions(store) == []            # missing store -> empty
        save_sessions(store, sessions)
        again = load_sessions(store)
        assert [s["sid"] for s in again] == ["s1", "s2"]
        assert again[0] == sessions[0]


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
