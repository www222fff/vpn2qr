#!/usr/bin/env bash
# Reprint the current OneXray import link + QR code without regenerating keys.
# Usage:
#   sudo bash reprint-link.sh
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "请用 root 运行：sudo bash reprint-link.sh"
  exit 1
fi

XRAY=/usr/local/bin/xray
CONFIG=/usr/local/etc/xray/config.json
NODE_NAME="${NODE_NAME:-VPS-Reality}"

if [ ! -x "$XRAY" ]; then
  echo "找不到 $XRAY，请先运行 install.sh"
  exit 1
fi

if [ ! -f "$CONFIG" ]; then
  echo "找不到 $CONFIG，请先运行 install.sh"
  exit 1
fi

command -v qrencode >/dev/null 2>&1 || apt install -y qrencode >/dev/null

eval "$(python3 - <<'PY'
import json, shlex

with open("/usr/local/etc/xray/config.json", encoding="utf-8") as f:
    cfg = json.load(f)

for inbound in cfg.get("inbounds", []):
    if inbound.get("protocol") != "vless":
        continue
    clients = inbound.get("settings", {}).get("clients", [])
    reality = inbound.get("streamSettings", {}).get("realitySettings", {})
    if not clients or not reality.get("privateKey") or not reality.get("shortIds"):
        continue
    server_names = reality.get("serverNames") or []
    sni = server_names[0] if server_names else "gateway.icloud.com"
    print("UUID=" + shlex.quote(clients[0]["id"]))
    print("PRIVATE=" + shlex.quote(reality["privateKey"]))
    print("SID=" + shlex.quote(reality["shortIds"][0]))
    print("PORT=" + shlex.quote(str(inbound.get("port", 443))))
    print("SNI=" + shlex.quote(sni))
    break
else:
    raise SystemExit("配置里没有可用的 VLESS + REALITY inbound")
PY
)"

PUBLIC_KEY="$("$XRAY" x25519 -i "$PRIVATE" | awk -F': ' 'tolower($1) ~ /password|public/ {print $2; exit}')"
test -n "$PUBLIC_KEY"

PUBLIC_IP="$(curl -4 -fsS --max-time 8 https://ifconfig.me || true)"
if [ -z "$PUBLIC_IP" ]; then
  PUBLIC_IP="$(curl -4 -fsS --max-time 8 https://api.ipify.org || true)"
fi
if [ -z "$PUBLIC_IP" ]; then
  PUBLIC_IP="把这里改成你的VPS公网IP"
fi

LINK="vless://${UUID}@${PUBLIC_IP}:${PORT}?encryption=none&flow=xtls-rprx-vision&security=reality&sni=${SNI}&fp=chrome&pbk=${PUBLIC_KEY}&sid=${SID}&spx=%2F&type=tcp#${NODE_NAME}"

QR_PNG=/root/onexray-reality.png
# UTF8 + 小边距：远程控制台里比 ANSIUTF8 紧凑约一半，便于扫码
qrencode -m 1 -s 4 -o "$QR_PNG" "$LINK"

echo "==================== 手机扫码导入 ===================="
qrencode -m 1 -t UTF8 "$LINK"
echo
echo "VPS IP     : $PUBLIC_IP"
echo "Port       : $PORT"
echo "UUID       : $UUID"
echo "Public Key : $PUBLIC_KEY"
echo "Short ID   : $SID"
echo "SNI        : $SNI"
echo
echo "导入链接（备用）："
echo "$LINK"
echo
echo "二维码图片：$QR_PNG"
echo "======================================================"
