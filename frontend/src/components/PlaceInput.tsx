import { useEffect, useId, useState } from 'react';
import { searchPlaces } from '../api';
import type { Place } from '../types';

export interface PlaceValue {
  text: string;
  place: Place | null; // set once a suggestion is picked
}

interface Props {
  label: string;
  value: PlaceValue;
  onChange: (value: PlaceValue) => void;
  placeholder?: string;
  error?: string;
}

export function PlaceInput({ label, value, onChange, placeholder, error }: Props) {
  const id = useId();
  const [results, setResults] = useState<Place[]>([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);

  useEffect(() => {
    const query = value.text.trim();
    if (value.place || query.length < 3) {
      setResults([]);
      return;
    }
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      searchPlaces(query, controller.signal)
        .then((found) => {
          setResults(found);
          setActive(-1);
          setOpen(true);
        })
        .catch(() => setResults([]));
    }, 300);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [value.text, value.place]);

  const choose = (place: Place) => {
    onChange({ text: place.label, place });
    setOpen(false);
  };

  const onKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (!open || results.length === 0) return;
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      setActive((i) => (i + 1) % results.length);
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      setActive((i) => (i <= 0 ? results.length - 1 : i - 1));
    } else if (event.key === 'Enter' && active >= 0) {
      event.preventDefault();
      choose(results[active]);
    } else if (event.key === 'Escape') {
      setOpen(false);
    }
  };

  const listId = `${id}-list`;
  return (
    <div className="field place-field">
      <label htmlFor={id}>{label}</label>
      <input
        id={id}
        type="text"
        role="combobox"
        aria-expanded={open && results.length > 0}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={active >= 0 ? `${listId}-${active}` : undefined}
        aria-invalid={Boolean(error)}
        autoComplete="off"
        placeholder={placeholder}
        value={value.text}
        onChange={(e) => onChange({ text: e.target.value, place: null })}
        onKeyDown={onKeyDown}
        onFocus={() => results.length && setOpen(true)}
        onBlur={() => setOpen(false)}
      />
      {open && results.length > 0 && (
        <ul className="suggestions" id={listId} role="listbox">
          {results.map((place, i) => (
            <li
              key={`${place.label}-${i}`}
              id={`${listId}-${i}`}
              role="option"
              aria-selected={i === active}
              className={i === active ? 'active' : undefined}
              onMouseDown={(e) => {
                e.preventDefault(); // keep focus so the click lands
                choose(place);
              }}
            >
              {place.label}
            </li>
          ))}
        </ul>
      )}
      {error && <p className="field-error">{error}</p>}
    </div>
  );
}
