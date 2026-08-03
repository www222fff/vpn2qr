#!/usr/bin/env bash
# One-click VLESS + REALITY for mobile OneXray.
# Usage on a fresh Ubuntu/Debian VPS as root:
#   bash install.sh
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "请用 root 运行：sudo bash install.sh"
  exit 1
fi

# ===== defaults (override with env vars) =====
PORT="${PORT:-443}"
SNI="${SNI:-gateway.icloud.com}"
NODE_NAME="${NODE_NAME:-VPS-Reality}"
# ============================================

export DEBIAN_FRONTEND=noninteractive

echo "==> 安装依赖"
apt update
apt install -y curl openssl ca-certificates ufw python3 qrencode

echo "==> 安装 / 更新 Xray"
bash -c "$(curl -L https://github.com/XTLS/Xray-install/raw/main/install-release.sh)" @ install

XRAY=/usr/local/bin/xray
CONFIG=/usr/local/etc/xray/config.json
BACKUP_DIR=/usr/local/etc/xray
BACKUP="${BACKUP_DIR}/config.json.bak.$(date +%Y%m%d-%H%M%S)"

if [ ! -x "$XRAY" ]; then
  echo "找不到 $XRAY，安装失败"
  exit 1
fi

echo "==> 生成 UUID / REALITY 密钥 / Short ID"
UUID="$("$XRAY" uuid)"
KEYPAIR="$("$XRAY" x25519)"
PRIVATE_KEY=$(printf '%s\n' "$KEYPAIR" | awk -F': ' 'tolower($1) ~ /private/ {print $2; exit}')
PUBLIC_KEY=$(printf '%s\n' "$KEYPAIR" | awk -F': ' 'tolower($1) ~ /password|public/ {print $2; exit}')
SHORT_ID=$(openssl rand -hex 8)

test -n "$UUID"
test -n "$PRIVATE_KEY"
test -n "$PUBLIC_KEY"
test -n "$SHORT_ID"

if [ -f "$CONFIG" ]; then
  cp -a "$CONFIG" "$BACKUP"
  echo "已备份旧配置：$BACKUP"
fi

echo "==> 写入配置：$CONFIG"
UUID="$UUID" PRIVATE_KEY="$PRIVATE_KEY" SHORT_ID="$SHORT_ID" PORT="$PORT" SNI="$SNI" \
python3 - <<'PY'
import json, os

cfg = {
  "log": {"loglevel": "warning"},
  "inbounds": [
    {
      "listen": "0.0.0.0",
      "port": int(os.environ["PORT"]),
      "protocol": "vless",
      "tag": "vless-in",
      "settings": {
        "clients": [
          {
            "id": os.environ["UUID"],
            "flow": "xtls-rprx-vision",
            "level": 0,
            "email": "phone"
          }
        ],
        "decryption": "none"
      },
      "streamSettings": {
        "network": "tcp",
        "security": "reality",
        "realitySettings": {
          "show": False,
          "dest": f"{os.environ['SNI']}:443",
          "xver": 0,
          "serverNames": [os.environ["SNI"]],
          "privateKey": os.environ["PRIVATE_KEY"],
          "shortIds": [os.environ["SHORT_ID"]]
        }
      },
      "sniffing": {
        "enabled": True,
        "destOverride": ["http", "tls", "quic"]
      }
    }
  ],
  "outbounds": [
    {"protocol": "freedom", "tag": "direct"},
    {"protocol": "blackhole", "tag": "block"}
  ]
}

with open("/usr/local/etc/xray/config.json", "w", encoding="utf-8") as f:
    json.dump(cfg, f, indent=2)
    f.write("\n")
PY

echo "==> 校验并启动 Xray"
"$XRAY" run -test -config "$CONFIG"
systemctl enable xray
systemctl restart xray
systemctl --no-pager --no-legend status xray | head -n 8

echo "==> 配置防火墙（SSH + ${PORT}/tcp）"
ufw allow OpenSSH >/dev/null 2>&1 || ufw allow 22/tcp >/dev/null 2>&1 || true
ufw allow "${PORT}/tcp" >/dev/null 2>&1 || true
ufw --force enable >/dev/null 2>&1 || true
ufw status || true

PUBLIC_IP="$(curl -4 -fsS --max-time 8 https://ifconfig.me || true)"
if [ -z "$PUBLIC_IP" ]; then
  PUBLIC_IP="$(curl -4 -fsS --max-time 8 https://api.ipify.org || true)"
fi
if [ -z "$PUBLIC_IP" ]; then
  PUBLIC_IP="把这里改成你的VPS公网IP"
fi

LINK="vless://${UUID}@${PUBLIC_IP}:${PORT}?encryption=none&flow=xtls-rprx-vision&security=reality&sni=${SNI}&fp=chrome&pbk=${PUBLIC_KEY}&sid=${SHORT_ID}&spx=%2F&type=tcp#${NODE_NAME}"

QR_PNG=/root/onexray-reality.png
# UTF8 + 小边距：远程控制台里比 ANSIUTF8 紧凑约一半，便于扫码
qrencode -m 1 -s 4 -o "$QR_PNG" "$LINK"

echo
echo "==================== 手机扫码导入 ===================="
qrencode -m 1 -t UTF8 "$LINK"
echo
echo "VPS IP     : $PUBLIC_IP"
echo "Port       : $PORT"
echo "UUID       : $UUID"
echo "Public Key : $PUBLIC_KEY"
echo "Short ID   : $SHORT_ID"
echo "SNI        : $SNI"
echo
echo "导入链接（备用）："
echo "$LINK"
echo
echo "二维码图片：$QR_PNG"
echo "======================================================"
echo
echo "注意：不要把 UUID / Public Key / 链接 / 二维码发到公开聊天。"
echo "验证：手机连接后打开 https://ifconfig.me ，应显示 $PUBLIC_IP"
