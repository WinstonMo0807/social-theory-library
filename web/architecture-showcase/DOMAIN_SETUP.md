# preview.winstonmo.com 接入说明

公开版服务已在 NAS 启动并通过 HTTP 检查。域名尚未接入；用户选择稍后自行配置 Cloudflare。

## 在 Cloudflare 添加路由

进入 **Networking → Tunnels**，选择当前承载 `books.winstonmo.com` 的隧道。在 **Routes → Add route → Published application** 中添加一条路由，不替换已有的书库路由。当前操作名称依据 [Cloudflare 官方说明](https://developers.cloudflare.com/tunnel/get-started/)。

| 配置项 | 填写值 |
| --- | --- |
| Subdomain | `preview` |
| Domain | `winstonmo.com` |
| Path | 留空 |
| Service Type | `HTTP` |
| Service URL | `stl-architecture-showcase:5196` |
| HTTP Host Header，如展开 HTTP 设置 | `preview.winstonmo.com` |

服务的完整地址为 `http://stl-architecture-showcase:5196`。这是现有隧道所在 Docker 网络中的服务名，无需开放 NAS 或路由器端口。只添加这一条演示路由。演示域名不能指向书库 API 或管理服务。

通过控制台新增路由时，Cloudflare 会创建指向隧道的 DNS 记录。详见官方[路由说明](https://developers.cloudflare.com/tunnel/concepts/routing/)。若已有同名 DNS 记录导致冲突，先核对其用途，再处理该记录，不改动其他域名。

保存后打开 <https://preview.winstonmo.com/>。应直接看到自动展示，不要求密码。若遇到 403，核对 HTTP Host Header；若遇到 502，核对服务名、端口和容器健康状态。当前仅验证了隧道网络到源站的 HTTP 200，未验证公网 TLS、DNS 或 Cloudflare 路由。

## 服务与恢复

NAS 目录为 `/volume2/library/stl-previews/architecture-showcase-v4-20261106`，容器名为 `stl-architecture-showcase`，镜像为 `stl-architecture-showcase:v4-20261106`。

服务使用只读文件系统、非 root 用户，无业务数据挂载，无宿主机端口，复用现有隧道网络。目录中保留公开成品、构建配置和 `deployment-proof.json`。恢复运行可在该目录执行：

```sh
sudo docker compose -p stl-architecture-showcase -f compose.public.yaml up -d --pull never
```

如需暂停公开演示，先停用新增的 `preview.winstonmo.com` 路由，再停止独立容器：

```sh
sudo docker stop stl-architecture-showcase
```

不需要修改或重启原书库、数据库及隧道。未执行删除操作，发布目录、镜像和 v3 本机备份均保留。
