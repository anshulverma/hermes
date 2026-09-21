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
import { EmptyState } from '../ds';
import { LoadingOverlay } from '../components/Spinner';

/** What a playbook's own component is handed. */
export type PlaybookViewComponentProps = {
  runId: string;
  data: Record<string, any>;
  refetch: () => void;
};

type PlaybookViewProps = {
  runId: string;
  /** The run's playbook: names both the asset route and the window global. */
  playbook: string;
  /** RunDetail.has_view — false means this playbook ships no view. */
  hasView: boolean;
  liveTick?: number;
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

export default function PlaybookView({ runId, playbook, hasView, liveTick }: PlaybookViewProps) {
  const [View, setView] = useState<ComponentType<PlaybookViewComponentProps> | null>(null);
  const [data, setData] = useState<Record<string, any> | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [reloads, setReloads] = useState(0);

  const refetch = useCallback(() => setReloads((n) => n + 1), []);

  useEffect(() => {
    if (!hasView) return;
    let live = true;
    setError(null);
    Promise.all([loadViewScript(playbook), fetchViewData(runId)])
      .then(([, payload]) => {
        if (!live) return;
        const found = (window as any)[`HermesView_${playbook}`];
        if (typeof found !== 'function') {
          setError(
            new Error(`The ${playbook} view loaded but registered no component on window.HermesView_${playbook}.`),
          );
          return;
        }
        // Set it through the updater form: React calls a bare function value.
        setView(() => found as ComponentType<PlaybookViewComponentProps>);
        setData(payload);
      })
      .catch((err) => {
        if (live) setError(err as Error);
      });
    return () => {
      live = false;
    };
  }, [hasView, playbook, runId, liveTick, reloads]);

  if (!hasView) return null;

  if (error) {
    return (
      <div style={{ padding: 32 }}>
        <EmptyState title="Error loading playbook view" description={error.message} icon="alert-circle" />
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
    <div style={{ flex: 1, overflow: 'auto', padding: 20 }}>
      <ViewErrorBoundary playbook={playbook}>
        <View runId={runId} data={data} refetch={refetch} />
      </ViewErrorBoundary>
    </div>
  );
}

type BoundaryProps = { playbook: string; children: ReactNode };
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
        />
      );
    }
    return this.props.children;
  }
}
