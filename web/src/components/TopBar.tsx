/**
 * TopBar - the app header: the wordmark (a link to the default run), the pages
 * that are about every run, and the live indicator.
 *
 * Nothing here is about one run: the runs rail picks the run and the run pane
 * carries its tabs, so no item comes or goes as the run changes.
 */

import type { CSSProperties } from 'react';
import LiveDot from './LiveDot';
import type { Route } from '../hooks/useRoute';

/**
 * Height of the app chrome, in px.
 *
 * Overlays anchor below this. The content wrapper sets a z-index, which creates
 * a stacking context the drawer's own z-index cannot escape, so a drawer pinned
 * to top:0 renders UNDER this bar however high its z-index is. Offsetting by the
 * bar's height avoids the overlap entirely (and keeps the nav usable).
 */
export const TOPBAR_HEIGHT = 56;

/**
 * The Hermes mark: the favicon artwork, standing in for the leading "H".
 *
 * Inlined rather than an <img src="/favicon.svg"> so it scales with the text and
 * costs no extra request.
 *
 * The paths are the favicon's, but NOT its viewBox. The favicon is a rounded
 * tile, so its 0 0 32 32 box insets the artwork by ~8.5 units a side to leave
 * room for the background — padding that, in a wordmark, renders as a visible
 * gap between the "H" and the "e". This box is cropped to the artwork's real
 * bounds: the H stems span x 8.5-23.5 (3-wide strokes, round caps) and y 7-25,
 * and the wing ticks reach x 5.6 and 26.4, y 6.9. What is left either side of
 * the stems is the wings' own 2.9 units, which reads as a normal letter gap.
 *
 * Sized in em off the cap height (Inter's is 0.727em) so the mark tracks the
 * font rather than a hardcoded pixel size, and baseline-aligned rather than
 * centred: the H's feet are flush with the bottom of the cropped box, so they
 * land on the text baseline the way a real glyph would.
 */
const CAP_EM = 0.727; // Inter cap height, in em
const MARK_UNITS_W = 20.8;
const MARK_UNITS_H = 18.1;
const MARK_CAP_UNITS = 18; // the H stems, y 7 -> 25

function HermesMark() {
  return (
    <svg
      viewBox="5.6 6.9 20.8 18.1"
      width={`${((MARK_UNITS_W / MARK_CAP_UNITS) * CAP_EM).toFixed(3)}em`}
      height={`${((MARK_UNITS_H / MARK_CAP_UNITS) * CAP_EM).toFixed(3)}em`}
      aria-hidden="true"
      focusable="false"
      style={{ verticalAlign: 'baseline' }}
    >
      <path
        d="M6.5 10 l3.2 -2.2 M25.5 10 l-3.2 -2.2"
        stroke="#863bff"
        strokeWidth="1.8"
        strokeLinecap="round"
        fill="none"
      />
      <path
        d="M10 8.5 V23.5 M22 8.5 V23.5"
        stroke="currentColor"
        strokeWidth="3"
        strokeLinecap="round"
        fill="none"
      />
      <path d="M10 16 H22" stroke="#863bff" strokeWidth="3" strokeLinecap="round" fill="none" />
    </svg>
  );
}

/** The cross-run pages, always shown, in this order. */
const PAGES: { page: Route['page']; href: string; label: string }[] = [
  { page: 'needs-you', href: '#/needs-you', label: 'Needs you' },
  { page: 'crew', href: '#/crew', label: 'Crew' },
  { page: 'activity', href: '#/activity', label: 'Activity' },
];

function itemStyle(current: boolean): CSSProperties {
  return {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 6,
    padding: '6px 12px',
    fontSize: 13,
    textDecoration: 'none',
    color: current ? 'var(--text-primary)' : 'var(--text-muted)',
    background: current ? 'var(--wash-subtle)' : 'transparent',
    borderRadius: 'var(--radius-md)',
    transition: 'all 120ms ease-out',
  };
}

type TopBarProps = {
  connected: boolean;
  /** The page on screen; its item carries aria-current="page". */
  page?: Route['page'];
  /** Decisions waiting across every run (the sum of `awaiting`); no badge when 0 or not yet known. */
  needsYouCount?: number | null;
};

export default function TopBar({ connected, page, needsYouCount }: TopBarProps) {
  return (
    <header
      style={{
        // Deliberately NOT sticky: the shell is a fixed-height flex column whose
        // content pane does the scrolling, so this bar is already pinned. Sticky
        // only let it drift when the page was overscrolled past its end.
        position: 'relative',
        zIndex: 40,
        flex: 'none',
        height: TOPBAR_HEIGHT,
        display: 'flex',
        alignItems: 'center',
        gap: 24,
        padding: '0 20px',
        background: 'oklab(0 0 0 / 0.85)',
        backdropFilter: 'blur(12px)',
        borderBottom: '1px solid var(--border-hairline)',
      }}
    >
      {/* Plain inline layout, not flex: the mark is a stand-in glyph, so it has to
          sit on the text baseline, and a flex container would strip that away. */}
      <a
        href="#/runs"
        aria-label="Hermes"
        style={{ color: 'var(--text-primary)', whiteSpace: 'nowrap', textDecoration: 'none' }}
      >
        <HermesMark />
        <span aria-hidden="true">ermes</span>
      </a>

      <nav aria-label="Pages" style={{ display: 'flex', gap: 4 }}>
        {PAGES.map((item) => {
          const current = item.page === page;
          return (
            <a
              key={item.page}
              href={item.href}
              aria-current={current ? 'page' : undefined}
              style={itemStyle(current)}
            >
              {item.label}
              {/* The item always shows; the count is what says there is something to do. */}
              {item.page === 'needs-you' && needsYouCount != null && needsYouCount > 0 && (
                <span
                  data-testid="needs-you-count"
                  style={{
                    padding: '0 6px',
                    fontSize: 11,
                    fontFamily: 'var(--font-mono)',
                    color: 'var(--status-attention, #e3b341)',
                    background: 'var(--wash-subtle)',
                    border: '1px solid var(--border-hairline)',
                    borderRadius: 'var(--radius-lg)',
                  }}
                >
                  {needsYouCount}
                </span>
              )}
            </a>
          );
        })}
      </nav>

      <div style={{ flex: 1 }} />

      <LiveDot connected={connected} />
    </header>
  );
}
