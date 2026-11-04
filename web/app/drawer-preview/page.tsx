"use client";
import { useState } from "react";
import { ArrowRight, X } from "lucide-react";
import { Drawer } from "@/components/ui/dialog";
import "./preview.css";

const options = [
  ["list", "清晰纵列"],
  ["columns", "双栏分组"],
  ["tiles", "分区卡片"],
];
export default function DrawerPreviewPage() {
  const [variant,setVariant]=useState("columns");
  const [contentOpen,setContentOpen]=useState(false);
  function openMenu(value:string) {
    setVariant(value);
    document.querySelector<HTMLButtonElement>(".site-masthead > .header-actions > .menu-button")?.click();
  }
  return <main className="drawer-layout-preview" data-variant={variant}>
    <header><h1>菜单布局</h1></header>
    <div className="drawer-layout-options">{options.map(([id,title])=><button key={id} type="button" aria-label={`预览${title}`} aria-pressed={variant===id} onClick={()=>openMenu(id)}><span>{title}</span><ArrowRight size={20} aria-hidden="true" /></button>)}</div>
    <section className="drawer-layout-note"><button type="button" onClick={()=>setContentOpen(true)}>查看内容抽屉</button></section>
    <Drawer open={contentOpen} onRequestClose={()=>setContentOpen(false)} className="drawer-layout-content" aria-label="内容抽屉排版示例"><header><h2>原文与说明</h2><button type="button" aria-label="关闭内容示例" onClick={()=>setContentOpen(false)}><X size={20}/></button></header><p>这是排版示例，不是书籍引文或后台记录。</p>{Array.from({length:6},(_,i)=><section key={i}><h3>{["清楚的阅读顺序","保留必要的来源","适合长标题","操作保持集中","小屏上的阅读","回到原来的位置"][i]}</h3><p>文字按段落展开，留出合适的行距。需要进一步阅读时，可以沿既有入口查看来源；浏览内容时，标题和关闭按钮始终位于顶部。此处仅演示长内容的布局和滚动，不提交或修改任何资料。</p></section>)}<button type="button" onClick={()=>setContentOpen(false)}>返回方案</button></Drawer>
  </main>;
}
