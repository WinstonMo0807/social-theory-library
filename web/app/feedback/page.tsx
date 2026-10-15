import { SiteFooter } from "@/components/site-footer";
import { FeedbackForm } from "@/components/public/feedback-form";
export const metadata = { title: "提交反馈" };
export default function FeedbackPage() { return <><div className="stl4-support-page stl4-feedback-page"><header><p className="stl4-support-kicker">使用帮助与反馈</p><h1>提交反馈</h1><p>我们希望知道哪些地方还不清楚。请尽量写下页面位置和操作步骤。</p></header><FeedbackForm /></div><SiteFooter /></>; }
