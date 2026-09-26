/** Supplemental interpretation; the original classifier and location contracts remain unchanged. */
export type ReportKind = "request" | "offer" | "correction" | "question" | "report";
export interface Signal {
  subject: string;
  kind: ReportKind;
  evidence: string;
  explanation: string;
}
export interface Interpretation {
  signals: Signal[];
  method: "evidence-rules-v1";
  needsReview: boolean;
}
export interface Review {
  relevance?: "relevant" | "unrelated" | "uncertain";
  locationDisputed?: boolean;
  note: string;
}
export function interpret(text: string): Interpretation {
  const signals: Signal[] = [];
  // Separate clauses so a denial about one subject cannot negate every other statement.
  const clauses = text.split(/(?<=[.!?;])\s+|\s+but\s+/i);
  for (const clause of clauses) {
    const subjects = [
      ["Access", /\b(bridge|roads?|highway|closed|closure|impassable)\b/i],
      ["Evacuation", /\b(evacuat\w*|shelter\w*)\b/i],
      ["Utilities", /\b(power|electricity|outage|drinking water|boil water)\b/i],
      ["Supplies & assistance", /\b(clothing|donat\w*|supplies|volunteer\w*|help|food|blankets|rescu\w*|livestock)\b/i],
      ["Flood conditions", /\b(flood\w*|dam|breach|damage|underwater|under water|basement)\b/i],
    ] as const;
    for (const [subject, pattern] of subjects) {
      if (!pattern.test(clause)) continue;
      const negative = /\b(no longer (?:needed|required)|not (?:needed|required)|no (?:risk|need|livestock)|safe and sound|reopened|re-opened|has been lifted)\b/i;
      const question = /\?|\b(?:is there|does anyone|can anyone confirm|are there|any updates)\b/i;
      const request = /\b(?:need(?:s|ed)?|urgent(?:ly)?|please (?:bring|deliver|send|help)|seeking|requesting)\b/i;
      const offer = /\b(?:accepting donations|offering|we (?:can|will)|available|at no charge|free meals|drop off|drop-off)\b/i;
      const kind: ReportKind = question.test(clause) ? "question" : negative.test(clause) ? "correction" :
        request.test(clause) ? "request" : offer.test(clause) ? "offer" : "report";
      if (signals.some(signal => signal.subject === subject && signal.kind === kind && signal.evidence === clause.trim())) continue;
      signals.push({ subject, kind, evidence: clause.trim(),
        explanation: kind === "correction" ? "Contains a denial, reassurance or change in need. Do not treat as an active hazard/request without reading the source." :
          kind === "question" ? "Asks about conditions; does not establish that they occurred." :
          kind === "request" ? "Contains request or need language. Check the source and who it refers to." :
          kind === "offer" ? "Contains assistance or donation-offer language. Availability is unverified." :
          "Mentions this subject. The wording alone does not establish an incident." });
    }
  }
  return { signals, method: "evidence-rules-v1", needsReview: !signals.length || signals.some(s => s.kind === "question" || s.kind === "correction") };
}
export function placeRole(text: string, mention: string): string {
  const index = text.toLowerCase().indexOf(mention.toLowerCase());
  if (index < 0) return "Role unresolved";
  const before = text.slice(Math.max(0, index - 45), index);
  const after = text.slice(index + mention.length, index + mention.length + 35);
  if (/\b(?:donations?|supplies|clothing|food|help)\s+(?:\w+\s+){0,2}for\s+#?$/i.test(before)) return "Possible beneficiary";
  if (/\b(?:at|to)\s+(?:our\s+)?#?$/i.test(before) && /office|drop.?off|collection|centre/i.test(after)) return "Possible collection point";
  return "Mentioned place · role unresolved";
}
