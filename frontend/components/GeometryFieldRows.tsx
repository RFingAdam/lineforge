"use client";

import { useMemo, useState } from "react";
import { ensureUnit, parseLengthStr } from "@/lib/units";
import { Card } from "./ui/Card";
import { HelpIcon } from "./ui/HelpIcon";
import { Input } from "./ui/Input";

/**
 * Row primitives used by GeometryPanel. They're split out so the main panel
 * stays under ~600 lines and reads top-to-bottom as a layout description
 * rather than a wall of validation logic.
 */

export type FieldInfo = {
  name: string;
  required: boolean;
  isLength: boolean;
  description?: string;
  defaultValue?: unknown;
  /** When the schema property is a $ref into $defs, resolve to the nested
   * fields (e.g. WirePosition → [x, y]). Otherwise undefined. */
  nestedFields?: FieldInfo[];
  /** True for type=boolean. */
  isBoolean?: boolean;
};

export type LengthUnit = "mil" | "mm" | "in" | "um";

export function FieldRow({
  field,
  value,
  onChange,
  unit,
}: {
  field: FieldInfo;
  value: string;
  onChange: (v: string) => void;
  unit: LengthUnit;
}) {
  const [touched, setTouched] = useState(false);

  const validation = useMemo(() => {
    if (!field.required && value === "") return { ok: true as const };
    if (field.required && value === "") {
      return touched
        ? { ok: false as const, msg: "required" }
        : { ok: true as const };
    }
    if (field.isLength) {
      const parsed = parseLengthStr(value);
      if (!parsed) return { ok: false as const, msg: "invalid length" };
      if (parsed.value <= 0) return { ok: false as const, msg: "must be > 0" };
      return { ok: true as const };
    }
    // Generic float field (er, tan_delta, etc.)
    if (Number.isNaN(Number(value))) {
      return { ok: false as const, msg: "must be a number" };
    }
    return { ok: true as const };
  }, [field, value, touched]);

  const showError = touched && !validation.ok;
  const placeholder = field.isLength
    ? `e.g. 6${unit}`
    : field.name === "er"
      ? "4.4"
      : "";

  return (
    <Input
      label={field.name}
      required={field.required}
      description={field.description}
      suffix={field.isLength ? `[${unit}]` : undefined}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      onBlur={() => {
        setTouched(true);
        if (field.isLength && value && parseLengthStr(value)?.unit === null) {
          onChange(ensureUnit(value, unit));
        }
      }}
      placeholder={placeholder}
      valid={touched && validation.ok && value !== ""}
      error={showError ? validation.msg : undefined}
    />
  );
}

export function BooleanRow({
  field,
  value,
  onChange,
}: {
  field: FieldInfo;
  value: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <label
      className="flex items-center justify-between gap-2 text-xs cursor-pointer
                 select-none py-1"
      title={field.description}
    >
      <span className="flex items-center gap-1 text-slate-300">
        <span>
          {field.name}
          {field.required && (
            <span aria-hidden="true" className="text-danger ml-0.5">
              *
            </span>
          )}
        </span>
        <HelpIcon description={field.description} />
      </span>
      <input
        type="checkbox"
        checked={value}
        onChange={(e) => onChange(e.target.checked)}
        className="accent-accent w-4 h-4 focus-ring rounded-xs"
      />
    </label>
  );
}

export function NestedFieldRow({
  field,
  value,
  onChange,
  unit,
}: {
  field: FieldInfo;
  value: Record<string, unknown> | undefined;
  onChange: (v: Record<string, unknown>) => void;
  unit: LengthUnit;
}) {
  const current = value ?? {};
  return (
    <Card tone="raised" padded className="space-y-2">
      <div className="flex items-center gap-1 text-xs text-slate-300">
        <span className="font-medium">
          {field.name}
          {field.required && (
            <span aria-hidden="true" className="text-danger ml-0.5">
              *
            </span>
          )}
        </span>
        <HelpIcon description={field.description} />
      </div>
      <div className="pl-1 space-y-2">
        {field.nestedFields!.map((sub) => (
          <FieldRow
            key={sub.name}
            field={sub}
            value={String(
              (current[sub.name] as string | number | undefined) ?? "",
            )}
            onChange={(v) => onChange({ ...current, [sub.name]: v })}
            unit={unit}
          />
        ))}
      </div>
    </Card>
  );
}

export function XCircleIcon() {
  return (
    <svg
      width={16}
      height={16}
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
      className="flex-shrink-0 text-danger"
    >
      <circle cx={12} cy={12} r={10} stroke="currentColor" strokeWidth={2} />
      <path
        d="M9 9l6 6M15 9l-6 6"
        stroke="currentColor"
        strokeWidth={2}
        strokeLinecap="round"
      />
    </svg>
  );
}
