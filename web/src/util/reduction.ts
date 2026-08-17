/**
 * Reading an arbitrary reduction document.
 *
 * A reduction's `json` is whatever the playbook banked — the engine's schema
 * stays generic on purpose, so the control plane cannot know its shape. The
 * findings list previously rendered `json.title`, which no reduction in
 * practice has: every card read "Untitled reduction", nineteen in a row, with
 * the content that distinguishes them never shown at all.
 *
 * So the document is read structurally instead of by key. Across the shapes
 * that exist — item/diff analyses, syntheses, reports — the pattern holds:
 *
 *   * a short string one level down is a title (`item.title`, `diff.title`)
 *   * scalars and small lists are facts (`status`, `succeeded_agents`)
 *   * long string leaves are the content (`report`, `analyses[].analysis`)
 *
 * These are heuristics over an open format, so each degrades to something
 * honest: no headline falls back to the kind rather than inventing a name, and
 * the whole document stays available to the reader regardless.
 */

/** Below this a string is a label; at or above it, it is content. */
const PROSE_MIN = 200;

/** A headline has to fit on one line. */
const HEADLINE_MAX = 160;

/** Documents nest a couple of levels; this is a loop guard, not a limit. */
const MAX_DEPTH = 6;

/** Keys the headline may consume, so the facts strip does not repeat it. */
const HEADLINE_KEYS = new Set(['title', 'name', 'subject']);

type Json = unknown;

function isObject(v: Json): v is Record<string, Json> {
  return typeof v === 'object' && v !== null && !Array.isArray(v);
}

/** How far into a body to look for a heading before giving up. */
const HEADING_SCAN_LINES = 20;

/**
 * The first markdown heading near the top of a body of prose.
 *
 * Not just line one: a report routinely opens with a sentence of preamble and
 * puts its heading below that, and looking only at the first line left the most
 * valuable card in the list named after its own kind.
 */
function firstHeading(text: string): string | null {
  const lines = text.trimStart().split('\n', HEADING_SCAN_LINES);
  for (const line of lines) {
    const m = /^#{1,6}\s+(.*\S)\s*$/.exec(line.trim());
    if (m) return m[1].slice(0, HEADLINE_MAX);
  }
  return null;
}

/**
 * The opening sentence of a body of prose, when it is short enough to be a name.
 *
 * Last resort before falling back to the kind: a synthesis that opens "Merging
 * the single analysis into one account." says more than "item_syntheses" does.
 */
function firstSentence(text: string): string | null {
  const opening = text.trimStart().split('\n').find((l) => l.trim())?.trim();
  if (!opening || opening.startsWith('#') || opening.startsWith('<')) return null;
  const m = /^(.{10,160}?[.!?])(\s|$)/.exec(opening);
  const candidate = m ? m[1] : opening;
  return candidate.length <= HEADLINE_MAX ? candidate : null;
}

/**
 * A one-line name for this reduction, or the kind when it has no name.
 *
 * Order: an explicit top-level `title`, then a title one level down (the shape
 * every analysis document uses), then the opening heading of a report body.
 */
export function reductionHeadline(json: Json, kind: string): string {
  if (!isObject(json)) return kind;

  const top = json.title;
  if (typeof top === 'string' && top.trim()) return top.trim().slice(0, HEADLINE_MAX);

  for (const value of Object.values(json)) {
    if (isObject(value)) {
      const nested = value.title ?? value.name ?? value.subject;
      if (typeof nested === 'string' && nested.trim()) {
        return nested.trim().slice(0, HEADLINE_MAX);
      }
    }
  }

  const bodies = reductionProse(json).map((p) => p.text);
  for (const body of bodies) {
    const heading = firstHeading(body);
    if (heading) return heading;
  }
  for (const body of bodies) {
    const sentence = firstSentence(body);
    if (sentence) return sentence;
  }

  return kind;
}

/**
 * The scalars that say what happened, as `key: value` pairs.
 *
 * Top-level scalars, plus identifiers one level down, plus short lists rendered
 * as their contents and long ones as a count. Prose is excluded — it is content,
 * and it has its own place.
 */
export function reductionFacts(json: Json): Array<{ key: string; value: string }> {
  if (!isObject(json)) return [];
  const facts: Array<{ key: string; value: string }> = [];

  for (const [key, value] of Object.entries(json)) {
    if (HEADLINE_KEYS.has(key)) continue;
    if (typeof value === 'string') {
      if (value.length < PROSE_MIN && value.trim()) facts.push({ key, value });
    } else if (typeof value === 'number' || typeof value === 'boolean') {
      facts.push({ key, value: String(value) });
    } else if (Array.isArray(value)) {
      const scalars = value.filter((v) => typeof v === 'string' || typeof v === 'number');
      if (scalars.length === value.length && value.length > 0 && value.length <= 4) {
        facts.push({ key, value: scalars.join(', ') });
      } else if (value.length > 0) {
        facts.push({
          key,
          value: `${value.length} ${value.length === 1 ? 'item' : 'items'}`,
        });
      }
    } else if (isObject(value)) {
      for (const idKey of ['id', 'number', 'ticket_id']) {
        const id = value[idKey];
        if (typeof id === 'string' || typeof id === 'number') {
          facts.push({ key: `${key}.${idKey}`, value: String(id) });
          break;
        }
      }
    }
  }

  return facts;
}

/**
 * The document's actual content: every long string leaf, with its path.
 *
 * One entry per agent analysis, per synthesis, or the single report body —
 * without the reader having to know which of those this document is.
 */
export function reductionProse(json: Json): Array<{ path: string; text: string }> {
  const out: Array<{ path: string; text: string }> = [];

  const walk = (value: Json, path: string, depth: number): void => {
    if (depth > MAX_DEPTH) return;
    if (typeof value === 'string') {
      if (value.length >= PROSE_MIN) out.push({ path, text: value });
      return;
    }
    if (Array.isArray(value)) {
      value.forEach((item, i) => walk(item, `${path}[${i}]`, depth + 1));
      return;
    }
    if (isObject(value)) {
      for (const [key, child] of Object.entries(value)) {
        walk(child, path ? `${path}.${key}` : key, depth + 1);
      }
    }
  };

  walk(json, '', 0);
  return out;
}

/**
 * Whether this reduction is holding a ticket that needs a person.
 *
 * The accept/reject decision is not "do I like this conclusion" — it is how a
 * `needs_human` ticket gets resolved: accept settles it to `done`, reject to
 * `failed`. A reduction routing no ticket to a human therefore has no decision
 * to make, and offering the buttons anyway implies an authority they do not
 * have: they would flip a flag and move nothing.
 *
 * Both spellings of the state are accepted. The engine writes `needs_human` and
 * the UI normalises to `needs-human`; a review queue that quietly empties itself
 * over an underscore is the worst way this could fail.
 */
export function awaitsDecision(reduction: {
  review_state: string;
  member_tickets: Array<{ state: string; [k: string]: unknown }>;
}): boolean {
  if (reduction.review_state !== 'pending') return false;
  return reduction.member_tickets.some(
    (t) => t.state === 'needs-human' || t.state === 'needs_human',
  );
}

/**
 * The key holding what this reduction *produced*, or null.
 *
 * A reduction document mixes what the agent was given with what it returned:
 * `item_analyses` carries both the item (id, title, an 800-line context) and
 * the analyses of it. Leading a card with the first is leading with hermes's own
 * input, which teaches the reader nothing.
 *
 * The kind names the payload. `item_analyses` → `analyses`, `research_report` →
 * `report`, `item_syntheses` → `syntheses`: true for every reduction kind the
 * built-in playbooks emit. A kind that names nothing returns null, and the
 * caller treats the whole document as content rather than guessing.
 */
export function primaryPath(json: Json, kind: string): string | null {
  if (!isObject(json)) return null;
  const tokens = String(kind).split(/[_\-.]/).filter(Boolean);
  const candidates = [kind, tokens[tokens.length - 1]].filter(Boolean) as string[];
  for (const key of candidates) {
    if (key in json) return key;
  }
  return null;
}

/**
 * Prose split into what the run produced and everything else.
 *
 * `primary` is the conclusion — what a reader came to learn. `secondary` is the
 * material behind it, worth keeping but not worth leading with.
 */
export function splitProse(
  json: Json,
  kind: string,
): { primary: Array<{ path: string; text: string }>; secondary: Array<{ path: string; text: string }> } {
  const all = reductionProse(json);
  const key = primaryPath(json, kind);
  if (!key) return { primary: all, secondary: [] };
  return {
    primary: all.filter((p) => p.path === key || p.path.startsWith(`${key}[`) || p.path.startsWith(`${key}.`)),
    secondary: all.filter(
      (p) => !(p.path === key || p.path.startsWith(`${key}[`) || p.path.startsWith(`${key}.`)),
    ),
  };
}

/**
 * A list payload as one labelled entry per element.
 *
 * `syntheses` holds one write-up per item, `analyses` one per agent. Rendered
 * as prose they stack into a card as seventeen documents — more reading than
 * the run was meant to save. As rows they are scannable.
 *
 * The label is whatever distinguishes the entries: the item they are about, or
 * the agent that wrote them. Entries with no prose in them are not rows.
 */
export function primaryItems(
  json: Json,
  kind: string,
): Array<{ id: string; label: string; text: string }> {
  const key = primaryPath(json, kind);
  if (!key || !isObject(json)) return [];
  const value = json[key];
  if (!Array.isArray(value)) return [];

  const out: Array<{ id: string; label: string; text: string }> = [];
  value.forEach((entry, i) => {
    if (!isObject(entry)) return;
    const text = Object.values(entry).find(
      (v) => typeof v === 'string' && v.length >= PROSE_MIN,
    ) as string | undefined;
    if (!text) return;
    const label =
      [entry.item_id, entry.agent, entry.id, entry.ticket_id].find(
        (v) => typeof v === 'string' && v,
      ) ?? `${key}[${i}]`;
    out.push({ id: `${key}-${i}`, label: String(label), text });
  });
  return out;
}

/**
 * The tone a fact deserves, or null for the ones that carry no judgement.
 *
 * Colour is only applied where the document *states* a condition: an agent that
 * failed, a status that is not ok. It is deliberately not inferred from prose —
 * in real syntheses the words "blocking" and "clean" appear as ordinary
 * adjectives ("the blocking window is bounded by a lease", "not a clean kill"),
 * so matching on them paints working diffs red and failed checks green. A wrong
 * colour in a review tool is worse than none: it is read as a verdict.
 */
export function factTone(key: string, value: string): 'ok' | 'danger' | null {
  const empty = !value || /^0\b/.test(value);
  if (/fail|error/i.test(key)) return empty ? null : 'danger';
  if (key === 'status') return /^(ok|success|passed|clean)$/i.test(value) ? 'ok' : 'danger';
  if (/^succeeded/i.test(key)) return empty ? null : 'ok';
  return null;
}
