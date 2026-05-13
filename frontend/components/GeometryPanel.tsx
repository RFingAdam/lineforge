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
import { CustomUsermapPanel } from "./CustomUsermapPanel";
import { MaterialPicker } from "./MaterialPicker";
import { StackupEditor } from "./StackupEditor";
import { GeometryDiagram } from "./diagrams";
import {
  BooleanRow,
  FieldRow,
  NestedFieldRow,
  XCircleIcon,
  type FieldInfo,
} from "./GeometryFieldRows";
import { Button, Card, Input, Section, Select } from "./ui";

// Length-typed fields use a unit-aware input.
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

const DIELECTRIC_FIELDS = new Set(["er", "er2", "tan_delta"]);

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

type SectionId = "dielectric" | "dimensions" | "advanced";

function sectionFor(f: FieldInfo): SectionId {
  if (DIELECTRIC_FIELDS.has(f.name)) return "dielectric";
  if (f.isLength) return "dimensions";
  // Booleans, nested fields, anything non-required and non-dimensional.
  return "advanced";
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

  useEffect(() => {
    if (geometry?.usermap_uri) setTab("custom");
    else if (geometry?.type) setTab("builtin");
  }, [geometry]);

  useEffect(() => {
    listGeometries()
      .then(setTypes)
      .catch((e) => setErr(String(e)));
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
  const buckets = useMemo(() => {
    const b: Record<SectionId, FieldInfo[]> = {
      dielectric: [],
      dimensions: [],
      advanced: [],
    };
    for (const f of fields) b[sectionFor(f)].push(f);
    return b;
  }, [fields]);

  function setField(field: string, value: string) {
    const current = (geometry ?? { type: currentType }) as Record<string, unknown>;
    setGeometry({ ...current, [field]: value });
  }

  function setType(type: string) {
    setGeometry(type ? { type } : null);
  }

  async function runCalculate() {
    if (!geometry) return;
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

  function renderField(f: FieldInfo) {
    if (f.nestedFields) {
      return (
        <NestedFieldRow
          key={f.name}
          field={f}
          value={geometry?.[f.name] as Record<string, unknown> | undefined}
          onChange={(v) => {
            const current = (geometry ?? { type: currentType }) as Record<string, unknown>;
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
            const current = (geometry ?? { type: currentType }) as Record<string, unknown>;
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
  }

  return (
    <div className="flex h-full flex-col">
      {/* ── header ─────────────────────────────────────────────────────── */}
      <div className="px-3 py-2 border-b border-border-subtle flex items-center justify-between gap-2">
        <span className="text-[11px] uppercase tracking-widest text-slate-400 font-display">
          Geometry
        </span>
        <div
          className="flex items-center gap-0.5 bg-surface-raised rounded-md p-0.5"
          role="tablist"
          aria-label="Geometry source"
        >
          {(["builtin", "custom"] as const).map((t) => {
            const active = tab === t;
            return (
              <Button
                key={t}
                variant="ghost"
                size="sm"
                role="tab"
                aria-selected={active}
                onClick={() => setTab(t)}
                className={
                  active
                    ? "bg-surface-overlay text-slate-100"
                    : "text-slate-400 hover:text-slate-200"
                }
              >
                {t === "builtin" ? "Built-in" : "Custom BMP"}
              </Button>
            );
          })}
        </div>
      </div>

      {/* ── body ───────────────────────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto p-3 space-y-4 text-sm">
        {tab === "builtin" ? (
          <>
            <Section title="Topology">
              <Select
                label="Type"
                value={currentType}
                onChange={(e) => setType(e.target.value)}
              >
                <option value="">(select type)</option>
                {types.map((t) => (
                  <option key={t.type} value={t.type} title={t.doc}>
                    {t.type}
                  </option>
                ))}
              </Select>
              {currentType && (
                <Card tone="raised" padded>
                  <GeometryDiagram />
                </Card>
              )}
            </Section>

            <Section title="Frequency" subtitle="optional · for loss / dispersion">
              <Input
                label="Frequency"
                suffix="Hz / MHz / GHz"
                value={frequency}
                onChange={(e) => setFrequency(e.target.value)}
                placeholder="e.g. 1GHz"
              />
            </Section>

            {schema && fields.length === 0 && (
              <div className="text-slate-500 text-xs">No editable fields.</div>
            )}

            {buckets.dielectric.length > 0 && (
              <Section title="Dielectric">
                {fields.some((f) => f.name === "er") && (
                  <MaterialPicker
                    onPick={(er, tanD, _name) => {
                      const current = (geometry ?? { type: currentType }) as Record<
                        string,
                        unknown
                      >;
                      setGeometry({
                        ...current,
                        er,
                        ...(fields.some((f) => f.name === "tan_delta")
                          ? { tan_delta: tanD }
                          : {}),
                      });
                    }}
                    currentEr={
                      typeof geometry?.er === "number" ? geometry.er : Number(geometry?.er)
                    }
                    currentTanDelta={
                      typeof geometry?.tan_delta === "number"
                        ? geometry.tan_delta
                        : Number(geometry?.tan_delta ?? 0)
                    }
                  />
                )}
                {buckets.dielectric.map(renderField)}
              </Section>
            )}

            {buckets.dimensions.length > 0 && (
              <Section title="Dimensions">
                {buckets.dimensions.map(renderField)}
              </Section>
            )}

            {currentType === "stripline_asymmetric" && (
              <Section title="Stackup" collapsible defaultOpen={false}>
                <Button
                  variant="secondary"
                  className="w-full"
                  onClick={() => setStackupOpen(true)}
                >
                  ▤ Edit multi-layer stack…
                </Button>
              </Section>
            )}

            {buckets.advanced.length > 0 && (
              <Section title="Advanced" collapsible defaultOpen={false}>
                {buckets.advanced.map(renderField)}
              </Section>
            )}
          </>
        ) : (
          <CustomUsermapPanel />
        )}

        {err && (
          <Card
            tone="raised"
            role="alert"
            className="border-danger/60 bg-danger/10 flex gap-2 items-start"
          >
            <XCircleIcon />
            <div className="min-w-0">
              <div className="text-xs font-semibold text-danger mb-0.5">Error</div>
              <div className="text-xs text-slate-200 break-words">{err}</div>
            </div>
          </Card>
        )}
      </div>

      {/* ── primary CTA ────────────────────────────────────────────────── */}
      <div className="p-3 border-t border-border-subtle bg-surface/40">
        <Button
          variant="primary"
          className="w-full"
          loading={busy}
          disabled={!geometry || busy}
          onClick={runCalculate}
        >
          {busy ? "Calculating…" : "Calculate Z₀"}
        </Button>
      </div>

      <StackupEditor open={stackupOpen} onClose={() => setStackupOpen(false)} />
    </div>
  );
}

function extractErrorMessage(e: unknown): string {
  if (e instanceof Error) {
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
