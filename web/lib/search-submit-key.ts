import type { KeyboardEvent } from "react";

/** Multiline search prompts: Enter submits the existing form; Shift+Enter adds a line. */
export function submitSearchOnEnter(event: KeyboardEvent<HTMLTextAreaElement>) {
  if (event.key !== "Enter" || event.shiftKey || event.ctrlKey || event.metaKey || event.altKey
    || event.nativeEvent.isComposing || event.nativeEvent.keyCode === 229) return;
  event.preventDefault();
  if (event.repeat) return;
  const form = event.currentTarget.form;
  const submitter = form?.querySelector<HTMLButtonElement | HTMLInputElement>('[type="submit"]');
  // Use the same disabled state, validation and submit handler as a button click.
  if (form && submitter && !submitter.disabled) form.requestSubmit(submitter);
}
