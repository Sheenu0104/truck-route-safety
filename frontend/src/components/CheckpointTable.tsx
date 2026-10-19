import { memo } from 'react';
import { fmtClock } from '../lib/format';
import { riskColor } from '../lib/risk';
import type { Checkpoint, RouteOption } from '../types';

interface Props {
  route: RouteOption;
  intervalMi: number;
  onFocus: (checkpoint: Checkpoint) => void;
}

export const CheckpointTable = memo(function CheckpointTable({ route, intervalMi, onFocus }: Props) {
  return (
    <section className="checkpoints">
      <h3>
        Route {route.id} checkpoints <small>every {intervalMi} mi, weather at the truck's ETA</small>
      </h3>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th scope="col">Mile</th>
              <th scope="col">ETA</th>
              <th scope="col">Wind</th>
              <th scope="col">Rain</th>
              <th scope="col">Snow</th>
              <th scope="col">Risk</th>
            </tr>
          </thead>
          <tbody>
            {route.checkpoints.map((cp) => (
              <tr key={cp.index} tabIndex={0} onClick={() => onFocus(cp)} onKeyDown={(e) => e.key === 'Enter' && onFocus(cp)} title={cp.risk.drivers.join('; ') || 'No hazards'}>
                <td>{Math.round(cp.mile)}</td>
                <td>{fmtClock(cp.eta)}</td>
                <td className={cp.risk.wind ? 'hot' : undefined}>{Math.round(cp.weather.wind_mph)} mph</td>
                <td className={cp.risk.rain ? 'hot' : undefined}>{cp.weather.rain_in_hr.toFixed(2)}</td>
                <td className={cp.risk.snow ? 'hot' : undefined}>{cp.weather.snow_in_hr.toFixed(2)}</td>
                <td>
                  <span className="pill" style={{ background: riskColor(cp.risk.level) }}>
                    {cp.risk.label}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="table-note">Rain and snow in inches per hour. Select a row to show it on the map.</p>
    </section>
  );
});
