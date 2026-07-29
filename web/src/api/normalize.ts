/**
 * Normalization layer: engine → UI mappings.
 * Maps engine values (snake_case, engine semantics) to UI values (kebab-case, prototype shapes).
 */

import type { RunDetail } from './client';

export type RunContext = {
  label: string;
  value: string;
}[];

export type PlaybookInfo = {
  name: string;
  summary: string;
  context_note: string;
  stops_at: string;
};

/**
 * Playbook descriptive copy (UI content, not run data).
 * This is the human-readable copy shown in PlaybookDialog.
 */
export const PLAYBOOK_CONTENT: Record<string, PlaybookInfo> = {
  example: {
    name: 'example',
    summary: 'Echo playbook for testing and demos',
    context_note: 'issue_kind determines what issues are fetched',
    stops_at: 'reduce phase completion',
  },
  mechanic: {
    name: 'mechanic',
    summary: 'Automated test suite investigation and triage',
    context_note: 'base is the codebase ref; suite is the test target',
    stops_at: 'diff published or all tests pass',
  },
  rigger: {
    name: 'rigger',
    summary: 'Model/metric performance regression investigation',
    context_note: 'model is the ML model; metric is the performance indicator',
    stops_at: 'root cause identified with mitigation plan',
  },
  medic: {
    name: 'medic',
    summary: 'Production incident investigation and remediation',
    context_note: 'incident is the SEV/alert; service is the affected system',
    stops_at: 'service restored and root cause documented',
  },
};

/**
 * Derive playbook-specific context from run config.
 * mechanic → base + suite
 * rigger → model + metric
 * medic → incident + service
 */
export function deriveContext(run: RunDetail): RunContext {
  const { playbook, config } = run;

  switch (playbook) {
    case 'example':
      return [
        { label: 'issue_kind', value: config.issue_kind || 'bug' },
      ];
    case 'mechanic':
      return [
        { label: 'base', value: config.base || 'unknown' },
        { label: 'suite', value: config.suite || 'unknown' },
      ];
    case 'rigger':
      return [
        { label: 'model', value: config.model || 'unknown' },
        { label: 'metric', value: config.metric || 'unknown' },
      ];
    case 'medic':
      return [
        { label: 'incident', value: config.incident || 'unknown' },
        { label: 'service', value: config.service || 'unknown' },
      ];
    default:
      return [];
  }
}

/**
 * Normalize ticket state: needs_human (engine) ↔ needs-human (UI)
 */
export function normalizeTicketState(engineState: string): string {
  return engineState.replace(/_/g, '-');
}

/**
 * Denormalize ticket state: needs-human (UI) ↔ needs_human (engine)
 */
export function denormalizeTicketState(uiState: string): string {
  return uiState.replace(/-/g, '_');
}
