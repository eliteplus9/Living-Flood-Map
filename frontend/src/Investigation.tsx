import { useMemo, useState } from "react";
import type { ProcessedTweet } from "../../shared/contracts";
import { interpret, placeRole, type Review, type ReportKind } from "../../shared/interpretation";
import MapPanel from "./MapPanel";

export function briefingText(rows: ProcessedTweet[], scope: string, reviews: Record<string, Review>) {
  const unique = new Set(rows.map(row => row.normalized_tweet.toLowerCase())).size;
  const interpreted = rows.map(row => interpret(row.tweet));
  const overview = (["request", "offer", "correction", "question", "report"] as const)
    .map(kind => kind + ": " + interpreted.filter(item => item.signals.some(signal => signal.kind === kind)).length + " source records");
  return [
    "# Community report briefing", "",
    "Scope: " + scope,
    rows.length + " source records; " + unique + " unique texts. Repetition is not independent corroboration.",
    "Report timestamps and independent verification are unavailable. Ordering below does not establish chronology.",
    "Interpretations use evidence rules and require review. Coordinates represent approximate mentioned places, not verified incident sites.", "",
    "## Evidence overview", ...overview,
    "Types may overlap. Corrections do not automatically supersede other reports without chronology.",
    "Records with no resolved or accepted map point: " + rows.filter(row => reviews[row.tweet_id]?.locationDisputed || !row.locations.some(loc => loc.status === "resolved")).length,
    "Reviewer annotations: " + rows.filter(row => reviews[row.tweet_id]).length, "",
    ...rows.flatMap(row => [
      "## Record " + row.source_row + " [" + row.tweet_id + "]",
      "Automated relevance: " + (row.classification?.relevance ?? "unprocessed"),
      "Reviewer relevance: " + (reviews[row.tweet_id]?.relevance ?? "unchanged"),
      "Places: " + (row.locations.map(loc => (loc.canonical_name ?? loc.mention) + " (" + loc.status + "; " + placeRole(row.tweet, loc.mention) + ")").join(", ") || "No resolved location"),
      ...(reviews[row.tweet_id]?.locationDisputed ? ["LOCATION DISPUTED BY REVIEWER — excluded from investigation map"] : []),
      "Reviewer note: " + (reviews[row.tweet_id]?.note || "None"), "",
      "Source: " + row.tweet, "",
      ...interpret(row.tweet).signals.map(signal => "- " + signal.subject + " / " + signal.kind + ': "' + signal.evidence + '"'),
      "",
    ]),
  ].join("\n");
}
interface Props {
  processing: boolean;
  rows: ProcessedTweet[];
  scope: string;
  onPlace: (name: string) => void;
  reviews: Record<string, Review>;
  onReview: (id: string, review: Review) => void;
}
export default function Investigation({ rows, scope, onPlace, reviews, onReview, processing }: Props) {
  const [kind, setKind] = useState<ReportKind | "all" | "unmapped">("all");
  const [active, setActive] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [limit, setLimit] = useState(30);
  const [reviewMode, setReviewMode] = useState(false);
  const interpretations = useMemo(() => new Map(rows.map(row => [row.tweet_id, interpret(row.tweet)])), [rows]);
  const visible = rows.filter(row => kind === "all" || (kind === "unmapped" ?
    reviews[row.tweet_id]?.locationDisputed || !row.locations.some(loc => loc.status === "resolved") :
    interpretations.get(row.tweet_id)!.signals.some(signal => signal.kind === kind)));
  const current = visible.find(row => row.tweet_id === active) ?? visible[0];
  const insight = current ? interpretations.get(current.tweet_id)! : undefined;
  const review = current ? reviews[current.tweet_id] ?? { note: "" } : { note: "" };
  const marked = rows.filter(row => selected.has(row.tweet_id));
  const exported = marked.length ? marked : visible;
  const kinds: [ReportKind | "unmapped" | "all", string][] = [["all", "All evidence"], ["request", "Requests"], ["offer", "Offers"], ["correction", "Corrections & reassurance"], ["question", "Questions"], ["unmapped", "Unmapped / disputed"]];
  function saveBriefing() {
    const url = URL.createObjectURL(new Blob([briefingText(exported, scope + (marked.length ? " / manually selected subset across evidence types" : " / " + kind + " / all matching evidence"), reviews)], { type: "text/markdown;charset=utf-8" }));
    const link = document.createElement("a"); link.href = url; link.download = "community-briefing.md"; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  return <div className="investigation">
    <div className="investigation-heading"><div><span className="eyebrow">Community investigation</span><h3>{scope}</h3><p>{rows.length.toLocaleString()} matching reports. Categories describe language in the posts; they are not verified conditions.</p></div>
      <button className="primary" disabled={!exported.length} onClick={saveBriefing}>Export briefing ({exported.length})</button></div>
    <div className="triage-filters" aria-label="Evidence type">{kinds.map(([value, label]) => {
      const count = rows.filter(row => value === "all" || (value === "unmapped" ? reviews[row.tweet_id]?.locationDisputed || !row.locations.some(loc => loc.status === "resolved") : interpretations.get(row.tweet_id)!.signals.some(signal => signal.kind === value))).length;
      return <button key={value} aria-pressed={kind === value} onClick={() => { setKind(value); setActive(""); setLimit(30); }}><strong>{count}</strong>{label}</button>;
    })}</div>
    <p className="context-note">Requests, offers and corrections may describe different situations or times. No chronology is available to decide which statement is current. Evidence types can overlap.</p>
    <div className="investigation-toolbar"><span>{visible.length} reports in this view · {marked.length} selected for briefing{marked.some(row => !visible.some(item => item.tweet_id === row.tweet_id)) ? " (includes other evidence types)" : ""}</span><button className="text-button" onClick={() => setSelected(new Set())}>Clear selection</button><button className="text-button" onClick={() => setReviewMode(value => !value)}>{reviewMode ? "Show linked map" : "Focus on review"}</button></div>
    <div className={"investigation-grid" + (reviewMode ? " review-focus" : "")}>
      <section className="investigation-list" aria-label="Evidence list">
        {visible.slice(0, limit).map(row => <article className={current?.tweet_id === row.tweet_id ? "selected" : ""} key={row.tweet_id}>
          <label className="inline"><input type="checkbox" aria-label={"Include record " + row.source_row + " in briefing"} checked={selected.has(row.tweet_id)} onChange={event => setSelected(previous => { const next = new Set(previous); if (event.target.checked) next.add(row.tweet_id); else next.delete(row.tweet_id); return next; })} />Record {row.source_row}</label>
          <button className="report-select" aria-pressed={current?.tweet_id === row.tweet_id} onClick={() => setActive(row.tweet_id)}>
            <div className="signal-tags">{[...new Set(interpretations.get(row.tweet_id)!.signals.map(signal => signal.kind))].map(label => <span className={label} key={label}>{label}</span>)}</div>
            <p>{row.tweet}</p><small>{row.locations.map(loc => loc.canonical_name ?? loc.mention).join(" · ") || "Place unresolved"} {reviews[row.tweet_id] ? " · reviewed" : ""}</small>
          </button>
        </article>)}
        {!visible.length && <p className="empty-state">No evidence matches this type within the current filters.</p>}
        {visible.length > limit && <button className="secondary" onClick={() => setLimit(limit + 30)}>Show 30 more ({visible.length - limit} remaining)</button>}
      </section>
      <section hidden={reviewMode} className="investigation-map" aria-label="Linked community map"><MapPanel processing={processing} tweets={visible.filter(row => row.classification?.relevance === "relevant" && !reviews[row.tweet_id]?.locationDisputed)} onEvidence={id => setActive(id)} onPlace={onPlace} activeTweetId={current?.tweet_id} compact /></section>
      <section className="evidence-detail" aria-label="Selected evidence">
        {current ? <>
          <span className="eyebrow">Source record {current.source_row}</span><h3>What does this report say?</h3>
          <blockquote>{current.tweet}</blockquote>
          <p className="context-note">Original wording preserved. Report time and factual accuracy have not been verified.</p>
          {insight?.signals.map((signal, index) => <article className={"signal-detail " + signal.kind} key={index}><strong>{signal.subject} · {signal.kind}</strong><blockquote>{signal.evidence}</blockquote><p>{signal.explanation}</p></article>)}
          {!insight?.signals.length && <p>No specific meaning was confidently extracted by the baseline rules. Review the original wording.</p>}
          <h4>Place relationships</h4>
          {current.locations.length ? current.locations.map((loc, index) => <div className="place-role" key={index}><button className="text-button" onClick={() => onPlace(loc.canonical_name ?? loc.mention)}>{loc.canonical_name ?? loc.mention}</button><span>{placeRole(current.tweet, loc.mention)}</span><small>{loc.status} · approximate place centre if mapped</small></div>) : <p>Location unresolved. This report remains part of the evidence.</p>}
          <h4>Reviewer corrections</h4><p className="context-note">Saved for this session and briefing exports. The automated result stays intact.</p>
          <label>Reviewer relevance<select value={review.relevance ?? ""} onChange={event => onReview(current.tweet_id, { ...review, relevance: (event.target.value || undefined) as Review["relevance"] })}><option value="">Keep automated result ({current.classification?.relevance ?? "unprocessed"})</option><option value="relevant">Relevant</option><option value="unrelated">Unrelated</option><option value="uncertain">Uncertain</option></select></label>
          <label className="inline"><input type="checkbox" checked={review.locationDisputed ?? false} onChange={event => onReview(current.tweet_id, { ...review, locationDisputed: event.target.checked })} />Flag location as incorrect</label>
          <label>Review note<textarea rows={3} value={review.note} placeholder="Explain the correction or information that needs checking." onChange={event => onReview(current.tweet_id, { ...review, note: event.target.value })} /></label>
        </> : <p>Select a report to inspect its evidence.</p>}
      </section>
    </div>
    <details className="briefing-preview"><summary>Preview briefing ({exported.length} source records)</summary><p>Manual selections limit the export; clear selection to include the entire evidence-type view. Check corrections and opposing statements before sharing.</p><pre>{briefingText(exported.slice(0, 10), scope, reviews)}</pre>{exported.length > 10 && <p>Preview shows 10 records; the export includes all {exported.length}.</p>}</details>
  </div>;
}
