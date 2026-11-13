# 人物引用检查修复 2026-11-11

真实管理员人物合并预览报“人物引用结构已经变化”。源于 ScholarRelation 加入模型后，PROFILE_REFERENCES 未登记 source_scholar、target_scholar 两项。补全登记，保留完整引用覆盖检查、冲突检测、原始资料、历史修订和正常回滚。

验证：41项人物预览、合并、接口权限、回滚测试全部通过。新增双向学者关系保留验证、预览后修改关系拒绝合并验证。旧接口测试补齐既有 X-Editor-Owner 请求头，并保留缺头403断言。运行时只改 person_resolution.py 两行。

19:00:08（北京时间）API-only 发布 4.0.0-20261111-person-scholar-references-r1。使用现行 media-page-budget-r1 的精确镜像基线，本机封装，NAS仅加载；隔离启动384MiB/0.5CPU检查通过。未构建NAS镜像。其他服务容器身份和启动状态保持；API OOM计数0。已核验原备份238460564字节及完整恢复证明；回滚仅恢复API代码，不能把旧数据库覆盖后续策展。

线上管理员预览已正常显示学术关系来源、对象；库恩两人物尚有旧失败发布包及人工字段引用保护，未执行合并。将继续通过书目贡献者管理恢复关联，历史人物留待明确处理。

镜像 sha256:6d282674b3de1aff15ce014fdb0ca1b696743d19fde2c126407ec75b818e083e

文件哈希 {'app/catalog/services/person_resolution.py': '2da34f1c9be803f2003b35440251f6f046eda486fa089665ab4582bd49412792'}
