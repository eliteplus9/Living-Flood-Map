import { useEffect, useMemo, useState } from "react";
import { CircleMarker, MapContainer, Popup, TileLayer, Tooltip, useMap } from "react-leaflet";
import type { ProcessedTweet } from "../../shared/contracts";
import { groupPlaces } from "./mapData";

function FitPoints({ points }: { points: [number, number][] }) {
  const map = useMap();
  useEffect(() => {
    if (points.length) map.fitBounds(points, { padding: [40, 40], maxZoom: 11 });
  }, [map, points]);
  return <button className="fit-map" onClick={() => points.length ? map.fitBounds(points, { padding: [40, 40], maxZoom: 11 }) : map.setView([30, 0], 2)}>Fit places</button>;
}
export default function MapPanel({ tweets, onEvidence, onPlace, activeTweetId, compact = false }: { tweets: ProcessedTweet[]; onEvidence: (id: string) => void; onPlace?: (name: string) => void; activeTweetId?: string; compact?: boolean }) {
  const [tileError, setTileError] = useState(false);
  const groups = useMemo(() => groupPlaces(tweets), [tweets]);
  const coordinates = useMemo(() => {
    const selected = groups.filter(group => group.reports.some(row => row.tweet_id === activeTweetId));
    return (selected.length ? selected : groups).map(group => group.coordinates);
  }, [groups, activeTweetId]);
  const mappedIds = new Set(groups.flatMap(group => group.reports.map(row => row.tweet_id)));
  const unmapped = tweets.filter(row => !mappedIds.has(row.tweet_id));
  return <>
    <p className="map-note">{groups.length} places · {mappedIds.size} mapped reports · Approximate locations</p>
    {tileError && <div role="status" className="alert warning">The background map could not load. Place names and source reports remain available below.</div>}
      <MapContainer center={coordinates[0] ?? [30, 0]} zoom={coordinates.length ? 6 : 2} className="map" scrollWheelZoom={true}>
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
      </MapContainer>
    {!groups.length && <p className="map-empty-note">No resolved places in this selection. Source reports remain available in Reports.</p>}
    <details className="place-directory"><summary>{compact ? "Explore a community" : "Mapped places & source reports"} ({groups.length})</summary>
      {groups.map(group => <details key={group.coordinates.join(",")}><summary>{group.name} <strong>{group.reports.length} reports</strong></summary>
        {onPlace && <button className="secondary" onClick={() => onPlace(group.name)}>Investigate {group.name}</button>}
        <p>{new Set(group.reports.map(row => row.normalized_tweet.toLowerCase())).size} unique texts · coordinates {group.coordinates.map(value => value.toFixed(4)).join(", ")}</p>
        {group.reports.slice(0, 5).map(row => <button className="evidence-link" key={row.tweet_id} onClick={() => onEvidence(row.tweet_id)}>Record {row.source_row}: {row.tweet}</button>)}
        {group.reports.length > 5 && <p>Use the Place filter above to view all {group.reports.length} reports.</p>}
      </details>)}
    </details>
    <details className="unmapped"><summary>{unmapped.length} relevant reports without a resolved place</summary><p>Location matching can miss or misread places. A missing map point does not mean a report has no location.</p>{unmapped.slice(0, 5).map(row => <button className="evidence-link" key={row.tweet_id} onClick={() => onEvidence(row.tweet_id)}>Record {row.source_row}: {row.tweet}</button>)}</details>
  </>;
}
