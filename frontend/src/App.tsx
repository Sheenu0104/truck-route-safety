import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ApiError, fetchHeatmap, planTrip } from './api';
import { CheckpointTable } from './components/CheckpointTable';
import { RouteCards } from './components/RouteCards';
import { TIMELINE_HOURS, Timeline } from './components/Timeline';
import { TripForm, type TripFormValues } from './components/TripForm';
import { TripMap, type FocusTarget } from './components/map/TripMap';
import { floorHour, nextHourLocalInput } from './lib/format';
import { RISK_LEVELS } from './lib/risk';
import { thinPath } from './lib/track';
import type { Checkpoint, HeatMetric, HeatmapResponse, PlanResponse } from './types';

const PLAY_HOURS_PER_SECOND = 3;

const initialForm: TripFormValues = {
  origin: { text: 'Denver, CO', place: { label: 'Denver, CO', lat: 39.7392, lng: -104.9903 } },
  destination: { text: 'Salt Lake City, UT', place: { label: 'Salt Lake City, UT', lat: 40.7608, lng: -111.891 } },
  departure: nextHourLocalInput(),
  loadLb: '38000',
  intervalMi: 25,
  hos: true,
};

type HeatStatus = 'idle' | 'loading' | 'ready' | 'error';

export default function App() {
  const [form, setForm] = useState<TripFormValues>(initialForm);
  const [plan, setPlan] = useState<PlanResponse | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const [heatmap, setHeatmap] = useState<HeatmapResponse | null>(null);
  const [heatStatus, setHeatStatus] = useState<HeatStatus>('idle');
  const [showHeat, setShowHeat] = useState(true);
  const [metric, setMetric] = useState<HeatMetric>('risk');
  const [hour, setHour] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [focus, setFocus] = useState<FocusTarget | null>(null);

  const requestRef = useRef<AbortController | null>(null);

  const loadHeatmap = useCallback(async (result: PlanResponse, signal: AbortSignal) => {
    setHeatStatus('loading');
    try {
      const data = await fetchHeatmap(
        {
          paths: result.routes.map((r) => thinPath(r.path, 400)),
          departure: new Date(result.departure * 1000).toISOString(),
          load_lb: result.load_lb,
        },
        signal,
      );
      setHeatmap(data);
      setHeatStatus('ready');
    } catch {
      if (!signal.aborted) setHeatStatus('error');
    }
  }, []);

  const submit = useCallback(
    async (values: TripFormValues) => {
      const load = Number(values.loadLb);
      const departure = new Date(values.departure);
      const errors: Record<string, string> = {};
      if (!values.origin.text.trim()) errors.origin = 'Enter a starting point.';
      if (!values.destination.text.trim()) errors.destination = 'Enter a destination.';
      if (Number.isNaN(departure.getTime())) errors.departure = 'Choose a departure time.';
      if (!Number.isFinite(load) || load < 0) errors.load_lb = 'Enter the load weight in pounds.';
      setFieldErrors(errors);
      if (Object.keys(errors).length) return;

      requestRef.current?.abort();
      const controller = new AbortController();
      requestRef.current = controller;
      setLoading(true);
      setError(null);
      setPlaying(false);
      try {
        const result = await planTrip(
          {
            origin: values.origin.place ?? values.origin.text,
            destination: values.destination.place ?? values.destination.text,
            departure: departure.toISOString(),
            load_lb: load,
            interval_mi: values.intervalMi,
            hos: values.hos,
          },
          controller.signal,
        );
        setPlan(result);
        setSelectedId(result.recommendation.route_id);
        setHour((result.departure - floorHour(result.departure)) / 3600);
        setHeatmap(null);
        void loadHeatmap(result, controller.signal);
      } catch (err) {
        if (controller.signal.aborted) return;
        if (err instanceof ApiError) {
          setFieldErrors(err.fields ?? {});
          setError(err.fields ? 'Some trip details need fixing.' : err.message);
        } else {
          setError('Could not reach the server. Check your connection and try again.');
        }
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    },
    [loadHeatmap],
  );

  // Changing checkpoint spacing re-runs the current trip.
  const changeForm = (next: TripFormValues) => {
    const intervalChanged = next.intervalMi !== form.intervalMi;
    setForm(next);
    if (intervalChanged && plan) void submit(next);
  };

  // Forecast playback.
  useEffect(() => {
    if (!playing) return;
    let frame = 0;
    let last = performance.now();
    const tick = (now: number) => {
      const dt = (now - last) / 1000;
      last = now;
      setHour((h) => (h + dt * PLAY_HOURS_PER_SECOND > TIMELINE_HOURS ? 0 : h + dt * PLAY_HOURS_PER_SECOND));
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [playing]);

  const selectedRoute = plan?.routes.find((r) => r.id === selectedId) ?? null;
  const timelineStart = heatmap?.hours[0] ?? (plan ? floorHour(plan.departure) : 0);
  const time = timelineStart + hour * 3600;
  const focusCheckpoint = useCallback((cp: Checkpoint) => setFocus({ lat: cp.lat, lng: cp.lng, key: Date.now() }), []);
  const trip = useMemo(() => (selectedRoute ? { id: selectedRoute.id, arrival: selectedRoute.arrival } : undefined), [selectedRoute]);

  return (
    <div className="app">
      <aside className="sidebar">
        <header className="brand">
          <h1>Truck Route Safety</h1>
          <p>Compare three routes by the weather your truck will actually meet, checked at each point's arrival time.</p>
        </header>

        <TripForm values={form} onChange={changeForm} onSubmit={() => submit(form)} busy={loading} fieldErrors={fieldErrors} />

        {error && (
          <p className="alert" role="alert">
            {error}
          </p>
        )}

        {plan ? (
          <>
            <RouteCards routes={plan.routes} recommendation={plan.recommendation} selectedId={selectedId} onSelect={setSelectedId} />
            {selectedRoute && <CheckpointTable route={selectedRoute} intervalMi={plan.interval_mi} onFocus={focusCheckpoint} />}
          </>
        ) : (
          !loading && (
            <section className="empty">
              <h2>How routes are ranked</h2>
              <ol>
                <li>Fewest miles in Severe conditions (No Travel counts worst of all)</li>
                <li>Fewest miles in High conditions</li>
                <li>Lowest average risk along the route</li>
                <li>Shortest travel time</li>
              </ol>
              <div className="level-key">
                {RISK_LEVELS.map((r) => (
                  <span key={r.level}>
                    <i style={{ background: r.color }} />
                    {r.label}
                  </span>
                ))}
              </div>
            </section>
          )
        )}

        <footer className="credits">
          Routing by OSRM, forecasts by Open-Meteo, places by Photon. Map data © OpenStreetMap contributors.
        </footer>
      </aside>

      <main className="map-area">
        <TripMap
          plan={plan}
          selectedId={selectedId}
          onSelect={setSelectedId}
          heatmap={heatmap}
          showHeat={showHeat}
          metric={metric}
          hour={hour}
          time={time}
          focus={focus}
        />
        {loading && (
          <div className="map-status" role="status">
            Finding routes and checking forecasts…
          </div>
        )}
        {plan && (
          <Timeline
            start={timelineStart}
            departure={plan.departure}
            hour={hour}
            onHour={(h) => {
              setPlaying(false);
              setHour(h);
            }}
            playing={playing}
            onPlay={setPlaying}
            metric={metric}
            onMetric={setMetric}
            showHeat={showHeat}
            onShowHeat={setShowHeat}
            trip={trip}
            heatStatus={heatStatus}
          />
        )}
      </main>
    </div>
  );
}
