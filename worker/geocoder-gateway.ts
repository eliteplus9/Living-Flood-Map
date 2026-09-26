import { DurableObject } from "cloudflare:workers";

interface Env { LOCATIONIQ_API_KEY: string; GEOCODER: DurableObjectNamespace; }
export class GeocoderQueue extends DurableObject<Env> {
  async fetch(request: Request): Promise<Response> {
    // One account-wide object serializes provider calls and enforces a daily cap.
    return this.ctx.blockConcurrencyWhile(async () => {
      const { mention, country } = await request.json() as { mention?: unknown; country?: unknown };
      if (typeof mention !== "string" || !mention.trim() || mention.length > 240 ||
        (country != null && (typeof country !== "string" || !/^[a-z]{2}$/i.test(country)))) {
        return Response.json({ error: "Invalid place query." }, { status: 422 });
      }
      const cacheKey = `place:${(country || "").toString().toLowerCase()}:${mention.toLowerCase()}`;
      const cached = await this.ctx.storage.get<{ at: number; rows: unknown[] }>(cacheKey);
      if (cached && Date.now() - cached.at < 24 * 60 * 60 * 1000) return Response.json(cached.rows);
      const day = new Date().toISOString().slice(0, 10);
      const quota = await this.ctx.storage.get<{ day: string; count: number }>("quota");
      const used = quota?.day === day ? quota.count : 0;
      if (used >= 1000) return Response.json({ error: "Daily geocoding safety cap reached. Retry tomorrow." }, { status: 429 });
      const last = await this.ctx.storage.get<number>("last") || 0;
      const wait = Math.max(0, 1100 - (Date.now() - last));
      if (wait) await new Promise(resolve => setTimeout(resolve, wait));
      await this.ctx.storage.put({ quota: { day, count: used + 1 }, last: Date.now() });
      const url = new URL("https://us1.locationiq.com/v1/search");
      url.search = new URLSearchParams({ key: this.env.LOCATIONIQ_API_KEY, q: mention,
        format: "json", limit: "5", addressdetails: "1", ...(country ? { countrycodes: country.toString().toLowerCase() } : {}) }).toString();
      let response: Response;
      try { response = await fetch(url, { redirect: "manual", signal: AbortSignal.timeout(10_000) }); }
      catch { return Response.json({ error: "Geocoding provider unavailable." }, { status: 503 }); }
      if (response.status === 404) {
        await this.ctx.storage.put(cacheKey, { at: Date.now(), rows: [] });
        return Response.json([]);
      }
      if (!response.ok) return Response.json({ error: response.status === 401 || response.status === 403
        ? "Geocoding provider rejected credentials." : "Geocoding provider unavailable or quota exceeded." }, { status: 503 });
      let rows: unknown;
      try { rows = await response.json(); } catch { return Response.json({ error: "Invalid provider response." }, { status: 502 }); }
      if (!Array.isArray(rows)) return Response.json({ error: "Invalid provider response." }, { status: 502 });
      await this.ctx.storage.put(cacheKey, { at: Date.now(), rows });
      // Remove expired cached records each day; never retain tweet bodies.
      const cleaned = await this.ctx.storage.get<string>("cleaned");
      if (cleaned !== day) {
        const entries = await this.ctx.storage.list<{ at: number }>({ prefix: "place:" });
        for (const [key, entry] of entries) if (Date.now() - entry.at >= 24 * 60 * 60 * 1000) await this.ctx.storage.delete(key);
        await this.ctx.storage.put("cleaned", day);
      }
      return Response.json(rows);
    });
  }
}

export default {
  async fetch(request: Request, env: Env) {
    if (!env.LOCATIONIQ_API_KEY) return Response.json({ error: "Geocoding secret missing." }, { status: 503 });
    return env.GEOCODER.get(env.GEOCODER.idFromName("account-wide")).fetch(request);
  },
} satisfies ExportedHandler<Env>;
