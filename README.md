# xray-onexray-reality

在 Ubuntu / Debian VPS 上一键搭建 **VLESS + REALITY**，给手机 **OneXray** 使用。

默认：

- 端口：`443`
- 伪装域名（SNI）：`gateway.icloud.com`
- Flow：`xtls-rprx-vision`
- 安装后直接在终端显示二维码，手机扫码导入

## 快速开始

SSH 登录 VPS（root）：

```bash
ssh root@你的VPS公网IP
```

### 推荐：一条命令安装（不用 clone）

```bash
curl -fsSL https://raw.githubusercontent.com/www222fff/xray-onexray-reality/main/install.sh | bash
```

安装成功后：

1. 终端会打印二维码  
2. 打开手机 OneXray → 扫码导入  
3. 连接后打开 `https://ifconfig.me`，应显示 VPS 公网 IP  

### 备选：clone 后安装

```bash
apt update && apt install -y git
git clone https://github.com/www222fff/xray-onexray-reality.git
cd xray-onexray-reality
bash install.sh
```

### 备选：先下载再执行

```bash
curl -fsSL -o install.sh https://raw.githubusercontent.com/www222fff/xray-onexray-reality/main/install.sh
bash install.sh
```

## 重新打印链接 / 二维码

不重装、不更换密钥：

```bash
bash reprint-link.sh
```

## 可选参数

安装前可覆盖默认值：

```bash
PORT=443 SNI=gateway.icloud.com NODE_NAME=MyPhone bash install.sh
```

说明：

| 变量 | 默认值 | 含义 |
|------|--------|------|
| `PORT` | `443` | 监听端口 |
| `SNI` | `gateway.icloud.com` | REALITY 伪装域名 |
| `NODE_NAME` | `VPS-Reality` | 客户端节点名称 |

不建议再使用 `www.microsoft.com`：部分环境下证书握手过大，可能导致 REALITY 失败。

## OneXray 手动核对

若扫码失败，可手动填写：

| 字段 | 值 |
|------|----|
| Protocol | VLESS |
| Address | VPS 公网 IP |
| Port | `443` |
| UUID | 脚本输出 |
| Encryption | none |
| Flow | `xtls-rprx-vision` |
| Network | tcp / raw |
| Security | reality |
| SNI | `gateway.icloud.com` |
| Fingerprint | `chrome` |
| Public Key | 脚本输出 |
| Short ID | 脚本输出 |
| SpiderX | `/` |
| Allow insecure | 关闭 |
| mldsa65Verify | 留空 |

## 常用检查

```bash
systemctl is-active xray
ss -lntp | grep ':443 '
journalctl -u xray -n 50 --no-pager
```

## 安全提醒

- 脚本每次安装都会生成新的 UUID / 密钥，**不要**把真实密钥、导入链接、二维码提交到 Git 或发到公开聊天
- 仅供个人学习与自用，请遵守当地法律及服务商条款
- 仓库内不包含任何真实节点凭据

## 文件说明

| 文件 | 作用 |
|------|------|
| `install.sh` | 安装 Xray、写入 REALITY 配置、开防火墙、打印二维码 |
| `reprint-link.sh` | 根据当前配置重新打印导入链接和二维码 |
| `README.md` | 使用说明 |
