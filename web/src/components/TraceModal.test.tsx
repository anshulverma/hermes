import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import TraceModal from './TraceModal';

const mockFetch = vi.fn();
(globalThis as any).fetch = mockFetch;

const trace = {
  attempt_id: 12,
  attempt: 1,
  ticket_id: 'run-5/3-research',
  run_id: 'run-5',
  ref: 'claude:session:9b0e67d3-772f-45cf-85b3-e95832ad150d',
  lines: 6,
  bytes: 4096,
  unparsed: 0,
  counts: { prompt: 1, answer: 1, thinking: 1, tool_call: 1, attachment: 2 },
  records: [
    { line: 0, kind: 'prompt', role: 'user', ts: null, title: '', text: 'review D123' },
    { line: 1, kind: 'thinking', role: 'assistant', ts: null, title: '', text: 'let me look' },
    { line: 1, kind: 'answer', role: 'assistant', ts: null, title: '', text: 'Found three issues' },
    { line: 2, kind: 'tool_call', role: 'assistant', ts: null, title: 'Bash', text: '{"command":"ls"}' },
    { line: 3, kind: 'attachment', role: null, ts: null, title: 'hook_success', text: '{"ok":1}' },
    { line: 4, kind: 'attachment', role: null, ts: null, title: 'hook_success', text: '{"ok":2}' },
  ],
};

function respond(body: any, ok = true, status = 200) {
  return Promise.resolve({
    ok,
    status,
    statusText: ok ? 'OK' : 'Not Found',
    json: () => Promise.resolve(body),
  });
}

describe('TraceModal', () => {
  beforeEach(() => {
    mockFetch.mockReset();
    mockFetch.mockImplementation(() => respond(trace));
  });

  it('fetches nothing until an attempt is given', () => {
    render(<TraceModal attemptId={null} onClose={() => {}} />);
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it('loads the trace for the attempt it is opened on', async () => {
    render(<TraceModal attemptId={12} onClose={() => {}} />);

    await waitFor(() => expect(mockFetch).toHaveBeenCalled());
    expect(mockFetch.mock.calls[0][0]).toContain('/api/attempts/12/trace');
  });

  it('shows the conversation, which is what the reader came for', async () => {
    render(<TraceModal attemptId={12} onClose={() => {}} />);

    expect(await screen.findByText('review D123')).toBeInTheDocument();
    expect(screen.getByText('Found three issues')).toBeInTheDocument();
  });

  it('keeps the noise out of the way but reachable', async () => {
    render(<TraceModal attemptId={12} onClose={() => {}} />);
    await screen.findByText('review D123');

    // Two attachments are not rendered as records until asked for.
    expect(screen.queryByText('hook_success')).not.toBeInTheDocument();

    fireEvent.click(screen.getByText(/2 non-conversation/));

    await waitFor(() => expect(screen.getAllByText('hook_success').length).toBe(2));
  });

  it('collapses thinking and tool calls but leaves the answer open', async () => {
    render(<TraceModal attemptId={12} onClose={() => {}} />);
    await screen.findByText('review D123');

    // Collapsed records still show a one-line preview, and the body is rendered
    // differently per kind (prose as markdown, the rest as text) — so the open
    // state is read from the disclosure itself, not from what it happens to
    // render.
    const expanded = (testId: string) =>
      screen.getByTestId(testId).querySelector('button')?.getAttribute('aria-expanded');

    expect(expanded('trace-record-1-answer')).toBe('true');
    expect(expanded('trace-record-1-thinking')).toBe('false');
    expect(expanded('trace-record-2-tool_call')).toBe('false');
  });

  it('expands a collapsed record when clicked', async () => {
    render(<TraceModal attemptId={12} onClose={() => {}} />);
    await screen.findByText('review D123');

    fireEvent.click(screen.getByText('Thinking'));

    expect(await screen.findByText('let me look')).toBeInTheDocument();
  });

  it('reports how much trace there is', async () => {
    render(<TraceModal attemptId={12} onClose={() => {}} />);

    expect(await screen.findByText(/6 records/)).toBeInTheDocument();
    expect(screen.getByText(/4\.0 KB/)).toBeInTheDocument();
  });

  it('fetches the raw form only when raw is asked for', async () => {
    render(<TraceModal attemptId={12} onClose={() => {}} />);
    await screen.findByText('review D123');
    expect(mockFetch).toHaveBeenCalledTimes(1);

    mockFetch.mockImplementation(() =>
      respond({ ...trace, raw: '{"type":"user"}\n{"type":"assistant"}\n' }),
    );
    fireEvent.click(screen.getByText('Raw'));

    await waitFor(() => expect(screen.getByTestId('trace-raw')).toBeInTheDocument());
    expect(mockFetch.mock.calls[1][0]).toContain('raw=1');
  });

  it('surfaces a server explanation rather than a blank window', async () => {
    mockFetch.mockImplementation(() =>
      respond({ detail: 'No trace was captured for attempt 1 of run-5/3-research.' }, false, 404),
    );

    render(<TraceModal attemptId={12} onClose={() => {}} />);

    expect(await screen.findByTestId('trace-error')).toHaveTextContent('No trace was captured');
  });

  it('says so when a trace has no conversation at all', async () => {
    mockFetch.mockImplementation(() =>
      respond({
        ...trace,
        records: [{ line: 0, kind: 'meta', role: null, ts: null, title: 'last-prompt', text: '{}' }],
      }),
    );

    render(<TraceModal attemptId={12} onClose={() => {}} />);

    expect(await screen.findByText(/no conversation records/)).toBeInTheDocument();
  });

  it('refetches when opened on a different attempt', async () => {
    const { rerender } = render(<TraceModal attemptId={12} onClose={() => {}} />);
    await waitFor(() => expect(mockFetch).toHaveBeenCalledTimes(1));

    rerender(<TraceModal attemptId={13} onClose={() => {}} />);

    await waitFor(() => expect(mockFetch).toHaveBeenCalledTimes(2));
    expect(mockFetch.mock.calls[1][0]).toContain('/api/attempts/13/trace');
  });
});

describe('TraceModal — one scrolling surface', () => {
  const longText = Array.from({ length: 120 }, (_, i) => `line ${i}`).join('\n');

  const bigTrace = {
    ...trace,
    records: [
      { line: 0, kind: 'prompt', role: 'user', ts: null, title: '', text: longText },
      { line: 1, kind: 'answer', role: 'assistant', ts: null, title: '', text: 'short answer' },
    ],
  };

  beforeEach(() => {
    mockFetch.mockReset();
    mockFetch.mockImplementation(() => respond(bigTrace));
  });

  it('gives record bodies no scrollbar of their own', async () => {
    render(<TraceModal attemptId={12} onClose={() => {}} />);
    await screen.findByTestId('trace-record-1-answer');

    // A body that scrolls independently steals the wheel from the modal.
    document.querySelectorAll('pre').forEach((pre) => {
      expect((pre as HTMLElement).style.overflow).not.toBe('auto');
      expect((pre as HTMLElement).style.overflow).not.toBe('scroll');
    });
  });

  it('has exactly one scroll container', async () => {
    render(<TraceModal attemptId={12} onClose={() => {}} />);
    await screen.findByTestId('trace-records');

    const scrollers = Array.from(document.querySelectorAll<HTMLElement>('*')).filter(
      (el) => el.style.overflow === 'auto' || el.style.overflowY === 'auto',
    );
    expect(scrollers.length).toBe(1);
  });

  it('clamps a very long body instead of scrolling it, and can show all', async () => {
    render(<TraceModal attemptId={12} onClose={() => {}} />);
    await screen.findByTestId('trace-record-0-prompt');

    const showAll = screen.getByRole('button', { name: /show all 120 lines/i });
    const body = screen.getByTestId('trace-body-0-prompt');
    expect(body.style.maxHeight).not.toBe('');

    fireEvent.click(showAll);

    expect(screen.getByTestId('trace-body-0-prompt').style.maxHeight).toBe('');
  });

  it('leaves a short body unclamped', async () => {
    render(<TraceModal attemptId={12} onClose={() => {}} />);
    await screen.findByTestId('trace-record-1-answer');

    expect(screen.getByTestId('trace-body-1-answer').style.maxHeight).toBe('');
    expect(screen.queryByRole('button', { name: /show all 1 line/i })).toBeNull();
  });

  it('does not give the raw view its own scrollbar either', async () => {
    render(<TraceModal attemptId={12} onClose={() => {}} />);
    await screen.findByTestId('trace-records');

    mockFetch.mockImplementation(() => respond({ ...bigTrace, raw: longText }));
    fireEvent.click(screen.getByText('Raw'));

    const raw = await screen.findByTestId('trace-raw');
    expect(raw.style.overflow).not.toBe('auto');
    const scrollers = Array.from(document.querySelectorAll<HTMLElement>('*')).filter(
      (el) => el.style.overflow === 'auto' || el.style.overflowY === 'auto',
    );
    expect(scrollers.length).toBe(1);
  });
});

describe('TraceModal — a trace that is one document', () => {
  beforeEach(() => {
    mockFetch.mockReset();
    mockFetch.mockImplementation(() =>
      respond({
        ...trace,
        counts: { document: 1 },
        records: [
          { line: 0, kind: 'document', role: null, ts: null, title: 'trace document',
            text: '{\n  "session_id": "s1"\n}' },
        ],
      }),
    );
  });

  it('shows it rather than filing it under non-conversation', async () => {
    // Not every agent writes JSONL; for one, this single record IS the trace.
    render(<TraceModal attemptId={12} onClose={() => {}} />);

    expect(await screen.findByTestId('trace-record-0-document')).toBeInTheDocument();
    expect(screen.queryByText(/no conversation records/)).toBeNull();
    expect(screen.queryByText(/non-conversation/)).toBeNull();
  });
});
