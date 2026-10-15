import Link from "next/link";

export type ReaderCenterSection = "research" | "notes" | "plans" | "lists" | "citation" | "confirmed";

const sections: Array<{ key: ReaderCenterSection; label: string; href: string }> = [
  { key: "research", label: "我的研究", href: "/account" },
  { key: "notes", label: "笔记", href: "/account/notes" },
  { key: "plans", label: "阅读计划", href: "/account/plans" },
  { key: "lists", label: "书单", href: "/account?section=lists" },
  { key: "citation", label: "引文核验", href: "/account/citation-audits" },
  { key: "confirmed", label: "已确认笔记", href: "/account/confirmed-notes" },
];

export function ResearchCenterNav({ active }: { active: ReaderCenterSection }) {
  return (
    <nav className="stl4-reader-tabs" aria-label="读者中心">
      {sections.map((section) => (
        <Link
          href={section.href}
          className={active === section.key ? "is-active" : undefined}
          aria-current={active === section.key ? "page" : undefined}
          key={section.key}
        >
          {section.label}
        </Link>
      ))}
    </nav>
  );
}
