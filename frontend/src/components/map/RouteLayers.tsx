import L from 'leaflet';
import { memo, useMemo } from 'react';
import { CircleMarker, Marker, Polyline, Tooltip } from 'react-leaflet';
import { fmtClock, fmtDuration, fmtMiles, fmtTime } from '../../lib/format';
import { riskColor, routeColor } from '../../lib/risk';
import type { Checkpoint, PlanResponse, RouteOption } from '../../types';
import { shieldHtml } from '../RouteShield';

interface Props {
  plan: PlanResponse;
  selectedId: string | null;
  onSelect: (id: string) => void;
}

function CheckpointDetails({ cp, route }: { cp: Checkpoint; route: RouteOption }) {
  const w = cp.weather;
  return (
    <div className="cp-tip">
      <strong>
        Route {route.id}, mile {Math.round(cp.mile)}
      </strong>
      <span className="cp-tip-risk" style={{ color: riskColor(cp.risk.level) }}>
        {cp.risk.label}
      </span>
      <span>ETA {fmtClock(cp.eta)}</span>
      <span>
        Wind {Math.round(w.wind_mph)} mph (gusts {Math.round(w.gust_mph)})
      </span>
      <span>
        Rain {w.rain_in_hr.toFixed(2)} in/hr, snow {w.snow_in_hr.toFixed(2)} in/hr
      </span>
      {w.temp_f !== null && <span>{Math.round(w.temp_f)}°F</span>}
      {cp.risk.drivers.length > 0 && <span className="cp-tip-why">{cp.risk.drivers.join('; ')}</span>}
    </div>
  );
}

const labelIcon = (id: string, selected: boolean) =>
  L.divIcon({
    className: `route-label${selected ? ' selected' : ''}`,
    html: shieldHtml(id, selected ? 34 : 28),
    iconSize: selected ? [34, 34] : [28, 28],
    iconAnchor: selected ? [17, 17] : [14, 14],
  });

const endpointIcon = (kind: 'start' | 'end') =>
  L.divIcon({ className: `endpoint ${kind}`, html: '<span></span>', iconSize: [18, 18], iconAnchor: [9, 9] });

/** Static route geometry. Memoised so the forecast slider never re-renders it. */
export const RouteLayers = memo(function RouteLayers({ plan, selectedId, onSelect }: Props) {
  const selected = plan.routes.find((r) => r.id === selectedId) ?? plan.routes[0];
  const others = plan.routes.filter((r) => r.id !== selected.id);

  // Spread the shield labels along different parts of each route so they don't stack.
  const labelPositions = useMemo(() => {
    const fractions = [0.5, 0.38, 0.62];
    return Object.fromEntries(
      plan.routes.map((r, i) => [r.id, r.path[Math.floor((r.path.length - 1) * fractions[i % fractions.length])]]),
    );
  }, [plan]);

  return (
    <>
      {others.map((route) => (
        <Polyline
          key={`alt-${route.id}`}
          positions={route.path}
          pathOptions={{ color: routeColor(route.id), weight: 5, opacity: 0.6, dashArray: '2 9', lineCap: 'round' }}
          eventHandlers={{ click: () => onSelect(route.id) }}
        >
          <Tooltip sticky>
            Route {route.id}: {fmtMiles(route.distance_mi)}, {fmtDuration(route.duration_s)}, {fmtMiles(route.stats.severe_miles)} severe. Click to inspect.
          </Tooltip>
        </Polyline>
      ))}
      {others.flatMap((route) =>
        route.checkpoints.map((cp) => (
          <CircleMarker
            key={`alt-cp-${route.id}-${cp.index}`}
            center={[cp.lat, cp.lng]}
            radius={3.5}
            pathOptions={{ stroke: false, fillColor: riskColor(cp.risk.level), fillOpacity: 0.85 }}
            eventHandlers={{ click: () => onSelect(route.id) }}
          >
            <Tooltip>
              <CheckpointDetails cp={cp} route={route} />
            </Tooltip>
          </CircleMarker>
        )),
      )}

      <Polyline positions={selected.path} pathOptions={{ color: '#ffffff', weight: 11, opacity: 0.95 }} interactive={false} />
      {selected.segments.map((seg, i) => (
        <Polyline key={`seg-${selected.id}-${i}`} positions={seg.path} pathOptions={{ color: riskColor(seg.level), weight: 6, opacity: 1 }}>
          <Tooltip sticky>
            Route {selected.id}, miles {Math.round(seg.from_mile)}–{Math.round(seg.to_mile)}: {['Low', 'Moderate', 'High', 'Severe', 'No Travel'][seg.level]} risk
          </Tooltip>
        </Polyline>
      ))}
      {selected.checkpoints.map((cp) => (
        <CircleMarker
          key={`cp-${selected.id}-${cp.index}`}
          center={[cp.lat, cp.lng]}
          radius={6}
          pathOptions={{ color: '#fff', weight: 2, fillColor: riskColor(cp.risk.level), fillOpacity: 1 }}
        >
          <Tooltip direction="top" offset={[0, -6]}>
            <CheckpointDetails cp={cp} route={selected} />
          </Tooltip>
        </CircleMarker>
      ))}
      {selected.rest_stops.map((stop, i) => (
        <CircleMarker key={`rest-${i}`} center={[stop.lat, stop.lng]} radius={5} pathOptions={{ color: '#18242c', weight: 2, fillColor: '#fff', fillOpacity: 1, dashArray: '2 2' }}>
          <Tooltip direction="top">
            {stop.kind} at mile {Math.round(stop.mile)}, {fmtClock(stop.start)} to {fmtTime(stop.end)}
          </Tooltip>
        </CircleMarker>
      ))}

      {plan.routes.map((route) => (
        <Marker
          key={`label-${route.id}-${route.id === selected.id}`}
          position={labelPositions[route.id]}
          icon={labelIcon(route.id, route.id === selected.id)}
          zIndexOffset={route.id === selected.id ? 1000 : 0}
          eventHandlers={{ click: () => onSelect(route.id) }}
          keyboard
          title={`Route ${route.id}`}
        >
          <Tooltip direction="right" offset={[16, 0]}>
            <strong>Route {route.id}</strong> {route.recommended ? '(recommended)' : `(rank ${route.rank})`}
            <br />
            {fmtMiles(route.distance_mi)}, {fmtDuration(route.duration_s)}, arrive {fmtClock(route.arrival)}
            <br />
            Severe {fmtMiles(route.stats.severe_miles)}, High {fmtMiles(route.stats.high_miles)}, avg risk {route.stats.avg_risk.toFixed(2)}
          </Tooltip>
        </Marker>
      ))}

      <Marker position={[plan.origin.lat, plan.origin.lng]} icon={endpointIcon('start')} title={plan.origin.label}>
        <Tooltip direction="left">Start: {plan.origin.label}</Tooltip>
      </Marker>
      <Marker position={[plan.destination.lat, plan.destination.lng]} icon={endpointIcon('end')} title={plan.destination.label}>
        <Tooltip direction="left">Destination: {plan.destination.label}</Tooltip>
      </Marker>
    </>
  );
});
