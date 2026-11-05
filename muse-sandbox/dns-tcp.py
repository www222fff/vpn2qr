#!/usr/bin/env python3
"""TCP DNS forwarder: 127.0.0.1:5353 -> DoH via proxy.
xray DNS uses TCP to avoid UDP blocks.
"""
import socket, ssl, struct, threading, urllib.parse, base64, os, random

def doh_resolve(qname):
    try:
        pu = urllib.parse.urlparse(os.environ.get("HTTPS_PROXY"))
        s = socket.create_connection((pu.hostname, pu.port or 3128), timeout=10)
        auth = "Proxy-Authorization: Basic " + base64.b64encode(f"{pu.username}:{pu.password}".encode()).decode() + "\r\n"
        s.sendall(b"CONNECT dns.google:443 HTTP/1.1\r\nHost: dns.google:443\r\n" + auth.encode() + b"\r\n")
        r = b""
        while b"\r\n\r\n" not in r: r += s.recv(4096)
        if b" 200 " not in r.split(b"\r\n")[0]: return []
        ctx = ssl.create_default_context()
        tls = ctx.wrap_socket(s, server_hostname="dns.google")
        qid = random.randint(0, 65535)
        header = struct.pack(">HHHHHH", qid, 0x0100, 1, 0, 0, 0)
        qname_enc = b"".join(bytes([len(p)]) + p.encode() for p in qname.rstrip(".").split(".")) + b"\x00"
        dns_q = header + qname_enc + struct.pack(">HH", 1, 1)
        req = f"POST /resolve HTTP/1.1\r\nHost: dns.google\r\nContent-Type: application/dns-message\r\nContent-Length: {len(dns_q)}\r\nConnection: close\r\n\r\n".encode() + dns_q
        tls.sendall(req)
        resp = b""
        tls.settimeout(10)
        try:
            while True:
                c = tls.recv(8192)
                if not c: break
                resp += c
        except: pass
        tls.close()
        bi = resp.find(b"\r\n\r\n")
        if bi < 0: return []
        dm = resp[bi+4:]
        ips = []
        try:
            an = struct.unpack(">H", dm[6:8])[0]
            pos = 12
            while dm[pos] != 0: pos += 1 + dm[pos]
            pos += 5
            for _ in range(an):
                if pos+10 > len(dm): break
                if dm[pos] & 0xc0 == 0xc0: pos += 2
                else:
                    while dm[pos] != 0: pos += 1 + dm[pos]
                    pos += 1
                at, ac, ttl, rdlen = struct.unpack(">HHIH", dm[pos:pos+10])
                pos += 10
                if at == 1 and rdlen == 4:
                    ips.append(".".join(str(b) for b in dm[pos:pos+4]))
                pos += rdlen
        except: pass
        return ips
    except:
        return []

def handle(conn):
    try:
        conn.settimeout(15)
        # TCP DNS: 2-byte length prefix
        hdr = conn.recv(2)
        if len(hdr) < 2: return
        ln = struct.unpack(">H", hdr)[0]
        data = b""
        while len(data) < ln:
            c = conn.recv(ln - len(data))
            if not c: return
            data += c
        if len(data) < 12: return
        qid = data[:2]
        pos = 12
        labels = []
        while pos < len(data) and data[pos] != 0:
            ll = data[pos]
            if ll & 0xc0: break
            pos += 1
            labels.append(data[pos:pos+ll].decode())
            pos += ll
        qname = ".".join(labels)
        ips = doh_resolve(qname)
        resp = qid + struct.pack(">HHHHHH", 0x8180, 1, len(ips), 0, 0)
        q_end = pos + 1 + 4
        resp += data[12:q_end]
        for ip in ips:
            resp += struct.pack(">H", 0xc00c) + struct.pack(">HHIH", 1, 1, 300, 4)
            resp += bytes(map(int, ip.split(".")))
        conn.sendall(struct.pack(">H", len(resp)) + resp)
    except: pass
    finally:
        try: conn.close()
        except: pass

srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind(("127.0.0.1", 5353))
srv.listen(16)
print("TCP DNS forwarder on 127.0.0.1:5353", flush=True)
while True:
    c, _ = srv.accept()
    threading.Thread(target=handle, args=(c,), daemon=True).start()
