# M31/M32 内容编排与共享选书接续

2026-10-23，M29代码检查点a92c85c后定位。M31/M32未改源码，不计新增完成。

唯一final-r2的173、176、177已实际查看。174/175/178/179已提取至tmp/pdfs/stl4-final-m31-m32-20261023但未查看。M31要求文字列表/当前条目/公共预览三栏，分组、选择、多选跨组移动、上下排序、当前/草稿/未保存区分、本页推荐理由与显示字段、版本与修改清单、撤销/恢复，编辑公共书目需明确转原馆藏；M32要求共用馆藏搜索筛选、作品/准确版本选择、已选列表、分组目标、本页对外理由与内部预期收获、移动选中栏。

已定位：api/catalog/services/content_placements.py和content_placement_views.py支持九类页面、原EditorialRevision与AuditEvent命令/恢复/发布。前面已读source/normalize开头，后半render/read/apply与共享发布投影须继续追踪。web/lib/api/curation-workspace.client.ts有完整类型；usePlacementCommand当前固定node，后续需在真实复用时接page_type，保留默认node以保护M21；ConceptPlacementEditor/PlacementHistory可参考。IssueSourcePicker目前面向原策划来源，不能把不同payload随意混用。WorkCurationEditor已读至removePlacement开头，其用途是编目中的阅读路径安排，不是通用M31视图，不应直接替换。

继续先读余下四幅实际图像与原调用链，再在原页面服务中接分组/显示配置/内部说明，检查公共投影只含明确对外字段；共享选书复用原馆藏与准确出版版本。不得创建平行内容库、把选书当作自动发布，或把私人研究资料混入管理来源。保持用户明确要求，不运行测试/浏览器/业务/迁移/生产/检索评测。

注意D010已明确本轮不新建第三步评测页面。M30仅记录旧源码，不应因本次读图再次启动评测开发。当前298契约，96源码/75部分/38待实施（M30三图按既定决策保留，统计不计完成）。
