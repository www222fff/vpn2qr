#!/usr/bin/env python3
"""Local proxy forwarder: 127.0.0.1:3129 (no auth) -> egress proxy (with current auth).
xray connects to 127.0.0.1:3129 without credentials.
This forwarder reads HTTPS_PROXY env var at startup for the current credentials.
Restart this (not xray) when credentials rotate.
"""
import os, socket, select, threading, urllib.parse, base64

def get_proxy():
    # Read fresh credentials on EVERY connection (they rotate frequently)
    pu = urllib.parse.urlparse(os.environ.get("HTTPS_PROXY"))
    auth = "Proxy-Authorization: Basic " + base64.b64encode(f"{pu.username}:{pu.password}".encode()).decode() + "\r\n"
    return pu.hostname, pu.port or 3128, auth

def handle(client):
    try:
        # Connect to real proxy first (fresh credentials each connection)
        ph, pp, auth = get_proxy()
        p = socket.create_connection((ph, pp), timeout=10)
        # Read the request from xray
        req = b""
        client.settimeout(10)
        while b"\r\n\r\n" not in req:
            c = client.recv(4096)
            if not c: return
            req += c
        # Parse request line: CONNECT host:port or GET http://host/path
        line = req.split(b"\r\n")[0].decode()
        parts = line.split()
        method, raw_target = parts[0], parts[1]
        if method.upper() == "CONNECT":
            target = raw_target  # e.g. example.com:443
            upstream_req = None  # CONNECT is built below
        else:
            # Plain HTTP: absolute-URI form, forward request as-is with auth injected
            u = urllib.parse.urlparse(raw_target)
            target = u.netloc or u.path.split("/")[0]
            if ":" not in target:
                target += ":80"
            # Inject Proxy-Authorization + UA into the header block
            head, _, body = req.partition(b"\r\n\r\n")
            headers = head.split(b"\r\n")
            if not any(h.lower().startswith(b"proxy-authorization:") for h in headers):
                headers.insert(1, auth.strip().encode())
            if not any(h.lower().startswith(b"user-agent:") for h in headers):
                headers.insert(1, b"User-Agent: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
            upstream_req = b"\r\n".join(headers) + b"\r\n\r\n" + body
        # Forward request: CONNECT for TLS, original request for plain HTTP
        ua = "User-Agent: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36\r\n"
        if upstream_req is None:
            p.sendall(f"CONNECT {target} HTTP/1.1\r\nHost: {target}\r\n{ua}{auth}\r\n".encode())
        else:
            p.sendall(upstream_req)
        resp = b""
        p.settimeout(10)
        while b"\r\n\r\n" not in resp:
            c = p.recv(4096)
            if not c: raise OSError("proxy closed")
            resp += c
        # Send response back to xray
        client.sendall(resp)
        # CONNECT requires 200; plain HTTP forwards whatever the origin returned
        if upstream_req is None and b" 200 " not in resp.split(b"\r\n")[0]:
            return
        # Bidirectional forward
        client.settimeout(None); p.settimeout(None)
        socks = [client, p]
        while socks:
            r, _, _ = select.select(socks, [], [])
            for src in r:
                dst = p if src is client else client
                d = src.recv(65536)
                if not d:
                    try: dst.shutdown(socket.SHUT_WR)
                    except: pass
                    socks.remove(src)
                else:
                    dst.sendall(d)
    except Exception as e:
        print(f"[proxy-fwd] error: {e}", flush=True)
    finally:
        try: client.close()
        except: pass
        try: p.close()
        except: pass

srv = socket.socket()
srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind(("127.0.0.1", 3129))
srv.listen(32)
print("proxy forwarder on 127.0.0.1:3129", flush=True)
while True:
    c, _ = srv.accept()
    threading.Thread(target=handle, args=(c,), daemon=True).start()
