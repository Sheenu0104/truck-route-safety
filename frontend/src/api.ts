import type { HeatmapResponse, LatLngTuple, Place, PlanResponse } from './types';

// Empty in the default single-service deploy; set VITE_API_BASE if the API lives elsewhere.
const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined)?.replace(/\/$/, '') ?? '';

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public fields?: Record<string, string>,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init.headers },
  });
  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    // non-JSON error page; handled below
  }
  if (!response.ok) {
    const data = (body ?? {}) as { error?: string; fields?: Record<string, string> };
    const message = data.fields ? Object.values(data.fields).join(' ') : data.error;
    throw new ApiError(message ?? `Request failed (${response.status}).`, response.status, data.fields);
  }
  return body as T;
}

export async function searchPlaces(query: string, signal?: AbortSignal): Promise<Place[]> {
  const data = await request<{ results: Place[] }>(`/api/geocode?q=${encodeURIComponent(query)}`, { signal });
  return data.results;
}

export interface PlanInput {
  origin: Place | string;
  destination: Place | string;
  departure: string; // ISO 8601 with offset
  load_lb: number;
  interval_mi: number;
  hos: boolean;
}

export function planTrip(input: PlanInput, signal?: AbortSignal): Promise<PlanResponse> {
  return request('/api/plan', { method: 'POST', body: JSON.stringify(input), signal });
}

export interface HeatmapInput {
  paths: LatLngTuple[][];
  departure: string;
  load_lb: number;
}

export function fetchHeatmap(input: HeatmapInput, signal?: AbortSignal): Promise<HeatmapResponse> {
  return request('/api/heatmap', { method: 'POST', body: JSON.stringify(input), signal });
}
