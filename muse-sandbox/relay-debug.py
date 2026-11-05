#!/usr/bin/env python3
"""Debug relay with byte counting in both directions."""
import os, socket, select, threading, urllib.parse, base64, time

LISTEN_HOST = "127.0.0.1"
LISTEN_PORT = 17844
TARGET_HOST = "198.41.192.47"
TARGET_PORT = 7844

proxy_url = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
pu = urllib.parse.urlparse(proxy_url)
proxy_host, proxy_port = pu.hostname, pu.port or 3128
auth = ""
if pu.username:
    creds = f"{pu.username}:{pu.password or ''}"
    auth = "Proxy-Authorization: Basic " + base64.b64encode(creds.encode()).decode() + "\r\n"

stats = {"up": 0, "down": 0, "conns": 0}
stats_lock = threading.Lock()

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

def handle(client):
    with stats_lock:
        stats["conns"] += 1
        cid = stats["conns"]
    log(f"conn#{cid}: new client")
    try:
        p = socket.create_connection((proxy_host, proxy_port), timeout=15)
        p.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        client.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        req = (f"CONNECT {TARGET_HOST}:{TARGET_PORT} HTTP/1.1\r\n"
               f"Host: {TARGET_HOST}:{TARGET_PORT}\r\n{auth}\r\n")
        p.sendall(req.encode())
        resp = b""
        p.settimeout(15)
        while b"\r\n\r\n" not in resp:
            chunk = p.recv(4096)
            if not chunk:
                raise OSError("proxy closed")
            resp += chunk
        if b" 200 " not in resp.split(b"\r\n", 1)[0]:
            raise OSError(f"CONNECT failed: {resp[:60]!r}")
        log(f"conn#{cid}: CONNECT ok")
        p.settimeout(None)
        client.settimeout(None)
        up_bytes = 0
        down_bytes = 0
        socks = [client, p]
        last_log = time.time()
        while socks:
            r, _, _ = select.select(socks, [], [])
            for src in r:
                dst = p if src is client else client
                try:
                    data = src.recv(65536)
                except OSError as e:
                    log(f"conn#{cid}: recv error {e}")
                    data = b""
                if not data:
                    log(f"conn#{cid}: EOF from {'client' if src is client else 'edge'}, up={up_bytes} down={down_bytes}")
                    try: dst.shutdown(socket.SHUT_WR)
                    except: pass
                    socks.remove(src)
                    try: src.close()
                    except: pass
                else:
                    if src is client:
                        up_bytes += len(data)
                    else:
                        down_bytes += len(data)
                    try:
                        dst.sendall(data)
                    except OSError as e:
                        log(f"conn#{cid}: send error {e}")
                        socks = []
                        break
            # periodic stats
            if time.time() - last_log > 10:
                log(f"conn#{cid}: up={up_bytes} down={down_bytes}")
                last_log = time.time()
        with stats_lock:
            stats["up"] += up_bytes
            stats["down"] += down_bytes
        log(f"conn#{cid}: closed, up={up_bytes} down={down_bytes}")
    except Exception as e:
        log(f"conn#{cid}: ERROR {e}")
    finally:
        try: client.close()
        except: pass
        try: p.close()
        except: pass

def main():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((LISTEN_HOST, LISTEN_PORT))
    srv.listen(32)
    log(f"debug relay on {LISTEN_HOST}:{LISTEN_PORT}")
    while True:
        c, _ = srv.accept()
        threading.Thread(target=handle, args=(c,), daemon=True).start()

if __name__ == "__main__":
    main()
