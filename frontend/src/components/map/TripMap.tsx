import L from 'leaflet';
import { memo, useEffect, useMemo } from 'react';
import { MapContainer, Marker, TileLayer, Tooltip, ZoomControl, useMap } from 'react-leaflet';
import { truckStateAt } from '../../lib/track';
import type { HeatMetric, HeatmapResponse, PlanResponse } from '../../types';
import { HeatmapOverlay } from './HeatmapOverlay';
import { RouteLayers } from './RouteLayers';

export interface FocusTarget {
  lat: number;
  lng: number;
  key: number; // changes on every request so the same point can be re-focused
}

interface Props {
  plan: PlanResponse | null;
  selectedId: string | null;
  onSelect: (id: string) => void;
  heatmap: HeatmapResponse | null;
  showHeat: boolean;
  metric: HeatMetric;
  hour: number;
  time: number; // unix seconds shown on the timeline
  focus: FocusTarget | null;
}

function FitToPlan({ plan }: { plan: PlanResponse | null }) {
  const map = useMap();
  useEffect(() => {
    if (!plan) return;
    const bounds = L.latLngBounds(plan.routes.flatMap((r) => r.path));
    map.invalidateSize(); // the container may have resized since mount (e.g. mobile layout)
    const small = map.getSize().x < 600;
    map.fitBounds(bounds, { padding: small ? [20, 20] : [48, 48], maxZoom: 10 });
  }, [map, plan]);
  return null;
}

function FlyTo({ focus }: { focus: FocusTarget | null }) {
  const map = useMap();
  useEffect(() => {
    if (focus) map.flyTo([focus.lat, focus.lng], Math.max(map.getZoom(), 9), { duration: 0.6 });
  }, [map, focus]);
  return null;
}

// Icons are cached so moving the truck only updates its position, not its DOM.
const truckIcons = new Map<string, L.DivIcon>();
function truckIcon(id: string, selected: boolean, resting: boolean): L.DivIcon {
  const key = `${id}-${selected}-${resting}`;
  let icon = truckIcons.get(key);
  if (!icon) {
    icon = L.divIcon({
      className: `truck${selected ? ' selected' : ''}${resting ? ' resting' : ''}`,
      html: `<span>${id}</span>`,
      iconSize: selected ? [26, 26] : [18, 18],
      iconAnchor: selected ? [13, 13] : [9, 9],
    });
    truckIcons.set(key, icon);
  }
  return icon;
}

const TruckMarkers = memo(function TruckMarkers({ plan, selectedId, time }: { plan: PlanResponse; selectedId: string | null; time: number }) {
  return (
    <>
      {plan.routes.map((route) => {
        const state = truckStateAt(route, time);
        const selected = route.id === selectedId;
        return (
          <Marker
            key={`truck-${route.id}`}
            position={[state.lat, state.lng]}
            icon={truckIcon(route.id, selected, state.status === 'resting')}
            zIndexOffset={selected ? 2000 : 1500}
            interactive
          >
            <Tooltip direction="top" offset={[0, -10]}>
              Route {route.id} truck: {state.status}
            </Tooltip>
          </Marker>
        );
      })}
    </>
  );
});

export function TripMap({ plan, selectedId, onSelect, heatmap, showHeat, metric, hour, time, focus }: Props) {
  const center = useMemo<[number, number]>(() => [39.5, -98.35], []);
  return (
    <MapContainer center={center} zoom={4} minZoom={3} preferCanvas zoomControl={false} className="map" worldCopyJump>
      <ZoomControl position="topright" />
      <TileLayer
        url="https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}"
        attribution="Tiles &copy; Esri &mdash; Esri, HERE, Garmin, &copy; OpenStreetMap contributors"
        maxZoom={16}
      />
      {heatmap && showHeat && <HeatmapOverlay data={heatmap} metric={metric} hour={hour} />}
      {plan && <RouteLayers plan={plan} selectedId={selectedId} onSelect={onSelect} />}
      {plan && <TruckMarkers plan={plan} selectedId={selectedId} time={time} />}
      <FitToPlan plan={plan} />
      <FlyTo focus={focus} />
    </MapContainer>
  );
}
