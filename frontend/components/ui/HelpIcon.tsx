"use client";

/**
 * Tiny info badge that surfaces a field's description on hover/focus via the
 * native `title` attribute. We deliberately keep `tabIndex={-1}` so the help
 * marker doesn't add an extra tab stop to every labelled control — keyboard
 * users still get the description from the underlying input's `aria-describedby`
 * (when the caller wires one up).
 */
export function HelpIcon({ description }: { description?: string }) {
  if (!description) return null;
  return (
    <button
      type="button"
      tabIndex={-1}
      title={description}
      aria-label={`Help: ${description}`}
      className="inline-flex items-center justify-center w-3.5 h-3.5 rounded-full
                 text-[10px] leading-none text-slate-500 hover:text-slate-300
                 transition-colors"
    >
      <span aria-hidden="true">&#9432;</span>
    </button>
  );
}
