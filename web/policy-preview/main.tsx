import { createRoot } from "react-dom/client";
import { ArrowUpRight } from "lucide-react";
import { BrandImage } from "@/components/brand-image";
import { PolicyWorkspace } from "@/app/policy/policy-workspace";
import "@/styles/tokens/type-fonts.css";
import "@/styles/layout/brand-identity.css";
import "./preview.css";

// Only the shell differs in standalone preview. The same workspace ships at /policy.
createRoot(document.getElementById("root")!).render(<>
  <header className="policy-preview-header site-header">
    <a className="policy-preview-brand" href="/policy" aria-label="政策库首页"><BrandImage /></a>
    <nav aria-label="书库栏目">
      {[['书库', '/'], ['探索', '/explore'], ['理论', '/theories'], ['学者', '/scholars'], ['主题', '/topics']].map(([label, path]) => <a key={path} href={`https://books.winstonmo.com${path}`} target="_blank" rel="noreferrer">{label}</a>)}
      <a className="policy-preview-active" href="/policy" aria-current="page">政策</a>
    </nav>
    <a className="policy-preview-stl" href="https://books.winstonmo.com" target="_blank" rel="noreferrer">社会理论书库<ArrowUpRight size={15} /></a>
  </header>
  <main><PolicyWorkspace libraryUrl="https://books.winstonmo.com" /></main>
</>);
