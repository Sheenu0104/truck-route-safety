const clock = new Intl.DateTimeFormat(undefined, { weekday: 'short', hour: 'numeric', minute: '2-digit' });
const clockShort = new Intl.DateTimeFormat(undefined, { hour: 'numeric', minute: '2-digit' });

export const fmtClock = (unix: number) => clock.format(new Date(unix * 1000));
export const fmtTime = (unix: number) => clockShort.format(new Date(unix * 1000));

export function fmtMiles(miles: number): string {
  return miles >= 100 ? `${Math.round(miles).toLocaleString()} mi` : `${miles.toFixed(miles < 10 ? 1 : 0)} mi`;
}

export function fmtDuration(seconds: number): string {
  const totalMinutes = Math.round(seconds / 60);
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  if (hours >= 24) return `${Math.floor(hours / 24)}d ${hours % 24}h ${minutes}m`;
  return hours ? `${hours}h ${String(minutes).padStart(2, '0')}m` : `${minutes}m`;
}

export function fmtOffset(seconds: number): string {
  const sign = seconds < 0 ? '−' : '+';
  return `${sign}${fmtDuration(Math.abs(seconds))}`;
}

const pad = (n: number) => String(n).padStart(2, '0');

/** Value for <input type="datetime-local"> in the browser's time zone. */
export function toLocalInput(date: Date): string {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

export function nextHourLocalInput(): string {
  const d = new Date();
  d.setMinutes(0, 0, 0);
  d.setHours(d.getHours() + 1);
  return toLocalInput(d);
}

export const floorHour = (unix: number) => Math.floor(unix / 3600) * 3600;
