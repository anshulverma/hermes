/**
 * ReductionCard — one reduction, read as a document.
 *
 * A reduction's `json` is whatever the playbook banked, so it is read
 * structurally rather than by key (see `util/reduction`): a derived headline,
 * the scalars that say what happened, the long string leaves rendered as the
 * markdown they were written as, and the whole document one disclosure away.
 *
 * Actions are a slot, not a fixture. The same card serves the outputs list,
 * where there is nothing to decide, and the review queue, where accepting or
 * rejecting settles a `needs_human` ticket.
 */

import type { ReactNode } from 'react';
import type { Reduction } from '../api/client';
import { deriveFindingStatus } from '../api/normalize';
import { Card, Badge, StatusPill, Divider } from '../ds';
import JsonView from './JsonView';
import Markdown from './Markdown';
import Clamp from './Clamp';
import { reductionHeadline, reductionFacts, reductionProse } from '../util/reduction';

type ReductionCardProps = {
  reduction: Reduction;
  /** Rendered at the foot of the card when the reduction can be acted on. */
  actions?: ReactNode;
};

export default function ReductionCard({ reduction, actions }: ReductionCardProps) {
  const status = deriveFindingStatus(reduction);
  const facts = reductionFacts(reduction.json);
  const prose = reductionProse(reduction.json);

  return (
    <Card padding="md">
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6, minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <span
            style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-muted)' }}
          >
            {reduction.id}
          </span>
          <Badge size="sm" variant="outline">
            {reduction.kind}
          </Badge>
          <Badge size="sm" variant="outline">
            {reduction.phase}
          </Badge>
          <StatusPill state={reduction.review_state} size="sm" />
          {status !== reduction.review_state && <StatusPill state={status} size="sm" />}
        </div>

        {/* Derived: reductions carry no `title`, so rendering that key alone
            gave every card the same "Untitled reduction". */}
        <span style={{ color: 'var(--text-primary)', fontSize: 16, lineHeight: '22px' }}>
          {reductionHeadline(reduction.json, reduction.kind)}
        </span>

        {facts.length > 0 && (
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
            {facts.map((f) => (
              <span key={f.key} style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                <span style={{ fontFamily: 'var(--font-mono)' }}>{f.key}</span>{' '}
                <span style={{ color: 'var(--text-secondary)' }}>{f.value}</span>
              </span>
            ))}
          </div>
        )}
      </div>

      {/* The content: the long string leaves, where the agent's analysis,
          synthesis or report actually lives. */}
      {prose.map((p) => (
        <div key={p.path} style={{ marginTop: 12 }}>
          <span
            style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)' }}
          >
            {p.path}
          </span>
          <div
            style={{
              marginTop: 4,
              padding: 10,
              background: 'var(--wash-subtle)',
              border: '1px solid var(--border-hairline)',
              borderRadius: 'var(--radius-sm)',
            }}
          >
            {/* Clamped, not scrolled: an 800-line input context must not bury
                the analysis under it, and a scroll box here would take the
                wheel from the page. */}
            <Clamp text={p.text} data-testid={`finding-prose-${reduction.id}`}>
              <Markdown maxHeight={null} fontSize={12}>
                {p.text}
              </Markdown>
            </Clamp>
          </div>
        </div>
      ))}

      <details style={{ marginTop: 12 }}>
        <summary style={{ cursor: 'pointer', fontSize: 12, color: 'var(--text-muted)' }}>
          Full document
        </summary>
        <div style={{ marginTop: 8 }}>
          <JsonView value={reduction.json} maxHeight={null} />
        </div>
      </details>

      {reduction.member_tickets.length > 0 && (
        <>
          <Divider style={{ margin: '16px 0 12px' }} />
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>
              {reduction.member_tickets.length}{' '}
              {reduction.member_tickets.length === 1 ? 'member ticket' : 'member tickets'}
            </span>
            {reduction.member_tickets.map((ticket) => (
              <div
                key={ticket.id}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 6,
                  padding: '2px 6px 2px 2px',
                  border: '1px solid var(--border-hairline)',
                  borderRadius: 'var(--radius-lg)',
                }}
              >
                <StatusPill state={ticket.state} size="sm" />
                <span
                  style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: 11,
                    color: 'var(--text-secondary)',
                  }}
                >
                  {ticket.id}
                </span>
              </div>
            ))}
          </div>
        </>
      )}

      {actions && (
        <>
          <Divider style={{ margin: '16px 0 12px' }} />
          <div style={{ display: 'flex', gap: 8 }}>{actions}</div>
        </>
      )}
    </Card>
  );
}
