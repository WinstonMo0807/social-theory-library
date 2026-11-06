# 编目可空日期修复

管理员编辑《中国国家治理的制度逻辑》时，纠正错误的自动出版年份，并清空未知的具体出版日期。HTML日期输入清空后发送空字符串，原API的可空DateField仍返回格式错误，导致整页无法保存。

WorkflowSectionSerializer将可空日期字段的空字符串转换为null。有效日期、无效日期和出版年份一致性校验保持。新增3项回归检查通过。真实管理员页面现已保存2017年、空具体日期和三联出版信息；截图位于F:/书库策展/策展工作区/编目修复-20261107/date-save-verified.png。

API镜像4.0.0-20261107-catalog-date-r1，sha256:d191647b56767340f9d2007b81e2d5bc46c202e82bbe3579e7707d16f56d2736，基于运行upload-r5镜像，仅覆盖workflow_serializers.py。文件SHA256为99b1bfdf227c1b174f72b2092e8aaa6fb11ee333d63b87fd6cf0636105766de0。只重建API，其他24个容器身份和启动时间一致，edge配置检查并平滑重载。无数据库迁移。

恢复资料在NAS /volume2/library/stl-releases/20261107-catalog-date-r1/recovery-r2，保存旧镜像、准确Compose命令、配置与数据库备份。备份20260182字节，pg_restore --list通过；本次未单独恢复数据库。回退仅使用旧API及配置，不能以备份覆盖新增策展数据。正式public/compose-command.json已追加本次API专用覆盖文件。后续API发布必须保留此修复，并以当前准确Compose和运行镜像为基线。

编目保存后确认本节出现一次409版本冲突，正在核对版本返回和后台处理更新；日期保存问题已经实测解决，409不计为已解决。
