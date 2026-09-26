/**
 * Everything this bundle reads off the host page, in one module.
 *
 * `Markdown` is externalised rather than imported: pulling react-markdown in
 * would inline unified/mdast/micromark into a committed, unminified artifact.
 * The host publishes it on `window.HermesUI`, the same way the design system
 * arrives on `window.DSNS`. A host that did not publish it still renders — as
 * preformatted text, which is worse than markdown and much better than nothing.
 *
 * `apiGet` / `apiPost` exist because this bundle cannot import the SPA's
 * `fetchJSON` (web/src/api/client.ts:69): that module lives in the host's app
 * chunk, not in this one. They carry the bearer token for the same reason it
 * does — `require_auth_read` gates GETs on a non-loopback bind, and
 * `require_auth` gates every POST on every bind.
 *
 * `imageUrl` and `renderMermaid` serve a turn's figures. An <img> cannot send a
 * bearer header, so `imageUrl` carries the token on the query, the same way the
 * SPA's <script> tag for this bundle does. `renderMermaid` is the host's: this
 * committed bundle never carries mermaid, and a host without it gets null.
 *
 * This file is the ONLY reader of `window.HermesUI` in the bundle. Two readers
 * of one global drift; CommitteeView.tsx imports `Markdown` from here.
 */

type MarkdownProps = {
  children: string;
  maxHeight?: number | null;
  fontSize?: number;
};

export function Markdown(props: MarkdownProps) {
  const Host = (window as any).HermesUI?.Markdown;
  if (Host) return <Host {...props} />;
  return (
    <div
      style={{
        whiteSpace: 'pre-wrap',
        fontSize: props.fontSize ?? 13,
        lineHeight: 1.55,
        color: 'var(--text-primary)',
      }}
    >
      {props.children}
    </div>
  );
}

function authHeaders(): Record<string, string> {
  // Through the host's own getToken, never off window.__HERMES_TOKEN__. The
  // server injects that global on a LOOPBACK bind only (server/app.py:1951);
  // on a remote bind the token is typed into TokenLogin and lives in
  // web/src/api/auth.ts's module memory, where this bundle cannot reach it.
  // Reading the raw global would send no header and 401 the diff and the
  // accept/reject on exactly the binds that need auth. `window.HermesUI` is
  // published by web/src/ds/_globals.ts, and PlaybookView uses the same
  // getToken for the ?token= on the script tag.
  const token = (window as any).HermesUI?.getToken?.() ?? null;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function readBody<T>(res: any): Promise<T> {
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const parsed = await res.json();
      if (parsed && parsed.detail) detail = String(parsed.detail);
    } catch {
      // Not a JSON error body; the status line is all there is to report.
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export async function apiGet<T>(path: string): Promise<T> {
  return readBody<T>(await fetch(path, { headers: authHeaders() }));
}

export async function apiPost<T>(path: string): Promise<T> {
  return readBody<T>(await fetch(path, { method: 'POST', headers: authHeaders() }));
}

/**
 * The run's own image, through the per-run file route, with the token when there
 * is one. `sha256` pins the bytes the master checked: a file a later worker
 * overwrote is then a 404, not someone else's picture under this caption.
 */
export function imageUrl(runId: string, name: string, sha256?: string): string {
  let url = `/api/runs/${encodeURIComponent(runId)}/view/artifact?path=${encodeURIComponent('images/' + name)}`;
  if (sha256) url += `&sha256=${encodeURIComponent(sha256)}`;
  const token = (window as any).HermesUI?.getToken?.() ?? null;
  return token ? `${url}&token=${encodeURIComponent(token)}` : url;
}

/** SVG markup for mermaid `source`, or null when the host publishes no renderer. */
export function renderMermaid(source: string): Promise<string> | null {
  const render = (window as any).HermesUI?.renderMermaid;
  // Through the executor, so a renderer that throws instead of rejecting still
  // reaches the caller's failure branch rather than escaping its effect.
  return typeof render === 'function' ? new Promise((resolve) => resolve(render(source))) : null;
}
