/**
 * PlaybookView — renders the view a playbook ships for itself.
 *
 * The playbook owns the component; web/ owns only the loading. The asset is a
 * UMD bundle that reads React off the window — the same mechanism the design
 * system already uses — so it is injected as a <script> and read back off
 * `window.HermesView_<playbook>`. `await import()` cannot load a UMD file.
 *
 * A playbook view is code the control plane did not write. A script that 404s,
 * a bundle that registers no global, and a component that throws all land in
 * the same place: an error card, with the rest of the shell still mounted.
 */

import { Component, useCallback, useEffect, useState } from 'react';
import type { ComponentType, ReactNode } from 'react';
import { fetchViewData } from '../api/client';
import { getToken, isRemote } from '../api/auth';
import { Button, EmptyState } from '../ds';
import { LoadingOverlay } from '../components/Spinner';

/** What a playbook's own component is handed. */
export type PlaybookViewComponentProps = {
  runId: string;
  data: Record<string, any>;
  refetch: () => void;
  /** Absent on the view's own tab; names the section another tab asks for. */
  variant?: string;
};

/** A view opts in to another tab by listing it on the function itself, so the
 *  bundle stays default-export-only. A view that lists nothing renders only on
 *  its own tab, whatever it does with `variant`. */
type PlaybookViewComponent = ComponentType<PlaybookViewComponentProps> & {
  variants?: readonly string[];
};

type PlaybookViewProps = {
  runId: string;
  /** The run's playbook: names both the asset route and the window global. */
  playbook: string;
  /** RunDetail.has_view — false means this playbook ships no view. */
  hasView: boolean;
  liveTick?: number;
  /** Set by a tab other than the view's own: a section beside the host's. */
  variant?: string;
};

// One injection per playbook, not one per mount: leaving the tab and coming
// back must not add a second <script> to <head>. A load that failed is evicted
// so the next mount retries instead of showing a cached failure forever.
const injected = new Map<string, Promise<void>>();

function loadViewScript(playbook: string): Promise<void> {
  const cached = injected.get(playbook);
  if (cached) return cached;

  // On a non-loopback bind the read routes want the token, and a <script> tag
  // carries no Authorization header. require_auth_read also accepts ?token=.
  const token = getToken();
  const query = isRemote() && token ? `?token=${encodeURIComponent(token)}` : '';

  const pending = new Promise<void>((resolve, reject) => {
    const el = document.createElement('script');
    el.src = `/api/playbooks/${playbook}/view.js${query}`;
    el.async = true;
    el.addEventListener('load', () => resolve());
    // The vendored DS loader (ds/_ds_bundle.js) resolves on error too, which
    // turns a 404 into a confusing "missing global" further down. Reject.
    el.addEventListener('error', () =>
      reject(new Error(`Could not load the ${playbook} view (/api/playbooks/${playbook}/view.js).`)),
    );
    document.head.appendChild(el);
  });
  injected.set(playbook, pending);
  pending.catch(() => injected.delete(playbook));
  return pending;
}

export default function PlaybookView({ runId, playbook, hasView, liveTick, variant }: PlaybookViewProps) {
  const [View, setView] = useState<PlaybookViewComponent | null>(null);
  const [data, setData] = useState<Record<string, any> | null>(null);
  // Two slots, not one: a poll that succeeds must not clear a standing asset
  // failure, and an asset failure must not be cleared by the next tick's data.
  const [assetError, setAssetError] = useState<Error | null>(null);
  const [dataError, setDataError] = useState<Error | null>(null);
  const [reloads, setReloads] = useState(0);

  const refetch = useCallback(() => setReloads((n) => n + 1), []);

  // The asset, keyed on the playbook and an EXPLICIT retry -- never on runId and
  // never on liveTick. Sharing one effect with the data fetch meant a failed
  // load evicted the cache and every poll tick then re-injected a <script>:
  // five dead tags and two GETs per tick after five ticks, unbounded while the
  // tab is open. `reloads` is in here (the reviewer's sketch had only
  // [hasView, playbook]) because otherwise the error card's Retry is a dead
  // button for the one failure it is most likely to be shown for.
  useEffect(() => {
    if (!hasView) return;
    let live = true;
    setAssetError(null);
    loadViewScript(playbook)
      .then(() => {
        if (!live) return;
        const found = (window as any)[`HermesView_${playbook}`];
        if (typeof found !== 'function') {
          setAssetError(
            new Error(`The ${playbook} view loaded but registered no component on window.HermesView_${playbook}.`),
          );
          return;
        }
        // Set it through the updater form: React calls a bare function value.
        setView(() => found as PlaybookViewComponent);
      })
      .catch((err) => {
        if (live) setAssetError(err as Error);
      });
    return () => {
      live = false;
    };
  }, [hasView, playbook, reloads]);

  // The data, which is what a tick is for.
  useEffect(() => {
    if (!hasView) return;
    let live = true;
    setDataError(null);
    fetchViewData(runId)
      .then((payload) => {
        if (live) setData(payload);
      })
      .catch((err) => {
        if (live) setDataError(err as Error);
      });
    return () => {
      live = false;
    };
  }, [hasView, runId, liveTick, reloads]);

  if (!hasView) return null;

  // On another tab the view is a guest: nothing until it has loaded, said it
  // has this section, and has data for it. A failed load is its own tab's to
  // report.
  if (variant && !(View?.variants?.includes(variant) && data)) return null;

  const error = assetError ?? dataError;
  if (error) {
    return (
      <div style={{ padding: 32 }}>
        <EmptyState
          title="Error loading playbook view"
          description={error.message}
          icon="alert-circle"
          action={
            <Button onClick={refetch} data-testid="playbook-view-retry">
              Retry
            </Button>
          }
        />
      </div>
    );
  }

  // Only blank the pane on the first load; a live refetch must not wipe what is
  // already on screen.
  if (!View || !data) {
    return (
      <div style={{ position: 'relative', flex: 1, minHeight: 0 }}>
        <LoadingOverlay label="Loading playbook view…" />
      </div>
    );
  }

  return (
    // A variant is a fixed column beside the host's own section, not half the pane.
    <div style={variant ? { width: 380, flexShrink: 0, overflow: 'auto', padding: 20 } : { flex: 1, overflow: 'auto', padding: 20 }}>
      {/* Keyed so an explicit retry clears a caught throw: `failed` is set once
          and a boundary has no other way back. NOT keyed on liveTick -- that
          would remount the view on every poll and lose its scroll and
          expansion state. */}
      <ViewErrorBoundary key={`${playbook}:${runId}:${reloads}`} playbook={playbook} onRetry={refetch}>
        <View runId={runId} data={data} refetch={refetch} variant={variant} />
      </ViewErrorBoundary>
    </div>
  );
}

type BoundaryProps = { playbook: string; onRetry: () => void; children: ReactNode };
type BoundaryState = { failed: Error | null };

/**
 * The only error boundary in the SPA, and it earns its place: a throw inside a
 * playbook's component unmounts the whole React tree by default, which would
 * let a broken view take the control plane down with it. React 19 still has no
 * hook form of this, so it is a class.
 */
class ViewErrorBoundary extends Component<BoundaryProps, BoundaryState> {
  state: BoundaryState = { failed: null };

  static getDerivedStateFromError(failed: Error): BoundaryState {
    return { failed };
  }

  render() {
    if (this.state.failed) {
      return (
        <EmptyState
          title={`The ${this.props.playbook} view failed to render`}
          description={this.state.failed.message}
          icon="alert-circle"
          action={
            <Button onClick={this.props.onRetry} data-testid="playbook-view-retry">
              Retry
            </Button>
          }
        />
      );
    }
    return this.props.children;
  }
}
