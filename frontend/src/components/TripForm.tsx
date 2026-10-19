import type { Place } from '../types';
import { PlaceInput, type PlaceValue } from './PlaceInput';

export type Interval = 10 | 25 | 50;

export interface TripFormValues {
  origin: PlaceValue;
  destination: PlaceValue;
  departure: string; // datetime-local value
  loadLb: string;
  intervalMi: Interval;
  hos: boolean;
}

const place = (label: string, lat: number, lng: number): PlaceValue => ({ text: label, place: { label, lat, lng } as Place });

const EXAMPLES: { label: string; origin: PlaceValue; destination: PlaceValue }[] = [
  { label: 'Denver to Salt Lake City', origin: place('Denver, CO', 39.7392, -104.9903), destination: place('Salt Lake City, UT', 40.7608, -111.891) },
  { label: 'Chicago to Minneapolis', origin: place('Chicago, IL', 41.8781, -87.6298), destination: place('Minneapolis, MN', 44.9778, -93.265) },
  { label: 'Dallas to Atlanta', origin: place('Dallas, TX', 32.7767, -96.797), destination: place('Atlanta, GA', 33.749, -84.388) },
];

interface Props {
  values: TripFormValues;
  onChange: (values: TripFormValues) => void;
  onSubmit: () => void;
  busy: boolean;
  fieldErrors: Record<string, string>;
}

export function TripForm({ values, onChange, onSubmit, busy, fieldErrors }: Props) {
  const set = <K extends keyof TripFormValues>(key: K, value: TripFormValues[K]) => onChange({ ...values, [key]: value });

  return (
    <form
      className="trip-form"
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit();
      }}
    >
      <PlaceInput label="From" placeholder="City, address or lat, lng" value={values.origin} onChange={(v) => set('origin', v)} error={fieldErrors.origin} />
      <PlaceInput label="To" placeholder="City, address or lat, lng" value={values.destination} onChange={(v) => set('destination', v)} error={fieldErrors.destination} />

      <div className="field-row">
        <div className="field">
          <label htmlFor="departure">Departure</label>
          <input id="departure" type="datetime-local" required value={values.departure} onChange={(e) => set('departure', e.target.value)} aria-invalid={Boolean(fieldErrors.departure)} />
        </div>
        <div className="field">
          <label htmlFor="load">Load weight</label>
          <div className="input-unit">
            <input id="load" type="number" inputMode="numeric" min={0} max={200000} step={500} required value={values.loadLb} onChange={(e) => set('loadLb', e.target.value)} aria-invalid={Boolean(fieldErrors.load_lb)} />
            <span>lb</span>
          </div>
        </div>
      </div>
      {(fieldErrors.departure || fieldErrors.load_lb) && <p className="field-error">{fieldErrors.departure ?? fieldErrors.load_lb}</p>}

      <div className="field-row align-end">
        <fieldset className="field segmented">
          <legend>Weather check every</legend>
          {([10, 25, 50] as Interval[]).map((mi) => (
            <label key={mi} className={values.intervalMi === mi ? 'on' : undefined}>
              <input type="radio" name="interval" value={mi} checked={values.intervalMi === mi} onChange={() => set('intervalMi', mi)} />
              {mi} mi
            </label>
          ))}
        </fieldset>
        <label className="check" title="30-min break after 8 h driving, 10 h rest after 11 h">
          <input type="checkbox" checked={values.hos} onChange={(e) => set('hos', e.target.checked)} />
          Include driver rest stops
        </label>
      </div>

      <button type="submit" className="primary" disabled={busy}>
        {busy ? 'Checking routes…' : 'Compare routes'}
      </button>

      <div className="examples">
        <span>Try</span>
        {EXAMPLES.map((ex) => (
          <button key={ex.label} type="button" className="link" onClick={() => onChange({ ...values, origin: ex.origin, destination: ex.destination })}>
            {ex.label}
          </button>
        ))}
      </div>
    </form>
  );
}
