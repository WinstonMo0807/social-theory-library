"use client";
import { useState } from "react";
import { X } from "lucide-react";
import { Drawer } from "@/components/ui/dialog";
import "./preview.css";

const options = [
  ["list", "01", "清晰纵列", "保留熟悉的上下顺序，入口齐整，外观设置按需展开。"],
  ["columns", "02", "双栏分组", "主导航和账户入口各排两列，减少滚动，适合桌面。"],
  ["tiles", "03", "分区卡片", "主导航使用独立方块，点击范围更明确，适合触屏。"],
];
export default function DrawerPreviewPage() {
  const [variant,setVariant]=useState("list");
  const [contentOpen,setContentOpen]=useState(false);
  function openMenu(value:string) {
    setVariant(value);
    document.querySelector<HTMLButtonElement>(".site-masthead > .header-actions > .menu-button")?.click();
  }
  return <main className="drawer-layout-preview" data-variant={variant}>
    <header><p>抽屉排版参考</p><h1>三种布局，同一套功能。</h1><p>下面打开的是本站实际菜单。比较完成后关闭抽屉，再选择另一套。</p></header>
    <div className="drawer-layout-options">{options.map(([id,number,title,copy])=><button key={id} type="button" aria-pressed={variant===id} onClick={()=>openMenu(id)}><span>{number}</span><h2>{title}</h2><p>{copy}</p><strong>打开此方案 →</strong></button>)}</div>
    <section className="drawer-layout-note"><h2>同类抽屉的共同调整</h2><p>标题与关闭按钮保持可见，内容独立滚动，长标题可以自然换行。菜单、策划原文和版本历史复用这些规则。</p><button type="button" onClick={()=>setContentOpen(true)}>查看内容抽屉</button><p>这里的三种菜单布局仅供比较，尚未替换全站默认菜单。</p></section>
    <Drawer open={contentOpen} onRequestClose={()=>setContentOpen(false)} className="drawer-layout-content" aria-label="内容抽屉排版示例"><header><h2>原文与说明</h2><button type="button" aria-label="关闭内容示例" onClick={()=>setContentOpen(false)}><X size={20}/></button></header><p>这是排版示例，不是书籍引文或后台记录。</p>{Array.from({length:6},(_,i)=><section key={i}><h3>{["清楚的阅读顺序","保留必要的来源","适合长标题","操作保持集中","小屏上的阅读","回到原来的位置"][i]}</h3><p>文字按段落展开，留出合适的行距。需要进一步阅读时，可以沿既有入口查看来源；浏览内容时，标题和关闭按钮始终位于顶部。此处仅演示长内容的布局和滚动，不提交或修改任何资料。</p></section>)}<button type="button" onClick={()=>setContentOpen(false)}>返回方案</button></Drawer>
  </main>;
}
