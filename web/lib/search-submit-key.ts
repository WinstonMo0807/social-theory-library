import type { KeyboardEvent } from "react";

/** Safari can report the IME confirmation key as 229 after isComposing clears. */
export function isImeComposing(event: Pick<KeyboardEvent, "nativeEvent">) {
  return event.nativeEvent.isComposing || event.nativeEvent.keyCode === 229;
}

/** Multiline search prompts: Enter submits the existing form; Shift+Enter adds a line. */
export function submitSearchOnEnter(event: KeyboardEvent<HTMLTextAreaElement>) {
  if (event.key !== "Enter" || event.shiftKey || event.ctrlKey || event.metaKey || event.altKey
    || isImeComposing(event)) return;
  event.preventDefault();
  if (event.repeat) return;
  const form = event.currentTarget.form;
  const submitter = form?.querySelector<HTMLButtonElement | HTMLInputElement>('[type="submit"]');
  // Use the same disabled state, validation and submit handler as a button click.
  if (form && submitter && !submitter.disabled) form.requestSubmit(submitter);
}
