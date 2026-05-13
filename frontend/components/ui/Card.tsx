"use client";

import type { HTMLAttributes, ReactNode } from "react";

type Tone = "default" | "raised" | "overlay";

const TONE_CLASS: Record<Tone, string> = {
  default: "surface",
  raised: "surface-raised",
  overlay: "surface-overlay",
};

export interface CardProps extends HTMLAttributes<HTMLDivElement> {
  tone?: Tone;
  padded?: boolean;
  children?: ReactNode;
}

/**
 * Surface primitive. Maps `tone` onto the design-token utilities defined in
 * globals.css. Stays out of the way: only adds padding when `padded` is set,
 * passes everything else through so callers can layer flex/grid on top.
 */
export function Card({
  tone = "default",
  padded = true,
  className = "",
  children,
  ...rest
}: CardProps) {
  const cls = [TONE_CLASS[tone], padded ? "p-3" : "", className]
    .filter(Boolean)
    .join(" ");
  return (
    <div className={cls} {...rest}>
      {children}
    </div>
  );
}
