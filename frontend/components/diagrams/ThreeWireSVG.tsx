"use client";

import { PALETTE, len, num } from "./utils";

type Pos = { x: number; y: number };

function readPos(geometry: Record<string, unknown> | null, key: string, fallback: Pos): Pos {
  const raw = geometry?.[key];
  if (raw && typeof raw === "object") {
    const obj = raw as Record<string, unknown>;
    return {
      x: len({ x: obj.x } as Record<string, unknown>, "x", fallback.x),
      y: len({ y: obj.y } as Record<string, unknown>, "y", fallback.y),
    };
  }
  return fallback;
}

export function ThreeWireSVG({
  geometry,
}: {
  geometry: Record<string, unknown> | null;
  unit: "mil" | "mm" | "in" | "um";
}) {
  const a = len(geometry, "a", 0.5e-3);
  const red = readPos(geometry, "red", { x: -2e-3, y: 5e-3 });
  const blue = readPos(geometry, "blue", { x: 2e-3, y: 5e-3 });
  const green = readPos(geometry, "green", { x: 0, y: 8e-3 });
  const er = num(geometry, "er", 1.0);
  const groundPlane = Boolean(geometry?.ground_plane);

  const conductors = [
    { ...red, color: PALETTE.signal, label: "+1" },
    { ...blue, color: PALETTE.signalAlt, label: "−1" },
    { ...green, color: PALETTE.ground, label: "0" },
  ];

  // Compute viewBox bounds — find the extents of all conductors + radius + a margin.
  const xs = conductors.map((c) => c.x);
  const ys = conductors.map((c) => c.y);
  const minX = Math.min(...xs) - a * 4;
  const maxX = Math.max(...xs) + a * 4;
  const minY = Math.min(...ys, groundPlane ? 0 : Math.min(...ys)) - a * 2;
  const maxY = Math.max(...ys) + a * 4;
  const spanX = maxX - minX;
  const spanY = maxY - minY;

  const VW = 400;
  const VH = 280;
  const PAD = 30;
  const scale = Math.min((VW - 2 * PAD) / spanX, (VH - 2 * PAD) / spanY);
  const sx = (x: number) => PAD + (x - minX) * scale;
  const sy = (y: number) => VH - (PAD + (y - minY) * scale); // flip y so 0 is at the bottom

  return (
    <svg viewBox={`0 0 ${VW} ${VH}`} className="w-full h-auto bg-navy-950 rounded">
      <rect x={0} y={0} width={VW} height={VH} fill="hsl(45 60% 75%)" opacity={0.15} />
      {groundPlane && (
        <>
          <line x1={0} y1={sy(0)} x2={VW} y2={sy(0)} stroke={PALETTE.ground} strokeWidth={3} />
          <text x={6} y={sy(0) + 14} fontSize={9} fill={PALETTE.ground}>
            ground (y=0)
          </text>
        </>
      )}
      {conductors.map((c, i) => (
        <g key={i}>
          <circle
            cx={sx(c.x)}
            cy={sy(c.y)}
            r={a * scale}
            fill={c.color}
            stroke={PALETTE.conductorOutline}
            strokeWidth={1}
          />
          <text
            x={sx(c.x)}
            y={sy(c.y) + 4}
            fontSize={11}
            textAnchor="middle"
            fill="white"
            fontFamily="ui-monospace, monospace"
            fontWeight={700}
          >
            {c.label}
          </text>
        </g>
      ))}
      <text
        x={VW - 6}
        y={16}
        fontSize={9}
        textAnchor="end"
        fill={PALETTE.conductorOutline}
        fontFamily="ui-monospace, monospace"
      >
        εr = {er.toFixed(2)}, a = {(a * 1e3).toFixed(2)}mm
      </text>
    </svg>
  );
}
