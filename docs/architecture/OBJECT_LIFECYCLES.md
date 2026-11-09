# 核心对象生命周期

[架构目录](README.md) · [领域模型](06_DOMAIN_MODEL.md)

## 候选与人工决定

```mermaid
flowchart TB
  Source[PDF / 书目源 / AI] --> Candidate[Metadata / Entity / Enrichment候选]
  Candidate --> Review[管理员核对来源与现有对象]
  Review --> Reject[拒绝并留决定记录]
  Review --> Draft[采用为草稿 / 字段决定]
  Draft --> Lock[可选人工字段锁]
  Draft --> Confirm[确认关联 / 发布预检]
  Confirm --> Publication[正式发布修订]
  Changed[依赖字段或源修订变化] --> Stale[候选 / 决定待重核]
  Stale --> Review
```

这是业务阶段图，不把不同模型的status枚举强行统一。reject不是删除来源；锁不是公开；采用候选不应掩盖人工实际修改的内容。

## 文件、正文与派生数据

```mermaid
flowchart TB
  Upload[接收文件] --> Validate[校验 / 查重]
  Validate --> Original[原件Asset保留]
  Original --> Text[原生提取或OCR派生Asset]
  Text --> Rev[DocumentRevision + Page / Passage / EvidenceSpan]
  Rev --> Index[语义 / Discovery索引投影]
  Rev --> Outline[目录识别或人工校准]
  Outline --> Download[新下载副本]
  Rev --> NewRev[重新处理产生新修订]
  NewRev --> Invalidate[旧证据失效检查 / 投影重建]
  Original -. 不覆盖 .-> Original
```

目录修订不是正文修订；带书签下载生成可能仍在任务中。私人注释保留原asset checksum与锚点，失配应显式orphaned/待核，不静默改绑。

## 公开内容

```mermaid
stateDiagram-v2
  [*] --> Draft: 编辑保存
  Draft --> Review: 读取版本对应预览
  Review --> Draft: 竞争版本 / 继续修改
  Review --> Preparing: 授权发布命令
  Preparing --> Active: 条件满足并切换活动快照
  Preparing --> Failed: 队列或投影失败
  Failed --> Preparing: 核对回执后重试
  Active --> Superseded: 新正式修订生效
  Active --> Withdrawn: 授权撤回
  Superseded --> Active: 校验后的历史恢复
  Withdrawn --> Review: 重新审核
```

此图综合馆藏业务阶段。EditorialRevision、CatalogPublicationRevision、Edition各自枚举不同；具体状态见模型CSV。恢复正式历史不是删除新历史或覆盖原始文件。知识对象和文章使用各自发布协议，见[模块契约](ADMIN_MODULE_CONTRACTS.md)。

## 私人研究

本人创建 → 加密保存 → 本人继续研究/引用原文 → 明确选择分享范围 → 可撤销分享/本人数据操作。共享的是授权范围，不能据此公开全项目、原上传或关联的其他私人笔记。研究派生候选进入公共策展必须经过单独授权与正式编辑流程；本轮没有实施这种数据迁移。
