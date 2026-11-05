# Muse Sandbox Helpers

Helper scripts for running network services (xray, etc.) inside the Muse sandbox VM.

## Sandbox network environment

The sandbox has a restricted network environment:

1. **Outbound via HTTP proxy only** — `HTTPS_PROXY` env var. The proxy password
   **rotates every few minutes**, so any long-lived process holding credentials will expire.
2. **Fake system DNS** — the sandbox resolver (198.19.0.1) returns fake `198.18.x.x`
   addresses for all queries. UDP DNS is blocked.
3. **cloudflared can't dial out directly** — it doesn't use the HTTP proxy and can't
   resolve `argotunnel` SRV records through the fake DNS.
4. **TLS interception** — the egress proxy MITMs HTTPS, presenting certificates signed
   by `CN = Hatch Sandbox Egress CA, O = Hatch` instead of the real site certs.
   Clients must either trust this CA or use plain HTTP.
5. **Processes get OOM-killed** — background processes may be SIGKILLed at random;
   every component needs a liveness check / supervisor.

## Scripts

| Script | Listens on | Purpose |
|---|---|---|
| `proxy-fwd.py` | 127.0.0.1:3129 | Forwarder to the egress proxy. Reads fresh `HTTPS_PROXY` credentials on **every** connection. Handles both `CONNECT` (HTTPS) and plain HTTP (injects `Proxy-Authorization` + browser `User-Agent`). xray's outbound points here via `http` protocol. |
| `cred-monitor.py` | — | Restarts `proxy-fwd.py` every 60s so it picks up rotated credentials. |
| `dns-tcp.py` | 127.0.0.1:5353 | TCP DNS forwarder. Resolves via DoH (`POST https://dns.google/resolve` through the egress proxy) because UDP is blocked and system DNS lies. xray config: `"dns": {"servers": ["tcp://127.0.0.1:5353"]}` (the `tcp://` prefix is required — bare `ip:port` fails to parse). |
| `cf-tunnel-relay.py` | 127.0.0.1:17844 | Relay for cloudflared's edge connection through the HTTP proxy (`CONNECT edge:7844`). cloudflared runs with `--edge 127.0.0.1:17844 --protocol http2`. |

## Usage

```bash
python3 dns-tcp.py &          # DNS
python3 proxy-fwd.py &        # egress forwarder (or use cred-monitor)
python3 cred-monitor.py &     # keep forwarder credentials fresh
python3 cf-tunnel-relay.py &  # cloudflare edge relay
./cloudflared tunnel --protocol http2 --edge 127.0.0.1:17844 \
    run --token $TOKEN --url http://127.0.0.1:10000
```

xray `config.json` needs:

```json
"dns": { "servers": ["tcp://127.0.0.1:5353"] }
```

and the `direct` outbound using `http` protocol to `127.0.0.1:3129` (no auth).

Tunnel health check: `curl https://<your-domain>/` → `404` = tunnel + xray OK;
`530` = cloudflared/relay down; `502` = xray down. The Cloudflare DNS CNAME for
the tunnel **must be Proxied** (DNS-only registers fine but forwards zero traffic).

## Retrospective — 2026-11-05 xray debugging (3h voice session)

Goal: run xray (VLESS+WS+TLS) in the sandbox, expose via Cloudflare Tunnel
(`xray.hashneuron.space`), connect from iPhone OneXray client.

**What we fixed, in order:**

1. cloudflared couldn't reach Cloudflare edge → wrote `cf-tunnel-relay.py`.
2. Tunnel CNAME was DNS-only → switched to Proxied, traffic started flowing.
3. Egress proxy password rotation → wrote `proxy-fwd.py` + `cred-monitor.py`.
4. Fake system DNS → wrote `dns-tcp.py` (DoH via proxy).

**Where we went wrong:**

- After (4), the phone showed "VLESS handshake OK, but no IP / tiny heartbeat traffic".
  I blamed DNS, then blamed "the sandbox blocking return packets at the NIC layer".
  **Both were guesses with no evidence.** The user called this out.
- The actual root cause (found later by re-reading code instead of guessing):
  `proxy-fwd.py` had **died silently** — its `except: pass` swallowed the exception.
  xray's outbound was hitting a dead port. Handshake worked (inbound path fine),
  but every outbound dial failed. Restarting the forwarder fixed it immediately.
- Lesson: when the symptom is "request arrives but nothing comes back", check
  whether the **outbound path process is alive** before theorizing about the network.
  And never ship `except: pass` in infrastructure code — log the error.

**Still open:**

- Egress TLS MITM (`Hatch Sandbox Egress CA`): clients must trust the CA
  (cert exported from `/usr/local/share/ca-certificates/hatch-egress-ca.crt`)
  or use plain HTTP for testing.
- Long-term stability of the whole chain in the sandbox is unproven;
  Railway/VPS was proposed twice and declined — revisit if flakiness persists.

**Debugging discipline agreed with the user:**

- Don't give up / don't declare the environment at fault without evidence.
- Test locally and confirm before reporting success.
- When challenged, bring measured evidence, not speculation.
- Admit wrong conclusions fast and precisely ("I retract X, the evidence shows Y").
