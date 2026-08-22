"use client";

import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";

/**
 * Tiny spinner used for the `loading` state. 14×14 inline SVG so we don't
 * pay for an icon library, and it spins via Tailwind's `animate-spin`.
 */
function Spinner({ className = "" }: { className?: string }) {
  return (
    <svg
      className={`animate-spin ${className}`}
      width={14}
      height={14}
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
    >
      <circle
        cx={12}
        cy={12}
        r={9}
        stroke="currentColor"
        strokeWidth={3}
        opacity={0.25}
      />
      <path
        d="M21 12a9 9 0 0 1-9 9"
        stroke="currentColor"
        strokeWidth={3}
        strokeLinecap="round"
      />
    </svg>
  );
}

type Variant = "primary" | "secondary" | "ghost";
type Size = "sm" | "md";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  leftIcon?: ReactNode;
  rightIcon?: ReactNode;
}

const VARIANT_CLASS: Record<Variant, string> = {
  primary: "btn-primary",
  secondary: "btn-secondary",
  ghost:
    "inline-flex items-center justify-center gap-1.5 rounded-md font-medium " +
    "text-slate-300 hover:text-slate-100 hover:bg-surface-raised " +
    "disabled:opacity-50 disabled:cursor-not-allowed " +
    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent " +
    "focus-visible:ring-offset-2 focus-visible:ring-offset-canvas " +
    "transition-colors",
};

const SIZE_CLASS: Record<Size, string> = {
  sm: "px-2 py-1 text-xs",
  md: "px-3 py-1.5 text-sm",
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  {
    variant = "secondary",
    size = "md",
    loading = false,
    leftIcon,
    rightIcon,
    disabled,
    className = "",
    children,
    type,
    ...rest
  },
  ref,
) {
  // .btn-primary / .btn-secondary already include px/py defaults. We only
  // apply a sizing override for the ghost variant, and for explicit `sm`
  // sizing where the caller wants a tighter footprint.
  const needsSize = variant === "ghost" || size === "sm";
  const cls = [
    VARIANT_CLASS[variant],
    needsSize ? SIZE_CLASS[size] : "",
    className,
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <button
      ref={ref}
      type={type ?? "button"}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={cls}
      {...rest}
    >
      {loading ? <Spinner /> : leftIcon}
      {children}
      {!loading && rightIcon}
    </button>
  );
});
