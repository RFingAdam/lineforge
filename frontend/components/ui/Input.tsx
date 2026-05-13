"use client";

import { forwardRef, type InputHTMLAttributes, type ReactNode } from "react";
import { HelpIcon } from "./HelpIcon";

/** ✓ glyph for valid + touched fields. Currently unused at the visual level
 *  (we only colour the border) but kept here so a follow-up agent can opt in
 *  without re-deriving the icon. */
function CheckIcon({ className = "" }: { className?: string }) {
  return (
    <svg
      className={className}
      width={12}
      height={12}
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
    >
      <path
        d="M5 12l4 4L19 6"
        stroke="currentColor"
        strokeWidth={2.5}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function XIcon({ className = "" }: { className?: string }) {
  return (
    <svg
      className={className}
      width={12}
      height={12}
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
    >
      <path
        d="M6 6l12 12M18 6L6 18"
        stroke="currentColor"
        strokeWidth={2.5}
        strokeLinecap="round"
      />
    </svg>
  );
}

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  /** Visible label rendered above the input. */
  label?: string;
  /** Right-aligned hint shown next to the label, e.g. unit `[mil]`. */
  suffix?: ReactNode;
  /** Long-form description surfaced via the help icon's tooltip. */
  description?: string;
  /** Error message — shown red under the input. Also drives border colour. */
  error?: string;
  /** Marks the label with a red asterisk and sets the underlying input. */
  required?: boolean;
  /** When true (and no error), draws a subtle success border. */
  valid?: boolean;
}

let uid = 0;

export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  {
    label,
    suffix,
    description,
    error,
    required,
    valid,
    id,
    className = "",
    ...inputProps
  },
  ref,
) {
  // Stable id so the <label htmlFor> hooks up to the input even when the
  // caller doesn't pass one. Using a counter (vs useId) keeps the component
  // SSR/CSR equivalent in our 100% client-side panel.
  const resolvedId =
    id ?? `lf-input-${(typeof window === "undefined" ? "s" : "c")}-${++uid}`;

  const stateBorder = error
    ? "border-danger bg-danger/5"
    : valid
      ? "border-success/50"
      : "border-border-subtle";

  return (
    <div className="block">
      {(label || suffix) && (
        <label
          htmlFor={resolvedId}
          className="flex items-center justify-between gap-2 text-xs text-slate-400 mb-1"
        >
          <span className="flex items-center gap-1">
            <span>
              {label}
              {required && (
                <span aria-hidden="true" className="text-danger ml-0.5">
                  *
                </span>
              )}
            </span>
            <HelpIcon description={description} />
          </span>
          {suffix && (
            <span className="text-[10px] text-slate-500 font-mono">
              {suffix}
            </span>
          )}
        </label>
      )}
      <input
        ref={ref}
        id={resolvedId}
        required={required}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? `${resolvedId}-err` : undefined}
        className={
          `w-full rounded-sm bg-canvas border px-2 py-1.5 text-sm text-slate-100 ` +
          `placeholder-slate-600 focus-ring ${stateBorder} ${className}`
        }
        {...inputProps}
      />
      {error && (
        <p
          id={`${resolvedId}-err`}
          role="alert"
          className="text-[11px] text-danger mt-1 flex items-center gap-1"
        >
          <XIcon className="text-danger" />
          <span>{error}</span>
        </p>
      )}
    </div>
  );
});

// Re-export the icons so consumers (e.g. error banners in panels) can reuse
// the same visual vocabulary without redefining their own SVGs.
export { CheckIcon, XIcon };
