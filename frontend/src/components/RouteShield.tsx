import { routeColor } from '../lib/risk';

/** Interstate-style shield carrying the route letter. */
export function RouteShield({ id, size = 26 }: { id: string; size?: number }) {
  return (
    <svg className="shield" width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">
      <path d="M3 3h26v15c0 6.5-6.5 10-13 12C9.5 28 3 24.5 3 18z" fill={routeColor(id)} stroke="#fff" strokeWidth="2" />
      <text x="16" y="21" textAnchor="middle" fontSize="15" fontWeight="700" fill="#fff" fontFamily="Barlow Condensed, sans-serif">
        {id}
      </text>
    </svg>
  );
}

export function shieldHtml(id: string, size = 30): string {
  return `<svg width="${size}" height="${size}" viewBox="0 0 32 32"><path d="M3 3h26v15c0 6.5-6.5 10-13 12C9.5 28 3 24.5 3 18z" fill="${routeColor(
    id,
  )}" stroke="#fff" stroke-width="2"/><text x="16" y="21" text-anchor="middle" font-size="15" font-weight="700" fill="#fff" font-family="Barlow Condensed, sans-serif">${id}</text></svg>`;
}
