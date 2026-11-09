import Link from "next/link";
import { AIRuntimeEditor } from "@/components/admin/ai-runtime-editor";

export default function IntelligenceSettings() {
  return <section className="admin-section"><Link href="/admin/intelligence">返回 STL Intelligence</Link>
    <h1>分析模型</h1><p>选择 OpenAI-compatible，填写服务地址和模型名称，保存并启用后回到任务恢复分析。密钥使用现有加密凭据管理。</p>
    <AIRuntimeEditor profileKey="curation-reasoning-default" />
    <details><summary>内网 HTTP 预览的配置方法</summary>
      <p>通过可信 SSH 终端进入候选 API 容器，运行 configure_intelligence_provider。命令会隐藏输入密钥，写入同一加密配置服务；不会测试接口或启动模型。</p>
      <pre>{"python manage.py configure_intelligence_provider --actor 馆长账号 --base-url https://你的服务/v1 --model 模型名称 --enable"}</pre>
      <p>模型只支持 JSON Object 时，增加 --json-mode json_object。保存后返回任务选择恢复分析。</p>
    </details>
  </section>;
}
