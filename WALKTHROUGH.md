# Loom walkthrough script (about 8 minutes)

Record with the live app in one tab and the GitHub repo in another. Times are targets.

## 1. The problem and the result (0:00 – 1:00)
- "A driver wants the safest route, not just the fastest. Weather changes over the hours of a trip, so I check each point at the time the truck will actually be there."
- Load the Denver to Salt Lake City example, set the load to 45,000 lb, and click **Compare routes**.
- Point at "Take Route X" and read the one-line reason out loud.

## 2. Routes, checkpoints, ETAs (1:00 – 2:30)
- Three routes from OSRM. When OSRM returns fewer than three, extra ones are generated through sideways via points and kept only if they're distinct and reasonable.
- The selected route is colored by risk. Hover a checkpoint: ETA, wind, gusts, rain, snow, the risk level, and why.
- Switch the spacing between 10, 25 and 50 miles. Point out that the trip re-runs.
- The checkpoint table: click a row and the map flies to that checkpoint.
- Rest stops: 30 minutes after 8 hours of driving, 10 hours after 11. They push later ETAs back, which changes which weather the truck meets.

## 3. Risk and load rules (2:30 – 4:00)
- Open `risk.py`. Show the table thresholds and the edges (1.00 in/hr of rain is Severe, more than 1.00 is No Travel).
- The load rules only ever raise the level. Demo: rerun with 20,000 lb and then 45,000 lb on the same trip and watch High turn into Severe.
- Miles per level: each checkpoint covers halfway to its neighbours, so a route's miles add up to its length.

## 4. Recommendation (4:00 – 5:00)
- Open `scoring.py`: No-Travel miles, then Severe, then High, then average risk, then time, with small differences treated as ties.
- Show a route card: the stacked risk bar and the Severe, High and average-risk figures.
- Mention the warning shown when every route crosses No-Travel conditions.

## 5. Heatmap and timeline (5:00 – 6:30)
- Drag the slider. The heatmap and three truck markers move together. The shaded band is the selected route's time on the road.
- Press play. Switch between Risk, Wind, Rain and Snow.
- How it stays smooth: a server-built corridor grid, one canvas pixel per cell stretched by Leaflet, and 49 pre-rendered frames cross-faded every 15 minutes.

## 6. Code quality and tests (6:30 – 7:30)
- Layout: `domain/` holds pure logic, `services/` holds the APIs, views stay thin.
- Run `python manage.py test routeplanner`: 53 tests, with the network mocked.
- The front end is typed TypeScript, and layers are memoised so the slider never re-renders routes.

## 7. Limitations and next steps (7:30 – 8:00)
- Car-profile routing with a truck speed cap (a truck router plugs in), simplified hours-of-service rules, and a per-worker cache.
