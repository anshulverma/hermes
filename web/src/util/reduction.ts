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

/** The first markdown heading in a body of prose, if it opens with one. */
function firstHeading(text: string): string | null {
  const line = text.trimStart().split('\n', 1)[0] ?? '';
  const m = /^#{1,6}\s+(.*\S)\s*$/.exec(line);
  return m ? m[1].slice(0, HEADLINE_MAX) : null;
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

  for (const value of Object.values(json)) {
    if (typeof value === 'string' && value.length >= PROSE_MIN) {
      const heading = firstHeading(value);
      if (heading) return heading;
    }
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
