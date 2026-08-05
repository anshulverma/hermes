/**
 * Spinner + LoadingOverlay — themed SVG loading indicators.
 *
 * Spinner is a rotating 3/4 arc in the accent color over a faint track ring.
 * LoadingOverlay centers a Spinner over its positioned parent and blurs whatever
 * is behind it (page or drawer), replacing bare "Loading..." text. The rotation
 * keyframes (`hermes-spin`) live in index.css.
 */

type SpinnerProps = {
  size?: number;
  stroke?: number;
};

export function Spinner({ size = 36, stroke = 4 }: SpinnerProps) {
  const r = 25 - stroke; // radius inside the 50x50 viewBox with room for the stroke
  const c = 2 * Math.PI * r;
  const arc = c * 0.72; // ~3/4 arc reads clearly as spinning
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 50 50"
      role="status"
      aria-label="Loading"
      style={{ animation: 'hermes-spin 0.8s linear infinite', display: 'block' }}
    >
      <circle cx="25" cy="25" r={r} fill="none" stroke="var(--border-hairline)" strokeWidth={stroke} />
      <circle
        cx="25"
        cy="25"
        r={r}
        fill="none"
        stroke="var(--status-live)"
        strokeWidth={stroke}
        strokeLinecap="round"
        strokeDasharray={`${arc} ${c}`}
      />
    </svg>
  );
}

type LoadingOverlayProps = {
  label?: string;
  size?: number;
  // Skip the backdrop blur. Set this when the overlay sits inside a surface that
  // is ALREADY behind a blurred scrim (a drawer/dialog): stacking two
  // full-viewport backdrop-filter layers is an expensive repaint.
  blur?: boolean;
  // Scrim color. Defaults to the page overlay (dark). Pass a surface-matched
  // translucent color when overlaying a lighter surface (e.g. a drawer card) so
  // the tint blends instead of looking like a black box.
  scrim?: string;
};

/**
 * Full-cover, blurred loading overlay. Requires a `position: relative|absolute|fixed`
 * ancestor; it fills that box, centers the spinner, and blurs the content behind.
 */
export function LoadingOverlay({ label, size = 40, scrim = 'var(--surface-overlay)', blur = true }: LoadingOverlayProps) {
  return (
    <div
      role="status"
      aria-live="polite"
      style={{
        position: 'absolute',
        inset: 0,
        zIndex: 50,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 12,
        background: scrim,
        ...(blur
          ? {
              backdropFilter: 'blur(var(--blur-overlay))',
              WebkitBackdropFilter: 'blur(var(--blur-overlay))',
            }
          : {}),
      }}
    >
      <Spinner size={size} />
      {label && <span style={{ color: 'var(--text-muted)', fontSize: 13 }}>{label}</span>}
    </div>
  );
}

/** A translucent scrim matched to the card surface — use over drawers/cards. */
export const CARD_SCRIM = 'color-mix(in srgb, var(--surface-card) 72%, transparent)';

export default Spinner;
