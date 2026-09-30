/**
 * Needs you: every decision waiting on a person, across all runs.
 *
 * The clock is fixed, so every age and wait reads exactly. The throttle is
 * useStreamTrigger's to test; here a test fires the refetch the page handed
 * it, when the throttle would.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, within, fireEvent, act, waitFor } from '@testing-library/react';
import NeedsYou from './NeedsYou';
import * as client from '../api/client';
import type { Event, NeedsYouItem, ReductionControlResponse, Run } from '../api/client';
import { useStreamTrigger } from '../hooks/useStreamTrigger';

const { NOW } = vi.hoisted(() => ({ NOW: 1_800_000_000 }));

vi.mock('../api/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/client')>()),
  fetchNeedsYou: vi.fn(),
  acceptReduction: vi.fn(),
  rejectReduction: vi.fn(),
}));
vi.mock('../hooks/useNow', () => ({ useNow: () => NOW }));
vi.mock('../hooks/useStreamTrigger', () => ({ useStreamTrigger: vi.fn() }));

/** A reduction holding one needs_human ticket, as /api/needs-you returns it. */
function item(id: number, run_id: string, waited: number, title: string): NeedsYouItem {
  return {
    id,
    run_id,
    phase: 'decide',
    kind: 'verdict',
    json: { title },
    review_state: 'pending',
    member_ticket_ids: [`${run_id}/t-${id}`],
    member_tickets: [{ id: `${run_id}/t-${id}`, state: 'needs_human', phase: 'decide' }],
    playbook: run_id === 'run-a' ? 'alpha' : 'beta',
    created_at: NOW - waited,
  };
}

// The server's order: created_at, then id, ascending.
const B1 = item(2, 'run-b', 7200, 'Pick the schema');
const A1 = item(1, 'run-a', 300, 'Ship the cache');
const A2 = item(3, 'run-a', 60, 'Rename the flag');
const ALL = [B1, A1, A2];

function runRow(id: string, playbook: string, state: string, awaiting: number): Run {
  return {
    id,
    playbook,
    site: 'local',
    state,
    phase: 'decide',
    base_ref: 'main',
    created_at: NOW - 9000,
    updated_at: NOW - 100,
    tickets: { needs_human: awaiting },
    has_view: false,
    awaiting,
    subject: null,
  };
}
// App's run list, handed down: the group headers' state labels come from it.
const RUNS = [runRow('run-a', 'alpha', 'running', 2), runRow('run-b', 'beta', 'stopped', 1)];

const announce = vi.fn<(message: string) => void>();
const onDecided = vi.fn<() => void>();

function page(runFilter: string | null = null, streamEvents: Event[] = []) {
  return (
    <NeedsYou
      runFilter={runFilter}
      runs={RUNS}
      streamEvents={streamEvents}
      onDecided={onDecided}
      announce={announce}
    />
  );
}

function renderPage(runFilter: string | null = null, streamEvents: Event[] = []) {
  return render(page(runFilter, streamEvents));
}

const button = (name: string) => screen.getByRole('button', { name });
const gone = (name: string) =>
  waitFor(() => expect(screen.queryByRole('button', { name })).toBeNull());
/** Let the effects a render queued run, so an assertion sees what they did. */
const flush = () => act(async () => {});

/** Fire the refetch NeedsYou handed its stream trigger, as the throttle would. */
async function fireStream() {
  const onTrigger = vi.mocked(useStreamTrigger).mock.calls.at(-1)![2];
  await act(async () => {
    onTrigger();
  });
}

/** A promise the test settles itself. */
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: Error) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

describe('NeedsYou', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(client.fetchNeedsYou).mockResolvedValue(ALL);
    vi.mocked(client.acceptReduction).mockResolvedValue({ review_state: 'accepted' });
    vi.mocked(client.rejectReduction).mockResolvedValue({ review_state: 'rejected' });
  });

  afterEach(() => {
    window.location.hash = '';
  });

  it('groups decisions by run, longest-waiting run first, items oldest first, all collapsed', async () => {
    renderPage();
    await screen.findByRole('button', { name: 'Pick the schema' });

    expect(screen.getAllByRole('heading', { level: 2 }).map((h) => h.textContent)).toEqual([
      'run-b',
      'run-a',
    ]);
    const a = screen.getByRole('region', { name: 'run-a' });
    expect(within(a).getAllByRole('button').map((b) => b.textContent)).toEqual([
      'Ship the cache',
      'Rename the flag',
    ]);
    for (const b of screen.getAllByRole('button')) {
      expect(b).toHaveAttribute('aria-expanded', 'false');
    }
  });

  it('heads each group with its run link, playbook, state and how long its oldest item has waited', async () => {
    renderPage();
    const b = await screen.findByRole('region', { name: 'run-b' });

    expect(within(b).getByRole('link', { name: 'run-b' })).toHaveAttribute(
      'href',
      '#/runs/run-b/summary',
    );
    expect(within(b).getByText('beta')).toBeInTheDocument();
    expect(within(b).getByText('stopped')).toBeInTheDocument();
    expect(within(b).getByText('waiting 2h 0m')).toBeInTheDocument();
    const a = screen.getByRole('region', { name: 'run-a' });
    expect(within(a).getByText('alpha')).toBeInTheDocument();
    expect(within(a).getByText('running')).toBeInTheDocument();
    expect(within(a).getByText('waiting 5m 0s')).toBeInTheDocument();
  });

  it('a decision stamped after the shared 30 s clock waits 0s, never a negative time', async () => {
    vi.mocked(client.fetchNeedsYou).mockResolvedValue([item(9, 'run-c', -12, 'Just arrived')]);
    renderPage();

    const c = await screen.findByRole('region', { name: 'run-c' });
    expect(within(c).getByText('waiting 0s')).toBeInTheDocument();
  });

  it("shows each item's headline and how long ago it arrived", async () => {
    renderPage();
    const a = await screen.findByRole('region', { name: 'run-a' });

    expect(within(a).getByRole('button', { name: 'Ship the cache' })).toBeInTheDocument();
    const age = within(a).getByText('5 minutes ago');
    expect(age.tagName).toBe('TIME');
    expect(age).toHaveAttribute('datetime', new Date((NOW - 300) * 1000).toISOString());
    expect(within(a).getByText('1 minute ago')).toBeInTheDocument();
    expect(
      within(screen.getByRole('region', { name: 'run-b' })).getByText('2 hours ago'),
    ).toBeInTheDocument();
  });

  it('is headed Needs you, focusable, with the help line under it', async () => {
    renderPage();

    expect(screen.getByRole('heading', { level: 1, name: 'Needs you' })).toHaveAttribute(
      'tabindex',
      '-1',
    );
    expect(
      screen.getByText(
        'A decision settles its tickets now; the run moves on when its master is running.',
      ),
    ).toBeInTheDocument();
    await screen.findByRole('button', { name: 'Pick the schema' });
  });

  it('filters to one run with a removable chip that sends focus to the heading', async () => {
    const { rerender } = renderPage('run-a');
    await screen.findByRole('button', { name: 'Ship the cache' });

    expect(screen.queryByRole('button', { name: 'Pick the schema' })).toBeNull();
    expect(screen.getAllByRole('heading', { level: 2 }).map((h) => h.textContent)).toEqual([
      'run-a',
    ]);
    // Two items from run-a: neither starts open.
    await flush();
    expect(button('Ship the cache')).toHaveAttribute('aria-expanded', 'false');
    expect(button('Rename the flag')).toHaveAttribute('aria-expanded', 'false');
    const chip = screen.getByTestId('needs-you-run-chip');
    expect(chip).toHaveTextContent('run run-a');

    fireEvent.click(within(chip).getByRole('button', { name: 'Remove run filter run-a' }));

    expect(window.location.hash).toBe('#/needs-you');
    expect(document.activeElement).toBe(screen.getByRole('heading', { level: 1 }));

    // App hands down the filter the address now names: none. A decision on
    // the item the filter hid moves focus to the item after it.
    rerender(page(null));
    fireEvent.click(button('Pick the schema'));
    vi.mocked(client.fetchNeedsYou).mockResolvedValue([A1, A2]);
    fireEvent.click(button('Accept'));

    await waitFor(() => expect(document.activeElement).toBe(button('Ship the cache')));
  });

  it('with ?run= and exactly one item, that item starts open', async () => {
    renderPage('run-b');

    const toggle = await screen.findByRole('button', { name: 'Pick the schema' });
    await waitFor(() => expect(toggle).toHaveAttribute('aria-expanded', 'true'));
    expect(button('Accept')).toBeInTheDocument();

    // Its toggle closes it, and a refetch does not reopen it.
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    await fireStream();
    await flush();
    expect(client.fetchNeedsYou).toHaveBeenCalledTimes(2);
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
  });

  it('expands an item into its ReductionCard with a needs-human pill, Accept, Reject and Open in run', async () => {
    renderPage();
    const toggle = await screen.findByRole('button', { name: 'Pick the schema' });
    expect(screen.queryByRole('button', { name: 'Accept' })).toBeNull();

    fireEvent.click(toggle);

    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    const body = document.getElementById(toggle.getAttribute('aria-controls')!)!;
    // Mapped through normalizeReduction: the card's status and its member
    // ticket read needs-human; raw, the status would read 'in progress'.
    expect(within(body).getAllByText('needs human')).toHaveLength(2);
    expect(within(body).queryByText('in progress')).toBeNull();
    expect(within(body).getByText('#2')).toBeInTheDocument();
    expect(within(body).getByRole('button', { name: 'Accept' })).toBeEnabled();
    expect(within(body).getByRole('button', { name: 'Reject' })).toBeEnabled();
    expect(within(body).getByRole('link', { name: 'Open in run' })).toHaveAttribute(
      'href',
      '#/runs/run-b/summary',
    );
  });

  it('accepts inline: the item leaves, the decision is announced, the list and the runs refetch', async () => {
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Pick the schema' }));
    vi.mocked(client.fetchNeedsYou).mockResolvedValue([A1, A2]);

    fireEvent.click(button('Accept'));

    await gone('Pick the schema');
    expect(client.acceptReduction).toHaveBeenCalledWith(2);
    expect(announce).toHaveBeenCalledWith('Accepted: Pick the schema');
    expect(onDecided).toHaveBeenCalledTimes(1);
    // onDecided is App's refetchRuns: the runs list refreshes there, not here.
    await waitFor(() => expect(client.fetchNeedsYou).toHaveBeenCalledTimes(2));
  });

  it('rejects only after the confirm, with no reason, and announces it', async () => {
    const confirmSpy = vi
      .spyOn(window, 'confirm')
      .mockReturnValueOnce(false)
      .mockReturnValueOnce(true);
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Pick the schema' }));
    vi.mocked(client.fetchNeedsYou).mockResolvedValue([A1, A2]);
    const post = deferred<ReductionControlResponse>();
    vi.mocked(client.rejectReduction).mockReturnValueOnce(post.promise);

    fireEvent.click(button('Reject'));

    expect(confirmSpy).toHaveBeenCalledWith(
      'Reject this reduction? This will fail the tickets it is holding.',
    );
    expect(client.rejectReduction).not.toHaveBeenCalled();

    fireEvent.click(button('Reject'));

    // In flight: both buttons are off, as for Accept.
    expect(button('Accept')).toBeDisabled();
    expect(button('Reject')).toBeDisabled();
    await act(async () => post.resolve({ review_state: 'rejected' }));
    await gone('Pick the schema');
    expect(announce).toHaveBeenCalledWith('Rejected: Pick the schema');
    expect(vi.mocked(client.rejectReduction).mock.calls).toEqual([[2]]);
    expect(client.acceptReduction).not.toHaveBeenCalled();
    confirmSpy.mockRestore();
  });

  it('disables both buttons while the decision is in flight', async () => {
    const post = deferred<ReductionControlResponse>();
    vi.mocked(client.acceptReduction).mockReturnValueOnce(post.promise);
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Pick the schema' }));

    fireEvent.click(button('Accept'));

    expect(button('Accept')).toBeDisabled();
    expect(button('Reject')).toBeDisabled();
    fireEvent.click(button('Accept'));
    expect(client.acceptReduction).toHaveBeenCalledTimes(1);

    vi.mocked(client.fetchNeedsYou).mockResolvedValue([A1, A2]);
    await act(async () => post.resolve({ review_state: 'accepted' }));
    await gone('Pick the schema');
    expect(announce).toHaveBeenCalledWith('Accepted: Pick the schema');
  });

  it('409: announces decided elsewhere and keeps the item, buttons off, until the refetch settles', async () => {
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Pick the schema' }));
    // fetchJSON's errors carry the status (Task 7).
    vi.mocked(client.acceptReduction).mockRejectedValueOnce(
      Object.assign(new Error("reduction 2 is 'accepted', not 'pending'; already resolved"), {
        status: 409,
      }),
    );
    const refetch = deferred<NeedsYouItem[]>();
    vi.mocked(client.fetchNeedsYou).mockReturnValueOnce(refetch.promise);

    fireEvent.click(button('Accept'));

    expect(await screen.findByText('Already decided elsewhere')).toBeInTheDocument();
    expect(announce).toHaveBeenCalledWith('run-b: decided elsewhere');
    expect(button('Accept')).toBeDisabled();
    expect(button('Reject')).toBeDisabled();
    expect(client.fetchNeedsYou).toHaveBeenCalledTimes(2);

    // The refetch still returns it: the message stays and the buttons return.
    await act(async () => refetch.resolve(ALL));

    await waitFor(() => expect(button('Accept')).toBeEnabled());
    expect(button('Reject')).toBeEnabled();
    expect(screen.getByText('Already decided elsewhere')).toBeInTheDocument();
    expect(announce).toHaveBeenCalledTimes(1);

    // A refetch that fails settles it too: the buttons return beside the page's alert.
    vi.mocked(client.acceptReduction).mockRejectedValueOnce(
      Object.assign(new Error('already resolved'), { status: 409 }),
    );
    vi.mocked(client.fetchNeedsYou).mockRejectedValueOnce(new Error('HTTP error! status: 500'));

    fireEvent.click(button('Accept'));

    expect(await screen.findByRole('alert')).toHaveTextContent('HTTP error! status: 500');
    await waitFor(() => expect(button('Accept')).toBeEnabled());
    expect(button('Reject')).toBeEnabled();
  });

  it('409: the refetch removes an item decided elsewhere, announced once', async () => {
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Pick the schema' }));
    vi.mocked(client.acceptReduction).mockRejectedValueOnce(
      Object.assign(new Error('already resolved'), { status: 409 }),
    );
    vi.mocked(client.fetchNeedsYou).mockResolvedValue([A1, A2]);

    fireEvent.click(button('Accept'));

    await gone('Pick the schema');
    expect(announce).toHaveBeenCalledTimes(1);
    expect(announce).toHaveBeenCalledWith('run-b: decided elsewhere');
  });

  it('any other failure shows on the item, keeps it and gives the buttons back', async () => {
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Pick the schema' }));
    vi.mocked(client.acceptReduction).mockRejectedValueOnce(
      Object.assign(new Error('database is locked'), { status: 500 }),
    );

    fireEvent.click(button('Accept'));

    expect(await screen.findByRole('alert')).toHaveTextContent('database is locked');
    expect(button('Accept')).toBeEnabled();
    expect(button('Reject')).toBeEnabled();
    expect(button('Pick the schema')).toBeInTheDocument();
    expect(announce).not.toHaveBeenCalled();
    expect(client.fetchNeedsYou).toHaveBeenCalledTimes(1);

    // Trying again clears the old error while the new request is in flight.
    vi.mocked(client.acceptReduction).mockReturnValueOnce(
      deferred<ReductionControlResponse>().promise,
    );
    fireEvent.click(button('Accept'));

    expect(button('Accept')).toBeDisabled();
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('refetches on its own stream trigger, for run events only', async () => {
    const events: Event[] = [];
    renderPage(null, events);
    await screen.findByRole('button', { name: 'Pick the schema' });

    const [passed, match] = vi.mocked(useStreamTrigger).mock.calls.at(-1)!;
    expect(passed).toBe(events);
    const event = (run_id: string | null): Event => ({
      id: 1,
      ts: NOW,
      kind: 'needs_human',
      run_id,
      ticket_id: null,
      host: null,
      message: null,
      data: {},
    });
    expect(match(event('run-a'))).toBe(true);
    expect(match(event(null))).toBe(false);

    vi.mocked(client.fetchNeedsYou).mockResolvedValue([A1, A2]);
    await fireStream();

    await gone('Pick the schema');
    expect(client.fetchNeedsYou).toHaveBeenCalledTimes(2);
    // A closed item that goes is not worth interrupting the reader for.
    expect(announce).not.toHaveBeenCalled();
  });

  it('keeps open items open across a refetch', async () => {
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Ship the cache' }));
    vi.mocked(client.fetchNeedsYou).mockResolvedValue([B1, A1]);

    await fireStream();

    await gone('Rename the flag');
    expect(button('Ship the cache')).toHaveAttribute('aria-expanded', 'true');
    expect(button('Accept')).toBeInTheDocument();
  });

  it('a refetch that lands before the accept resolves announces Accepted, not decided elsewhere', async () => {
    const post = deferred<ReductionControlResponse>();
    vi.mocked(client.acceptReduction).mockReturnValueOnce(post.promise);
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Pick the schema' }));
    fireEvent.click(button('Accept'));

    // accept_reduction emits reduction_accepted in its own commit, so the
    // stream's refetch can come back without the item before the POST does.
    // It brings a decision stamped the same second as the one in flight, with
    // a higher id.
    const tie = item(4, 'run-a', 7200, 'Tie the knot');
    vi.mocked(client.fetchNeedsYou).mockResolvedValue([tie, A1]);
    await fireStream();
    await gone('Rename the flag');
    expect(button('Pick the schema')).toBeInTheDocument();
    // The item kept in flight keeps its place: oldest first, then lowest id.
    expect(screen.getAllByRole('heading', { level: 2 }).map((h) => h.textContent)).toEqual([
      'run-b',
      'run-a',
    ]);

    await act(async () => post.resolve({ review_state: 'accepted' }));

    await gone('Pick the schema');
    expect(announce).toHaveBeenCalledWith('Accepted: Pick the schema');
    expect(announce).not.toHaveBeenCalledWith('run-b: decided elsewhere');
  });

  it('a refetch that drops an open item announces decided elsewhere; a closed one says nothing', async () => {
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Rename the flag' }));
    vi.mocked(client.fetchNeedsYou).mockResolvedValue([A1]);

    await fireStream();

    await gone('Rename the flag');
    expect(screen.queryByRole('button', { name: 'Pick the schema' })).toBeNull();
    expect(announce).toHaveBeenCalledTimes(1);
    expect(announce).toHaveBeenCalledWith('run-a: decided elsewhere');
  });

  it('keeps focus where it is when a refetch removes another item', async () => {
    renderPage();
    (await screen.findByRole('button', { name: 'Pick the schema' })).focus();
    // The item that goes has a next item, Rename the flag: focus does not go there.
    vi.mocked(client.fetchNeedsYou).mockResolvedValue([B1, A2]);

    await fireStream();

    await gone('Ship the cache');
    expect(document.activeElement).toBe(button('Pick the schema'));
  });

  it('a refetch that lands after a newer one changes nothing', async () => {
    renderPage();
    await screen.findByRole('button', { name: 'Pick the schema' });
    const older = deferred<NeedsYouItem[]>();
    const failing = deferred<NeedsYouItem[]>();
    const newest = deferred<NeedsYouItem[]>();
    vi.mocked(client.fetchNeedsYou)
      .mockReturnValueOnce(older.promise)
      .mockReturnValueOnce(failing.promise)
      .mockReturnValueOnce(newest.promise);
    await fireStream();
    await fireStream();
    await fireStream();

    await act(async () => newest.resolve([A1, A2]));
    await gone('Pick the schema');
    await act(async () => older.resolve(ALL));
    await act(async () => failing.reject(new Error('HTTP error! status: 500')));

    expect(screen.queryByRole('button', { name: 'Pick the schema' })).toBeNull();
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('after a decision removes its item, focus moves to the next item, else the previous one, else the heading', async () => {
    // On screen: Pick the schema, Ship the cache, Rename the flag. Accept is
    // clicked, never focused: focus follows the decision from wherever it was.
    const cases: [string, NeedsYouItem[], string][] = [
      ['Ship the cache', [B1, A2], 'Rename the flag'],
      ['Rename the flag', [B1, A1], 'Ship the cache'],
    ];
    for (const [decided, left, next] of cases) {
      vi.mocked(client.fetchNeedsYou).mockResolvedValue(ALL);
      const { unmount } = renderPage();
      fireEvent.click(await screen.findByRole('button', { name: decided }));
      vi.mocked(client.fetchNeedsYou).mockResolvedValue(left);

      fireEvent.click(button('Accept'));

      await waitFor(() => expect(document.activeElement).toBe(button(next)));
      unmount();
    }

    vi.mocked(client.fetchNeedsYou).mockResolvedValue([B1]);
    renderPage();
    const only = await screen.findByRole('button', { name: 'Pick the schema' });
    // One item, but no ?run=: it starts closed all the same.
    await flush();
    expect(only).toHaveAttribute('aria-expanded', 'false');
    fireEvent.click(only);
    vi.mocked(client.fetchNeedsYou).mockResolvedValue([]);

    fireEvent.click(button('Accept'));

    await waitFor(() => expect(screen.getByRole('heading', { level: 1 })).toHaveFocus());
  });

  it('says so when nothing is waiting', async () => {
    const first = deferred<NeedsYouItem[]>();
    vi.mocked(client.fetchNeedsYou).mockReturnValueOnce(first.promise);
    renderPage();

    // Still loading: that is not nothing.
    expect(screen.getByText('Loading decisions…')).toBeInTheDocument();
    expect(screen.queryByText('Nothing is waiting on you.')).toBeNull();

    await act(async () => first.resolve([]));

    expect(await screen.findByText('Nothing is waiting on you.')).toBeInTheDocument();
    expect(screen.queryByText('Loading decisions…')).toBeNull();
    expect(screen.queryByRole('link', { name: 'Show all runs' })).toBeNull();
    expect(screen.queryByRole('region')).toBeNull();
  });

  it('with ?run= and nothing from that run, names it and offers every run', async () => {
    renderPage('run-z');

    expect(await screen.findByText('Nothing from run-z is waiting on you.')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Show all runs' })).toHaveAttribute(
      'href',
      '#/needs-you',
    );
    expect(screen.getByTestId('needs-you-run-chip')).toHaveTextContent('run run-z');

    fireEvent.click(screen.getByRole('link', { name: 'Show all runs' }));

    // The link is about to go: focus the page heading, not <body>.
    expect(screen.getByRole('heading', { level: 1 })).toHaveFocus();
  });

  it('a failed load shows an alert with Retry', async () => {
    vi.mocked(client.fetchNeedsYou).mockRejectedValueOnce(new Error('HTTP error! status: 500'));
    renderPage();

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('HTTP error! status: 500');
    expect(screen.getByRole('heading', { level: 1, name: 'Needs you' })).toBeInTheDocument();
    expect(screen.queryByText('Loading decisions…')).toBeNull();

    fireEvent.click(within(alert).getByRole('button', { name: 'Retry' }));

    expect(await screen.findByRole('button', { name: 'Pick the schema' })).toBeInTheDocument();
    expect(screen.queryByRole('alert')).toBeNull();

    // A refetch that fails after a good load keeps the list and adds the alert.
    vi.mocked(client.fetchNeedsYou).mockRejectedValueOnce(new Error('HTTP error! status: 502'));
    await fireStream();

    expect(await screen.findByRole('alert')).toHaveTextContent('HTTP error! status: 502');
    expect(button('Pick the schema')).toBeInTheDocument();
  });
});
