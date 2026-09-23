export function ProcessingError({ message, code = "" }: { message: string; code?: string }) {
  const longIndex = /index row size.*exceeds.*maximum/i.test(message);
  const unavailable = /OCRServiceUnavailable|paddleocr_nas.*不可用/.test(`${code} ${message}`);
  const guidance = longIndex
    ? "文字已提取，但保存检索索引时失败。这不代表 PDF 损坏。可重新处理；仍失败时请联系书库所有者检查索引。"
    : unavailable
      ? "未能连接文字识别服务。已保存的页数会保留，可在处理中心重试并查看进度。"
      : "本次处理未完成。请查看原因后重试，或删除本次上传；原文件和处理历史会保留。";
  return <div className="ingestion-item-error" role="alert"><div><p>{guidance}</p><details><summary>查看具体原因</summary><p>{code ? `${code}：` : ""}{message}</p></details></div></div>;
}
