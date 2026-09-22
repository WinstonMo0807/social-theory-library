"use client";

import styles from "@/app/explore/opinions/viewpoint-search.module.css";

/** Preview only the public editorial field. Private notes are never accepted. */
export function CurationDiscoveryPreview({ sourceTitle, subjectTitle, reason }: {
  sourceTitle: string; subjectTitle?: string; reason: string;
}) {
  return <details className="curation-discovery-preview">
    <summary>观点检索中的策展卡片</summary>
    <p className={styles.help}>推荐理由可以自然写明适合讨论的问题、方法或阅读用途，无需另外建立复杂标签。保存并发布后，公开文字会参与策展检索；编辑备注只保留在后台。</p>
    {reason.trim() ? <article className={styles.curationCard}>
      <span className={styles.sourceTag}>策展推荐 · 当前输入预览</span>
      <h3>{subjectTitle || sourceTitle || "尚未填写标题"}</h3>
      <p>{reason}</p>
      <small>来源：{sourceTitle || "尚未选择阅读路径"}</small>
      <small>这里预览当前输入，尚不能据此确认已经发布或进入索引。</small>
    </article> : <p className={styles.help}>填写公开推荐理由后，这里会按当前文字预览。空白不会自动生成替代文案。</p>}
  </details>;
}
