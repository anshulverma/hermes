import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within, act } from '@testing-library/react';
import ActivityFeed from './ActivityFeed';
import { fetchEvents, fetchEventKinds } from '../api/client';
import type { Event } from '../api/client';
import { parseRoute } from '../hooks/useRoute';

vi.mock('../api/client');
const mockFetchEvents = vi.mocked(fetchEvents);
const mockFetchEventKinds = vi.mocked(fetchEventKinds);

function ev(id: number, over: Partial<Event> = {}): Event {
  return {
    id,
    ts: 1_700_000_000 + id,
    kind: 'ticket_claimed',
    run_id: 'r1',
    ticket_id: `r1/t-${id}`,
    host: 'w1',
    message: `event ${id}`,
    data: {},
    ...over,
  };
}

/** Ids lo..hi ascending, the order the shared stream buffers them in. */
function range(lo: number, hi: number): Event[] {
  return Array.from({ length: hi - lo + 1 }, (_, i) => ev(lo + i));
}

/** Ids hi..lo, newest first, as `order=desc` returns them. */
function page(hi: number, lo: number): Event[] {
  return range(lo, hi).reverse();
}

type Props = { runFilter?: string | null; kindFilter?: string | null; streamEvents?: Event[] };

function el({ runFilter = null, kindFilter = null, streamEvents = [] }: Props) {
  return <ActivityFeed runFilter={runFilter} kindFilter={kindFilter} streamEvents={streamEvents} />;
}

/** The event ids on screen, top to bottom. */
function ids(): number[] {
  return Array.from(document.querySelectorAll('[data-event-id]'), (r) =>
    Number(r.getAttribute('data-event-id')),
  );
}

function row(id: number): HTMLElement {
  return document.querySelector<HTMLElement>(`[data-event-id="${id}"]`)!;
}

describe('ActivityFeed', () => {
  beforeEach(() => {
    mockFetchEvents.mockReset();
    mockFetchEventKinds.mockReset();
    mockFetchEventKinds.mockResolvedValue([]);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('loads the newest page first, newest at the top, under the Activity heading', async () => {
    mockFetchEvents.mockResolvedValue([ev(3), ev(2), ev(1)]);
    render(el({}));

    expect(await screen.findByText('event 3')).toBeInTheDocument();
    expect(mockFetchEvents).toHaveBeenCalledTimes(1);
    expect(mockFetchEvents).toHaveBeenCalledWith({ order: 'desc', limit: 200 });
    expect(ids()).toEqual([3, 2, 1]);
    // A page shorter than 200 is the whole history.
    expect(screen.getByText('Start of history')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Load older' })).toBeNull();
    expect(screen.getByRole('heading', { level: 1, name: 'Activity' })).toHaveAttribute('tabindex', '-1');
  });

  it('Load older asks for the page before the smallest id shown until a short page shows Start of history and focuses its first row', async () => {
    mockFetchEvents
      .mockResolvedValueOnce(page(600, 401))
      .mockResolvedValueOnce(page(400, 201))
      .mockResolvedValueOnce(page(200, 151));
    render(el({}));

    fireEvent.click(await screen.findByRole('button', { name: 'Load older' }));
    await waitFor(() => expect(ids()).toHaveLength(400));
    expect(mockFetchEvents).toHaveBeenLastCalledWith({ order: 'desc', limit: 200, before: 401 });
    // A full page: there may be more.
    expect(screen.queryByText('Start of history')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: 'Load older' }));
    await screen.findByText('Start of history');
    expect(mockFetchEvents).toHaveBeenLastCalledWith({ order: 'desc', limit: 200, before: 201 });
    expect(ids()).toHaveLength(450);
    expect(ids().at(-1)).toBe(151);
    expect(screen.queryByRole('button', { name: 'Load older' })).toBeNull();
    expect(row(200)).toHaveFocus();
  });

  it('an empty older page shows Start of history and focuses it', async () => {
    mockFetchEvents.mockResolvedValueOnce(page(400, 201)).mockResolvedValueOnce([]);
    render(el({}));

    fireEvent.click(await screen.findByRole('button', { name: 'Load older' }));
    expect(await screen.findByText('Start of history')).toHaveFocus();
    expect(mockFetchEvents).toHaveBeenLastCalledWith({ order: 'desc', limit: 200, before: 201 });
    expect(ids()).toHaveLength(200);
  });

  it("names each row's run as a link to its summary, and a crew event with no run shows —", async () => {
    mockFetchEvents.mockResolvedValue([
      ev(2, { run_id: 'r-2' }),
      ev(1, { run_id: null, kind: 'crew_health', ticket_id: null, host: 'w1' }),
    ]);
    render(el({}));

    await screen.findByText('event 2');
    const link = within(row(2)).getByRole('link', { name: 'r-2' });
    expect(link).toHaveAttribute('href', '#/runs/r-2/summary');
    expect(within(row(1)).queryByRole('link')).toBeNull();
    expect(within(row(1)).getByText('—')).toBeInTheDocument();
  });

  it('takes the run chip and the kind select from the route, and both navigate', async () => {
    mockFetchEventKinds.mockResolvedValue(['needs_human', 'ticket_claimed']);
    mockFetchEvents.mockResolvedValue([ev(1, { kind: 'needs_human' })]);
    render(el({ runFilter: 'r1', kindFilter: 'needs_human' }));

    await screen.findByText('event 1');
    expect(mockFetchEvents).toHaveBeenCalledWith({ order: 'desc', limit: 200, run: 'r1', kind: 'needs_human' });
    expect(screen.getByText('run r1')).toBeInTheDocument();
    const select = screen.getByRole('combobox', { name: 'Event kind' });
    await waitFor(() => expect(select).toHaveValue('needs_human'));

    fireEvent.change(select, { target: { value: 'ticket_claimed' } });
    expect(parseRoute(window.location.hash).route).toEqual({ page: 'activity', run: 'r1', kind: 'ticket_claimed' });

    fireEvent.change(select, { target: { value: 'all' } });
    expect(parseRoute(window.location.hash).route).toEqual({ page: 'activity', run: 'r1', kind: null });

    fireEvent.click(screen.getByRole('button', { name: 'Remove run filter r1' }));
    expect(parseRoute(window.location.hash).route).toEqual({ page: 'activity', run: null, kind: 'needs_human' });
    // The chip is going away: focus lands on the page heading, not <body>.
    expect(screen.getByRole('heading', { level: 1, name: 'Activity' })).toHaveFocus();
  });

  it('changing a filter discards the loaded pages and refetches', async () => {
    mockFetchEvents
      .mockResolvedValueOnce([ev(3), ev(2), ev(1)])
      .mockResolvedValueOnce([ev(2, { kind: 'phase_advanced' })]);
    const { rerender } = render(el({}));
    await screen.findByText('event 3');

    rerender(el({ kindFilter: 'phase_advanced' }));
    await waitFor(() => expect(ids()).toEqual([2]));
    expect(mockFetchEvents).toHaveBeenCalledTimes(2);
    expect(mockFetchEvents).toHaveBeenLastCalledWith({ order: 'desc', limit: 200, kind: 'phase_advanced' });
  });

  it('drops a page that answers a filter no longer shown', async () => {
    let answerOld!: (p: Event[]) => void;
    mockFetchEvents
      .mockReturnValueOnce(new Promise<Event[]>((resolve) => { answerOld = resolve; }))
      .mockResolvedValueOnce([ev(2, { kind: 'phase_advanced', message: 'new filter' })]);
    const { rerender } = render(el({}));

    rerender(el({ kindFilter: 'phase_advanced' }));
    expect(await screen.findByText('new filter')).toBeInTheDocument();
    await act(async () => answerOld([ev(9, { message: 'old filter' })]));
    expect(screen.queryByText('old filter')).toBeNull();
    expect(ids()).toEqual([2]);
  });

  it('prepends every matching event of a burst, deduped, and replays nothing buffered before mount', async () => {
    mockFetchEvents.mockResolvedValue(page(400, 201));
    const buffered = [ev(1, { message: 'buffered before mount' })];
    const { rerender } = render(el({ runFilter: 'r1', streamEvents: buffered }));
    await waitFor(() => expect(ids()).toHaveLength(200));

    // One render delivers the whole burst: 400 is already loaded, 402 is another run's.
    rerender(el({
      runFilter: 'r1',
      streamEvents: [...buffered, ev(400), ev(401), ev(402, { run_id: 'r2' }), ev(403)],
    }));
    expect(ids().slice(0, 3)).toEqual([403, 401, 400]);
    expect(ids()).toHaveLength(202);
    expect(screen.queryByText('buffered before mount')).toBeNull();
  });

  it('keeps live events that arrive during the first load', async () => {
    let answer!: (p: Event[]) => void;
    mockFetchEvents.mockReturnValueOnce(new Promise<Event[]>((resolve) => { answer = resolve; }));
    const { rerender } = render(el({}));

    rerender(el({ streamEvents: [ev(6), ev(7)] }));
    await act(async () => answer([ev(6), ev(5)]));
    expect(ids()).toEqual([7, 6, 5]);
  });

  it('caps live prepends at 1000 rows and brings Load older back, which appends past the cap', async () => {
    mockFetchEvents.mockResolvedValueOnce(page(5, 1)).mockResolvedValueOnce(page(5, 1));
    const { rerender } = render(el({}));
    await screen.findByText('Start of history');

    // The stream buffer slides: each render hands over the next 500 events.
    rerender(el({ streamEvents: range(6, 505) }));
    expect(ids()).toHaveLength(505);
    expect(screen.getByText('Start of history')).toBeInTheDocument();

    rerender(el({ streamEvents: range(506, 1005) }));
    expect(ids()).toHaveLength(1000);
    expect(ids()[0]).toBe(1005);
    expect(ids().at(-1)).toBe(6);
    expect(screen.queryByText('Start of history')).toBeNull();

    // act flushes the resolved page; a findBy* poll over 1000 rows can outrun its 1 s timeout under load.
    const loadOlder = screen.getByRole('button', { name: 'Load older' });
    await act(async () => fireEvent.click(loadOlder));
    expect(screen.getByText('Start of history')).toBeInTheDocument();
    expect(mockFetchEvents).toHaveBeenLastCalledWith({ order: 'desc', limit: 200, before: 6 });
    expect(ids()).toHaveLength(1005);
    expect(row(5)).toHaveFocus();
  });

  it('reads the passed-in stream and opens no WebSocket of its own', async () => {
    const socket = vi.fn();
    vi.stubGlobal('WebSocket', socket);
    mockFetchEvents.mockResolvedValue([ev(1)]);
    const { rerender } = render(el({}));
    await screen.findByText('event 1');

    rerender(el({ streamEvents: [ev(2)] }));
    expect(await screen.findByText('event 2')).toBeInTheDocument();
    expect(socket).not.toHaveBeenCalled();
  });

  it('shows an alert with Retry when the first page fails', async () => {
    mockFetchEvents.mockRejectedValueOnce(new Error('boom')).mockResolvedValueOnce([ev(1)]);
    render(el({}));

    expect(await screen.findByRole('alert')).toHaveTextContent('Could not load events: boom');
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(await screen.findByText('event 1')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).toBeNull();
    expect(mockFetchEvents).toHaveBeenCalledTimes(2);
    expect(mockFetchEvents).toHaveBeenLastCalledWith({ order: 'desc', limit: 200 });
  });

  it('a failed Load older keeps the rows and Retry asks for the same page', async () => {
    mockFetchEvents
      .mockResolvedValueOnce(page(400, 201))
      .mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValueOnce(page(200, 190));
    render(el({}));

    fireEvent.click(await screen.findByRole('button', { name: 'Load older' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('offline');
    expect(ids()).toHaveLength(200);

    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    await screen.findByText('Start of history');
    expect(mockFetchEvents).toHaveBeenLastCalledWith({ order: 'desc', limit: 200, before: 201 });
    expect(ids()).toHaveLength(211);
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('shows No events yet. when there are none', async () => {
    mockFetchEvents.mockResolvedValue([]);
    render(el({}));

    expect(await screen.findByText('No events yet.')).toBeInTheDocument();
    expect(screen.queryByText('Start of history')).toBeNull();
  });

  it('should handle loading state', () => {
    mockFetchEvents.mockReturnValue(new Promise<Event[]>(() => {}));
    render(el({}));

    expect(screen.getByText(/loading/i)).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 1, name: 'Activity' })).toBeInTheDocument();
  });

  it('should populate kind filter options from fetchEventKinds, not hardcoded', async () => {
    mockFetchEventKinds.mockResolvedValue(['kind_a', 'kind_b']);
    mockFetchEvents.mockResolvedValue([]);
    render(el({}));

    await waitFor(() => {
      const options = Array.from(
        screen.getByRole('combobox').querySelectorAll('option'),
        (opt) => (opt as HTMLOptionElement).value,
      );
      expect(options).toEqual(['all', 'kind_a', 'kind_b']);
      expect(options).not.toContain('ticket_claimed');
      expect(options).not.toContain('needs_human');
      expect(options).not.toContain('crew_health');
    });
  });
});
