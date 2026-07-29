(function () {
  var SUBJECTS = [
    'core//search/index:index_test - testShardRotation',
    'core//net/rpc:client_test - testRetryBackoff',
    'core//store/kv:compaction_test - testTombstones',
    'core//auth/session:session_test - testExpiry',
    'core//ml/loader:batch_test - testPrefetchStall',
    'core//api/gateway:limit_test - testBurstWindow',
    'core//store/wal:replay_test - testTornWrite',
    'core//ml/train:sched_test - testGpuAffinity',
    'core//net/dns:resolve_test - testNegativeCache',
    'core//search/rank:score_test - testTieBreak',
  ];
  var PHASES = ['diagnose', 'reduce', 'fix'];
  var HOSTS = ['node-a11', 'node-a12', 'node-b04', 'gpu-c07', 'gpu-c08', 'node-d21'];
  var STATES = ['queued', 'dispatched', 'running', 'reducing', 'done', 'parked', 'failed', 'needs-human'];

  function ticket(i, state) {
    var gpu = i % 3 === 0;
    return {
      id: 't-' + (1100 + i),
      run_id: 'r-4821',
      state: state,
      phase: PHASES[i % PHASES.length],
      subject: SUBJECTS[i % SUBJECTS.length],
      resource_req: gpu ? 'gpu' : 'cpu',
      host: state === 'queued' ? null : HOSTS[i % HOSTS.length],
      attempts: (i % 3) + 1,
      elapsed_s: 18 + ((i * 37) % 900),
      priority: 20 + ((i * 13) % 78),
    };
  }

  var tickets = [];
  var perState = { queued: 6, dispatched: 3, running: 5, reducing: 2, done: 6, parked: 4, failed: 2, 'needs-human': 2 };
  var n = 0;
  STATES.forEach(function (st) {
    for (var i = 0; i < perState[st]; i++) tickets.push(ticket(n++, st));
  });

  // Run context is playbook-dependent: what identifies a run differs by job type.
  // mechanic pins every worker to one commit; rigger pins a model + metric; medic pins an incident.
  var PLAYBOOK_CONTEXT = {
    mechanic: [{ label: 'base', value: 'a1b2c3d' }, { label: 'suite', value: 'core//search/...' }],
    rigger: [{ label: 'model', value: 'ranker-v7' }, { label: 'metric', value: 'tokens/s' }],
    medic: [{ label: 'incident', value: 'sev-2214' }, { label: 'service', value: 'api-gateway' }],
  };

  var PLAYBOOKS = {
    mechanic: {
      name: 'mechanic',
      summary: 'Diagnoses and fixes large batches of failing or flaky tests.',
      phases: ['diagnose', 'reduce', 'fix'],
      stops_at: 'A proposed diff per root cause. Nothing lands without a human review.',
      context_note: 'Every crew member works the same base revision, so results are comparable across hosts.',
    },
    rigger: {
      name: 'rigger',
      summary: 'Iteratively optimizes a metric, e.g. model training efficiency.',
      phases: ['baseline', 'sweep', 'confirm'],
      stops_at: 'A ranked set of changes with measured deltas against the baseline.',
      context_note: 'Runs are pinned to a model and the metric being moved, not to a commit.',
    },
    medic: {
      name: 'medic',
      summary: 'Root-causes a production incident.',
      phases: ['triage', 'correlate', 'root-cause'],
      stops_at: 'A root-cause writeup with evidence links. Mitigation stays with the on-call.',
      context_note: 'Runs are pinned to an incident and the affected service.',
    },
  };

  window.HERMES = {
    playbookContext: PLAYBOOK_CONTEXT,
    playbooks: PLAYBOOKS,
    run: {
      id: 'r-4821', playbook: 'mechanic', site: 'primary', base_ref: 'a1b2c3d',
      state: 'running', phase: 'diagnose', started_at: '1h 42m ago',
      context: PLAYBOOK_CONTEXT.mechanic,
      tickets: { total: 214, done: 96, running: 12, parked: 8, failed: 3, queued: 95 },
      eta: '~1h 55m remaining',
    },
    phases: [
      { name: 'diagnose', state: 'running', share: 46 },
      { name: 'reduce', state: 'queued', share: 34 },
      { name: 'fix', state: 'queued', share: 20 },
    ],
    tickets: tickets,
    states: STATES,
    crew: [
      { id: 'gpu-c07', mem_gb: 512, util: { cpu: 78, gpu: 88, mem: 72 }, errors: 1, error_rate: 2.9, site: 'primary', state: 'busy', resources: { gpu: 8, cpu: 96 }, current_ticket: 't-1207', throughput_per_min: 0.3, last_heartbeat: '3s ago', health: { reachable: true, agent_ok: true, auth_ok: true, workspace_ready: true, guard_installed: true, latency_ms: 41 } },
      { id: 'gpu-c08', mem_gb: 512, util: { cpu: 74, gpu: 88, mem: 69 }, errors: 0, error_rate: 0, site: 'primary', state: 'busy', resources: { gpu: 8, cpu: 96 }, current_ticket: 't-1211', throughput_per_min: 0.2, last_heartbeat: '4s ago', health: { reachable: true, agent_ok: true, auth_ok: true, workspace_ready: true, guard_installed: true, latency_ms: 38 } },
      { id: 'node-a11', mem_gb: 256, util: { cpu: 6, gpu: 0, mem: 11 }, errors: 0, error_rate: 0, site: 'primary', state: 'idle', resources: { cpu: 64 }, current_ticket: null, throughput_per_min: 0, last_heartbeat: '2s ago', health: { reachable: true, agent_ok: true, auth_ok: true, workspace_ready: true, guard_installed: true, latency_ms: 12 } },
      { id: 'node-a12', mem_gb: 256, util: { cpu: 41, gpu: 0, mem: 38 }, errors: 1, error_rate: 5.6, site: 'primary', state: 'draining', resources: { cpu: 64 }, current_ticket: 't-1188', throughput_per_min: 0.2, last_heartbeat: '5s ago', health: { reachable: true, agent_ok: true, auth_ok: true, workspace_ready: true, guard_installed: false, latency_ms: 19 } },
      { id: 'node-b04', mem_gb: 256, util: { cpu: 0, gpu: 0, mem: 0 }, errors: 1, error_rate: 14.3, site: 'secondary', state: 'down', resources: { cpu: 32 }, current_ticket: null, throughput_per_min: 0, last_heartbeat: '4m 12s ago', health: { reachable: false, agent_ok: false, auth_ok: true, workspace_ready: true, guard_installed: true, latency_ms: 0 } },
      { id: 'node-d21', mem_gb: 256, util: { cpu: 64, gpu: 0, mem: 52 }, errors: 0, error_rate: 0, site: 'secondary', state: 'busy', resources: { cpu: 48 }, current_ticket: 't-1194', throughput_per_min: 0.2, last_heartbeat: '1s ago', health: { reachable: true, agent_ok: true, auth_ok: true, workspace_ready: true, guard_installed: true, latency_ms: 67 } },
    ],
    findings: [
      { id: 'f-31', kind: 'root_cause', title: 'Shared fixture leaks a temp dir between shards', category: 'test isolation', member_ticket_ids: ['t-1100', 't-1104', 't-1112', 't-1119', 't-1127'], fix_state: 'diff_published', diff_url: '#' },
      { id: 'f-32', kind: 'root_cause', title: 'Retry backoff races the 500ms client deadline', category: 'flaky timing', member_ticket_ids: ['t-1101', 't-1108', 't-1131'], fix_state: 'proposed', diff_url: '#' },
      { id: 'f-33', kind: 'root_cause', title: 'GPU affinity pin ignored when 2 leases land on one host', category: 'resource', member_ticket_ids: ['t-1106', 't-1122'], fix_state: 'needs_human', diff_url: '#' },
    ],
    events: [
      { ts: '19:44:02', kind: 'host_down', host: 'node-b04', message: 'No heartbeat in 4m — 2 tickets requeued', severity: 'critical' },
      { ts: '19:43:58', kind: 'result_recorded', host: 'gpu-c07', ticket_id: 't-1207', message: 'Reduction matched finding f-31' },
      { ts: '19:43:41', kind: 'phase_advanced', host: null, ticket_id: 't-1188', message: 'diagnose to reduce' },
      { ts: '19:43:22', kind: 'lease_acquired', host: 'gpu-c08', ticket_id: 't-1211', message: 'gpu lease, ttl 90m' },
      { ts: '19:43:04', kind: 'ticket_claimed', host: 'node-d21', ticket_id: 't-1194', message: 'Claimed at priority 74' },
      { ts: '19:42:47', kind: 'result_recorded', host: 'node-a12', ticket_id: 't-1188', message: 'Strict result: reproduced in 2 of 3 attempts' },
      { ts: '19:42:11', kind: 'ticket_claimed', host: 'gpu-c07', ticket_id: 't-1207', message: 'Claimed at priority 57' },
      { ts: '19:41:55', kind: 'lease_released', host: 'gpu-c08', ticket_id: 't-1180', message: 'gpu lease released after 41m' },
    ],
    leases: [
      { id: 'l-9', resource_class: 'gpu', holder_ticket: 't-1207', host: 'gpu-c07', ttl_s: 5400 },
      { id: 'l-10', resource_class: 'gpu', holder_ticket: 't-1211', host: 'gpu-c08', ttl_s: 4980 },
    ],
    metrics: {
      // 24 five-minute buckets = last 2h
      throughput: [0.4,0.5,0.6,0.7,0.7,0.8,0.9,1.0,0.8,1.0,1.1,1.0,0.9,1.1,1.2,1.1,0.9,0.7,0.9,1.0,1.1,1.0,0.9,0.9],
      done_cum:   [2,4,7,10,14,18,23,28,32,37,43,48,53,58,64,70,75,79,84,88,91,93,95,96],
      failed_cum: [0,0,0,0,0,1,1,1,1,1,1,2,2,2,2,2,2,3,3,3,3,3,3,3],
      error_rate: [0,0,0,0,0,5.3,4.2,3.5,3.0,2.6,2.3,4.0,3.6,3.3,3.0,2.8,2.6,3.7,3.5,3.3,3.2,3.1,3.0,3.0],
      crew_online:[6,6,6,6,6,6,6,5,5,6,6,6,6,6,6,6,5,4,4,5,5,5,5,5],
      bucket_labels: ['-2h','-90m','-60m','-30m','now'],
      burn_rate_gpu_h: 14,
      burn_rate_cpu_h: 212,
      gpu_hours_used: 23.8,
      gpu_hours_budget: 120,
      cpu_hours_used: 360,
      cpu_hours_budget: 2400,
      cost_per_ticket: '14m gpu · 3.6 core-h cpu',
      results: 99,
      failed: 3,
      mean_time_to_result: '6m 12s',
      retry_rate: 14,
      drain_eta: '~1h 55m',
      agent: {
        tokens_in: 61400000,
        tokens_out: 8900000,
        cache_read: 214300000,
        tokens_per_min: 690000,
        spend_usd: 386.4,
        budget_usd: 1000,
        cost_per_ticket_usd: 3.9,
        cost_per_finding_usd: 128.8,
        // per 5m bucket, last 2h
        tokens: [1.2,1.6,1.9,2.3,2.2,2.6,3.0,3.2,2.8,3.4,3.7,3.3,3.0,3.5,3.9,3.6,3.1,2.4,2.9,3.4,3.7,3.3,3.1,3.2],
        spend_cum: [9.8,19.6,30.6,42.8,55,69.1,85.6,102.7,117.4,135.7,155.9,173.6,190.1,209.1,230.5,250.1,267.2,280.6,296.5,315.5,335.7,353.4,369.9,386.4],
        models: [
          { name: 'sonnet-4.5', share: 78, tokens: '54.9M', spend: 214.2, role: 'ticket agents' },
          { name: 'opus-4.1', share: 14, tokens: '9.8M', spend: 148.6, role: 'reductions' },
          { name: 'haiku-4', share: 8, tokens: '5.6M', spend: 23.6, role: 'log triage' },
        ],
        by_phase: [
          { name: 'diagnose', tokens: '38.2M', spend: 188.4, per_ticket: 1.6 },
          { name: 'reduce', tokens: '21.6M', spend: 122.7, per_ticket: 2.0 },
          { name: 'fix', tokens: '10.5M', spend: 75.3, per_ticket: 2.2 },
        ],
      },
      resources: {
        cpu: { used: 212, total: 400, unit: 'cores' },
        gpu: { used: 14, total: 16, unit: 'gpus' },
        mem: { used: 1180, total: 2048, unit: 'gb' },
        series: {
          cpu: [96,128,150,168,182,196,208,214,206,220,232,226,218,228,240,236,224,180,190,204,216,220,210,212],
          gpu: [4,6,8,9,10,11,12,13,12,13,14,14,13,14,15,15,14,10,11,12,13,14,13,14],
          mem: [420,560,660,730,800,860,920,980,940,1020,1090,1060,1010,1080,1160,1140,1080,820,880,960,1040,1120,1150,1180],
        },
      },
      phases: [
        { name: 'diagnose', tickets: 54, mean: '4m 48s', failure_pct: 1.9, gpu_h: 5.4 },
        { name: 'reduce', tickets: 29, mean: '7m 02s', failure_pct: 3.4, gpu_h: 3.4 },
        { name: 'fix', tickets: 16, mean: '9m 31s', failure_pct: 6.3, gpu_h: 2.1 },
      ],
    },
    logTail: [
      '[19:43:58] agent: reduced 3 candidate causes to 1',
      '[19:43:44] agent: reran target 3x with --stress=8',
      '[19:43:12] agent: parsed 1,204 lines of failure output',
      '[19:42:11] engine: payload delivered (2.1kb)',
    ],
  };
})();
