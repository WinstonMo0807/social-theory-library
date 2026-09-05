# Cloudflare 1033 连接恢复记录

2026-09-05 15:52。当前为部分缓解，公网仍因无法建立隧道连接而返回 1033，不标记整体修复。

## 实际证据

书库 API/Edge 内网返回 3.0.4，database=true，pending_migrations=0。NAS 的现有 LAN 入口仍为 192.168.5.6:3000、18080、18082。公网 HTTP 530 的正文为 error code: 1033，与先前工作台漏参数的 API 500 是两个问题。

部署的 cloudflared 为 2026.7.3，Go 1.26.4，使用 HTTP/2，容器独立 public_front 网络。现有 image ID 为 41320ce229c5fb52a316a5e3af2e6a1faa32b114aa9e2a5eed0652eff59e8eef，RepoDigest 为 e39ee8da81ad5e05d77f38d2f51c60ca51bf2a8450ac3abab50c17fdb91d91bf。

诊断时 /ready 返回 readyConnections=3，而实际 3 个 TCP 连接 Send-Q=39、lastrecv 约 810 秒、RTO 120 秒、backoff 13–14，持续重传且收不到 ACK。ha_connections=4 不是可达连接证明。对应源码的 readiness 根据连接事件记账，HTTP/2 初始化未启用空闲探测。

NAS 的 DOCKER-USER/UG_FORWARD 与 NAT 规则未发现此次修改造成的拦截。conntrack 为 447/262144，并未耗尽。没有可用的默认 IPv6 路由。主机和容器对多组官方全球/美国 Cloudflare 7844 地址均发生新连接超时，容器到 api.cloudflare.com:443 亦超时。因此仍存在 NAS 外网出站路径问题，不能仅凭现有资料归咎于某台防火墙。

## 已执行的窄范围修改

1. 保存原 compose、镜像 ID、TCP 状态和网络参数到 NAS `storage/backups/cloudflared-stall-20260905-1546`。
2. 确认容器与宿主网络命名空间不同，仅修改容器的 net.ipv4.tcp_retries2 为 8。宿主保持 15。
3. 旧失联连接随后退出，自动重连不再等待默认约 15 分钟。新连接仍受出站超时影响。
4. 在 compose.cloudflare.yaml 持久化该容器参数，并将镜像固定为当前实际 RepoDigest，未升级或替换 cloudflared 程序。
5. 仅重建 cloudflared 使持久配置生效。API、Web、Worker、数据库、索引及 OCR 没有重建或修改；没有降低 TLS 校验、修改凭据、开放端口或扩大防火墙规则。

默认 15 次重试的理论超时下界为 924.6 秒。8 仍满足 Linux 文档列出的至少 100 秒建议。这是失效识别和重连的缓解措施，不会消除实际网络丢包。

## 下一步与回退

需要由用户提供安全的路由器管理会话，继续核对 NAS 192.168.5.6 经网关 192.168.5.1 到 Cloudflare 的出站策略及上游连通性。不要在聊天发送密码。未取得该管理范围前不修改路由器、防火墙或代理配置，不新建隧道或绕开现有访问约束。

若需回退此次配置，将备份的 compose.cloudflare.before.yaml 恢复到原路径，仅重建 cloudflared 即可，或在该容器网络命名空间恢复 tcp_retries2=15。不得回滚书库数据库或应用代码来处理隧道故障。

本轮执行了部署与网络诊断，没有单元、集成、E2E 或书库功能测试。没有验证持续可用性，不将 running、readyConnections 或重启后的短暂成功作为长期恢复证明。

## 依据

- [Cloudflare 1033 官方说明](https://developers.cloudflare.com/support/troubleshooting/http-status-codes/cloudflare-1xxx-errors/error-1033/)
- [Cloudflare 连接超时与所需端口](https://developers.cloudflare.com/tunnel/troubleshooting/)
- [Cloudflared 2026.7.3 HTTP/2 初始化](https://raw.githubusercontent.com/cloudflare/cloudflared/2026.7.3/connection/http2.go)
- [Linux tcp_retries2 文档](https://docs.kernel.org/networking/ip-sysctl.html#tcp-retries2-integer)
