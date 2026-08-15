# 观点检索质量评估

本目录用于比较旧模糊检索、纯关键词、纯向量、混合召回和混合召回加重排。评估脚本只调用书库 API，不读取或复制 PDF 正文。

## 标注数据

`queries.json` 预置十类查询。管理员可在后台测试查询后，将正确的 `passage_id` 或 `work_id` 填入对应数组。没有标注的查询仍会参与延迟和同书重复率统计，但不会进入 Recall、MRR 与 nDCG 计算。

每条查询可填写：

- `relevant_passage_ids`：被判断为相关的观点分块 ID，越靠前代表相关等级越高。
- `relevant_work_ids`：只有作品级判断时填写，脚本会将该作品的返回段落视为相关。
- `irrelevant_passage_ids`：已确认不相关的困难负例。
- `filters`：与公开观点检索相同的后端筛选条件。

## 运行

管理员策略参数仅向已登录管理员开放。先登录后台，复制访问令牌，再运行：

```powershell
$env:LIBRARY_API_URL='http://127.0.0.1:8000/api'
$env:LIBRARY_ADMIN_TOKEN='粘贴访问令牌'
python tests/semantic_search/evaluate.py
```

指定其他标注文件和结果目录：

```powershell
python tests/semantic_search/evaluate.py --dataset tests/semantic_search/queries.json --output tmp/semantic-evaluation.json
```

输出包括 Recall@10、Recall@20、MRR、nDCG@10、同书重复率、已标注无关结果率、平均延迟和 P95 延迟。后台索引任务返回的单本文献分块与索引耗时会原样收入 `indexing_snapshot`，便于长期追加统计。

## 解释边界

评估脚本不会把向量分数转换为观点相同百分比。公开页面只显示高度相关、较为相关和可能相关。原文是否支持学术判断，仍须回到 PDF 原页核对。
