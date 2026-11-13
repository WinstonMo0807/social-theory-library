"use client";

import { Fragment, type KeyboardEvent } from "react";

/** Selectable text keeps title italics when readers copy into a rich-text editor. */
export function CitationText({ text, italicTitle = "", className }: { text: string; italicTitle?: string; className?: string }) {
  const parts = italicTitle ? text.split(italicTitle) : [text];
  function selectAll(event: KeyboardEvent<HTMLDivElement>) {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "a") {
      event.preventDefault();
      const range = document.createRange();
      range.selectNodeContents(event.currentTarget);
      const selection = window.getSelection();
      selection?.removeAllRanges();
      selection?.addRange(range);
    }
  }
  return <div className={className} role="textbox" aria-readonly="true" aria-multiline="true" aria-label="可复制的引用文本" tabIndex={0} onKeyDown={selectAll}>
    {parts.map((part, index) => <Fragment key={index}>{index > 0 ? <i>{italicTitle}</i> : null}{part}</Fragment>)}
  </div>;
}
