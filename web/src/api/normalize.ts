/**
 * Normalization layer: engine → UI mappings.
 * Maps engine values (snake_case, engine semantics) to UI values (kebab-case, prototype shapes).
 */

import type { RunDetail } from './client';

export type RunContext = {
  label: string;
  value: string;
}[];

/**
 * Derive playbook-specific context from run config.
 * mechanic → base + suite
 * rigger → model + metric
 * medic → incident + service
 */
export function deriveContext(run: RunDetail): RunContext {
  const { playbook, config } = run;

  switch (playbook) {
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
