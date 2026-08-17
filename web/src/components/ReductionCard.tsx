/**
 * ReductionCard — one reduction, leading with what it concluded.
 *
 * A reduction document mixes what the agent was given with what it returned,
 * and the given part is much the larger: an item's context ran to 800 lines of
 * material hermes had itself assembled. Rendering the document in key order put
 * that first and the conclusion below the fold, so the card was a wall of text
 * that taught the reader nothing.
 *
 * So the card is ordered by what it is worth reading first: a headline, a short
 * status line, then the conclusion itself clamped to a glance. The inputs, the
 * member tickets and the raw document are real but secondary, and sit together
 * behind one disclosure.
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
import { reductionHeadline, reductionFacts, splitProse } from '../util/reduction';

type ReductionCardProps = {
  reduction: Reduction;
  /** Rendered at the foot of the card when the reduction can be acted on. */
  actions?: ReactNode;
};

export default function ReductionCard({ reduction, actions }: ReductionCardProps) {
  const status = deriveFindingStatus(reduction);
  const facts = reductionFacts(reduction.json);
  const { primary, secondary } = splitProse(reduction.json, reduction.kind);

  return (
    <Card padding="md">
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6, minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <Badge size="sm" variant="outline">
            {reduction.kind}
          </Badge>
          {/* The scalars, inline: what happened, in a line rather than a block. */}
          {facts.slice(0, 4).map((f) => (
            <span key={f.key} style={{ fontSize: 11, color: 'var(--text-muted)' }}>
              <span style={{ fontFamily: 'var(--font-mono)' }}>{f.key}</span>{' '}
              <span style={{ color: 'var(--text-secondary)' }}>{f.value}</span>
            </span>
          ))}
          <span
            style={{
              marginLeft: 'auto',
              fontFamily: 'var(--font-mono)',
              fontSize: 11,
              color: 'var(--text-muted)',
            }}
          >
            #{reduction.id}
          </span>
          {/* A decision that was actually made is information; `pending` on
              every card is not — it only means nobody has decided anything,
              which for an output is the permanent and uninteresting case. */}
          {reduction.review_state !== 'pending' && (
            <StatusPill state={reduction.review_state} size="sm" />
          )}
          {status !== reduction.review_state && <StatusPill state={status} size="sm" />}
        </div>

        {/* Derived: reductions carry no `title`, so rendering that key alone
            gave every card the same "Untitled reduction". */}
        <span style={{ color: 'var(--text-primary)', fontSize: 16, lineHeight: '22px' }}>
          {reductionHeadline(reduction.json, reduction.kind)}
        </span>

      </div>

      {/* What the run concluded — the only thing above the fold. */}
      {primary.map((p) => (
        <div key={p.path} style={{ marginTop: 12 }}>
          {primary.length > 1 && (
            <span
              style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)' }}
            >
              {p.path}
            </span>
          )}
          <div
            style={{
              marginTop: 4,
              padding: 10,
              background: 'var(--wash-subtle)',
              border: '1px solid var(--border-hairline)',
              borderRadius: 'var(--radius-sm)',
            }}
          >
            {/* Clamped short: a card is a glance, and the whole thing is one
                click away. Clamped rather than scrolled, so it does not take
                the wheel from the page. */}
            <Clamp
              text={p.text}
              lines={10}
              height={200}
              data-testid={`finding-prose-${reduction.id}`}
            >
              <Markdown maxHeight={null} fontSize={12}>
                {p.text}
              </Markdown>
            </Clamp>
          </div>
        </div>
      ))}

      {/* Everything the reader did not come for: the material the agent was
          given, the tickets rolled up, and the document as banked. One
          disclosure, mounted only when opened. */}
      <details style={{ marginTop: 12 }}>
        <summary style={{ cursor: 'pointer', fontSize: 12, color: 'var(--text-muted)' }}>
          {secondary.length > 0 ? 'Inputs, tickets and raw document' : 'Tickets and raw document'}
        </summary>

        {secondary.map((p) => (
          <div key={p.path} style={{ marginTop: 8 }}>
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
              <Clamp text={p.text} lines={10} height={200}>
                <Markdown maxHeight={null} fontSize={12}>
                  {p.text}
                </Markdown>
              </Clamp>
            </div>
          </div>
        ))}

        <div style={{ marginTop: 8 }}>
          <JsonView value={reduction.json} maxHeight={null} />
        </div>
      </details>

      {reduction.member_tickets.length > 0 && (
        <>
          <Divider style={{ margin: '12px 0' }} />
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
