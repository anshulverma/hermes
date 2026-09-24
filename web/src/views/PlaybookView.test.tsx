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

/** Every <script> the loader has injected for `playbook` so far. */
const scriptCount = (playbook: string) =>
  document.querySelectorAll(`script[src^="/api/playbooks/${playbook}/view.js"]`).length;

/** Renders whatever `data.kind` the loader handed it -- enough to tell two
 *  runs' payloads apart on screen. */
const namesItsData = ({ data }: any) => <div>payload {data.kind}</div>;

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

  it('clears a caught throw when the operator retries', async () => {
    let explode = true;
    (window as any).HermesView_flaky_pb = () => {
      if (explode) throw new Error('boom on turn 3');
      return <div>rendered fine</div>;
    };

    const quiet = vi.spyOn(console, 'error').mockImplementation(() => {});
    try {
      const { rerender } = render(
        <PlaybookView runId="run-2" playbook="flaky_pb" hasView liveTick={1} />,
      );
      const script = await injectedScript('flaky_pb');
      await act(async () => {
        script.dispatchEvent(new Event('load'));
      });
      await waitFor(() => {
        expect(screen.getByText('The flaky_pb view failed to render')).toBeInTheDocument();
      });

      // A poll does NOT clear it -- keying the boundary on liveTick would
      // remount the view every tick and lose its scroll and expansion state.
      explode = false;
      rerender(<PlaybookView runId="run-2" playbook="flaky_pb" hasView liveTick={2} />);
      await waitFor(() => expect(mockFetch).toHaveBeenCalledTimes(2));
      expect(screen.getByText('The flaky_pb view failed to render')).toBeInTheDocument();

      // The retry does.
      await act(async () => {
        screen.getByTestId('playbook-view-retry').click();
      });
      await waitFor(() => expect(screen.getByText('rendered fine')).toBeInTheDocument());
    } finally {
      quiet.mockRestore();
    }
  });

  // --- the module's own load-bearing claims (finding 7.4) -------------------

  it('injects one <script> per playbook, not one per mount', async () => {
    (window as any).HermesView_once_pb = namesItsData;

    const first = render(<PlaybookView runId="run-2" playbook="once_pb" hasView />);
    const script = await injectedScript('once_pb');
    await act(async () => {
      script.dispatchEvent(new Event('load'));
    });
    await waitFor(() => expect(screen.getByText('payload committee')).toBeInTheDocument());
    first.unmount();

    render(<PlaybookView runId="run-9" playbook="once_pb" hasView />);
    await waitFor(() => expect(screen.getByText('payload committee')).toBeInTheDocument());
    expect(scriptCount('once_pb')).toBe(1);
  });

  it('re-injects after a failed load, so the next mount retries', async () => {
    const first = render(<PlaybookView runId="run-2" playbook="evict_pb" hasView />);
    const script = await injectedScript('evict_pb');
    await act(async () => {
      script.dispatchEvent(new Event('error'));
    });
    await waitFor(() => expect(screen.getByText('Error loading playbook view')).toBeInTheDocument());
    first.unmount();

    (window as any).HermesView_evict_pb = namesItsData;
    render(<PlaybookView runId="run-2" playbook="evict_pb" hasView />);
    await waitFor(() => expect(scriptCount('evict_pb')).toBe(2));
    await act(async () => {
      document
        .querySelectorAll('script[src^="/api/playbooks/evict_pb/view.js"]')[1]
        .dispatchEvent(new Event('load'));
    });
    await waitFor(() => expect(screen.getByText('payload committee')).toBeInTheDocument());
  });

  it('drops a superseded in-flight response rather than clobbering the new run', async () => {
    (window as any).HermesView_race_pb = namesItsData;
    const pending: Array<(value: any) => void> = [];
    mockFetch.mockImplementation(() => new Promise((resolve) => pending.push(resolve)));

    const { rerender } = render(<PlaybookView runId="run-A" playbook="race_pb" hasView />);
    const script = await injectedScript('race_pb');
    await act(async () => {
      script.dispatchEvent(new Event('load'));
    });
    await waitFor(() => expect(pending).toHaveLength(1));

    rerender(<PlaybookView runId="run-B" playbook="race_pb" hasView />);
    await waitFor(() => expect(pending).toHaveLength(2));

    // B answers, then A's superseded request lands second.
    await act(async () => {
      pending[1]({ ok: true, json: async () => ({ kind: 'B' }) });
      pending[0]({ ok: true, json: async () => ({ kind: 'A' }) });
    });

    await waitFor(() => expect(screen.getByText('payload B')).toBeInTheDocument());
    expect(screen.queryByText('payload A')).toBeNull();
  });

  it('drops a superseded in-flight FAILURE rather than reddening the new run', async () => {
    (window as any).HermesView_race2_pb = namesItsData;
    const pending: Array<(value: any) => void> = [];
    mockFetch.mockImplementation(() => new Promise((resolve) => pending.push(resolve)));

    const { rerender } = render(<PlaybookView runId="run-A" playbook="race2_pb" hasView />);
    const script = await injectedScript('race2_pb');
    await act(async () => {
      script.dispatchEvent(new Event('load'));
    });
    await waitFor(() => expect(pending).toHaveLength(1));

    rerender(<PlaybookView runId="run-B" playbook="race2_pb" hasView />);
    await waitFor(() => expect(pending).toHaveLength(2));

    await act(async () => {
      pending[1]({ ok: true, json: async () => ({ kind: 'B' }) });
      pending[0]({ ok: false, status: 500, json: async () => ({ detail: 'run A is gone' }) });
    });

    await waitFor(() => expect(screen.getByText('payload B')).toBeInTheDocument());
    expect(screen.queryByText('Error loading playbook view')).toBeNull();
  });

  it('re-fetches the data on a liveTick bump', async () => {
    (window as any).HermesView_tick_pb = namesItsData;

    const { rerender } = render(
      <PlaybookView runId="run-2" playbook="tick_pb" hasView liveTick={1} />,
    );
    const script = await injectedScript('tick_pb');
    await act(async () => {
      script.dispatchEvent(new Event('load'));
    });
    await waitFor(() => expect(mockFetch).toHaveBeenCalledTimes(1));

    rerender(<PlaybookView runId="run-2" playbook="tick_pb" hasView liveTick={2} />);
    await waitFor(() => expect(mockFetch).toHaveBeenCalledTimes(2));
    expect(scriptCount('tick_pb')).toBe(1);
  });

  // --- variants: a view's section on another tab ----------------------------

  it('hands a variant to a view that declares it', async () => {
    (window as any).HermesView_var_pb = Object.assign(
      ({ variant, data }: any) => <div>section {variant} of {data.kind}</div>,
      { variants: ['metrics'] },
    );

    render(<PlaybookView runId="run-2" playbook="var_pb" hasView variant="metrics" />);
    const script = await injectedScript('var_pb');
    await act(async () => {
      script.dispatchEvent(new Event('load'));
    });

    await waitFor(() => expect(screen.getByText('section metrics of committee')).toBeInTheDocument());
  });

  it('shows no loading overlay on another tab while the data is in flight', async () => {
    (window as any).HermesView_varwait_pb = Object.assign((props: any) => namesItsData(props), {
      variants: ['metrics'],
    });
    mockFetch.mockImplementation(() => new Promise(() => {}));

    const { container } = render(
      <PlaybookView runId="run-2" playbook="varwait_pb" hasView variant="metrics" />,
    );
    const script = await injectedScript('varwait_pb');
    await act(async () => {
      script.dispatchEvent(new Event('load'));
    });
    await act(async () => {});

    expect(container.innerHTML).toBe('');
  });

  it('renders nothing for a variant the view does not declare', async () => {
    // A view that ignores `variant` would otherwise draw its whole tab again on
    // the Metrics tab.
    (window as any).HermesView_novar_pb = namesItsData;

    const { container } = render(
      <PlaybookView runId="run-2" playbook="novar_pb" hasView variant="metrics" />,
    );
    const script = await injectedScript('novar_pb');
    await act(async () => {
      script.dispatchEvent(new Event('load'));
    });
    await waitFor(() => expect(mockFetch).toHaveBeenCalledTimes(1));
    await act(async () => {});

    expect(screen.queryByText('payload committee')).toBeNull();
    expect(container.innerHTML).toBe('');
  });

  it('leaves a failed asset to the view\'s own tab rather than carding it on another', async () => {
    const { container } = render(
      <PlaybookView runId="run-2" playbook="vargone_pb" hasView variant="metrics" />,
    );
    const script = await injectedScript('vargone_pb');
    await act(async () => {
      script.dispatchEvent(new Event('error'));
    });
    await act(async () => {});

    expect(screen.queryByText('Error loading playbook view')).toBeNull();
    expect(container.innerHTML).toBe('');
  });

  it('keeps a loaded section on another tab through a failed poll', async () => {
    // The card would replace the host's tab body, not sit in the 380px column.
    (window as any).HermesView_varpoll_pb = Object.assign(
      ({ data }: any) => <div>section of {data.kind}</div>,
      { variants: ['metrics'] },
    );

    const { rerender } = render(
      <PlaybookView runId="run-2" playbook="varpoll_pb" hasView variant="metrics" liveTick={1} />,
    );
    const script = await injectedScript('varpoll_pb');
    await act(async () => {
      script.dispatchEvent(new Event('load'));
    });
    await waitFor(() => expect(screen.getByText('section of committee')).toBeInTheDocument());

    mockFetch.mockResolvedValue({ ok: false, status: 503, json: async () => ({ detail: 'busy' }) });
    rerender(<PlaybookView runId="run-2" playbook="varpoll_pb" hasView variant="metrics" liveTick={2} />);
    await waitFor(() => expect(mockFetch).toHaveBeenCalledTimes(2));
    await act(async () => {});

    expect(screen.queryByText('Error loading playbook view')).toBeNull();
    expect(screen.getByText('section of committee')).toBeInTheDocument();
  });

  it('never re-injects the asset on a tick, even after the load failed', async () => {
    // Finding 7.1, measured: with the asset load sharing the data effect, a
    // failing bundle evicted the cache and every poll re-injected -- five dead
    // tags and two GETs a tick, unbounded while the tab is open.
    const { rerender } = render(
      <PlaybookView runId="run-2" playbook="storm_pb" hasView liveTick={1} />,
    );
    const script = await injectedScript('storm_pb');
    await act(async () => {
      script.dispatchEvent(new Event('error'));
    });
    await waitFor(() => expect(screen.getByText('Error loading playbook view')).toBeInTheDocument());

    for (let tick = 2; tick <= 6; tick++) {
      rerender(<PlaybookView runId="run-2" playbook="storm_pb" hasView liveTick={tick} />);
      await waitFor(() => expect(mockFetch).toHaveBeenCalledTimes(tick));
    }

    expect(scriptCount('storm_pb')).toBe(1);
    // And the card is still the card -- a successful poll must not clear a
    // standing asset failure.
    expect(screen.getByText('Error loading playbook view')).toBeInTheDocument();
  });
});
