/**
 * renderMermaid - mermaid source to SVG markup, with mermaid loaded on first use.
 *
 * On the host shelf (window.HermesUI.renderMermaid) so a playbook view bundle can
 * draw a diagram without inlining mermaid into its committed artifact. The
 * import is dynamic, so the SPA splits mermaid into its own chunk and loads it
 * only when a diagram is drawn. `securityLevel: 'strict'` and `htmlLabels: false`
 * are asked for, and `secure` stops the diagram's own directives from changing
 * them or from setting CSS (themeCSS, fonts) that the page would apply while it
 * draws. The caller still shows the markup only as an <img> of a blob, never as
 * inline HTML.
 *
 * The source is worker-written, and a blob: URL is same-origin: "Open image in
 * new tab" loads it as a document, where an SVG's script would run. So as a
 * backstop, markup that still carries script, a javascript: URL, an event
 * attribute or foreignObject is rejected here, before any caller can make a blob
 * of it, and so is markup that is not well-formed XML (an <img> could not decode
 * it); the caller shows the source as code, as for any failed diagram.
 *
 * A diagram's <style> (a classDef's `fill:url(...)`) still applies to the page
 * while it draws; web/index.html's img-src policy keeps that from fetching.
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
      mermaid.initialize({
        startOnLoad: false,
        securityLevel: 'strict',
        htmlLabels: false,
        suppressErrorRendering: true, // else a failed diagram leaves its error graphic in <body>
        journey: { textPlacement: 'tspan' }, // its default draws labels as foreignObject
        secure: [
          'secure',
          'securityLevel',
          'startOnLoad',
          'maxTextSize',
          'suppressErrorRendering',
          'maxEdges',
          'themeCSS',
          'fontFamily',
          'altFontFamily',
          'htmlLabels',
        ],
      });
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
  const id = `hermes-mermaid-${drawn}`;
  let svg: string;
  try {
    ({ svg } = await mermaid.render(id, source));
  } catch (err) {
    // A classDef style that fails insertRule throws past mermaid's own cleanup,
    // leaving its empty container in <body>, one per failed diagram.
    document.getElementById(`d${id}`)?.remove();
    throw err;
  }
  if (UNSAFE.test(svg)) throw new Error('unsafe markup in the drawn SVG');
  const doc = new DOMParser().parseFromString(svg, 'image/svg+xml');
  if (doc.getElementsByTagName('parsererror').length) throw new Error('the drawn SVG is not well-formed XML');
  return svg;
}
