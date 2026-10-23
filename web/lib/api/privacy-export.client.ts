import { ApiRequestError, apiStreamRequest, getServerSessionCredential } from "../api";
import { createRequestKey } from "../request-key";
import { PrivateOwnerVerificationError, withPrivateOwner } from "./private-owner";
import { downloadPrivacyOperation, operationPath } from "./privacy.client";

export type PrivacyExportFormat = "zip" | "folder" | "csv" | "json";
type PickerWindow = Window & { showDirectoryPicker?: (options: { mode: "readwrite" }) => Promise<FileSystemDirectoryHandle> };
export const canExportFolder = () => typeof window !== "undefined" && window.isSecureContext && typeof (window as PickerWindow).showDirectoryPicker === "function";

function saveBlob(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob), anchor = document.createElement("a");
  anchor.href = url; anchor.download = name; document.body.append(anchor); anchor.click(); anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

async function writeFile(directory: FileSystemDirectoryHandle, name: string, value: unknown, signal: AbortSignal) {
  signal.throwIfAborted();
  const file = await directory.getFileHandle(name, { create: true });
  const stream = await file.createWritable();
  try { await stream.write(JSON.stringify(value, null, 2)); signal.throwIfAborted(); await stream.close(); }
  catch (reason) { await stream.abort().catch(() => undefined); throw reason; }
}

export async function downloadPrivacyFiles(owner: string, id: string, format: PrivacyExportFormat, signal: AbortSignal) {
  // Invoke the picker during the original click, before any network await consumes user activation.
  let destination: FileSystemDirectoryHandle | null = null;
  if (format === "folder") {
    if (!canExportFolder()) throw Error("当前浏览器或连接不支持直接选择文件夹。请选择 ZIP，解压后保留相同的分类目录。");
    try { destination = await (window as PickerWindow).showDirectoryPicker!({ mode: "readwrite" }); }
    catch (reason) { if (reason instanceof DOMException && reason.name === "AbortError") return "已取消选择文件夹，资料任务仍保留。"; throw reason; }
  }
  if (format === "zip" || format === "csv") {
    const result = await withPrivateOwner(owner, async () => {
      const response = await apiStreamRequest(`${operationPath(id)}download/?export_format=${format}`, {
        cache: "no-store", headers: { "X-Reader-Owner": owner }, signal: AbortSignal.any([signal, AbortSignal.timeout(60000)]),
      }, getServerSessionCredential(), false);
      if (!response.ok) {
        const body = await response.json().catch(() => null);
        const detail = body?.detail ?? body?.error?.detail;
        throw new ApiRequestError(typeof detail === "string" ? detail : "文件尚未取得，请重新读取任务后下载。", response.status);
      }
      if (response.headers.get("X-Reader-Owner") !== owner || response.headers.get("X-Privacy-Operation") !== id) throw new PrivateOwnerVerificationError("导出归属未核实，已阻止下载。请重新验证账户。", 403);
      const mime = response.headers.get("Content-Type")?.split(";")[0];
      if (mime !== (format === "zip" ? "application/zip" : "text/csv")) throw Error("导出格式与选择不符，请重新读取任务。");
      const countHeader = response.headers.get("X-Privacy-Record-Count") || "", unavailableHeader = response.headers.get("X-Privacy-Unavailable-Count") || "";
      if (!/^\d+$/.test(countHeader) || !/^\d+$/.test(unavailableHeader)) throw Error("导出清单无法核对，请重新读取任务。");
      const count = Number(countHeader), unavailable = Number(unavailableHeader);
      const blob = await response.blob();
      if (!Number.isSafeInteger(count) || count < 0 || !Number.isSafeInteger(unavailable) || unavailable < 0) throw Error("导出清单无法核对，请重新读取任务。");
      return { count, unavailable, blob };
    }, signal);
    signal.throwIfAborted(); saveBlob(result.blob, `书库资料-${id}.${format}`);
    return `已准备 ${result.count} 项资料并请求浏览器下载。${result.unavailable ? `${result.unavailable} 项在准备后变化，原因已列入文件。` : "失败项目可在导出清单中核对。"}`;
  }
  const output = await withPrivateOwner(owner, () => downloadPrivacyOperation(owner, id, signal), signal);
  signal.throwIfAborted();
  if (output.operation_id !== id) throw new PrivateOwnerVerificationError("导出任务不匹配，已阻止下载。", 403);
  if (format === "json") {
    saveBlob(new Blob([JSON.stringify(output, null, 2)], { type: "application/json;charset=utf-8" }), `书库资料-${id}.json`);
    return `已准备 ${output.records.length} 项资料并请求浏览器下载，失败及已变化项目保留在清单中。`;
  }
  if (!destination) throw Error("尚未选定保存位置。");
  const paths = output.records.map(entry => {
    if (!/^[a-z_]{1,40}$/.test(entry.category) || !/^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(entry.id)) throw Error("资料文件名无法核对，已停止保存。");
    return `${entry.category}/${entry.id}.json`;
  });
  if (new Set(paths).size !== paths.length) throw Error("资料清单包含重复文件，请重新准备任务。");
  const name = `stl-data-${createRequestKey()}`;
  try { await destination.getDirectoryHandle(name); throw Error("保存位置已存在，请重新选择。已有文件没有被覆盖。"); }
  catch (reason) { if (!(reason instanceof DOMException && reason.name === "NotFoundError")) throw reason; }
  signal.throwIfAborted();
  const folder = await destination.getDirectoryHandle(name, { create: true });
  const { records, ...metadata } = output;
  const manifest = { ...metadata, files: paths, local_save_state: "incomplete" };
  let completed = 0;
  try {
    await writeFile(folder, "manifest.json", manifest, signal);
    for (const entry of records) {
      signal.throwIfAborted();
      const category = await folder.getDirectoryHandle(entry.category, { create: true });
      await writeFile(category, `${entry.id}.json`, entry, signal); completed += 1;
    }
    await writeFile(folder, "manifest.json", { ...manifest, local_save_state: "complete" }, signal);
  } catch {
    throw Error(`文件夹 ${name} 已保存 ${completed} / ${records.length} 项，尚未全部完成。现有文件保留；重新下载会创建新文件夹，原资料任务不受影响。`);
  }
  return `已将 ${records.length} 项资料保存到 ${name}。manifest.json 列出失败及下载时已变化的项目。`;
}
