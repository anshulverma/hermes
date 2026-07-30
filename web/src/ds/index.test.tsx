import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import * as DS from './index';

describe('Design System Components', () => {
  it('should export all DS components', () => {
    // Check that all expected components are exported
    expect(DS.Badge).toBeDefined();
    expect(DS.Button).toBeDefined();
    expect(DS.Card).toBeDefined();
    expect(DS.Divider).toBeDefined();
    expect(DS.IconButton).toBeDefined();
    expect(DS.Table).toBeDefined();
    expect(DS.Dialog).toBeDefined();
    expect(DS.EmptyState).toBeDefined();
    expect(DS.Tooltip).toBeDefined();
    expect(DS.AttentionBanner).toBeDefined();
    expect(DS.CrewBackdrop).toBeDefined();
    expect(DS.CrewRow).toBeDefined();
    expect(DS.Drawer).toBeDefined();
    expect(DS.EventRow).toBeDefined();
    expect(DS.HealthBadge).toBeDefined();
    expect(DS.KanbanColumn).toBeDefined();
    expect(DS.StatTile).toBeDefined();
    expect(DS.StatusPill).toBeDefined();
    expect(DS.TicketCard).toBeDefined();
    expect(DS.Checkbox).toBeDefined();
    expect(DS.Input).toBeDefined();
    expect(DS.Select).toBeDefined();
    expect(DS.Switch).toBeDefined();
    expect(DS.Header).toBeDefined();
    expect(DS.Tabs).toBeDefined();
  });

  it('should render Badge without crashing', () => {
    const { container } = render(<DS.Badge>Test</DS.Badge>);
    expect(container).toBeDefined();
  });

  it('should render Button without crashing', () => {
    const { container } = render(<DS.Button>Click me</DS.Button>);
    expect(container).toBeDefined();
  });

  it('should render Card without crashing', () => {
    const { container } = render(<DS.Card><div>Content</div></DS.Card>);
    expect(container).toBeDefined();
  });

  it('should render StatTile without crashing', () => {
    const { container } = render(<DS.StatTile label="Test" value="42" />);
    expect(container).toBeDefined();
  });

  it('should render StatusPill without crashing', () => {
    const { container } = render(<DS.StatusPill state="queued" label="Queued" />);
    expect(container).toBeDefined();
  });

  it('should render TicketCard without crashing', () => {
    const ticket = {
      id: 't-1',
      subject: 'Test ticket',
      phase: 'diagnose',
      attempts: 1,
      elapsed_s: 60,
      resource_req: 'cpu',
      host: 'test-host'
    };
    const { container } = render(<DS.TicketCard ticket={ticket} />);
    expect(container).toBeDefined();
  });

  it('should render KanbanColumn without crashing', () => {
    const { container } = render(
      <DS.KanbanColumn state="queued" count={5} tickets={[]} />
    );
    expect(container).toBeDefined();
  });

  it('should render CrewRow without crashing', () => {
    const member = {
      id: 'host-1',
      state: 'idle',
      resources: { gpu: 8, cpu: 96 },
      health: {
        reachable: true,
        agent_ok: true,
        auth_ok: true,
        workspace_ready: true,
        guard_installed: true,
        latency_ms: 41
      }
    };
    const { container } = render(<DS.CrewRow member={member} />);
    expect(container).toBeDefined();
  });

  it('should render HealthBadge without crashing', () => {
    const health = {
      reachable: true,
      agent_ok: true,
      auth_ok: true,
      workspace_ready: true,
      guard_installed: true,
      latency_ms: 41
    };
    const { container } = render(<DS.HealthBadge health={health} />);
    expect(container).toBeDefined();
  });

  it('should render EventRow without crashing', () => {
    const event = {
      ts: '2026-07-29T02:00:00Z',
      kind: 'result_recorded',
      message: 'Result recorded for ticket t-1'
    };
    const { container } = render(<DS.EventRow event={event} />);
    expect(container).toBeDefined();
  });

  it('should render AttentionBanner without crashing', () => {
    const { container } = render(
      <DS.AttentionBanner kind="warning">Test warning</DS.AttentionBanner>
    );
    expect(container).toBeDefined();
  });

  it('should render Drawer without crashing', () => {
    const { container } = render(
      <DS.Drawer open={false} onClose={() => {}}>
        <div>Content</div>
      </DS.Drawer>
    );
    expect(container).toBeDefined();
  });

  it('should render Dialog without crashing', () => {
    const { container } = render(
      <DS.Dialog open={false} onClose={() => {}}>
        <div>Content</div>
      </DS.Dialog>
    );
    expect(container).toBeDefined();
  });

  it('should render Table without crashing', () => {
    const { container } = render(
      <DS.Table>
        <thead>
          <tr><th>Header</th></tr>
        </thead>
        <tbody>
          <tr><td>Cell</td></tr>
        </tbody>
      </DS.Table>
    );
    expect(container).toBeDefined();
  });

  it('should render Tabs without crashing', () => {
    const tabs = [
      { id: 'tab1', label: 'Tab 1', content: <div>Content 1</div> }
    ];
    const { container } = render(<DS.Tabs tabs={tabs} activeTab="tab1" />);
    expect(container).toBeDefined();
  });

  it('should render EmptyState without crashing', () => {
    const { container } = render(
      <DS.EmptyState title="No data" message="Nothing to show" />
    );
    expect(container).toBeDefined();
  });

  it('should render Input without crashing', () => {
    const { container } = render(<DS.Input placeholder="Enter text" />);
    expect(container).toBeDefined();
  });

  it('should render Tooltip without crashing', () => {
    const { container } = render(
      <DS.Tooltip label="Tooltip text">
        <button>Hover me</button>
      </DS.Tooltip>
    );
    expect(container).toBeDefined();
  });

  it('should render IconButton without crashing', () => {
    const { container } = render(<DS.IconButton icon="x" />);
    expect(container).toBeDefined();
  });

  it('should render Checkbox without crashing', () => {
    const { container } = render(<DS.Checkbox checked={false} onChange={() => {}} />);
    expect(container).toBeDefined();
  });

  it('should render Switch without crashing', () => {
    const { container } = render(<DS.Switch checked={false} onChange={() => {}} />);
    expect(container).toBeDefined();
  });

  it('should render Select without crashing', () => {
    const options = [{ value: '1', label: 'Option 1' }];
    const { container } = render(<DS.Select options={options} value="1" />);
    expect(container).toBeDefined();
  });

  it('should render Header without crashing', () => {
    const { container } = render(<DS.Header title="Test Header" />);
    expect(container).toBeDefined();
  });

  it('should render CrewBackdrop without crashing', () => {
    const { container } = render(<DS.CrewBackdrop theme="grid" />);
    expect(container).toBeDefined();
  });
});
