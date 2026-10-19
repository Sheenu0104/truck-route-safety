import type { RouteOption } from '../types';

export type TruckStatus = 'not departed' | 'driving' | 'resting' | 'arrived';

export interface TruckState {
  lat: number;
  lng: number;
  status: TruckStatus;
}

/**
 * Where the truck is at clock time `t`. The backend sends a clock time for every
 * path vertex and encodes rest stops as two identical points, so a plain
 * interpolation along `path_times` is exact.
 */
export function truckStateAt(route: RouteOption, t: number): TruckState {
  const { path, path_times: times } = route;
  const n = times.length;
  if (t <= times[0]) return { lat: path[0][0], lng: path[0][1], status: 'not departed' };
  if (t >= times[n - 1]) return { lat: path[n - 1][0], lng: path[n - 1][1], status: 'arrived' };

  let lo = 0;
  let hi = n - 1;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (times[mid] <= t) lo = mid;
    else hi = mid;
  }
  const span = times[hi] - times[lo];
  const f = span > 0 ? (t - times[lo]) / span : 0;
  const [la, lna] = path[lo];
  const [lb, lnb] = path[hi];
  const resting = la === lb && lna === lnb;
  return { lat: la + (lb - la) * f, lng: lna + (lnb - lna) * f, status: resting ? 'resting' : 'driving' };
}

/** Evenly thinned copy of a path, for sending to the heatmap endpoint. */
export function thinPath<T>(path: T[], maxPoints: number): T[] {
  if (path.length <= maxPoints) return path;
  const step = Math.ceil(path.length / maxPoints);
  const out = path.filter((_, i) => i % step === 0);
  if (out[out.length - 1] !== path[path.length - 1]) out.push(path[path.length - 1]);
  return out;
}
