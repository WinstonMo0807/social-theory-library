"use client";

import Link from "next/link";
import type { ButtonHTMLAttributes, ComponentProps, ReactNode } from "react";
import { AlertCircle, CheckCircle2, LoaderCircle, X } from "lucide-react";

export type ActionState = "idle" | "pending" | "success" | "error";

type ActionContentProps = {
  state: ActionState;
  children: ReactNode;
  pendingLabel?: ReactNode;
  successLabel?: ReactNode;
  errorLabel?: ReactNode;
};

function ActionContent({ state, children, pendingLabel, successLabel, errorLabel }: ActionContentProps) {
  if (state === "pending") {
    return <><LoaderCircle className="action-feedback-indicator spin" aria-hidden="true" size={15} />{pendingLabel ?? children}</>;
  }
  if (state === "success") {
    return <><CheckCircle2 className="action-feedback-indicator" aria-hidden="true" size={15} />{successLabel ?? children}</>;
  }
  if (state === "error") {
    return <><AlertCircle className="action-feedback-indicator" aria-hidden="true" size={15} />{errorLabel ?? children}</>;
  }
  return <>{children}</>;
}

export type ActionButtonProps = Omit<ButtonHTMLAttributes<HTMLButtonElement>, "children"> & {
  children: ReactNode;
  state?: ActionState;
  pressed?: boolean;
  pendingLabel?: ReactNode;
  successLabel?: ReactNode;
  errorLabel?: ReactNode;
};

export function ActionButton({
  children,
  state = "idle",
  pressed,
  pendingLabel,
  successLabel,
  errorLabel,
  className = "",
  disabled = false,
  type = "button",
  onBlur,
  onKeyDown,
  onKeyUp,
  onPointerCancel,
  onPointerDown,
  onPointerLeave,
  onPointerUp,
  ...buttonProps
}: ActionButtonProps) {
  const blocked = disabled || state === "pending";
  const setPhysicalPress = (element: HTMLElement, active: boolean) => {
    element.dataset.physicalPress = String(active);
  };
  return (
    <button
      {...buttonProps}
      className={`action-feedback action-button ${className}`.trim()}
      type={type}
      disabled={blocked}
      aria-disabled={blocked}
      aria-busy={state === "pending"}
      aria-pressed={pressed}
      data-action-state={state}
      data-pressed={pressed === undefined ? undefined : String(pressed)}
      data-physical-press="false"
      onPointerDown={(event) => {
        if (!blocked) setPhysicalPress(event.currentTarget, true);
        onPointerDown?.(event);
      }}
      onPointerUp={(event) => {
        setPhysicalPress(event.currentTarget, false);
        onPointerUp?.(event);
      }}
      onPointerCancel={(event) => {
        setPhysicalPress(event.currentTarget, false);
        onPointerCancel?.(event);
      }}
      onPointerLeave={(event) => {
        setPhysicalPress(event.currentTarget, false);
        onPointerLeave?.(event);
      }}
      onKeyDown={(event) => {
        if (!blocked && (event.key === "Enter" || event.key === " ")) {
          setPhysicalPress(event.currentTarget, true);
        }
        onKeyDown?.(event);
      }}
      onKeyUp={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          setPhysicalPress(event.currentTarget, false);
        }
        onKeyUp?.(event);
      }}
      onBlur={(event) => {
        setPhysicalPress(event.currentTarget, false);
        onBlur?.(event);
      }}
    >
      <ActionContent state={state} pendingLabel={pendingLabel} successLabel={successLabel} errorLabel={errorLabel}>
        {children}
      </ActionContent>
    </button>
  );
}

type NextActionLinkProps = Omit<ComponentProps<typeof Link>, "children" | "className">;

export type ActionLinkProps = NextActionLinkProps & {
  children: ReactNode;
  className?: string;
  state?: ActionState;
  disabled?: boolean;
  pressed?: boolean;
  pendingLabel?: ReactNode;
  successLabel?: ReactNode;
  errorLabel?: ReactNode;
};

export function ActionLink({
  children,
  state = "idle",
  disabled = false,
  pressed,
  pendingLabel,
  successLabel,
  errorLabel,
  className = "",
  onClick,
  onBlur,
  onKeyDown,
  onKeyUp,
  onPointerCancel,
  onPointerDown,
  onPointerLeave,
  onPointerUp,
  ...linkProps
}: ActionLinkProps) {
  const blocked = disabled || state === "pending";
  return (
    <Link
      {...linkProps}
      className={`action-feedback action-link ${className}`.trim()}
      aria-disabled={blocked}
      aria-busy={state === "pending"}
      aria-current={pressed ? "page" : undefined}
      data-action-state={state}
      data-pressed={pressed === undefined ? undefined : String(pressed)}
      data-physical-press="false"
      tabIndex={blocked ? -1 : linkProps.tabIndex}
      onClick={(event) => {
        if (blocked) {
          event.preventDefault();
          return;
        }
        onClick?.(event);
      }}
      onPointerDown={(event) => {
        if (blocked) {
          event.preventDefault();
          return;
        }
        event.currentTarget.dataset.physicalPress = "true";
        onPointerDown?.(event);
      }}
      onPointerUp={(event) => {
        event.currentTarget.dataset.physicalPress = "false";
        onPointerUp?.(event);
      }}
      onPointerCancel={(event) => {
        event.currentTarget.dataset.physicalPress = "false";
        onPointerCancel?.(event);
      }}
      onPointerLeave={(event) => {
        event.currentTarget.dataset.physicalPress = "false";
        onPointerLeave?.(event);
      }}
      onKeyDown={(event) => {
        if (blocked) {
          if (event.key === "Enter" || event.key === " ") event.preventDefault();
          return;
        }
        if (event.key === "Enter") event.currentTarget.dataset.physicalPress = "true";
        onKeyDown?.(event);
      }}
      onKeyUp={(event) => {
        if (event.key === "Enter") event.currentTarget.dataset.physicalPress = "false";
        onKeyUp?.(event);
      }}
      onBlur={(event) => {
        event.currentTarget.dataset.physicalPress = "false";
        onBlur?.(event);
      }}
    >
      <ActionContent state={state} pendingLabel={pendingLabel} successLabel={successLabel} errorLabel={errorLabel}>
        {children}
      </ActionContent>
    </Link>
  );
}

export type AsyncStatusProps = {
  state: ActionState;
  message: ReactNode;
  className?: string;
  assertive?: boolean;
};

export function AsyncStatus({ state, message, className = "", assertive = false }: AsyncStatusProps) {
  if (!message) return null;
  return (
    <div
      className={`async-status ${state} ${className}`.trim()}
      role={state === "error" ? "alert" : "status"}
      aria-live={assertive || state === "error" ? "assertive" : "polite"}
      aria-atomic="true"
      aria-busy={state === "pending"}
      data-action-state={state}
    >
      {state === "pending" ? <LoaderCircle className="spin" aria-hidden="true" size={16} /> : null}
      {state === "success" ? <CheckCircle2 aria-hidden="true" size={16} /> : null}
      {state === "error" ? <AlertCircle aria-hidden="true" size={16} /> : null}
      <span>{message}</span>
    </div>
  );
}

export type ToastItem = {
  id: string;
  state: Exclude<ActionState, "idle">;
  message: ReactNode;
};

export function ToastHost({
  items,
  onDismiss,
  label = "操作反馈",
}: {
  items: ToastItem[];
  onDismiss?: (id: string) => void;
  label?: string;
}) {
  if (!items.length) return null;
  return (
    <aside className="toast-host" aria-label={label}>
      {items.map((item) => (
        <div className={`toast-item ${item.state}`} key={item.id}>
          <AsyncStatus state={item.state} message={item.message} />
          {onDismiss && item.state !== "pending" ? (
            <button type="button" aria-label="关闭操作反馈" onClick={() => onDismiss(item.id)}>
              <X aria-hidden="true" size={15} />
            </button>
          ) : null}
        </div>
      ))}
    </aside>
  );
}
