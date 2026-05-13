"use client";

import { forwardRef, type SelectHTMLAttributes, type ReactNode } from "react";
import { HelpIcon } from "./HelpIcon";

/**
 * Thin wrapper around the native <select>, styled to match <Input>. Native
 * options dropdowns keep keyboard / screen-reader behaviour for free.
 */
export interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label?: string;
  description?: string;
  error?: string;
  required?: boolean;
  /** Right-aligned hint shown next to the label, mirroring <Input suffix>. */
  suffix?: ReactNode;
}

let uid = 0;

export const Select = forwardRef<HTMLSelectElement, SelectProps>(function Select(
  {
    label,
    description,
    error,
    required,
    suffix,
    id,
    className = "",
    children,
    ...rest
  },
  ref,
) {
  const resolvedId =
    id ?? `lf-select-${(typeof window === "undefined" ? "s" : "c")}-${++uid}`;
  const stateBorder = error
    ? "border-danger bg-danger/5"
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
      <select
        ref={ref}
        id={resolvedId}
        required={required}
        aria-invalid={error ? true : undefined}
        className={
          `w-full rounded-sm bg-canvas border px-2 py-1.5 text-sm text-slate-100 ` +
          `focus-ring ${stateBorder} ${className}`
        }
        {...rest}
      >
        {children}
      </select>
      {error && (
        <p role="alert" className="text-[11px] text-danger mt-1">
          {error}
        </p>
      )}
    </div>
  );
});
