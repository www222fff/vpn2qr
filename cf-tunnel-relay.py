#!/usr/bin/env python3
"""Fixed relay: non-blocking sockets with proper read/write select."""
import os, socket, select, threading, urllib.parse, base64, time, collections

LISTEN_HOST = "127.0.0.1"
LISTEN_PORT = 17844
TARGET_HOST = "198.41.192.47"
TARGET_PORT = 7844

pu = urllib.parse.urlparse(os.environ.get("HTTPS_PROXY"))
proxy_host, proxy_port = pu.hostname, pu.port or 3128
auth = ""
if pu.username:
    auth = "Proxy-Authorization: Basic " + base64.b64encode(f"{pu.username}:{pu.password}".encode()).decode() + "\r\n"

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

def handle(client):
    try:
        p = socket.create_connection((proxy_host, proxy_port), timeout=15)
        req = (f"CONNECT {TARGET_HOST}:{TARGET_PORT} HTTP/1.1\r\n"
               f"Host: {TARGET_HOST}:{TARGET_PORT}\r\n{auth}\r\n")
        p.sendall(req.encode())
        resp = b""
        p.settimeout(15)
        while b"\r\n\r\n" not in resp:
            c = p.recv(4096)
            if not c: raise OSError("proxy closed")
            resp += c
        if b" 200 " not in resp.split(b"\r\n", 1)[0]:
            raise OSError("CONNECT failed")
        # Non-blocking for select-based forwarding
        client.setblocking(False)
        p.setblocking(False)
        # Buffers for pending outgoing data
        buf_c2p = collections.deque()  # client -> proxy
        buf_p2c = collections.deque()  # proxy -> client
        while True:
            rlist = []
            wlist = []
            # Always read from both if we can buffer
            rlist = [client, p]
            # Write to proxy if we have buffered client data
            if buf_c2p: wlist.append(p)
            # Write to client if we have buffered proxy data
            if buf_p2c: wlist.append(client)
            r, w, _ = select.select(rlist, wlist, [], 60)
            if not r and not w:
                continue
            for src in r:
                try:
                    data = src.recv(65536)
                except BlockingIOError:
                    continue
                except OSError:
                    data = b""
                if not data:
                    return  # EOF, close connection
                if src is client:
                    buf_c2p.append(data)
                else:
                    buf_p2c.append(data)
            for dst in w:
                try:
                    if dst is p and buf_c2p:
                        data = buf_c2p.popleft()
                        sent = dst.send(data)
                        if sent < len(data):
                            buf_c2p.appendleft(data[sent:])
                    elif dst is client and buf_p2c:
                        data = buf_p2c.popleft()
                        sent = dst.send(data)
                        if sent < len(data):
                            buf_p2c.appendleft(data[sent:])
                except BlockingIOError:
                    # Put it back
                    if dst is p: buf_c2p.appendleft(data)
                    else: buf_p2c.appendleft(data)
                except OSError:
                    return
    except Exception as e:
        log(f"relay error: {e}")
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
    log(f"fixed relay on {LISTEN_HOST}:{LISTEN_PORT}")
    while True:
        c, _ = srv.accept()
        threading.Thread(target=handle, args=(c,), daemon=True).start()

if __name__ == "__main__":
    main()
