# 数据模型与权限

更新日期为 2026-08-26。以下 3.0.2 模型延续 3.0 的正式职责划分。旧章节保留基础对象说明。

## 3.0 分层

### Canonical

- Discipline、Subdiscipline、Topic 是独立规范身份。
- KnowledgeNode 只承载 THEORY_TRADITION、CONCEPT、DEBATE 和 RESEARCH_PROBLEM 等知识节点。
- Person 与 ScholarProfile、Work 与 Edition、ReadingPath 分别保存身份和呈现职责。
- KnowledgeRelation、WorkNodeRelation、PersonNodeRelation 和专门的 Discipline、Subdiscipline、Topic relation 保存正式关系。
- CuratedClaim 是 Editor 从 DerivedClaim 采用的策展命题。只有 published 状态才进入公网。

### Derived

- DocumentRevision 保存 Asset 的 parser、extraction、OCR、source checksum、text checksum、quality summary 和 active/superseded provenance。它不是 Page 的父对象。
- DocumentQualityAssessment 分别保存 reader、fulltext、semantic、claim、structure 和 OCR 质量，并可记录 critical pages。
- EvidenceSpan 只表示馆藏内部原文。它保存 revision、Page、页码、纸本页码、block/offset/bbox、原文、规范文本、语言、section、content hash 和 OCR provenance。
- DerivedClaim 保存原子命题、subject、predicate、object、polarity、modality、qualifier、三类 scope、attribution、claim type、prompt 和 model provenance。
- CandidateEvidence、EnrichmentEvidence、QueryLexiconCandidateEvidence、EvidenceSnippet 与 UnknownEntityObservation 继续按各自职责保留，不合并成万能 Evidence 表。
- ResearchTaskProfile、EvidencePack、PromptRegistryEntry、DebateCandidate、ReadingPathCandidate 和 IntelligenceFeedback 支持研究任务、候选与人工校准。
- Library Synthesis 不增加新知识表。它把馆内 EvidenceSpan 组成 EvidencePack，经 task-specific synthesis 后写入现有 MetadataCandidate，并保存 Evidence 引用。人工采用前始终属于 Derived。
- Knowledge Growth 没有持久化 `KnowledgeUpdateSuggestion` 表。它是 EvidenceSpan、DerivedClaim、EnrichmentCandidate、DebateCandidate 与 ReadingPathCandidate 的有界派生读模型。
- ClaimBenchmarkJudgment 保存人工 Gold，只能引用当前 active DocumentRevision 上未失效的 EvidenceSpan。它用于 benchmark 和 gate，不是公开知识。

### Projection 与执行状态

- CanonicalObjectRevision 和 DomainChangeEvent 记录正式对象 revision 与变更事实。
- ProjectionState 保存 source revision、projected revision、stale reason、lease 与 retry。
- CapabilityDemand 和 ExecutorRegistration 协调现有 ProcessingJob、ResearchRun、SemanticIndexJob 与 QueryLexicon event，不替代这些专业任务表。
- QueryLexicon、全文、Semantic、Claim Index、Knowledge Graph、Timeline、Recommendation、Reading Path support 和公共缓存均可重建。

## 3.0 兼容对象

TheorySchool、legacy Concept 与 WorkKnowledgeRelation 停止新增正式写入。LegacyKnowledgeMapping 只接受人工确认 mapping。兼容读取在 normalized parity、零旧写调用和观察期完成前保留。不得直接删除旧表，也不得自动修复语义可疑的 mapping。

## 文献

### Work

抽象作品记录。保存作品类型、主标题、其他标题、摘要、语言、公开状态和稳定地址。

### Edition

保存版本、译本、出版信息和引用所需字段。首期每部作品只显示一个版本，但接口允许多个版本。

### Asset

具体 PDF 文件。保存哈希、归档位置、公开文件名、页数、文件大小、处理版本、云端状态和权限。

`is_current` 表示当前公开阅读文件，`version` 保存同一版本记录下的文件修订序号。历史文件不删除。

### Page

具体 PDF 页面。保存 PDF 页序、纸本页码、章节、规范文本、坐标系和提取状态。

### TextBlock

页面中的标题、正文、脚注、表格、公式、页眉、页脚等区域。

### Passage

用于搜索的页内段落。每条段落必须能够返回页面和高亮坐标。

## 人物与知识组织

### Person

所有责任者和被识别人物。保存规范姓名、原文姓名、中文译名、拼音和其他别名。

### ScholarProfile

经过确认后公开的学者档案。人物可以没有学者档案。

### Contribution

连接作品与人物，并区分作者、编辑、译者、机构作者和其他责任关系。

### TheorySchool

迁移兼容的旧思想传统。新理论使用 `KnowledgeNode(node_type=THEORY_TRADITION)`，本表停止新增正式写入。

### Topic

研究对象或问题领域。

### Concept

迁移兼容的旧概念。新概念使用 `KnowledgeNode(node_type=CONCEPT)`，本表停止新增正式写入。

### KnowledgeRelation

保存关系两端、关系类型、方向、来源、证据、置信度和公开状态。

## 用户数据

- `User` 登录身份、角色和安全状态
- `ReaderProfile` 读者资料和偏好
- `ReadingProgress` 当前页、最远页和更新时间
- `SavedItem` 收藏的文献、学者、主题或流派
- `ReadingList` 私人书单
- `Annotation` 高亮、划线、笔记和页面批注
- `Bookmark` 书签
- `ReadingHistory` 阅读历史
- `RecoveryCode` 一次性恢复码
- `Session` 活跃登录会话

## 入库与管理

- `UploadBatch` 一次批量上传
- `UploadItem` 批次中的单个 PDF，包含客户端幂等标识和可选的被替换文件
- `ProcessingAttempt` 每个阶段的一次执行
- `MetadataCandidate` 字段候选与证据
- `FieldLock` 人工锁定字段
- `PublicationEvent` 发布、修改、下架和删除事件
- `AuditEvent` 用户及管理员操作
- `SiteSetting` 可编辑网站名称、导航、首页文案和投稿邮箱
- `ProviderCredentialSecret` 保存 Provider credential alias、用途、加密 ciphertext、key version、更新时间和测试状态。catalog 0039 只新增该表；主密钥来自服务端环境，API 不返回明文
- `FeaturedSlot` 首页与各页面策展位置
- `BackupJob` 手动备份记录

## 云端分发

- `CloudProvider` 对象存储配置引用，不保存明文密钥
- `CloudObject` 文件、对象键、校验值、同步状态和最后验证时间
- `CloudBudgetPolicy` 预算、告警和停止新发布阈值
- `CloudUsageSnapshot` 存储、流量、请求和费用估算

## 权限

| 能力 | 访客 | Reader | Editor | Administrator | System Owner |
| --- | :---: | :---: | :---: | :---: | :---: |
| 浏览、搜索、在线阅读 | 是 | 是 | 是 | 是 | 是 |
| 下载、复制、引用 | 是 | 是 | 是 | 是 | 是 |
| 高亮、划线、笔记、书签 | 否 | 是 | 是 | 是 | 是 |
| 收藏、书单、进度、历史 | 否 | 是 | 是 | 是 | 是 |
| 导出自己的数据 | 否 | 是 | 是 | 是 | 是 |
| 上传、编辑、候选决定与研究 | 否 | 否 | 是 | 是 | 是 |
| 授权范围内单人发布 | 否 | 否 | 是 | 是 | 是 |
| 任务重试、状态与审计查看 | 否 | 否 | 否 | 是 | 是 |
| Knowledge administration、Processing Center、普通用户、安全恢复 | 否 | 否 | 否 | 是 | 是 |
| Provider secret、敏感 AI runtime、破坏性 Prompt、Authority merge | 否 | 否 | 否 | 否 | 是 |
| 全局破坏性 Projection、backup/restore、角色提升 | 否 | 否 | 否 | 否 | 是 |
| 备份和破坏性维护 | 否 | 否 | 否 | 否 | 是 |
| 查看其他用户笔记正文 | 否 | 否 | 否 | 否 | 否 |

Reviewer 只为旧账户兼容保留，不参与强制审核流程。Editor expertise 只影响候选和任务优先级，不形成审批门槛。
