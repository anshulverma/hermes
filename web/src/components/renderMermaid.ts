/**
 * renderMermaid - mermaid source to SVG markup, with mermaid loaded on first use.
 *
 * On the host shelf (window.HermesUI.renderMermaid) so a playbook view bundle can
 * draw a diagram without inlining mermaid into its committed artifact. The
 * import is dynamic, so the SPA splits mermaid into its own chunk and loads it
 * only when a diagram is drawn. `securityLevel: 'strict'` and root-level
 * `htmlLabels: false` keep script and foreignObject HTML out of the markup; the
 * caller still shows it only as an <img> of a blob, never as inline HTML.
 *
 * The source is worker-written, and a blob: URL is same-origin: "Open image in
 * new tab" loads it as a document, where an SVG's script would run. So markup
 * that still carries script, a javascript: URL, an event attribute or
 * foreignObject is rejected here, before any caller can make a blob of it, and
 * the caller shows the source as code, as for any failed diagram.
 *
 * Like Markdown, this must not import '../ds': ds/index -> _globals -> here
 * would be a cycle.
 */
import type { Mermaid } from 'mermaid';

// ponytail: a text screen behind mermaid's own strict sanitizer, not an SVG
// parser; an entity-encoded scheme (`&#106;avascript:`) gets past it.
const UNSAFE = /<script|javascript:|<foreignobject|\bon[a-z]+\s*=/i;

let loading: Promise<Mermaid> | null = null;
let drawn = 0;

function load(): Promise<Mermaid> {
  loading ??= import('mermaid').then(
    ({ default: mermaid }) => {
      mermaid.initialize({ startOnLoad: false, securityLevel: 'strict', htmlLabels: false });
      return mermaid;
    },
    (err: unknown) => {
      loading = null; // a failed chunk load may succeed on the next diagram
      throw err;
    },
  );
  return loading;
}

export default async function renderMermaid(source: string): Promise<string> {
  const mermaid = await load();
  drawn += 1;
  const { svg } = await mermaid.render(`hermes-mermaid-${drawn}`, source);
  if (UNSAFE.test(svg)) throw new Error('unsafe markup in the drawn SVG');
  return svg;
}
