import { Suspense } from "react";
import { CatalogOcrPicker } from "@/components/admin/workflow/edition-ocr-control";

export const metadata = {title:"识别书中文字"};
export default function Page() {
  return <div className="admin-page"><Suspense fallback={<p>正在读取馆藏…</p>}><CatalogOcrPicker fullPage/></Suspense></div>;
}
