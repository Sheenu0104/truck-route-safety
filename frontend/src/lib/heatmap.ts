import type { HeatMetric, HeatmapResponse } from '../types';

type RGBA = [number, number, number, number]; // alpha 0..1
interface Stop {
  v: number;
  c: RGBA;
}

export interface HeatScale {
  label: string;
  unit: string;
  stops: Stop[];
  ticks: { v: number; label: string }[];
}

// Color stops sit on the risk-table thresholds, so the heatmap colors mean the same thing as route colors.
export const HEAT_SCALES: Record<HeatMetric, HeatScale> = {
  risk: {
    label: 'Weather risk for this load',
    unit: '',
    stops: [
      { v: 0, c: [47, 138, 79, 0.14] },
      { v: 1, c: [217, 164, 0, 0.45] },
      { v: 2, c: [232, 89, 12, 0.55] },
      { v: 3, c: [201, 42, 42, 0.62] },
      { v: 4, c: [95, 42, 132, 0.72] },
    ],
    ticks: [
      { v: 0, label: 'Low' },
      { v: 1, label: 'Mod' },
      { v: 2, label: 'High' },
      { v: 3, label: 'Severe' },
      { v: 4, label: 'No travel' },
    ],
  },
  wind: {
    label: 'Wind',
    unit: 'mph',
    stops: [
      { v: 0, c: [29, 79, 145, 0] },
      { v: 12, c: [29, 79, 145, 0.14] },
      { v: 25, c: [217, 164, 0, 0.45] },
      { v: 35, c: [232, 89, 12, 0.55] },
      { v: 45, c: [201, 42, 42, 0.62] },
      { v: 55, c: [95, 42, 132, 0.72] },
    ],
    ticks: [0, 25, 35, 45, 55].map((v) => ({ v, label: String(v) })),
  },
  rain: {
    label: 'Rain',
    unit: 'in/hr',
    stops: [
      { v: 0, c: [29, 79, 145, 0] },
      { v: 0.02, c: [29, 79, 145, 0.2] },
      { v: 0.1, c: [217, 164, 0, 0.45] },
      { v: 0.25, c: [232, 89, 12, 0.55] },
      { v: 0.5, c: [201, 42, 42, 0.62] },
      { v: 1.0, c: [95, 42, 132, 0.72] },
    ],
    ticks: [0, 0.1, 0.25, 0.5, 1].map((v) => ({ v, label: String(v) })),
  },
  snow: {
    label: 'Snow',
    unit: 'in/hr',
    stops: [
      { v: 0, c: [91, 155, 213, 0] },
      { v: 0.1, c: [91, 155, 213, 0.3] },
      { v: 0.5, c: [217, 164, 0, 0.45] },
      { v: 1, c: [232, 89, 12, 0.55] },
      { v: 2, c: [201, 42, 42, 0.62] },
      { v: 3, c: [95, 42, 132, 0.72] },
    ],
    ticks: [0, 0.5, 1, 2, 3].map((v) => ({ v, label: String(v) })),
  },
};

export function colorAt(stops: Stop[], value: number): RGBA {
  if (value <= stops[0].v) return stops[0].c;
  for (let i = 1; i < stops.length; i++) {
    if (value <= stops[i].v) {
      const a = stops[i - 1];
      const b = stops[i];
      const t = (value - a.v) / (b.v - a.v);
      return [0, 1, 2, 3].map((k) => a.c[k] + (b.c[k] - a.c[k]) * t) as RGBA;
    }
  }
  return stops[stops.length - 1].c;
}

export function cssGradient(scale: HeatScale): string {
  const max = scale.stops[scale.stops.length - 1].v;
  const parts = scale.stops.map(({ v, c }) => `rgba(${c[0]},${c[1]},${c[2]},${Math.max(c[3], 0.08)}) ${(v / max) * 100}%`);
  return `linear-gradient(90deg, ${parts.join(', ')})`;
}

/** Pre-render one RGBA bitmap (cols x rows) per forecast hour, so scrubbing is just a copy. */
export function buildFrames(data: HeatmapResponse, metric: HeatMetric): Uint8ClampedArray[] {
  const { rows, cols, cells } = data;
  const { stops } = HEAT_SCALES[metric];
  return data.layers[metric].map((values) => {
    const pixels = new Uint8ClampedArray(rows * cols * 4);
    values.forEach((value, k) => {
      const [r, g, b, a] = colorAt(stops, value);
      const o = cells[k] * 4;
      pixels[o] = r;
      pixels[o + 1] = g;
      pixels[o + 2] = b;
      pixels[o + 3] = Math.round(a * 255);
    });
    return pixels;
  });
}

/** Cross-fade between the two hourly frames around a fractional hour. */
export function blendFrames(frames: Uint8ClampedArray[], hour: number, out: Uint8ClampedArray): void {
  const last = frames.length - 1;
  const i = Math.max(0, Math.min(last, Math.floor(hour)));
  const j = Math.min(last, i + 1);
  const t = Math.max(0, Math.min(1, hour - i));
  const a = frames[i];
  const b = frames[j];
  if (t === 0 || i === j) {
    out.set(a);
    return;
  }
  for (let k = 0; k < out.length; k++) out[k] = a[k] + (b[k] - a[k]) * t;
}
