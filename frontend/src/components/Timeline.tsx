import { fmtClock, fmtOffset, fmtTime } from '../lib/format';
import { HEAT_SCALES, cssGradient } from '../lib/heatmap';
import type { HeatMetric } from '../types';

export const TIMELINE_HOURS = 48;

interface Props {
  start: number; // unix seconds of hour 0
  departure: number;
  hour: number;
  onHour: (hour: number) => void;
  playing: boolean;
  onPlay: (playing: boolean) => void;
  metric: HeatMetric;
  onMetric: (metric: HeatMetric) => void;
  showHeat: boolean;
  onShowHeat: (show: boolean) => void;
  trip?: { id: string; arrival: number };
  heatStatus: 'idle' | 'loading' | 'ready' | 'error';
}

const METRICS: { id: HeatMetric; label: string }[] = [
  { id: 'risk', label: 'Risk' },
  { id: 'wind', label: 'Wind' },
  { id: 'rain', label: 'Rain' },
  { id: 'snow', label: 'Snow' },
];

const pct = (h: number) => `${(Math.max(0, Math.min(TIMELINE_HOURS, h)) / TIMELINE_HOURS) * 100}%`;

export function Timeline(props: Props) {
  const { start, departure, hour, trip, metric } = props;
  const now = start + hour * 3600;
  const departHour = (departure - start) / 3600;
  const arriveHour = trip ? (trip.arrival - start) / 3600 : departHour;
  const scale = HEAT_SCALES[metric];

  return (
    <div className="timeline" aria-label="Forecast timeline">
      <div className="timeline-top">
        <button type="button" className="play" onClick={() => props.onPlay(!props.playing)} aria-label={props.playing ? 'Pause' : 'Play forecast'}>
          {props.playing ? (
            <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><rect x="3" y="2" width="3.5" height="12" fill="currentColor" /><rect x="9.5" y="2" width="3.5" height="12" fill="currentColor" /></svg>
          ) : (
            <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><path d="M4 2l10 6-10 6z" fill="currentColor" /></svg>
          )}
        </button>
        <div className="time-readout">
          <strong>{fmtClock(now)}</strong>
          <span>{fmtOffset(now - departure)} from departure</span>
        </div>
        <div className="metric-switch" role="radiogroup" aria-label="Heatmap layer">
          {METRICS.map((m) => (
            <button key={m.id} type="button" role="radio" aria-checked={metric === m.id} className={metric === m.id ? 'on' : undefined} onClick={() => props.onMetric(m.id)}>
              {m.label}
            </button>
          ))}
        </div>
        <label className="check heat-toggle">
          <input type="checkbox" checked={props.showHeat} onChange={(e) => props.onShowHeat(e.target.checked)} />
          Heatmap
        </label>
      </div>

      <div className="slider">
        {trip && (
          <div className="trip-window" style={{ left: pct(departHour), width: `calc(${pct(arriveHour)} - ${pct(departHour)})` }} title={`Route ${trip.id} on the road`}>
            <span>Route {trip.id} on the road</span>
          </div>
        )}
        <input
          type="range"
          min={0}
          max={TIMELINE_HOURS}
          step={0.25}
          value={hour}
          aria-label="Forecast hour"
          aria-valuetext={fmtClock(now)}
          onChange={(e) => props.onHour(Number(e.target.value))}
        />
        <div className="ticks" aria-hidden="true">
          {[0, 12, 24, 36, 48].map((h) => (
            <span key={h} style={{ left: pct(h) }}>
              {h === 0 ? fmtTime(start) : `+${h}h`}
            </span>
          ))}
        </div>
      </div>

      <div className="heat-legend">
        <span className="heat-legend-label">
          {scale.label}
          {scale.unit && ` (${scale.unit})`}
          {props.heatStatus === 'loading' && <em> loading forecast grid…</em>}
          {props.heatStatus === 'error' && <em> heatmap unavailable</em>}
        </span>
        <div className="heat-ramp" style={{ background: cssGradient(scale) }} />
        <div className="heat-ticks">
          {scale.ticks.map((t) => (
            <span key={t.v} style={{ left: `${(t.v / scale.stops[scale.stops.length - 1].v) * 100}%` }}>
              {t.label}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
