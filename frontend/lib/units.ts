/**
 * Unit helpers for length values.
 *
 * The backend's atlc3 library accepts inputs in either canonical SI meters
 * (a number) or a unit string ("6mil", "4mm", "1.4mil", "30AWG"). The GUI
 * keeps form state as the user-typed *string* so we never lose precision
 * to a round-trip conversion. This module's job is purely to:
 *
 *   - Detect the unit suffix (or absence of one).
 *   - Provide quick-add suffix helpers when the user toggles preference.
 *   - Convert canonical numeric meters → display string in chosen unit.
 *   - Persist the unit preference to localStorage.
 */

export type LengthUnit = "mil" | "mm" | "in" | "um";

export const UNIT_TO_METERS: Record<LengthUnit, number> = {
  mil: 25.4e-6,
  mm: 1e-3,
  in: 25.4e-3,
  um: 1e-6,
};

const STORAGE_KEY = "atlc3-gui:length-unit";

export function getPreferredUnit(): LengthUnit {
  if (typeof window === "undefined") return "mil";
  const stored = window.localStorage.getItem(STORAGE_KEY);
  if (stored && stored in UNIT_TO_METERS) return stored as LengthUnit;
  return "mil";
}

export function setPreferredUnit(unit: LengthUnit): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(STORAGE_KEY, unit);
}

const UNIT_REGEX = /^\s*(-?\d+(?:\.\d+)?)\s*(mil|mm|in|inch|um|µm|cm|m)?\s*$/i;

export type ParsedLength = {
  value: number;
  unit: LengthUnit | null;
};

/**
 * Try to parse a user-typed string into (numeric value, unit). Returns null
 * if unparseable. Doesn't convert to meters. That's the backend's job; we
 * just want the display-side decomposition.
 */
export function parseLengthStr(input: string): ParsedLength | null {
  const m = input.match(UNIT_REGEX);
  if (!m) return null;
  const value = parseFloat(m[1]);
  if (Number.isNaN(value)) return null;
  const rawUnit = (m[2] || "").toLowerCase();
  let unit: LengthUnit | null;
  switch (rawUnit) {
    case "mil":
      unit = "mil";
      break;
    case "mm":
      unit = "mm";
      break;
    case "in":
    case "inch":
      unit = "in";
      break;
    case "um":
    case "µm":
      unit = "um";
      break;
    case "":
      unit = null;
      break;
    default:
      return null; // 'cm', 'm' etc. are valid but we don't surface in toggle
  }
  return { value, unit };
}

/**
 * Convert a length string to canonical meters. Returns null on parse fail.
 * If no unit is given, treats the value as already meters (matches atlc3's
 * Pydantic Length validator behavior).
 */
export function toMeters(input: string, fallbackUnit?: LengthUnit): number | null {
  const parsed = parseLengthStr(input);
  if (!parsed) return null;
  const unit = parsed.unit ?? fallbackUnit ?? null;
  if (unit === null) return parsed.value; // bare number → meters
  return parsed.value * UNIT_TO_METERS[unit];
}

/**
 * Format meters as a string in the given unit, with sensible decimals.
 * 0.0808mm has different precision needs than 50mil.
 */
export function formatMeters(meters: number, unit: LengthUnit): string {
  const value = meters / UNIT_TO_METERS[unit];
  // Decide decimals: aim for 3-4 significant digits, but at least 2 dp for mils.
  const abs = Math.abs(value);
  let digits: number;
  if (abs >= 100) digits = 1;
  else if (abs >= 10) digits = 2;
  else if (abs >= 1) digits = 3;
  else if (abs >= 0.1) digits = 4;
  else digits = 5;
  return `${value.toFixed(digits)}${unit}`;
}

/**
 * Convert a user-input string from one unit to another, preserving meaning.
 * If the input has no explicit unit, ``fromUnit`` is assumed.
 */
export function convertLengthStr(
  input: string,
  fromUnit: LengthUnit,
  toUnit: LengthUnit,
): string | null {
  const meters = toMeters(input, fromUnit);
  if (meters === null) return null;
  return formatMeters(meters, toUnit);
}

/**
 * Append the preferred unit to a bare numeric string. Useful as the "format
 * on blur" pass so the form ends up storing values like "6mil" rather than
 * "6". Pass-through if input already has a unit.
 */
export function ensureUnit(input: string, unit: LengthUnit): string {
  const parsed = parseLengthStr(input);
  if (!parsed) return input;
  if (parsed.unit !== null) return input;
  return `${parsed.value}${unit}`;
}
