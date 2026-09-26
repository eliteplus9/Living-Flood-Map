import { useEffect, useMemo, useState } from "react";
import { CircleMarker, MapContainer, Popup, TileLayer, Tooltip, useMap } from "react-leaflet";
import type { ProcessedTweet } from "../../shared/contracts";

function FitPoints({ points }: { points: [number, number][] }) {
  const map = useMap();
  useEffect(() => {
    if (points.length) map.fitBounds(points, { padding: [40, 40], maxZoom: 11 });
  }, [map, points]);
  return null;
}
export default function MapPanel({ tweets, onEvidence, onPlace, activeTweetId, compact = false }: { tweets: ProcessedTweet[]; onEvidence: (id: string) => void; onPlace?: (name: string) => void; activeTweetId?: string; compact?: boolean }) {
  const [tileError, setTileError] = useState(false);
  const groups = useMemo(() => {
    const grouped = new Map<string, { name: string; coordinates: [number, number]; reports: ProcessedTweet[] }>();
    for (const tweet of tweets) for (const location of tweet.locations) {
      if (location.status !== "resolved" || location.latitude == null || location.longitude == null) continue;
      const key = location.latitude + "," + location.longitude;
      const group = grouped.get(key) ?? { name: location.canonical_name ?? location.mention,
        coordinates: [location.latitude, location.longitude], reports: [] };
      if (!group.reports.some(row => row.tweet_id === tweet.tweet_id)) group.reports.push(tweet);
      grouped.set(key, group);
    }
    return [...grouped.values()].sort((a, b) => b.reports.length - a.reports.length);
  }, [tweets]);
  const coordinates = useMemo(() => {
    const selected = groups.filter(group => group.reports.some(row => row.tweet_id === activeTweetId));
    return (selected.length ? selected : groups).map(group => group.coordinates);
  }, [groups, activeTweetId]);
  const unmapped = tweets.filter(row => !row.locations.some(loc => loc.status === "resolved"));
  return <>
    <p className="map-note">Showing relevant reports only. Markers identify mentioned places, using approximate place centres. They do not mark exact flood incidents.</p>
    {tileError && <div role="status" className="alert warning">The background map could not load. Place names and source reports remain available below.</div>}
    {!groups.length ? <div className="empty-state">No resolved places in this selection. Reports without a map point remain available in the Reports view.</div> :
      <MapContainer center={coordinates[0]} zoom={6} className="map" scrollWheelZoom={false}>
        <FitPoints points={coordinates} />
        <TileLayer attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" eventHandlers={{ tileerror: () => setTileError(true) }} />
        {groups.map(group => <CircleMarker key={group.coordinates.join(",")} center={group.coordinates}
          radius={Math.min(28, 9 + Math.log2(group.reports.length + 1) * 2)}
          pathOptions={{ color: "#075b66", fillColor: group.reports.some(row => row.tweet_id === activeTweetId) ? "#ef6a32" : "#539b95", fillOpacity: .75, weight: 2 }}>
          <Tooltip>{group.name} · {group.reports.length} reports</Tooltip>
          <Popup><strong>{group.name}</strong><p>{group.reports.length} matching reports · approximate place centre</p>
            {onPlace && <button onClick={() => onPlace(group.name)}>Investigate {group.name}</button>}
            {group.reports.slice(0, 4).map(row => <div key={row.tweet_id}><p>{row.tweet}</p><button onClick={() => onEvidence(row.tweet_id)}>Read record {row.source_row}</button></div>)}
            {group.reports.length > 4 && <small>Filter by this place above to see all reports.</small>}
          </Popup>
        </CircleMarker>)}
      </MapContainer>}
    <div className="place-directory"><h3>{compact ? "Explore a community" : "Mapped places & source reports"}</h3><p className="muted">Accessible list of every mapped place. Counts follow your filters.</p>
      {groups.map(group => <details key={group.coordinates.join(",")}><summary>{group.name} <strong>{group.reports.length} reports</strong></summary>
        {onPlace && <button className="secondary" onClick={() => onPlace(group.name)}>Investigate {group.name}</button>}
        <p>{new Set(group.reports.map(row => row.normalized_tweet.toLowerCase())).size} unique texts · coordinates {group.coordinates.map(value => value.toFixed(4)).join(", ")}</p>
        {group.reports.slice(0, 5).map(row => <button className="evidence-link" key={row.tweet_id} onClick={() => onEvidence(row.tweet_id)}>Record {row.source_row}: {row.tweet}</button>)}
        {group.reports.length > 5 && <p>Use the Place filter above to view all {group.reports.length} reports.</p>}
      </details>)}
    </div>
    <details className="unmapped"><summary>{unmapped.length} relevant reports without a resolved place</summary><p>The baseline gazetteer covers only a small set of Alberta locations. A missing map point does not mean a report has no location.</p>{unmapped.slice(0, 5).map(row => <button className="evidence-link" key={row.tweet_id} onClick={() => onEvidence(row.tweet_id)}>Record {row.source_row}: {row.tweet}</button>)}</details>
  </>;
}
