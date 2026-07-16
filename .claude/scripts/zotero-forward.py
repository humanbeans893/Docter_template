"""WSL2 -> Windows Zotero local-API port forwarder.

Forwards localhost:23119 to the Windows host gateway so that
pyzotero (which hardcodes 127.0.0.1:23119) can reach the Zotero
desktop app running on the Windows side.
"""

import argparse
import select
import socket
import subprocess
import sys
import threading


def get_windows_gateway() -> str:
    """Get the Windows host IP from the default route."""
    result = subprocess.run(
        ["ip", "route", "show", "default"],
        capture_output=True,
        text=True,
        check=True,
    )
    # e.g. "default via 172.30.224.1 dev eth0"
    fields = result.stdout.split()
    assert len(fields) >= 3 and fields[0] == "default" and fields[1] == "via", (
        f"Unexpected default route: {result.stdout!r}"
    )
    return fields[2]


def forward(src: socket.socket, dst: socket.socket) -> None:
    try:
        while True:
            r, _, _ = select.select([src], [], [], 1.0)
            if r:
                data = src.recv(65536)
                if not data:
                    break
                dst.sendall(data)
    except (ConnectionError, OSError) as exc:
        print(f"Zotero forwarding connection closed: {exc}", file=sys.stderr, flush=True)
    finally:
        for s in (src, dst):
            try:
                s.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            s.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=23119, help="Zotero API port")
    parser.add_argument("--gateway", help="Windows host address (auto-detected by default)")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    assert 1 <= args.port <= 65535, f"Invalid port: {args.port}"
    port = args.port
    gateway = args.gateway or get_windows_gateway()

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        server.bind(("127.0.0.1", port))
    except OSError as e:
        if e.errno == 98:  # Address already in use
            print(f"Port {port} already in use — forwarder is already running.", flush=True)
            sys.exit(0)
        raise
    server.listen(5)
    print(f"Forwarding localhost:{port} -> {gateway}:{port}", flush=True)

    while True:
        client, _ = server.accept()
        remote = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        remote.settimeout(10)
        remote.connect((gateway, port))
        remote.settimeout(None)
        threading.Thread(target=forward, args=(client, remote), daemon=True).start()
        threading.Thread(target=forward, args=(remote, client), daemon=True).start()


if __name__ == "__main__":
    main()
