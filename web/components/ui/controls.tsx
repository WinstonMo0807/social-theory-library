import type { ComponentPropsWithRef } from "react";

export type ButtonProps = ComponentPropsWithRef<"button">;

/** Native controls keep form submission, refs and existing page classes intact. */
export function Button({ type = "button", ...props }: ButtonProps) {
  return <button type={type} {...props} />;
}

export type IconButtonProps = ButtonProps & { "aria-label": string };

export function IconButton(props: IconButtonProps) {
  return <Button {...props} />;
}

export function Input(props: ComponentPropsWithRef<"input">) {
  return <input {...props} />;
}

export function Textarea(props: ComponentPropsWithRef<"textarea">) {
  return <textarea {...props} />;
}

export function Select(props: ComponentPropsWithRef<"select">) {
  return <select {...props} />;
}

export function SearchInput({ autoComplete = "off", ...props }: Omit<ComponentPropsWithRef<"input">, "type">) {
  return <Input autoComplete={autoComplete} {...props} type="search" />;
}

export function Badge(props: ComponentPropsWithRef<"span">) {
  return <span {...props} />;
}
