# 原文关联发布资格修复

2026-11-12 19:14:14（北京时间），API-only curation-source-readiness-r1 已上线。

管理员更新郑杭生与社会转型论的已确认关系时，被提示准确版本未公开。只读核验显示：出处、活动文档修订、文件哈希与公开版本均匹配；原文未失效，文件为 ready/valid，唯一未满足项为全文索引 fulltext_ready=false。

修复仅让 shared_curation 与 relation_source_anchor 的准确原文引用独立于搜索索引完成状态。查询默认继续要求索引完成，访问权限、准确文档修订、文件哈希、页序和文字定位校验保持。没有更新数据库完成标志。

本机33项定向检查通过：test_curation_registered_sources_20261110.py、test_stl4_person_node_sources_20261024.py、test_v307_shared_curation.py。覆盖索引完成/未完成的学者、理论、主题原文发布，登录权限、错误版本、文字变化、页码偏移、失效及哈希变更。隔离镜像 manage.py check 通过。

镜像 social-theory-library-api:4.0.0-20261112-curation-source-readiness-r1，ID sha256:a35a867e3f39c9077630eb204367201a1a8c1a6e1a7ac611efdaffa36088a1f8。基线为线上 placement-reader-access-r3，仅替换3个文件；没有并入引用格式或检索布局候选。线上文件哈希、健康检查通过，其他容器配置/身份/启动状态保持，OOM 0。

原恢复档案238460564字节已重新核对SHA256，恢复时仅回退API代码，不用旧数据库覆盖新策展。没有启动OCR、恢复旧模型、构建NAS镜像或执行完整compose up。

发布脚本与结果：tmp/curation-source-readiness-20261112。浏览器正在进行原阻断操作的实际复核，结果另追加。

浏览器复核：郑杭生→社会转型论原关系通过确认更新，准确B055 PDF6引用保留；公开理论页已显示精简说明，原阻断已解除。
