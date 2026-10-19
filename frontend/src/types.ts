/** Shapes returned by the Django API (see backend/routeplanner/services/planner.py). */

export type RiskLevel = 0 | 1 | 2 | 3 | 4;
export type LatLngTuple = [number, number];

export interface Place {
  label: string;
  lat: number;
  lng: number;
}

export interface WeatherReading {
  wind_mph: number;
  gust_mph: number;
  rain_in_hr: number;
  snow_in_hr: number;
  temp_f: number | null;
  code: number | null;
  missing: boolean;
}

export interface RiskInfo {
  level: RiskLevel;
  label: string;
  wind: RiskLevel;
  rain: RiskLevel;
  snow: RiskLevel;
  load_rule: RiskLevel | null;
  drivers: string[];
}

export interface Checkpoint {
  index: number;
  mile: number;
  lat: number;
  lng: number;
  eta: number; // unix seconds
  weather: WeatherReading;
  risk: RiskInfo;
}

export interface Segment {
  level: RiskLevel;
  from_mile: number;
  to_mile: number;
  path: LatLngTuple[];
}

export interface RestStop {
  kind: string;
  mile: number;
  lat: number;
  lng: number;
  start: number;
  end: number;
}

export interface RouteStats {
  miles_by_level: number[];
  no_travel_miles: number;
  severe_miles: number;
  high_miles: number;
  avg_risk: number;
  max_level: RiskLevel;
}

export interface RouteOption {
  id: string;
  name: string;
  roads: string;
  distance_mi: number;
  drive_s: number;
  duration_s: number;
  departure: number;
  arrival: number;
  path: LatLngTuple[];
  path_times: number[];
  segments: Segment[];
  checkpoints: Checkpoint[];
  rest_stops: RestStop[];
  stats: RouteStats;
  rank: number;
  recommended: boolean;
}

export interface Recommendation {
  route_id: string;
  reason: string;
  criteria: string[];
  warnings: string[];
}

export interface PlanResponse {
  origin: Place;
  destination: Place;
  departure: number;
  load_lb: number;
  interval_mi: number;
  hos: boolean;
  routes: RouteOption[];
  recommendation: Recommendation;
}

export type HeatMetric = 'risk' | 'wind' | 'rain' | 'snow';

export interface HeatmapResponse {
  bounds: { south: number; west: number; north: number; east: number };
  rows: number;
  cols: number;
  cells: number[];
  hours: number[];
  layers: Record<HeatMetric, number[][]>;
  corridor_mi: number;
}
