import * as DS from '../ds';

function Gallery() {
  return (
    <div style={{ padding: 'var(--space-6)', maxWidth: 1400, margin: '0 auto' }}>
      <h1 style={{
        fontSize: 'var(--text-3xl-size)',
        fontWeight: 600,
        marginBottom: 'var(--space-8)',
        color: 'var(--text-primary)'
      }}>
        Hermes Design System Gallery
      </h1>

      <section style={{ marginBottom: 'var(--space-8)' }}>
        <h2 style={{
          fontSize: 'var(--text-xl-size)',
          fontWeight: 600,
          marginBottom: 'var(--space-4)',
          color: 'var(--text-primary)'
        }}>
          Core Components
        </h2>

        <DS.Card style={{ marginBottom: 'var(--space-4)' }}>
          <h3 style={{ fontSize: 'var(--text-lg-size)', fontWeight: 500, marginBottom: 'var(--space-3)' }}>
            Badges
          </h3>
          <div style={{ display: 'flex', gap: 'var(--space-3)', flexWrap: 'wrap' }}>
            <DS.Badge>Default</DS.Badge>
            <DS.Badge variant="outline">Outline</DS.Badge>
            <DS.Badge variant="solid">Solid</DS.Badge>
            <DS.Badge tone="live">Live</DS.Badge>
            <DS.Badge tone="ok">OK</DS.Badge>
            <DS.Badge tone="attention">Attention</DS.Badge>
            <DS.Badge tone="danger">Danger</DS.Badge>
            <DS.Badge size="sm">Small</DS.Badge>
          </div>
        </DS.Card>

        <DS.Card style={{ marginBottom: 'var(--space-4)' }}>
          <h3 style={{ fontSize: 'var(--text-lg-size)', fontWeight: 500, marginBottom: 'var(--space-3)' }}>
            Buttons
          </h3>
          <div style={{ display: 'flex', gap: 'var(--space-3)', flexWrap: 'wrap' }}>
            <DS.Button variant="primary">Primary</DS.Button>
            <DS.Button variant="secondary">Secondary</DS.Button>
            <DS.Button variant="ghost">Ghost</DS.Button>
            <DS.Button variant="danger">Danger</DS.Button>
            <DS.Button size="sm">Small</DS.Button>
            <DS.Button size="lg">Large</DS.Button>
            <DS.Button disabled>Disabled</DS.Button>
          </div>
        </DS.Card>

        <DS.Card style={{ marginBottom: 'var(--space-4)' }}>
          <h3 style={{ fontSize: 'var(--text-lg-size)', fontWeight: 500, marginBottom: 'var(--space-3)' }}>
            Icon Buttons
          </h3>
          <div style={{ display: 'flex', gap: 'var(--space-3)', flexWrap: 'wrap' }}>
            <DS.IconButton icon="play" />
            <DS.IconButton icon="pause" />
            <DS.IconButton icon="stop" />
            <DS.IconButton icon="trash" variant="danger" />
            <DS.IconButton icon="settings" size="sm" />
          </div>
        </DS.Card>
      </section>

      <section style={{ marginBottom: 'var(--space-8)' }}>
        <h2 style={{
          fontSize: 'var(--text-xl-size)',
          fontWeight: 600,
          marginBottom: 'var(--space-4)',
          color: 'var(--text-primary)'
        }}>
          Foreman Components
        </h2>

        <DS.Card style={{ marginBottom: 'var(--space-4)' }}>
          <h3 style={{ fontSize: 'var(--text-lg-size)', fontWeight: 500, marginBottom: 'var(--space-3)' }}>
            Status Pills
          </h3>
          <div style={{ display: 'flex', gap: 'var(--space-3)', flexWrap: 'wrap' }}>
            <DS.StatusPill state="queued" label="Queued" />
            <DS.StatusPill state="running" label="Running" />
            <DS.StatusPill state="done" label="Done" />
            <DS.StatusPill state="failed" label="Failed" />
            <DS.StatusPill state="parked" label="Parked" />
            <DS.StatusPill state="needs-human" label="Needs Human" />
            <DS.StatusPill state="idle" label="Idle" size="sm" />
          </div>
        </DS.Card>

        <DS.Card style={{ marginBottom: 'var(--space-4)' }}>
          <h3 style={{ fontSize: 'var(--text-lg-size)', fontWeight: 500, marginBottom: 'var(--space-3)' }}>
            Stat Tiles
          </h3>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 'var(--space-3)' }}>
            <DS.StatTile label="Total Tickets" value="214" />
            <DS.StatTile label="Completed" value="96" trend="up" delta="+12" />
            <DS.StatTile label="Running" value="12" trend="neutral" />
            <DS.StatTile label="Failed" value="3" trend="down" delta="-1" />
          </div>
        </DS.Card>

        <DS.Card style={{ marginBottom: 'var(--space-4)' }}>
          <h3 style={{ fontSize: 'var(--text-lg-size)', fontWeight: 500, marginBottom: 'var(--space-3)' }}>
            Ticket Card
          </h3>
          <DS.TicketCard
            ticket={{
              id: 't-1207',
              subject: 'fbcode//foo:bar - testBaz',
              phase: 'diagnose',
              attempts: 1,
              elapsed_s: 83,
              resource_req: 'gpu',
              host: 'devgpu042'
            }}
          />
        </DS.Card>

        <DS.Card style={{ marginBottom: 'var(--space-4)' }}>
          <h3 style={{ fontSize: 'var(--text-lg-size)', fontWeight: 500, marginBottom: 'var(--space-3)' }}>
            Health Badge
          </h3>
          <DS.HealthBadge
            health={{
              reachable: true,
              agent_ok: true,
              auth_ok: true,
              workspace_ready: true,
              guard_installed: true,
              latency_ms: 41
            }}
          />
        </DS.Card>

        <DS.Card style={{ marginBottom: 'var(--space-4)' }}>
          <h3 style={{ fontSize: 'var(--text-lg-size)', fontWeight: 500, marginBottom: 'var(--space-3)' }}>
            Crew Row
          </h3>
          <DS.CrewRow
            member={{
              id: 'devgpu042',
              state: 'busy',
              resources: { gpu: 8, cpu: 96 },
              current_ticket: 't-1207',
              health: {
                reachable: true,
                agent_ok: true,
                auth_ok: true,
                workspace_ready: true,
                guard_installed: true,
                latency_ms: 41
              },
              throughput_per_min: 0.7,
              last_heartbeat: '3s ago'
            }}
          />
        </DS.Card>

        <DS.Card style={{ marginBottom: 'var(--space-4)' }}>
          <h3 style={{ fontSize: 'var(--text-lg-size)', fontWeight: 500, marginBottom: 'var(--space-3)' }}>
            Event Row
          </h3>
          <DS.EventRow
            event={{
              ts: '2026-07-29T02:27:00Z',
              kind: 'result_recorded',
              message: 'Result recorded for ticket t-1207',
              host: 'devgpu042',
              ticket_id: 't-1207'
            }}
          />
        </DS.Card>

        <DS.Card style={{ marginBottom: 'var(--space-4)' }}>
          <h3 style={{ fontSize: 'var(--text-lg-size)', fontWeight: 500, marginBottom: 'var(--space-3)' }}>
            Attention Banner
          </h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
            <DS.AttentionBanner kind="info">
              Run is progressing normally. 96/214 tickets complete.
            </DS.AttentionBanner>
            <DS.AttentionBanner kind="warning">
              Parked ticket ratio exceeds 50%. Review needed.
            </DS.AttentionBanner>
            <DS.AttentionBanner kind="error">
              All crew members are down. Check network connectivity.
            </DS.AttentionBanner>
          </div>
        </DS.Card>

        <DS.Card style={{ marginBottom: 'var(--space-4)' }}>
          <h3 style={{ fontSize: 'var(--text-lg-size)', fontWeight: 500, marginBottom: 'var(--space-3)' }}>
            Kanban Column (empty)
          </h3>
          <DS.KanbanColumn state="queued" count={0} tickets={[]} />
        </DS.Card>
      </section>

      <section style={{ marginBottom: 'var(--space-8)' }}>
        <h2 style={{
          fontSize: 'var(--text-xl-size)',
          fontWeight: 600,
          marginBottom: 'var(--space-4)',
          color: 'var(--text-primary)'
        }}>
          Form Components
        </h2>

        <DS.Card style={{ marginBottom: 'var(--space-4)' }}>
          <h3 style={{ fontSize: 'var(--text-lg-size)', fontWeight: 500, marginBottom: 'var(--space-3)' }}>
            Input
          </h3>
          <DS.Input placeholder="Enter text..." />
        </DS.Card>

        <DS.Card style={{ marginBottom: 'var(--space-4)' }}>
          <h3 style={{ fontSize: 'var(--text-lg-size)', fontWeight: 500, marginBottom: 'var(--space-3)' }}>
            Select
          </h3>
          <DS.Select
            options={[
              { value: 'mechanic', label: 'Mechanic' },
              { value: 'rigger', label: 'Rigger' },
              { value: 'medic', label: 'Medic' }
            ]}
            value="mechanic"
          />
        </DS.Card>

        <DS.Card style={{ marginBottom: 'var(--space-4)' }}>
          <h3 style={{ fontSize: 'var(--text-lg-size)', fontWeight: 500, marginBottom: 'var(--space-3)' }}>
            Checkbox
          </h3>
          <DS.Checkbox checked={true} onChange={() => {}} label="Enable feature" />
        </DS.Card>

        <DS.Card style={{ marginBottom: 'var(--space-4)' }}>
          <h3 style={{ fontSize: 'var(--text-lg-size)', fontWeight: 500, marginBottom: 'var(--space-3)' }}>
            Switch
          </h3>
          <DS.Switch checked={true} onChange={() => {}} label="Auto-refresh" />
        </DS.Card>
      </section>

      <section style={{ marginBottom: 'var(--space-8)' }}>
        <h2 style={{
          fontSize: 'var(--text-xl-size)',
          fontWeight: 600,
          marginBottom: 'var(--space-4)',
          color: 'var(--text-primary)'
        }}>
          Feedback Components
        </h2>

        <DS.Card style={{ marginBottom: 'var(--space-4)' }}>
          <h3 style={{ fontSize: 'var(--text-lg-size)', fontWeight: 500, marginBottom: 'var(--space-3)' }}>
            Empty State
          </h3>
          <DS.EmptyState
            title="No tickets yet"
            message="Start a run to see tickets appear here"
            icon="inbox"
          />
        </DS.Card>

        <DS.Card style={{ marginBottom: 'var(--space-4)' }}>
          <h3 style={{ fontSize: 'var(--text-lg-size)', fontWeight: 500, marginBottom: 'var(--space-3)' }}>
            Tooltip
          </h3>
          <DS.Tooltip content="This is a helpful tooltip">
            <DS.Button>Hover me</DS.Button>
          </DS.Tooltip>
        </DS.Card>
      </section>

      <section style={{ marginBottom: 'var(--space-8)' }}>
        <h2 style={{
          fontSize: 'var(--text-xl-size)',
          fontWeight: 600,
          marginBottom: 'var(--space-4)',
          color: 'var(--text-primary)'
        }}>
          Data Components
        </h2>

        <DS.Card style={{ marginBottom: 'var(--space-4)' }}>
          <h3 style={{ fontSize: 'var(--text-lg-size)', fontWeight: 500, marginBottom: 'var(--space-3)' }}>
            Table
          </h3>
          <DS.Table>
            <thead>
              <tr>
                <th>ID</th>
                <th>State</th>
                <th>Phase</th>
                <th>Host</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>t-1207</td>
                <td><DS.StatusPill state="running" label="Running" size="sm" /></td>
                <td>diagnose</td>
                <td>devgpu042</td>
              </tr>
              <tr>
                <td>t-1208</td>
                <td><DS.StatusPill state="queued" label="Queued" size="sm" /></td>
                <td>-</td>
                <td>-</td>
              </tr>
            </tbody>
          </DS.Table>
        </DS.Card>

        <DS.Card style={{ marginBottom: 'var(--space-4)' }}>
          <h3 style={{ fontSize: 'var(--text-lg-size)', fontWeight: 500, marginBottom: 'var(--space-3)' }}>
            Tabs
          </h3>
          <DS.Tabs
            tabs={[
              { id: 'overview', label: 'Overview', content: <div style={{ padding: 'var(--space-4)' }}>Overview content</div> },
              { id: 'details', label: 'Details', content: <div style={{ padding: 'var(--space-4)' }}>Details content</div> },
              { id: 'logs', label: 'Logs', content: <div style={{ padding: 'var(--space-4)' }}>Logs content</div> }
            ]}
            activeTab="overview"
          />
        </DS.Card>
      </section>

      <section style={{ marginBottom: 'var(--space-8)' }}>
        <h2 style={{
          fontSize: 'var(--text-xl-size)',
          fontWeight: 600,
          marginBottom: 'var(--space-4)',
          color: 'var(--text-primary)'
        }}>
          Layout Components
        </h2>

        <DS.Card style={{ marginBottom: 'var(--space-4)' }}>
          <h3 style={{ fontSize: 'var(--text-lg-size)', fontWeight: 500, marginBottom: 'var(--space-3)' }}>
            Header
          </h3>
          <DS.Header
            title="Hermes Control Plane"
            subtitle="Orchestrating headless agents across fleet"
          />
        </DS.Card>

        <DS.Card style={{ marginBottom: 'var(--space-4)' }}>
          <h3 style={{ fontSize: 'var(--text-lg-size)', fontWeight: 500, marginBottom: 'var(--space-3)' }}>
            Divider
          </h3>
          <div>
            <p>Content above divider</p>
            <DS.Divider />
            <p>Content below divider</p>
          </div>
        </DS.Card>

        <DS.Card style={{ marginBottom: 'var(--space-4)' }}>
          <h3 style={{ fontSize: 'var(--text-lg-size)', fontWeight: 500, marginBottom: 'var(--space-3)' }}>
            Crew Backdrop
          </h3>
          <div style={{ position: 'relative', height: 200, overflow: 'hidden' }}>
            <DS.CrewBackdrop theme="grid" />
          </div>
        </DS.Card>
      </section>

      <section style={{ marginBottom: 'var(--space-8)' }}>
        <h2 style={{
          fontSize: 'var(--text-xl-size)',
          fontWeight: 600,
          marginBottom: 'var(--space-4)',
          color: 'var(--text-primary)'
        }}>
          Note
        </h2>
        <DS.Card>
          <p style={{ color: 'var(--text-secondary)' }}>
            Modal components (Dialog, Drawer) are not shown in open state here to avoid blocking the gallery.
            They render without crashing and are tested in the test suite.
          </p>
        </DS.Card>
      </section>
    </div>
  );
}

export default Gallery;
