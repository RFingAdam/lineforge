/**
 * Thin REST client for the FastAPI backend.
 *
 * The Next.js dev server rewrites /api/* to http://localhost:8000/api/* so
 * we can call relative URLs from the browser without CORS dance.
 */

export type GeometryListItem = {
  type: string;
  class: string;
  doc: string;
  required_fields: string[];
};

export async function listGeometries(): Promise<GeometryListItem[]> {
  const r = await fetch('/api/geometries');
  if (!r.ok) throw new Error(`listGeometries: ${r.status}`);
  const body = (await r.json()) as { geometries: GeometryListItem[] };
  return body.geometries;
}

/**
 * The Pydantic JSON Schema for one geometry type — drives the form's
 * field rendering. Properties values include type / description / gt /
 * default / etc. Required fields are listed under the top-level "required".
 *
 * Nested objects (e.g. three_wire's WirePosition) appear as ``$ref``s
 * pointing into ``$defs``; the form classifier follows the ref to render
 * sub-forms.
 */
export type GeometrySchemaProp = {
  type?: string;
  title?: string;
  description?: string;
  default?: unknown;
  anyOf?: Array<Record<string, unknown>>;
  const?: unknown;
  exclusiveMinimum?: number;
  minimum?: number;
  $ref?: string;
};

export type GeometrySchemaDef = {
  type?: string;
  title?: string;
  description?: string;
  required?: string[];
  properties?: Record<string, GeometrySchemaProp>;
};

export type GeometrySchema = {
  type: string;
  title: string;
  required: string[];
  properties: Record<string, GeometrySchemaProp>;
  $defs?: Record<string, GeometrySchemaDef>;
};

export async function describeGeometry(name: string): Promise<GeometrySchema> {
  const r = await fetch(`/api/geometries/${encodeURIComponent(name)}`);
  if (!r.ok) throw new Error(`describeGeometry: ${r.status}`);
  return (await r.json()) as GeometrySchema;
}

export type CalculateResponse = {
  z0?: number;
  eps_eff?: number;
  vp?: number;
  td_per_inch?: number;
  method?: string;
  _kind: string;
  [k: string]: unknown;
};

export async function calculate(
  geometry: Record<string, unknown>,
  frequency?: number | string,
): Promise<CalculateResponse> {
  // Bitmap path: geometry has a usermap_uri instead of a type discriminator.
  const body =
    typeof geometry?.usermap_uri === "string"
      ? { usermap_uri: geometry.usermap_uri, frequency }
      : { geometry, frequency };
  const r = await fetch('/api/solve/calculate', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    const err = await r.text();
    throw new Error(`calculate: ${r.status} ${err}`);
  }
  return (await r.json()) as CalculateResponse;
}

export type SweepPoint = {
  params: Record<string, number>;
  result: Record<string, unknown> | null;
};

export type SweepResponse = {
  points: SweepPoint[];
  touchstone?: { path: string; n_ports: number; z_ref: number; line_length: string | number };
  touchstone_error?: string;
};

export async function runSweep(args: {
  geometry: Record<string, unknown>;
  parameter: string;
  values: number[];
  solver?: string;
  frequency?: number | string;
  touchstone_out?: string;
  line_length?: string | number;
  z_ref?: number;
}): Promise<SweepResponse> {
  const r = await fetch('/api/solve/sweep', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ solver: 'analytical', ...args }),
  });
  if (!r.ok) {
    const err = await r.text();
    throw new Error(`sweep: ${r.status} ${err}`);
  }
  return (await r.json()) as SweepResponse;
}

export async function getState(): Promise<unknown> {
  const r = await fetch('/api/state');
  if (!r.ok) throw new Error(`getState: ${r.status}`);
  return r.json();
}

export async function resetState(): Promise<void> {
  await fetch('/api/state/reset', { method: 'POST' });
}
