/**
 * Reading agent prose as an outline instead of a wall.
 *
 * A report runs to a hundred lines under four themes; a synthesis to four
 * thousand characters under a dozen headings. Rendered flat, both are text you
 * scroll past rather than read — which defeats the point of having had an agent
 * read the material for you.
 *
 * Markdown headings are the structure the agent already wrote. Splitting on them
 * gives an outline that can be collapsed, so the page shows what a document
 * covers before asking anyone to read it.
 */

export type Section = { level: number; title: string; body: string };

/** A heading line, outside a fenced code block. */
const HEADING = /^(#{1,6})\s+(.*\S)\s*$/;

/**
 * Split markdown into its opening prose and its headed sections.
 *
 * Fenced code is skipped: a `# comment` in a shell block is not a heading, and
 * treating it as one turns the outline into nonsense.
 */
export function markdownSections(text: string): { intro: string; sections: Section[] } {
  const lines = (text ?? '').split('\n');
  const intro: string[] = [];
  const sections: Section[] = [];
  let current: Section | null = null;
  let fenced = false;

  for (const line of lines) {
    if (/^\s*(```|~~~)/.test(line)) fenced = !fenced;

    const m = fenced ? null : HEADING.exec(line);
    if (m) {
      current = { level: m[1].length, title: m[2], body: '' };
      sections.push(current);
      continue;
    }
    if (current) current.body += `${line}\n`;
    else intro.push(line);
  }

  for (const s of sections) s.body = s.body.trim();
  return { intro: intro.join('\n').trim(), sections };
}

/**
 * A one-line summary of a body of prose: its first heading, else its first line.
 *
 * Horizontal rules and blank lines are skipped — they are punctuation, not a
 * summary of anything.
 */
export function firstLine(text: string): string {
  const lines = (text ?? '').split('\n');
  for (const line of lines) {
    const t = line.trim();
    if (!t || /^(-{3,}|\*{3,}|_{3,})$/.test(t)) continue;
    const m = HEADING.exec(t);
    return (m ? m[2] : t).slice(0, 200);
  }
  return '';
}
