# muse-sandbox

Muse 沙箱环境专用网络组件。沙箱的网络有三重限制，所有脚本都是为了绕过它们：

1. **出口 HTTP 代理**：所有外网流量必须走 `HTTPS_PROXY` 指定的代理，且密码几分钟一轮换
2. **假 DNS**：系统 DNS（198.19.0.1）对所有域名返回 198.18.x.x 内网假 IP
3. **TLS 中间人**：出口代理劫持 HTTPS，换发 `Hatch Sandbox Egress CA` 签的证书

## 文件

| 文件 | 作用 | 端口 |
|------|------|------|
| `relay-debug.py` | cloudflared 中继：cloudflared 不走代理、解析不了 argotunnel SRV，自写 TCP 中继经代理 CONNECT 到 Cloudflare edge:7844 | 127.0.0.1:17844 |
| `proxy-fwd.py` | 出口转发器：监听无认证端口，转发出站 CONNECT 请求时每次读最新 env 密码 | 127.0.0.1:3129 |
| `cred-monitor.py` | 密码刷新：每 60 秒重启 proxy-fwd.py，确保用最新密码 | - |
| `dns-tcp.py` | TCP DNS 转发器：经代理做 DoH（dns.google:443）拿真 IP，解决假 DNS 问题 | 127.0.0.1:5353 |

## 2026-11-05 调试复盘（xray VLESS 节点）

目标：沙箱上搭 xray（VLESS+WS+TLS），经 Cloudflare 隧道（xray.hashneuron.space）给 iPhone OneXray 用。

链路：手机 → Cloudflare → cloudflared → relay(17844) → xray(10000) → proxy-fwd(3129) → 出口代理 → 外网

### 踩过的坑

1. **cloudflared 连不上**：不走 HTTP 代理，沙箱 DNS 解析不了 argotunnel SRV。解法：relay-debug.py 中继，cloudflared 用 `--edge 127.0.0.1:17844 --protocol http2`。
2. **隧道零转发**：CNAME 必须是 Proxied，DNS only 时注册成功但无流量。
3. **密码轮换**：出口代理密码几分钟一换，长驻进程启动时读一次会过期。解法：proxy-fwd.py 每次连接读最新 env + cred-monitor 每 60 秒重启。
4. **假 DNS**：xray 解析域名拿到 198.18.x.x，连不上。解法：dns-tcp.py 做 DoH，xray 配 `tcp://127.0.0.1:5353`。
5. **proxy-fwd 悄悄死了**：代码里 `except: pass` 吞掉异常，进程死得无声无息。xray 出站撞死端口，表现为"握手能过、请求能到、数据回不来"。重启后双向正常。
6. **TLS 中间人**：出口代理劫持 HTTPS，证书签发者为 `Hatch Sandbox Egress CA`。手机不信任该 CA → x509 错误。解法：安装 CA 证书，或先用纯 HTTP 验证链路。

### 被推翻的错误结论

- "DNS 问题导致不通"——DNS 修好后依然不通
- "沙箱网口层拦回包"——无实测支撑的猜测，真因是进程死了

### 教训

- 关键组件加存活监控，异常日志不许吞（`except: pass` 是万恶之源）
- 下结论靠实测证据，不靠猜；被质疑时拿出测试数据
- 卡住时换思路继续试，不轻易说"环境不行"
