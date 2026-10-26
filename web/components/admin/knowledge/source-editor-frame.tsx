"use client";

import type { ReactNode } from "react";
import { Dialog } from "@/components/ui/dialog";
import styles from "./person-authority.module.css";

export type SourceEditorState = { dirty: boolean; busy: boolean; saveable: boolean };
export type SourceEditorOptions = { embedded?: boolean; formId?: string; onState?: (state: SourceEditorState | null) => void };

export function SourceEditorFrame({embedded,children,onClose,label}:{embedded?:boolean;children:ReactNode;onClose?:()=>void;label:string}) {
  const className=`${styles.dialog} ${styles.aliasDialog} ${embedded?styles.inlineAliases:""}`;
  return embedded?<section className={className} aria-label={label}>{children}</section>:<Dialog open className={className} onRequestClose={onClose} aria-label={label}>{children}</Dialog>;
}
