/**
 * A turn as the room reads it: its prose, at most one figure, and what the
 * voice rules made of it.
 *
 * `Segments` is the only renderer of a turn body or a verdict. A body is never
 * handed to Markdown whole: Markdown passes an image's `src` through raw, so a
 * relative `images/x.svg` resolves against the SPA's own path and an http src
 * makes the operator's browser fetch whatever a worker wrote. `view_data`
 * splits every image reference out of the prose first (voice.segments), so
 * Markdown here only ever receives text. A file image is drawn only when the
 * master checked it (`ok`) and only from this run's images/ folder, through
 * `imageUrl`. A mermaid figure is rendered by the host and shown as an <img> of
 * a blob, never as inline markup, so a diagram cannot run script.
 */
import { useEffect, useState } from 'react';
import { Markdown, imageUrl, renderMermaid } from './host';

export type TextSegment = { kind: 'text'; text: string };
export type ImageSegment = {
  kind: 'image';
  name: string;
  ref?: string;
  caption: string;
  description: string;
  ok: boolean;
  /** The bytes the master checked; the route serves nothing else when it is sent. */
  sha256?: string;
};
export type MermaidSegment = { kind: 'mermaid'; source: string; caption: string; description: string };
export type Segment = TextSegment | ImageSegment | MermaidSegment;

/** The hard rules in plain words: voice.note's phrasing without the numbers. */
export const VIOLATION_LABEL: Record<string, string> = {
  over_cap: 'over the word cap',
  multi_line: 'more than one line',
  multi_sentence: 'more than one sentence',
  headers: 'headers',
  bold: 'bold',
  tables: 'tables',
  nested: 'nested bullets',
  too_many_bullets: 'too many bullets',
  too_many_images: 'too many images',
  image_uncaptioned: 'an image caption or description missing or too long',
  image_missing: 'an image missing or not your own file',
  action_too_long: 'an action over 200 characters',
  stance_too_long: 'a stance over its cap',
  filler: 'filler phrases',
  retake_failed: 'the retake delivered nothing, so an earlier take was kept',
};

export function violationText(violations: string[]): string {
  return violations.map((v) => VIOLATION_LABEL[v] ?? v).join('; ');
}

const figure: React.CSSProperties = {
  margin: 0,
  padding: 8,
  display: 'flex',
  flexDirection: 'column',
  gap: 6,
  border: '1px solid var(--border-hairline)',
  borderRadius: 'var(--radius-sm)',
  background: 'var(--wash-subtle)',
};

const muted: React.CSSProperties = { fontSize: 11.5, fontStyle: 'italic', color: 'var(--text-muted)' };

const code: React.CSSProperties = {
  margin: 0,
  fontFamily: 'var(--font-mono)',
  fontSize: 11,
  whiteSpace: 'pre-wrap',
  color: 'var(--text-secondary)',
};

/** Plain text, never Markdown: a caption is worker-written too. */
function Caption({ caption, description }: { caption: string; description: string }) {
  return (
    <figcaption style={{ fontSize: 11.5, lineHeight: 1.45, color: 'var(--text-secondary)' }}>
      {caption && <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{caption}</div>}
      {description && <div>{description}</div>}
    </figcaption>
  );
}

function FileFigure({ runId, seg }: { runId: string; seg: ImageSegment }) {
  return (
    <figure data-testid="figure-image" style={figure}>
      {seg.ok === true ? (
        <img src={imageUrl(runId, seg.name, seg.sha256)} alt={seg.caption} style={{ maxWidth: '100%' }} />
      ) : (
        <div data-testid="image-unavailable" style={muted}>
          image unavailable
        </div>
      )}
      <Caption caption={seg.caption} description={seg.description} />
    </figure>
  );
}

type Drawing =
  | { state: 'pending' }
  | { state: 'absent' }
  | { state: 'drawn'; url: string }
  | { state: 'failed'; error: string };

export function MermaidFigure({ seg }: { seg: MermaidSegment }) {
  const [drawing, setDrawing] = useState<Drawing>({ state: 'pending' });

  useEffect(() => {
    const pending = renderMermaid(seg.source);
    if (pending === null) {
      setDrawing({ state: 'absent' });
      return undefined;
    }
    setDrawing({ state: 'pending' });
    let live = true;
    let url: string | null = null;
    pending.then(
      (svg) => {
        if (!live) return;
        url = URL.createObjectURL(new Blob([svg], { type: 'image/svg+xml' }));
        setDrawing({ state: 'drawn', url });
      },
      (err: unknown) => {
        if (live) setDrawing({ state: 'failed', error: err instanceof Error ? err.message : String(err) });
      },
    );
    return () => {
      live = false;
      if (url) URL.revokeObjectURL(url);
    };
  }, [seg.source]);

  const source = (
    <pre data-testid="mermaid-source" style={code}>
      <code>{seg.source}</code>
    </pre>
  );
  return (
    <figure data-testid="figure-mermaid" style={figure}>
      {drawing.state === 'pending' && (
        <div role="status" style={muted}>
          rendering diagram…
        </div>
      )}
      {drawing.state === 'drawn' && <img src={drawing.url} alt={seg.caption} style={{ maxWidth: '100%' }} />}
      {drawing.state === 'absent' && source}
      {drawing.state === 'failed' && (
        <>
          {source}
          <div data-testid="mermaid-error" role="status" style={muted}>
            diagram failed to render: {drawing.error}
          </div>
        </>
      )}
      <Caption caption={seg.caption} description={seg.description} />
    </figure>
  );
}

export function Segments({
  segments,
  runId,
  fontSize = 12,
}: {
  segments: Segment[];
  runId: string;
  fontSize?: number;
}) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      {segments.map((seg, i) =>
        seg.kind === 'text' ? (
          // A reference voice's scan missed (alt text across a line, a broken code span)
          // must never reach Markdown as an image: disarm it, as Diff.tsx does.
          <Markdown key={i} fontSize={fontSize}>
            {seg.text.replaceAll('![', '!\u200B[')}
          </Markdown>
        ) : seg.kind === 'image' ? (
          <FileFigure key={i} runId={runId} seg={seg} />
        ) : (
          <MermaidFigure key={i} seg={seg} />
        ),
      )}
    </div>
  );
}
