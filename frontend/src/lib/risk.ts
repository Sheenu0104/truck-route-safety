export const RISK_LEVELS = [
  { level: 0, label: 'Low', color: '#2f8a4f' },
  { level: 1, label: 'Moderate', color: '#d9a400' },
  { level: 2, label: 'High', color: '#e8590c' },
  { level: 3, label: 'Severe', color: '#c92a2a' },
  { level: 4, label: 'No Travel', color: '#5f2a84' },
] as const;

const clampLevel = (level: number) => Math.max(0, Math.min(4, Math.round(level)));

export const riskColor = (level: number) => RISK_LEVELS[clampLevel(level)].color;
export const riskLabel = (level: number) => RISK_LEVELS[clampLevel(level)].label;

/** Identity colors for routes A/B/C, kept clear of the risk palette. */
export const ROUTE_COLORS: Record<string, string> = { A: '#1d4f91', B: '#3b7f8c', C: '#6b5b95' };
export const routeColor = (id: string) => ROUTE_COLORS[id] ?? '#46535c';
