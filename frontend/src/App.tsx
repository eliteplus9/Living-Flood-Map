import { useEffect, useMemo, useRef, useState } from "react";
import type { Classification, LocationResult, ProcessedTweet } from "../../shared/contracts";
import { processBatches } from "./api";
import { parseCsv, rowsToTweets, type ParsedCsv } from "./csv";
import { defaultFilters, exportCsv, filterReports, rankedCounts, type Filters } from "./analysis";
import MapPanel from "./MapPanel";
import Investigation from "./Investigation";
import type { Review } from "../../shared/interpretation";

type Tab = "investigate" | "overview" | "reports" | "map";
const number = (value: number) => value.toLocaleString();

export default function App() {
  const [parsed, setParsed] = useState<ParsedCsv>();
  const [column, setColumn] = useState("tweet");
  const [fileName, setFileName] = useState("");
  const [region, setRegion] = useState("");
  const [countryCode, setCountryCode] = useState("");
  const [results, setResults] = useState<ProcessedTweet[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [phase, setPhase] = useState("");
  const [tab, setTab] = useState<Tab>("map");
  const [filters, setFilters] = useState<Filters>({ ...defaultFilters });
  const [page, setPage] = useState(1);
  const [reviews, setReviews] = useState<Record<string, Review>>({});
  const [intakeOpen, setIntakeOpen] = useState(false);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [elapsed, setElapsed] = useState<number>();
  const [classifierMode, setClassifierMode] = useState<"preview" | "service" | "unconfigured" | "unknown">("unknown");
  const [locationMode, setLocationMode] = useState<"preview" | "service" | "unconfigured" | "unknown">("unknown");
  const controller = useRef<AbortController | null>(null);
  const loadVersion = useRef(0);
  const panel = useRef<HTMLElement>(null);
  const inputRows = useMemo(() => parsed ? rowsToTweets(parsed.rows, column) : [], [parsed, column]);
  const skipped = (parsed?.rows.length ?? 0) - inputRows.length;
  useEffect(() => {
    const control = new AbortController();
    fetch("/api/health", { signal: control.signal }).then(response => response.json())
      .then((health: { classifier_mode?: string; location_mode?: string }) => {
        setClassifierMode(health.classifier_mode === "service" ? "service" : health.classifier_mode === "preview" ? "preview" : "unconfigured");
        setLocationMode(health.location_mode === "service" ? "service" : health.location_mode === "preview" ? "preview" : "unconfigured");
      })
      .catch(() => { if (!control.signal.aborted) { setClassifierMode("unknown"); setLocationMode("unknown"); } });
    return () => control.abort();
  }, []);

  async function acceptFile(file: File, sample = false) {
    const version = ++loadVersion.current;
    controller.current?.abort();
    setBusy(false); setLoading(true); setParsed(undefined); setError(""); setResults([]); setPhase("");
    setFilters({ ...defaultFilters }); setPage(1);
    setReviews({}); setElapsed(undefined); setIntakeOpen(true);
    try {
      const next = await parseCsv(file);
      if (version !== loadVersion.current) return;
      if (!next.rows.length || !next.columns.length) throw new Error("This CSV has no data rows. Include a header and at least one report.");
      setParsed(next); setColumn(next.columns.find(item => item.toLowerCase() === "tweet") ?? next.columns[0]);
      setFileName(file.name); setRegion(sample ? "Alberta, Canada" : ""); setCountryCode(sample ? "CA" : "");
    } catch (cause) {
      if (version === loadVersion.current) setError(cause instanceof Error ? cause.message : String(cause));
    } finally { if (version === loadVersion.current) setLoading(false); }
  }
  async function loadSample() {
    setLoading(true); setError("");
    try {
      const response = await fetch("/data/main_contestant.csv");
      if (!response.ok) throw new Error("Sample could not be loaded. Choose the CSV from your computer.");
      await acceptFile(new File([await response.blob()], "main_contestant.csv", { type: "text/csv" }), true);
    } catch (cause) { setLoading(false); setError(String(cause)); }
  }
  function resetAnalysis() { controller.current?.abort(); setResults([]); setPhase(""); setBusy(false); }
  async function analyze(retry = false) {
    const started = performance.now();
    if (!inputRows.length) { setError("The selected column contains no usable text."); return; }
    if (countryCode && !/^[A-Za-z]{2}$/.test(countryCode)) { setError("Use a two-letter country code, or leave it blank for worldwide matching."); return; }
    controller.current?.abort();
    const control = new AbortController(); controller.current = control;
    const working: ProcessedTweet[] = retry ? results.map(row => ({ ...row, locations: [...row.locations] })) :
      inputRows.map(row => ({ ...row, locations: [] }));
    const byId = new Map(working.map(row => [row.tweet_id, row]));
    const context = { event_name: "Flood", region: region.trim(), country_code: countryCode.trim().toUpperCase() || undefined };
    setBusy(true); setError(""); setProgress(0); setPhase("Classifying reports"); setIntakeOpen(false); setTab("map");
    if (!retry) setReviews({});
    setResults(working); setPage(1);
    try {
      await processBatches<Classification>(working.filter(row => !row.classification), "/api/classify", context,
        (batch, output, failure) => {
          const labels = new Map(output.map(item => [item.tweet_id, item]));
          batch.forEach(row => { const target = byId.get(row.tweet_id)!; target.classification = labels.get(row.tweet_id); target.classification_error = failure; });
          setResults(working.map(row => ({ ...row })));
        }, (done, total) => setProgress(done / total * 65), control.signal);
      setPhase("Resolving mentioned places");
      const candidates = working.filter(row => row.classification?.relevance === "relevant" &&
        (!retry || row.location_error || !results.find(old => old.tweet_id === row.tweet_id)?.classification));
      await processBatches<LocationResult>(candidates, "/api/locations", context,
        (batch, output, failure) => {
          batch.forEach(row => {
            const target = byId.get(row.tweet_id)!;
            target.locations = output.filter(item => item.tweet_id === row.tweet_id);
            target.location_error = failure;
          });
          setResults(working.map(row => ({ ...row })));
        }, (done, total) => setProgress(65 + done / total * 35), control.signal);
      const failed = working.filter(row => !row.classification || row.location_error).length;
      setProgress(100); setPhase(failed ? `Analysis finished · ${number(failed)} reports need a retry` : "Analysis complete");
      setElapsed((performance.now() - started) / 1000);
      setIntakeOpen(false);
    } catch (cause) {
      if (control.signal.aborted) {
        working.forEach(row => {
          if (!row.classification) row.classification_error = "Analysis cancelled before classification.";
          else if (row.classification.relevance === "relevant" && !row.locations.length) row.location_error = "Location step may be incomplete.";
        });
        setResults(working.map(row => ({ ...row }))); setPhase("Cancelled · completed results are preserved");
      } else { setError(cause instanceof Error ? cause.message : String(cause)); }
    } finally { if (controller.current === control) setBusy(false); }
  }
  const filtered = useMemo(() => filterReports(results, filters), [results, filters]);
  const categories = useMemo(() => rankedCounts(filtered, "category"), [filtered]);
  const places = useMemo(() => rankedCounts(filtered, "location"), [filtered]);
  const allCategories = useMemo(() => rankedCounts(results, "category"), [results]);
  const allPlaces = useMemo(() => rankedCounts(results, "location"), [results]);
  const failed = results.filter(row => !row.classification || row.location_error).length;
  const noLocation = filtered.filter(row => row.classification?.relevance === "relevant" && !row.locations.some(loc => loc.status === "resolved")).length;
  const mapped = filtered.filter(row => row.classification?.relevance === "relevant" && row.locations.some(loc => loc.status === "resolved")).length;
  const pages = Math.max(1, Math.ceil(filtered.length / 30));
  const activePage = Math.min(page, pages);
  const visible = filtered.slice((activePage - 1) * 30, activePage * 30);
  function changeFilter<K extends keyof Filters>(key: K, value: Filters[K]) {
    setFilters(current => ({ ...current, [key]: value })); setPage(1);
  }
  function download() {
    const url = URL.createObjectURL(new Blob([exportCsv(filtered)], { type: "text/csv;charset=utf-8" }));
    const link = document.createElement("a"); link.href = url; link.download = "flood-reports.csv"; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  function showEvidence(tweetId: string) {
    const index = filtered.findIndex(row => row.tweet_id === tweetId);
    setPage(Math.floor(Math.max(0, index) / 30) + 1); setTab("reports");
    setTimeout(() => document.getElementById(tweetId)?.scrollIntoView({ behavior: "smooth", block: "center" }), 100);
  }

  return <div className="app-shell">
    <header className="app-bar">
      <h1><span aria-hidden="true">≈</span> Living Flood Map</h1>
      <nav className="tabs" aria-label="Analysis views">{(["map", "reports", "investigate", "overview"] as Tab[]).map(item => <button aria-current={tab === item ? "page" : undefined} className={tab === item ? "active" : ""} key={item} onClick={() => setTab(item)}>{item}</button>)}</nav>
      <button className="secondary dataset-button" aria-expanded={intakeOpen} aria-controls="dataset-panel" onClick={() => setIntakeOpen(value => !value)}>{parsed ? "Dataset / settings" : "Upload CSV"}</button>
    </header>
    <main>
      <section id="dataset-panel" hidden={!intakeOpen} className="panel intake" aria-labelledby="intake-heading" onKeyDown={event => { if (event.key === "Escape") setIntakeOpen(false); }}>
        <div className="section-heading"><h2 id="intake-heading">Dataset</h2><button className="text-button" onClick={() => setIntakeOpen(false)}>Close settings</button></div>
        <p className="privacy">CSV · up to 10 MB / 25,000 rows</p>
        {results.length > 0 && !busy && <div className="dataset-switch"><span>{fileName} · {number(results.length)} reports {elapsed !== undefined ? "· " + elapsed.toFixed(1) + " seconds processing" : ""}</span></div>}
        <div hidden={!intakeOpen && !busy}>
        <div className="upload-row">
          <label className="upload-box" onDragOver={event => event.preventDefault()} onDrop={event => { event.preventDefault(); if (!busy && !loading && event.dataTransfer.files[0]) void acceptFile(event.dataTransfer.files[0]); }}>
            <span className="upload-icon" aria-hidden="true">↑</span><strong>{loading ? "Reading dataset…" : fileName || "Choose a CSV or drop it here"}</strong><span>One social report per row. Select your text column after upload.</span>
            <input aria-label="Upload CSV" disabled={busy || loading} type="file" accept=".csv,text/csv" onChange={event => { if (event.target.files?.[0]) void acceptFile(event.target.files[0]); event.target.value = ""; }} />
          </label>
          <div className="sample-card"><span className="eyebrow">Try the supplied dataset</span><strong>Alberta flood reports</strong><p>8,024 posts · historical dataset</p><button className="secondary" disabled={busy || loading} onClick={loadSample}>Use supplied dataset</button></div>
        </div>
        {parsed && <>
          <div className="configuration">
            <label>Report text column<select disabled={busy} value={column} onChange={event => { resetAnalysis(); setColumn(event.target.value); }}>{parsed.columns.map(item => <option key={item}>{item}</option>)}</select></label>
            <label>Regional context (optional)<input disabled={busy} value={region} placeholder="e.g. Alberta, Canada" onChange={event => { resetAnalysis(); setRegion(event.target.value); }} /></label>
            <label>Country code for place matching (optional)<input disabled={busy} value={countryCode} maxLength={2} placeholder="e.g. CA" onChange={event => { resetAnalysis(); setCountryCode(event.target.value.toUpperCase()); }} /></label>
            <div className="dataset-stat"><strong>{number(inputRows.length)}</strong><span>usable reports · {number(skipped)} blank rows skipped</span></div>
          </div>
          <details className="preview"><summary>Preview selected column</summary>{inputRows.slice(0, 3).map(row => <p key={row.tweet_id}><small>Record {row.source_row}</small>{row.tweet}</p>)}</details>
          {parsed.warnings.length > 0 && <div className="alert warning">{parsed.warnings.join(" ")}</div>}
        </>}
        <div className="action-row"><button className="primary" disabled={!inputRows.length || busy || loading} onClick={() => analyze()}>{busy ? "Analysis in progress…" : results.length ? "Run analysis again" : "Analyze dataset"} <span aria-hidden="true">↗</span></button>
          {busy && <button className="secondary" onClick={() => controller.current?.abort()}>Cancel analysis</button>}
        </div>
        <p className="baseline-note">{classifierMode === "service" ? "Classification uses Edward's hosted disaster-relevance model through the Worker. Relevance scores are uncalibrated estimates, not verification or severity." : classifierMode === "preview" ? "Classification uses local keyword preview rules until the Worker classifier secret is configured. Scores are heuristic, not measured accuracy." : classifierMode === "unconfigured" ? "The hosted classifier is only partly configured; classification will fail until both the URL and Worker secret are set." : "Classifier status could not be checked; verify the API before relying on these results."} {locationMode === "service" ? "Location matching uses Mutasim's service. Mentioned places are approximate, not verified incident sites." : locationMode === "preview" ? "Place detection uses a limited Alberta gazetteer until a location service is configured." : locationMode === "unconfigured" ? "The location service is only partly configured; location matching will fail until both its URL and Worker secret are set." : "Location service status could not be checked."} Uploaded report text is processed by this Worker and, when configured, forwarded to those services. Other places may remain unmapped. Refreshing clears this session.</p>
        </div>
        {locationMode === "service" && <p className="baseline-note">Geocoding: <a href="https://locationiq.com" target="_blank" rel="noopener noreferrer">Search by LocationIQ.com</a>. Only extracted place queries are sent to LocationIQ. A daily safety cap and provider quotas can pause processing; location scores are heuristic, not verified accuracy.</p>}
      </section>
      {error && <div className="alert error" role="alert">{error}</div>}
      {phase && <div className="processing-status"><span role="status">{phase}</span>{busy ? <><progress aria-label="Analysis progress" value={progress} max={100} /><button className="text-button" onClick={() => controller.current?.abort()}>Cancel analysis</button></> : failed > 0 && <button className="text-button" onClick={() => analyze(true)}>Retry incomplete reports ({number(failed)})</button>}</div>}
      <section className={"workspace " + (tab === "map" ? "map-workspace" : "")} ref={panel} aria-label="Analysis results">
        <div className="workspace-toolbar">
          <label className="search-control"><span className="sr-only">Search reports</span><input type="search" placeholder="Search reports or places" value={filters.query} onChange={event => changeFilter("query", event.target.value)} /></label>
          <button className="secondary" aria-expanded={filtersOpen} aria-controls="report-filters" onClick={() => setFiltersOpen(value => !value)}>Filters</button>
          <span className="view-count">{number(filtered.length)} matching reports</span>
          <button className="secondary export-control" onClick={download} disabled={!filtered.length}>Export filtered CSV ↓</button>
        </div>
        <div id="report-filters" hidden={!filtersOpen}>
        <div className="dataset-totals" aria-label="Dataset totals">
          {["relevant", "unrelated", "uncertain"].map(label => <span key={label}><strong>{number(results.filter(row => row.classification?.relevance === label).length)}</strong> {label}</span>)}
          <span><strong>{number(results.filter(row => row.classification?.needs_review).length)}</strong> needs review</span><span><strong>{number(results.filter(row => !row.classification).length)}</strong> unprocessed</span><span><strong>{number(results.length)}</strong> total</span>
        </div>
        <div className="filters">
          <label>Relevance<select value={filters.relevance} onChange={event => changeFilter("relevance", event.target.value)}><option value="all">All reports</option><option value="relevant">Relevant</option><option value="uncertain">Uncertain</option><option value="unrelated">Unrelated</option><option value="failed">Unprocessed</option></select></label>
          <label>Category<select value={filters.category} onChange={event => changeFilter("category", event.target.value)}><option value="all">All categories</option>{allCategories.map(([name]) => <option key={name}>{name}</option>)}</select></label>
          <label>Place<select value={filters.location} onChange={event => changeFilter("location", event.target.value)}><option value="all">All places</option>{allPlaces.map(([name]) => <option key={name}>{name}</option>)}</select></label>
        </div>
        <div className="filter-options"><label className="inline"><input type="checkbox" checked={filters.unique} onChange={event => changeFilter("unique", event.target.checked)} /> Unique reports only</label>
          <label className="inline">Minimum relevance score <input aria-label="Minimum relevance score" type="range" min="0" max="1" step=".05" value={filters.minScore} onChange={event => changeFilter("minScore", Number(event.target.value))} /><strong>{Math.round(filters.minScore * 100)}%</strong></label>
          <button className="text-button" onClick={() => { setFilters({ ...defaultFilters }); setPage(1); }}>Reset filters</button>
        </div>
        </div>
        <div className="view-content">
          {tab === "investigate" && <Investigation rows={filtered} scope={(filters.location === "all" ? "All communities" : filters.location) + (filters.query ? " · Search: " + filters.query : "") + " · " + filters.relevance + (filters.unique ? " · unique texts" : " · all rows")}
            onPlace={name => changeFilter("location", name)} reviews={reviews} onReview={(id, review) => setReviews(current => ({ ...current, [id]: review }))} />}
          {tab === "overview" && <>
            <div className="metric-grid">{[["Matching reports", filtered.length], ["Relevant reports mapped", mapped], ["Places mentioned", places.length], ["Relevant without a map point", noLocation]].map(([label, count]) => <article key={label}><span>{label}</span><strong>{number(count as number)}</strong></article>)}</div>
            <div className="summary-card"><span className="eyebrow">Overview of the current selection</span><p>{filtered.length ? `Across ${number(filtered.length)} selected reports, ${number(mapped)} relevant reports mention a mapped place. ${places.length ? "The most mentioned places are " + places.slice(0, 3).map(([name, count]) => name + " (" + number(count) + ")").join(", ") + "." : "No resolved places are present in this selection."}` : "No reports match these filters. Clear your search or reset the filters to explore the dataset."}</p><small>Computed from every matching report. Mention counts describe reporting activity, not flood severity or verified incidents.</small></div>
            <div className="breakdowns">{[[categories, "Report categories"], [places, "Mentioned places"]].map(([entries, title]) => <section key={title as string}><h3>{title as string}</h3>{(entries as [string, number][]).slice(0, 6).map(([name, count]) => <div className="bar-row" key={name}><span>{name}</span><div><i style={{ width: (count / Math.max(1, filtered.length) * 100) + "%" }} /></div><strong>{number(count)}</strong></div>)}{!(entries as unknown[]).length && <p className="muted">Nothing to display for this selection.</p>}</section>)}</div>
            <h3>Source evidence</h3><div className="evidence-grid">{filtered.slice(0, 3).map(row => <button key={row.tweet_id} onClick={() => showEvidence(row.tweet_id)}><small>Record {row.source_row} ↗</small><p>{row.tweet}</p></button>)}</div>
          </>}
          {tab === "reports" && <>
            <div className="pagination"><span>{filtered.length ? `${number((activePage - 1) * 30 + 1)}–${number(Math.min(activePage * 30, filtered.length))} of ${number(filtered.length)} reports` : "No matching reports"}</span><div><button className="secondary" disabled={activePage <= 1} onClick={() => setPage(activePage - 1)}>Previous</button><span>Page {activePage} / {pages}</span><button className="secondary" disabled={activePage >= pages} onClick={() => setPage(activePage + 1)}>Next</button></div></div>
            {!visible.length && <div className="empty-state">No reports match. Try another search or reset your filters.</div>}
            <div className="report-list">{visible.map(row => <article id={row.tweet_id} key={row.tweet_id}><div className="report-meta"><span className={"badge " + (row.classification?.relevance ?? "uncertain")}>{row.classification?.relevance ?? (busy ? "pending" : "unprocessed")}</span><span>Record {row.source_row}</span>{row.classification && <span>Relevance score: {Math.round(row.classification.relevance_score * 100)}%</span>}{row.classification?.needs_review && <span>Needs review</span>}{row.duplicate_of && <span>Repeated text</span>}</div><p>{row.tweet}</p><div className="locations">{row.locations.map((loc, index) => <span key={index}>{loc.canonical_name ?? loc.mention} · {loc.status}</span>)}</div>{(row.classification_error || row.location_error) && <p className="error-text">{row.classification_error ?? row.location_error}</p>}<details><summary>Why this result?</summary><p>{row.classification?.reason ?? "Processing did not complete. Retry this report."}</p><small>{row.classification?.model_version} · ID: {row.tweet_id}</small></details></article>)}</div>
          </>}
          {tab === "map" && <div className="map-stage"><MapPanel tweets={filtered.filter(row => row.classification?.relevance === "relevant")} onEvidence={showEvidence} />
            {!results.length && <div className="map-start"><strong>No dataset loaded</strong><p>Upload a CSV to map its reports.</p><div><button className="primary" onClick={() => setIntakeOpen(true)}>Choose a CSV</button><button className="secondary" disabled={loading} onClick={loadSample}>Use supplied dataset</button></div><small>Sample: Alberta floods, 2013</small></div>}
          </div>}
        </div>
      </section>
    </main><footer><span>{fileName || "No dataset"} · Mentioned places, not verified incidents</span><span>{classifierMode === "preview" || locationMode === "preview" ? "Preview services" : classifierMode === "service" && locationMode === "service" ? "Services connected" : "Check service status"}{locationMode === "service" && <> · <a href="https://locationiq.com" target="_blank" rel="noopener noreferrer">Search by LocationIQ.com</a></>}</span></footer>
  </div>;
}
