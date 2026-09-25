#!/usr/bin/env python3
"""TCP proxy: expose host's localhost-only Ollama on the docker bridge gateway.

Listens on 0.0.0.0:<listen_port> and forwards to 127.0.0.1:<target_port>.
Containers on an --internal docker network reach it via the bridge gateway IP.
"""
import argparse
import socket
import threading


def pipe(a, b):
    try:
        while True:
            data = a.recv(65536)
            if not data:
                break
            b.sendall(data)
    except OSError:
        pass
    finally:
        for s in (a, b):
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                s.close()
            except OSError:
                pass


def handle(client, target, target_port):
    client.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
    try:
        upstream = socket.create_connection((target, target_port), timeout=10)
    except OSError:
        client.close()
        return
    # create_connection leaves its 10s timeout on the socket, which would kill
    # any connection idle longer than that between bytes. A slow model doing
    # prompt eval on CPU/GPU offload can pause for minutes, so the relay must
    # not have a read/write deadline. Keep only the connect timeout.
    upstream.settimeout(None)
    threading.Thread(target=pipe, args=(client, upstream), daemon=True).start()
    threading.Thread(target=pipe, args=(upstream, client), daemon=True).start()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--listen", default="0.0.0.0")
    ap.add_argument("--listen-port", type=int, default=11435)
    ap.add_argument("--target", default="127.0.0.1")
    ap.add_argument("--target-port", type=int, default=11434)
    args = ap.parse_args()

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((args.listen, args.listen_port))
    srv.listen(512)
    print(f"proxy {args.listen}:{args.listen_port} -> {args.target}:{args.target_port}", flush=True)
    while True:
        client, _ = srv.accept()
        threading.Thread(target=handle, args=(client, args.target, args.target_port), daemon=True).start()


if __name__ == "__main__":
    main()
