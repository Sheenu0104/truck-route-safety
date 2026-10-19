import { memo } from 'react';
import { fmtClock, fmtDuration, fmtMiles } from '../lib/format';
import { RISK_LEVELS, riskColor, riskLabel } from '../lib/risk';
import type { Recommendation, RouteOption } from '../types';
import { RouteShield } from './RouteShield';

function RiskBar({ route }: { route: RouteOption }) {
  const total = route.distance_mi || 1;
  return (
    <div className="risk-bar" role="img" aria-label={RISK_LEVELS.map((r) => `${r.label} ${fmtMiles(route.stats.miles_by_level[r.level])}`).join(', ')}>
      {route.stats.miles_by_level.map((miles, level) =>
        miles > 0 ? (
          <span key={level} style={{ width: `${(miles / total) * 100}%`, background: riskColor(level) }} title={`${riskLabel(level)}: ${fmtMiles(miles)}`} />
        ) : null,
      )}
    </div>
  );
}

interface Props {
  routes: RouteOption[];
  recommendation: Recommendation;
  selectedId: string | null;
  onSelect: (id: string) => void;
}

export const RouteCards = memo(function RouteCards({ routes, recommendation, selectedId, onSelect }: Props) {
  const ordered = [...routes].sort((a, b) => a.rank - b.rank);
  return (
    <section className="routes" aria-label="Route options">
      <div className="recommendation">
        <h2>
          Take Route {recommendation.route_id}
        </h2>
        <p>{recommendation.reason}</p>
        {recommendation.warnings.map((w) => (
          <p key={w} className="warning">
            {w}
          </p>
        ))}
      </div>

      <ol className="route-list">
        {ordered.map((route) => {
          const s = route.stats;
          return (
            <li key={route.id}>
              <button
                type="button"
                className={`route-card${route.id === selectedId ? ' selected' : ''}`}
                aria-pressed={route.id === selectedId}
                onClick={() => onSelect(route.id)}
              >
                <div className="route-head">
                  <RouteShield id={route.id} />
                  <span className="route-roads">{route.roads || route.name}</span>
                  {route.recommended ? <span className="badge">Recommended</span> : <span className="rank">#{route.rank}</span>}
                </div>
                <dl className="route-figures">
                  <div>
                    <dt>Distance</dt>
                    <dd>{fmtMiles(route.distance_mi)}</dd>
                  </div>
                  <div>
                    <dt>Travel time</dt>
                    <dd>{fmtDuration(route.duration_s)}</dd>
                  </div>
                  <div>
                    <dt>Arrive</dt>
                    <dd>{fmtClock(route.arrival)}</dd>
                  </div>
                </dl>
                <RiskBar route={route} />
                <dl className="route-risk">
                  {s.no_travel_miles > 0 && (
                    <div className="nt">
                      <dt>No travel</dt>
                      <dd>{fmtMiles(s.no_travel_miles)}</dd>
                    </div>
                  )}
                  <div>
                    <dt>Severe</dt>
                    <dd>{fmtMiles(s.severe_miles)}</dd>
                  </div>
                  <div>
                    <dt>High</dt>
                    <dd>{fmtMiles(s.high_miles)}</dd>
                  </div>
                  <div>
                    <dt>Avg risk</dt>
                    <dd>{s.avg_risk.toFixed(2)}</dd>
                  </div>
                </dl>
                {route.drive_s !== route.duration_s && (
                  <p className="route-note">
                    {fmtDuration(route.drive_s)} driving + {route.rest_stops.length} required stop{route.rest_stops.length === 1 ? '' : 's'}
                  </p>
                )}
              </button>
            </li>
          );
        })}
      </ol>
    </section>
  );
});
