"use client";

import {asArray,asRecord,asString} from "./workflow-types";
import {safeAdminHref} from "@/lib/admin-route-context";

const labels:Record<string,string>={ready:"已就绪",partial:"部分就绪",pending:"等待处理",paused:"已暂停",disabled:"未启用",not_applicable:"不适用",failed:"处理失败",stale:"来源已过期",unknown:"待核实"};

/** One view of the server's existing revision/task evidence, not a second
 * readiness calculation. GET never triggers a new probe or a paid service. */
export function CatalogAvailability({value}:{value:unknown}){
  const payload=asRecord(value);
  const capabilities=asArray(payload.capabilities).map(asRecord);
  if(!capabilities.length) return <p>各项阅读与检索能力尚无可核实结果，请刷新当前版本。</p>;
  return <section aria-label="当前版本的阅读与检索能力">
    <div className="workflow-reader-states">{capabilities.map(capability=>{
      const source=asRecord(capability.source);
      return <article key={asString(capability.key)} data-capability={asString(capability.key)} data-status={asString(capability.status)}>
        <strong>{asString(capability.label)}</strong><span>{labels[asString(capability.status)]||"待核实"}</span><p>{capability.status === "not_applicable" ? "这条书目没有文件，不需要处理这一项。" : capability.status === "failed" ? "处理时遇到问题，请查看下面的记录并重试。" : capability.status === "paused" ? "当前已暂停，不会自动继续。" : capability.status === "unknown" || capability.status === "stale" ? "暂时不能确认最新结果，可以刷新后再检查。" : capability.status === "disabled" ? "这项功能尚未启用，不影响编辑书目。" : capability.key === "pdf" && capability.status === "ready" ? "文件检查已通过，可以打开预览核对。" : capability.status === "ready" ? "已有完成记录。" : "还在等待或处理中，不必留在页面等待。"}</p>
        <details><summary>查看处理记录</summary><p>{asString(capability.detail)}</p><p>最近更新：{asString(source.record_updated_at)||"无记录"}</p>
          <details><summary>技术信息</summary><p>公开修订：{asString(source.catalog_revision_id)||"无"}<br/>正文修订：{asString(source.document_revision_id)||"无"}</p><p>{capability.runtime_verified ? "附有近期服务检查。" : "本次没有重新检测服务。"}</p></details>
          {asArray(capability.tasks).map(asRecord).map(task=><p key={asString(task.id)}><a href={safeAdminHref(asString(task.url),"/admin/processing")}>{asString(task.label)||"查看原处理任务"}</a> · {labels[asString(task.status)]||asString(task.status)}</p>)}
        </details>
      </article>;
    })}</div>
    <p>这里显示已有处理结果。查看页面不会启动新的任务，也不会读取读者的私人笔记。</p>
  </section>;
}
