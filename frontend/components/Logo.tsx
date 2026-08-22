"use client";

/** atlc3 logo. A stylized transmission-line cross-section icon.
 *
 * Wave-line strip on top of a labeled εr dielectric over a green ground:
 * effectively a tiny microstrip schematic. Sized to inline next to the
 * "atlc3" wordmark in the header.
 */
export function Logo({ size = 28 }: { size?: number }) {
  return (
    <svg
      viewBox="0 0 32 32"
      width={size}
      height={size}
      aria-label="atlc3 logo"
    >
      {/* dielectric */}
      <rect x={2} y={14} width={28} height={12} rx={1.5} fill="#fde68a" opacity={0.55} />
      {/* ground plane */}
      <rect x={2} y={26} width={28} height={3} fill="#16a34a" />
      {/* signal strip with sine accent */}
      <rect x={11} y={11} width={10} height={3.5} fill="#dc2626" />
      <path
        d="M2 9 Q 8 4 14 9 T 26 9"
        stroke="#06b6d4"
        strokeWidth={1.5}
        fill="none"
        strokeLinecap="round"
      />
    </svg>
  );
}
