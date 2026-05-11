"use client";

import { useEffect, useMemo, useState } from "react";
import {
  calculate,
  describeGeometry,
  listGeometries,
  type GeometrySchema,
  type GeometryListItem,
} from "@/lib/api";
import { useGuiStore } from "@/lib/store";
import { ensureUnit, parseLengthStr } from "@/lib/units";
import { CustomUsermapPanel } from "./CustomUsermapPanel";
import { MaterialPicker } from "./MaterialPicker";
import { StackupEditor } from "./StackupEditor";
import { GeometryDiagram } from "./diagrams";

// Length-typed fields use a unit-aware input. A field is treated as a
// length if its name appears here OR its schema has a numeric type with
// gt:0 and a description mentioning "length"/"thickness"/"width"/etc.
const KNOWN_LENGTH_FIELDS = new Set([
  "W",
  "H",
  "T",
  "S",
  "B",
  "H1",
  "H2",
  "H_between",
  "a",
  "x",
  "y",
]);

type FieldInfo = {
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

function classifyFields(schema: GeometrySchema): FieldInfo[] {
  const required = new Set(schema.required);
  const defs = schema.$defs ?? {};
  const out: FieldInfo[] = [];
  for (const [name, prop] of Object.entries(schema.properties)) {
    if (name === "type") continue;
    const isBool = prop.type === "boolean";
    let nestedFields: FieldInfo[] | undefined;
    if (typeof prop.$ref === "string") {
      const refName = prop.$ref.replace(/^#\/\$defs\//, "");
      const def = defs[refName];
      if (def?.properties) {
        const nestedReq = new Set(def.required ?? []);
        nestedFields = Object.entries(def.properties).map(([nName, nProp]) => ({
          name: nName,
          required: nestedReq.has(nName),
          isLength: KNOWN_LENGTH_FIELDS.has(nName),
          description: nProp.description ?? nProp.title,
          defaultValue: nProp.default,
        }));
      }
    }
    out.push({
      name,
      required: required.has(name),
      isLength: KNOWN_LENGTH_FIELDS.has(name) && !nestedFields && !isBool,
      description: prop.description ?? prop.title,
      defaultValue: prop.default,
      nestedFields,
      isBoolean: isBool,
    });
  }
  out.sort((a, b) => {
    if (a.required !== b.required) return a.required ? -1 : 1;
    return a.name.localeCompare(b.name);
  });
  return out;
}

function NestedFieldRow({
  field,
  value,
  onChange,
  unit,
}: {
  field: FieldInfo;
  value: Record<string, unknown> | undefined;
  onChange: (v: Record<string, unknown>) => void;
  unit: "mil" | "mm" | "in" | "um";
}) {
  const current = value ?? {};
  return (
    <div className="bg-navy-900/40 border border-navy-800 rounded p-2 space-y-2">
      <div className="text-xs text-slate-400" title={field.description}>
        {field.name}
        {field.required && <span className="text-rose-400 ml-0.5">*</span>}
      </div>
      <div className="pl-2 space-y-2">
        {field.nestedFields!.map((sub) => (
          <FieldRow
            key={sub.name}
            field={sub}
            value={String((current[sub.name] as string | number | undefined) ?? "")}
            onChange={(v) => onChange({ ...current, [sub.name]: v })}
            unit={unit}
          />
        ))}
      </div>
    </div>
  );
}

function BooleanRow({
  field,
  value,
  onChange,
}: {
  field: FieldInfo;
  value: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <label className="flex items-center justify-between gap-2 text-xs" title={field.description}>
      <span className="text-slate-400">
        {field.name}
        {field.required && <span className="text-rose-400 ml-0.5">*</span>}
      </span>
      <input
        type="checkbox"
        checked={value}
        onChange={(e) => onChange(e.target.checked)}
        className="accent-emerald-500 w-4 h-4"
      />
    </label>
  );
}

function FieldRow({
  field,
  value,
  onChange,
  unit,
}: {
  field: FieldInfo;
  value: string;
  onChange: (v: string) => void;
  unit: "mil" | "mm" | "in" | "um";
}) {
  const [touched, setTouched] = useState(false);

  const validation = useMemo(() => {
    if (!field.required && value === "") return { ok: true };
    if (field.required && value === "") {
      return touched ? { ok: false, msg: "required" } : { ok: true };
    }
    if (field.isLength) {
      const parsed = parseLengthStr(value);
      if (!parsed) return { ok: false, msg: "invalid length" };
      if (parsed.value <= 0) return { ok: false, msg: "must be > 0" };
      return { ok: true };
    }
    // Generic float field (er, tan_delta, etc.)
    if (Number.isNaN(Number(value))) return { ok: false, msg: "must be a number" };
    return { ok: true };
  }, [field, value, touched]);

  const showError = touched && !validation.ok;
  const placeholder = field.isLength ? `e.g. 6${unit}` : field.name === "er" ? "4.4" : "";

  return (
    <label className="block" title={field.description}>
      <span className="flex items-center gap-1 text-xs text-slate-400 mb-1">
        <span>
          {field.name}
          {field.required && <span className="text-rose-400 ml-0.5">*</span>}
        </span>
        {field.isLength && (
          <span className="text-[10px] text-slate-500 ml-auto">[{unit}]</span>
        )}
      </span>
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onBlur={() => {
          setTouched(true);
          if (field.isLength && value && parseLengthStr(value)?.unit === null) {
            onChange(ensureUnit(value, unit));
          }
        }}
        placeholder={placeholder}
        className={
          "w-full bg-navy-900 border rounded px-2 py-1.5 text-slate-100 placeholder-slate-600 " +
          (showError ? "border-rose-500" : "border-navy-700")
        }
      />
      {showError && (
        <span className="block text-[11px] text-rose-400 mt-0.5">⚠ {validation.msg}</span>
      )}
    </label>
  );
}

type Tab = "builtin" | "custom";

export function GeometryPanel() {
  const geometry = useGuiStore((s) => s.geometry);
  const setGeometry = useGuiStore((s) => s.setGeometry);
  const setLastResult = useGuiStore((s) => s.setLastResult);
  const setIsSolving = useGuiStore((s) => s.setIsSolving);
  const unit = useGuiStore((s) => s.unit);
  const frequency = useGuiStore((s) => s.frequency);
  const setFrequency = useGuiStore((s) => s.setFrequency);

  const [tab, setTab] = useState<Tab>("builtin");
  const [types, setTypes] = useState<GeometryListItem[]>([]);
  const [schema, setSchema] = useState<GeometrySchema | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [stackupOpen, setStackupOpen] = useState(false);

  const currentType = (geometry?.type as string | undefined) ?? "";

  // Switch tab automatically if the current geometry came from elsewhere
  // (chat agent, custom upload, etc.)
  useEffect(() => {
    if (geometry?.usermap_uri) setTab("custom");
    else if (geometry?.type) setTab("builtin");
  }, [geometry]);

  useEffect(() => {
    listGeometries().then(setTypes).catch((e) => setErr(String(e)));
  }, []);

  useEffect(() => {
    if (!currentType) {
      setSchema(null);
      return;
    }
    let cancelled = false;
    describeGeometry(currentType)
      .then((s) => {
        if (!cancelled) setSchema(s);
      })
      .catch((e) => {
        if (!cancelled) setErr(String(e));
      });
    return () => {
      cancelled = true;
    };
  }, [currentType]);

  const fields = useMemo(() => (schema ? classifyFields(schema) : []), [schema]);

  function setField(field: string, value: string) {
    const current = (geometry ?? { type: currentType }) as Record<string, unknown>;
    setGeometry({ ...current, [field]: value });
  }

  function setType(type: string) {
    setGeometry(type ? { type } : null);
  }

  async function runCalculate() {
    if (!geometry) return;
    // Allow Calculate even when there's no `type` (e.g. usermap_uri-only path).
    setBusy(true);
    setIsSolving(true);
    setErr(null);
    try {
      const freq = frequency.trim();
      const result = await calculate(
        geometry as Record<string, unknown>,
        freq === "" ? undefined : freq,
      );
      setLastResult(result as unknown as Record<string, unknown>);
    } catch (e: unknown) {
      setErr(extractErrorMessage(e));
    } finally {
      setBusy(false);
      setIsSolving(false);
    }
  }

  const showDiagram = tab === "builtin" && currentType !== "";

  return (
    <div className="flex h-full flex-col bg-navy-950 border-r border-navy-800">
      <div className="px-4 py-2 border-b border-navy-800 flex items-center justify-between">
        <span className="text-xs uppercase tracking-wider text-slate-500">Geometry</span>
        <div className="flex items-center gap-1 text-xs">
          {(["builtin", "custom"] as const).map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => setTab(t)}
              className={
                tab === t
                  ? "px-2 py-0.5 rounded bg-navy-800 text-slate-100"
                  : "px-2 py-0.5 rounded text-slate-500 hover:text-slate-300"
              }
            >
              {t === "builtin" ? "Built-in" : "Custom BMP"}
            </button>
          ))}
        </div>
      </div>

      {/* Diagram preview (built-in only) */}
      {showDiagram && (
        <div className="border-b border-navy-800 p-3 bg-navy-900/40">
          <GeometryDiagram />
        </div>
      )}

      <div className="flex-1 overflow-y-auto p-3 space-y-3 text-sm">
        {tab === "builtin" ? (
          <>
            <label className="block">
              <span className="flex items-center gap-1 text-xs text-slate-400 mb-1">
                <span>Frequency</span>
                <span className="text-[10px] text-slate-500 ml-auto italic">
                  optional — for loss / dispersion
                </span>
              </span>
              <input
                type="text"
                value={frequency}
                onChange={(e) => setFrequency(e.target.value)}
                placeholder="e.g. 1GHz"
                className="w-full bg-navy-900 border border-navy-700 rounded px-2 py-1.5 text-slate-100 placeholder-slate-600"
              />
            </label>

            <label className="block">
              <span className="block text-xs text-slate-400 mb-1">Type</span>
              <select
                value={currentType}
                onChange={(e) => setType(e.target.value)}
                className="w-full bg-navy-900 border border-navy-700 rounded px-2 py-1.5 text-slate-100"
              >
                <option value="">(select type)</option>
                {types.map((t) => (
                  <option key={t.type} value={t.type} title={t.doc}>
                    {t.type}
                  </option>
                ))}
              </select>
            </label>

            {schema && fields.length === 0 && (
              <div className="text-slate-500 text-xs">No editable fields.</div>
            )}

            {/* Material picker — appears when both er + tan_delta are
                expected fields (i.e. for any insulator-using geometry). */}
            {fields.some((f) => f.name === "er") && (
              <MaterialPicker
                onPick={(er, tanD, _name) => {
                  const current = (geometry ?? { type: currentType }) as Record<string, unknown>;
                  setGeometry({
                    ...current,
                    er,
                    ...(fields.some((f) => f.name === "tan_delta") ? { tan_delta: tanD } : {}),
                  });
                }}
                currentEr={typeof geometry?.er === "number" ? geometry.er : Number(geometry?.er)}
                currentTanDelta={
                  typeof geometry?.tan_delta === "number"
                    ? geometry.tan_delta
                    : Number(geometry?.tan_delta ?? 0)
                }
              />
            )}

            {/* Stackup editor — only meaningful on stripline_asymmetric */}
            {currentType === "stripline_asymmetric" && (
              <button
                type="button"
                onClick={() => setStackupOpen(true)}
                className="w-full text-xs bg-navy-800 hover:bg-slate-700 text-slate-200 py-1.5 rounded border border-navy-700"
              >
                ▤ Edit multi-layer stack…
              </button>
            )}

            {fields.map((f) => {
              if (f.nestedFields) {
                return (
                  <NestedFieldRow
                    key={f.name}
                    field={f}
                    value={geometry?.[f.name] as Record<string, unknown> | undefined}
                    onChange={(v) => {
                      const current = (geometry ?? { type: currentType }) as Record<
                        string,
                        unknown
                      >;
                      setGeometry({ ...current, [f.name]: v });
                    }}
                    unit={unit}
                  />
                );
              }
              if (f.isBoolean) {
                return (
                  <BooleanRow
                    key={f.name}
                    field={f}
                    value={Boolean(geometry?.[f.name])}
                    onChange={(v) => {
                      const current = (geometry ?? { type: currentType }) as Record<
                        string,
                        unknown
                      >;
                      setGeometry({ ...current, [f.name]: v });
                    }}
                  />
                );
              }
              return (
                <FieldRow
                  key={f.name}
                  field={f}
                  value={String((geometry?.[f.name] as string | number | undefined) ?? "")}
                  onChange={(v) => setField(f.name, v)}
                  unit={unit}
                />
              );
            })}
          </>
        ) : (
          <CustomUsermapPanel />
        )}

        {err && (
          <div className="bg-rose-950/40 border border-rose-800 rounded p-2 text-xs text-rose-300">
            <div className="font-semibold mb-1">Error</div>
            <div className="break-words">{err}</div>
          </div>
        )}
      </div>
      <div className="p-3 border-t border-navy-800">
        <button
          onClick={runCalculate}
          disabled={!geometry || busy}
          className="w-full bg-emerald-600 hover:bg-emerald-500 disabled:bg-slate-700 disabled:text-slate-500 text-white text-sm py-2 rounded transition-colors"
        >
          {busy ? "Solving…" : "Calculate Z₀"}
        </button>
      </div>

      <StackupEditor open={stackupOpen} onClose={() => setStackupOpen(false)} />
    </div>
  );
}

function extractErrorMessage(e: unknown): string {
  if (e instanceof Error) {
    // Backend errors come through fetch as "calculate: 400 <body>"
    const m = e.message.match(/^[a-zA-Z]+: \d+ (.+)$/);
    if (m) {
      try {
        const body = JSON.parse(m[1]);
        if (typeof body === "object" && body !== null && "detail" in body) {
          return String((body as { detail: unknown }).detail);
        }
      } catch {
        return m[1];
      }
    }
    return e.message;
  }
  return String(e);
}
