# 理论系统数据模型

## 建模原则

- 一个理论只有一个规范节点。
- 理论传统、子学科、概念、理论争论和研究问题用类型区分。
- 学者、作品和 PDF 继续使用现有模型，不复制到知识节点表。
- 所有自动关系先进入待审核。
- 每个公开关系可以追溯到原始 PDF 页与原文。
- 旧理论和子学科记录通过映射表兼容，不立即删除。

## KnowledgeNode

字段：

- `id`
- `type`，取值为 `theory_tradition`、`subdiscipline`、`concept`、`debate`、`research_problem`
- `canonical_name_zh`
- `canonical_name_en`
- `slug`
- `summary`
- `definition`
- `core_questions`
- `basic_propositions`
- `theoretical_boundary`
- `start_year`
- `end_year`
- `period_label`
- `primary_discipline`
- `status`，取值为 `draft`、`pending`、`published`、`rejected`、`archived`
- `sort_order`
- `cover_asset`
- `created_by`
- `reviewed_by`
- `published_at`
- `created_at`
- `updated_at`

约束：规范中文名和类型使用规范化后的联合重复检测。`slug` 全局唯一并建立索引。公开查询必须包含 `status=published`。

## KnowledgeNodeAlias

- `node`
- `alias`
- `language`
- `alias_type`
- `normalized_alias`
- `created_by`
- `created_at`

同一节点内不保存重复规范化别名。检索同时覆盖中文名、外文名和别名。

## KnowledgeNodeDiscipline

- `node`
- `discipline`
- `relation_type`，取值为 `primary`、`related`、`transferred`
- `discipline_specific_summary`
- `sort_order`
- `status`
- `reviewed_by`
- `reviewed_at`

每个节点最多一个 primary。节点可以没有学科关系，仍可与作品、主题和学者关联。

## KnowledgeRelation

- `source_node`
- `target_node`
- `relation_type`
- `direction`，取值为 `directed` 或 `undirected`
- `description`
- `evidence_source`
- `confidence`
- `status`
- `created_by`
- `reviewed_by`
- `published_at`
- `created_at`
- `updated_at`

关系类型：

- `inherited_from`
- `revises`
- `criticizes`
- `competes_with`
- `synthesizes`
- `branches_from`
- `borrows_concept_from`
- `transferred_to`
- `influenced_by`
- `overlaps_with`

禁止 source 与 target 相同。无方向关系写入时按稳定主键排序，避免反向重复。

## WorkNodeRelation

- `work`
- `node`
- `role`
- `is_primary`
- `strength`
- `confidence`
- `status`
- `source`
- `created_by`
- `reviewed_by`
- `reviewed_at`
- `created_at`
- `updated_at`

角色：

- `foundational_work`
- `systematic_exposition`
- `theoretical_development`
- `empirical_application`
- `comparative_study`
- `critique`
- `general_mention`

同一作品可以用不同角色关联多个节点。一般提及不进入经典文献栏目。

## EvidenceSnippet

- `work`
- `file`，关联现有 Asset
- `node`
- `work_node_relation`
- `knowledge_relation`
- `page_number`
- `page_end`
- `printed_page_label`
- `quote`
- `bounding_box`
- `extraction_method`
- `ocr_confidence`
- `semantic_confidence`
- `review_status`
- `reviewed_by`
- `reviewed_at`
- `created_at`

至少关联一种关系对象。`quote` 保存真实原文，AI 说明另存审核备注，不能替代原文。

## TheoryReviewTask

- `task_type`
- `work`
- `file`
- `candidate_node`
- `suggested_node_name`
- `suggested_relation_type`
- `confidence`
- `evidence_pages`
- `evidence_text`
- `status`
- `assigned_to`
- `submitted_at`
- `reviewed_at`
- `review_note`

新理论名称只能停留在建议字段。管理员选择创建节点、添加别名、合并或拒绝后才产生正式关系。

## TimelineEvent 与 TimelineEventRelation

现有 `TheoryTimelineEvent` 保留并扩展事件类型、证据与发布状态。多对象关联进入 `TimelineEventRelation`。

事件类型至少支持：

- `important_publication`
- `concept_proposed`
- `school_formed`
- `institution_established`
- `major_debate`
- `theoretical_turn`
- `important_translation`
- `introduced_to_china`
- `scholar_life_event`
- `disciplinary_institutionalization`

关系表可关联节点、学科、学者、作品和证据片段，并保存排序与关系说明。

## ReadingPath 与 ReadingPathItem

ReadingPath：

- 标题、slug、简介、主要学科、适合人群、难度、预计阅读量、封面、状态和排序。

ReadingPathItem：

- 路径、阶段名称、阶段说明、节点、作品、推荐理由、阅读顺序、是否必读和编辑说明。

项目至少关联节点或作品之一。公开接口只返回发布路径和当前发布作品。

## 版本与合并

`KnowledgeNodeVersion` 和 `KnowledgeRelationVersion` 保存每次重要修改的 JSON 快照、操作者、时间和修改说明。

`KnowledgeNodeMergeRecord` 保存：

- 来源节点
- 目标节点
- 合并前来源快照
- 合并前目标快照
- 受影响关系和对象数量
- 操作者与时间
- 是否已回滚

合并在数据库事务中重新指向别名、学科、作品、证据、关系、事件和阅读路径。发生唯一约束冲突时合并而非丢弃证据。

## 旧数据映射

`LegacyKnowledgeMapping` 保存：

- `legacy_model`
- `legacy_id`
- `node`
- `migration_status`
- `migration_note`
- `created_at`

初次迁移规则：

- `TheorySchool` 映射为 `theory_tradition`。
- `Subdiscipline` 映射为 `subdiscipline`。
- `Concept` 映射为 `concept`。
- Topic 默认保留原对象，不自动变为 `research_problem`。
- 无法确定和疑似重复记录进入待审核。

旧对象不删除。旧详情地址通过映射找到新节点，功能开关关闭时仍按旧对象展示。

## 索引

为以下字段建立索引：

- 节点 `slug`、`status`、`type`、`primary_discipline`
- 别名 `normalized_alias`
- 学科关联 `node`、`discipline`、`relation_type`、`status`
- 节点关系 source、target、type、status
- 文献关系 work、node、role、status
- 证据 work、file、node、page_number、review_status
- 时间轴 start_year、event_type、status
- 阅读路径 slug、status、sort_order
