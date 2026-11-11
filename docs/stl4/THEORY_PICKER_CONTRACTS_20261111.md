# 理论编辑器子学科与主题选取修复

2026-11-11 策展管理员在功能主义人类学条目输入子学科和主题时，界面报告缺少 `maintenance_theory_nodes.subdiscipline_links` / `topic_links` 的 ResearchFieldContract。

调用链为 theory-system-admin → ResearchEntityPicker → entity-discovery → resolve_contract。前端已有两个字段，后台契约登记遗漏。沿原登记表增加两项 entity_list；仅允许相应实体类型，仍需管理员权限，选取只进入草稿，未放宽写入或发布权限。

验证：`DATABASE_URL=sqlite:///:memory: DJANGO_DEBUG=true ../.venv/Scripts/python.exe -m pytest tests/test_universal_entity_admin_inputs_v292.py -q -p no:cacheprovider`，8 项通过。两项新增用例核验既有子学科/主题可发现、结果只允许查看及加入草稿、不持久化候选、拒绝跨类型请求。首次运行因测试名称与初始化学科重名而失败，改用独立测试名称后通过。

公网 API-only 于 2026-11-11 19:27:50 +08:00 切换至 `4.0.0-20261111-theory-picker-contracts-r1`，镜像 `sha256:cd462adf1a8ae6c823d758542795fddce74423ca7f8017660f5f1eab30a08638`。保留上一版人物关系引用修复。运行文件哈希、ready 200、其他容器身份与启动时间一致，API OOM 0；本机打包，NAS 仅 load，未迁移或重启任务角色。

部署记录在 `tmp/theory-picker-contracts-20261111/`。NAS 恢复点位于同名 release 的 recovery-code-only；回退仅 API 镜像，不回滚数据库覆盖后续策展。复核既有 238460564 字节完整恢复包 SHA-256 `9b190f71d450c1852e7a19a12813966063b7a8996bede336dfe1ac25a9cdb7d0`。

实际管理员界面已恢复两个选择器，并选入礼物交换与社会关系主题及经济人类学子学科，保存成功。条目公开回读继续随策展进行。
