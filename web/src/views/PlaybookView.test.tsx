/**
 * Tests for PlaybookView — the generic loader for a playbook-owned view.
 *
 * Every test uses its own playbook name: the injection cache is module-level on
 * purpose (one <script> per playbook, not one per mount) and so it outlives a
 * single test.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, act } from '@testing-library/react';
import PlaybookView from './PlaybookView';

const mockFetch = vi.fn();
(globalThis as any).fetch = mockFetch;

/** The <script> the loader injected for `playbook`, once it is in the DOM. */
async function injectedScript(playbook: string): Promise<HTMLScriptElement> {
  return waitFor(() => {
    const el = document.querySelector<HTMLScriptElement>(
      `script[src^="/api/playbooks/${playbook}/view.js"]`,
    );
    if (!el) throw new Error(`no script injected for ${playbook}`);
    return el;
  });
}

describe('PlaybookView', () => {
  beforeEach(() => {
    mockFetch.mockReset();
    mockFetch.mockResolvedValue({ ok: true, json: async () => ({ kind: 'committee', turn: 20 }) });
  });

  afterEach(() => {
    document
      .querySelectorAll('script[src^="/api/playbooks/"]')
      .forEach((el) => el.remove());
    for (const key of Object.keys(window)) {
      if (key.startsWith('HermesView_')) delete (window as any)[key];
    }
  });

  it('renders nothing and fetches nothing without has_view', () => {
    const { container } = render(
      <PlaybookView runId="run-2" playbook="quiet_pb" hasView={false} />,
    );

    expect(container.innerHTML).toBe('');
    expect(mockFetch).not.toHaveBeenCalled();
    expect(document.querySelector('script[src^="/api/playbooks/quiet_pb"]')).toBeNull();
  });

  it('renders the global component with runId, data and refetch', async () => {
    (window as any).HermesView_ok_pb = ({ runId, data, refetch }: any) => (
      <div>
        <span>
          {runId} · {data.kind} · {data.turn} turns
        </span>
        <button type="button" onClick={refetch}>
          reload
        </button>
      </div>
    );

    render(<PlaybookView runId="run-2" playbook="ok_pb" hasView />);

    const script = await injectedScript('ok_pb');
    await act(async () => {
      script.dispatchEvent(new Event('load'));
    });

    await waitFor(() => {
      expect(screen.getByText('run-2 · committee · 20 turns')).toBeInTheDocument();
    });
    expect(mockFetch).toHaveBeenCalledWith('/api/runs/run-2/view', expect.anything());

    // refetch is wired: the component can ask for fresh data itself.
    await act(async () => {
      screen.getByText('reload').click();
    });
    await waitFor(() => expect(mockFetch).toHaveBeenCalledTimes(2));
  });

  it('carries the token on the asset URL when the bind is not loopback', async () => {
    (window as any).__HERMES_BIND__ = 'remote';
    (window as any).__HERMES_TOKEN__ = 'tok en';
    try {
      render(<PlaybookView runId="run-2" playbook="remote_pb" hasView />);

      const script = await injectedScript('remote_pb');
      expect(script.getAttribute('src')).toBe('/api/playbooks/remote_pb/view.js?token=tok%20en');
    } finally {
      delete (window as any).__HERMES_BIND__;
      delete (window as any).__HERMES_TOKEN__;
    }
  });

  it('shows an error card when the asset fails to load', async () => {
    render(<PlaybookView runId="run-2" playbook="gone_pb" hasView />);

    const script = await injectedScript('gone_pb');
    await act(async () => {
      script.dispatchEvent(new Event('error'));
    });

    await waitFor(() => {
      expect(screen.getByText('Error loading playbook view')).toBeInTheDocument();
    });
    expect(
      screen.getByText('Could not load the gone_pb view (/api/playbooks/gone_pb/view.js).'),
    ).toBeInTheDocument();
  });

  it('shows an error card when the asset registers no global', async () => {
    render(<PlaybookView runId="run-2" playbook="empty_pb" hasView />);

    const script = await injectedScript('empty_pb');
    await act(async () => {
      script.dispatchEvent(new Event('load'));
    });

    await waitFor(() => {
      expect(
        screen.getByText(
          'The empty_pb view loaded but registered no component on window.HermesView_empty_pb.',
        ),
      ).toBeInTheDocument();
    });
  });

  it('keeps the shell mounted when the view throws while rendering', async () => {
    (window as any).HermesView_bad_pb = () => {
      throw new Error('boom in the view');
    };

    // React logs every error an error boundary catches — one console.error with
    // "The above error occurred in one of your React components". Expected here;
    // silence it so the failure output of a real regression stays readable.
    const quiet = vi.spyOn(console, 'error').mockImplementation(() => {});
    try {
      render(
        <div>
          <div data-testid="shell">control plane</div>
          <PlaybookView runId="run-2" playbook="bad_pb" hasView />
        </div>,
      );

      const script = await injectedScript('bad_pb');
      await act(async () => {
        script.dispatchEvent(new Event('load'));
      });

      await waitFor(() => {
        expect(screen.getByText('The bad_pb view failed to render')).toBeInTheDocument();
      });
      expect(screen.getByText('boom in the view')).toBeInTheDocument();
      expect(screen.getByTestId('shell')).toBeInTheDocument();
    } finally {
      quiet.mockRestore();
    }
  });
});
