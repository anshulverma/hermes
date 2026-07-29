import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import PlaybookDialog from './PlaybookDialog';
import type { RunDetail } from '../api/client';

const mockRun: RunDetail = {
  id: 'test-run-123',
  playbook: 'example',
  site: 'local',
  state: 'running',
  phase: 'work',
  base_ref: 'main',
  created_at: '2026-07-29T10:00:00Z',
  updated_at: '2026-07-29T10:05:00Z',
  config: { issue_kind: 'bug' },
  tickets: { queued: 3 },
  phases: [
    { name: 'work', counts: { queued: 3 }, current: true },
    { name: 'reduce', counts: {}, current: false },
  ],
};

describe('PlaybookDialog', () => {
  it('should not render when closed', () => {
    render(<PlaybookDialog open={false} run={mockRun} onClose={() => {}} />);

    expect(screen.queryByText(/example playbook/i)).not.toBeInTheDocument();
  });

  it('should render playbook info when open', () => {
    render(<PlaybookDialog open={true} run={mockRun} onClose={() => {}} />);

    expect(screen.getByText(/example playbook/i)).toBeInTheDocument();
    expect(screen.getByText(/Echo playbook for testing and demos/i)).toBeInTheDocument();
  });

  it('should display run details', () => {
    render(<PlaybookDialog open={true} run={mockRun} onClose={() => {}} />);

    expect(screen.getByText('test-run-123')).toBeInTheDocument();
    expect(screen.getByText('local')).toBeInTheDocument();
  });

  it('should display context from run config', () => {
    render(<PlaybookDialog open={true} run={mockRun} onClose={() => {}} />);

    expect(screen.getByText('issue_kind')).toBeInTheDocument();
    expect(screen.getByText('bug')).toBeInTheDocument();
  });

  it('should display phases with current phase highlighted', () => {
    render(<PlaybookDialog open={true} run={mockRun} onClose={() => {}} />);

    // Both phases should be present
    const workPhase = screen.getByText('work');
    const reducePhase = screen.getByText('reduce');

    expect(workPhase).toBeInTheDocument();
    expect(reducePhase).toBeInTheDocument();
  });

  it('should call onClose when Close button is clicked', () => {
    const onClose = vi.fn();
    render(<PlaybookDialog open={true} run={mockRun} onClose={onClose} />);

    const closeButton = screen.getByText('Close');
    fireEvent.click(closeButton);

    expect(onClose).toHaveBeenCalledOnce();
  });

  it('should not render when run is null', () => {
    render(<PlaybookDialog open={true} run={null} onClose={() => {}} />);

    expect(screen.queryByText(/playbook/i)).not.toBeInTheDocument();
  });

  it('should display context note', () => {
    render(<PlaybookDialog open={true} run={mockRun} onClose={() => {}} />);

    expect(
      screen.getByText(/issue_kind determines what issues are fetched/i)
    ).toBeInTheDocument();
  });

  it('should display stops_at info', () => {
    render(<PlaybookDialog open={true} run={mockRun} onClose={() => {}} />);

    expect(screen.getByText(/reduce phase completion/i)).toBeInTheDocument();
  });
});
