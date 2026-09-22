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
