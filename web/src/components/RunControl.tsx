/**
 * RunControl - Pause/Resume/Stop controls for a run.
 * Phase D1b: legal-transitions-only, auth headers, 409 handling.
 */

import { useEffect, useRef, useState } from 'react';
import { pauseRun, resumeRun, stopRun, reopenRun, AuthError } from '../api/client';

type RunControlProps = {
  runId: string;
  runState: string;
  onSuccess?: () => void;
};

export default function RunControl({ runId, runState, onSuccess }: RunControlProps) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showStopConfirm, setShowStopConfirm] = useState(false);

  // Focus follows the control that replaces the pressed one: Resume after
  // Pause, Pause after Resume or Reopen, Reopen after a confirmed Stop. Only a
  // success here arms it, so a background state change never moves focus. It
  // moves only when focus was lost or is still in here: if you have moved on by
  // the time the new state arrives, a stray Space must not press Resume or Reopen.
  const rootRef = useRef<HTMLDivElement>(null);
  const primaryRef = useRef<HTMLButtonElement>(null);
  const stopRef = useRef<HTMLButtonElement>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);
  const focusPrimary = useRef(false);
  const focusStop = useRef(false);

  useEffect(() => {
    if (!focusPrimary.current) return;
    focusPrimary.current = false;
    const active = document.activeElement;
    if (active && active !== document.body && !rootRef.current?.contains(active)) return;
    primaryRef.current?.focus();
  }, [runState]);

  // Opening the Stop confirmation focuses Cancel; Cancel hands focus back to Stop.
  useEffect(() => {
    if (showStopConfirm) {
      cancelRef.current?.focus();
    } else if (focusStop.current) {
      focusStop.current = false;
      stopRef.current?.focus();
    }
  }, [showStopConfirm]);

  // Determine legal actions based on run state
  const canPause = runState === 'running';
  const canResume = runState === 'paused';
  const canStop = runState === 'running' || runState === 'paused';

  // A finished run dispatches nothing; reopening puts it back to work.
  const isTerminal = ['done', 'stopped', 'failed'].includes(runState);

  async function handlePause() {
    setLoading(true);
    setError(null);

    try {
      await pauseRun(runId);
      focusPrimary.current = true;
      onSuccess?.();
    } catch (e: any) {
      if (e instanceof AuthError) {
        setError('Unauthorized: invalid or missing token');
      } else {
        setError(e.message);
      }
    } finally {
      setLoading(false);
    }
  }

  async function handleResume() {
    setLoading(true);
    setError(null);

    try {
      await resumeRun(runId);
      focusPrimary.current = true;
      onSuccess?.();
    } catch (e: any) {
      if (e instanceof AuthError) {
        setError('Unauthorized: invalid or missing token');
      } else {
        setError(e.message);
      }
    } finally {
      setLoading(false);
    }
  }

  async function handleReopen() {
    setLoading(true);
    setError(null);

    try {
      await reopenRun(runId);
      focusPrimary.current = true;
      onSuccess?.();
    } catch (e: any) {
      if (e instanceof AuthError) {
        setError('Unauthorized: invalid or missing token');
      } else {
        setError(e.message);
      }
    } finally {
      setLoading(false);
    }
  }

  async function handleStopConfirm() {
    setLoading(true);
    setError(null);
    setShowStopConfirm(false);

    try {
      await stopRun(runId);
      focusPrimary.current = true;
      onSuccess?.();
    } catch (e: any) {
      if (e instanceof AuthError) {
        setError('Unauthorized: invalid or missing token');
      } else {
        setError(e.message);
      }
    } finally {
      setLoading(false);
    }
  }

  function handleStopCancel() {
    focusStop.current = true;
    setShowStopConfirm(false);
  }

  if (isTerminal) {
    return (
      <div ref={rootRef} style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <button
            ref={primaryRef}
            onClick={handleReopen}
            disabled={loading}
            title="Put this finished run back to running so its tickets dispatch again"
            style={{
              padding: '6px 12px',
              fontSize: 13,
              color: 'var(--text-primary)',
              background: 'var(--wash-subtle)',
              border: '1px solid var(--border-hairline)',
              borderRadius: 'var(--radius-md)',
              cursor: loading ? 'not-allowed' : 'pointer',
            }}
          >
            {loading ? 'Reopening...' : 'Reopen'}
          </button>
          <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
            Run is {runState} — reopen it to dispatch remaining tickets.
          </span>
        </div>
        {error && (
          <div style={{ fontSize: 13, color: 'var(--status-danger)' }}>{error}</div>
        )}
      </div>
    );
  }

  return (
    <div ref={rootRef} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ display: 'flex', gap: 8 }}>
        {canPause && (
          <button
            ref={primaryRef}
            onClick={handlePause}
            disabled={loading}
            style={{
              padding: '6px 12px',
              fontSize: 13,
              color: 'var(--text-primary)',
              background: 'var(--wash-subtle)',
              border: '1px solid var(--border-hairline)',
              borderRadius: 'var(--radius-md)',
              cursor: loading ? 'not-allowed' : 'pointer',
            }}
          >
            {loading ? 'Pausing...' : 'Pause'}
          </button>
        )}

        {canResume && (
          <button
            ref={primaryRef}
            onClick={handleResume}
            disabled={loading}
            style={{
              padding: '6px 12px',
              fontSize: 13,
              color: 'var(--text-primary)',
              background: 'var(--wash-subtle)',
              border: '1px solid var(--border-hairline)',
              borderRadius: 'var(--radius-md)',
              cursor: loading ? 'not-allowed' : 'pointer',
            }}
          >
            {loading ? 'Resuming...' : 'Resume'}
          </button>
        )}

        {canStop && !showStopConfirm && (
          <button
            ref={stopRef}
            onClick={() => setShowStopConfirm(true)}
            disabled={loading}
            style={{
              padding: '6px 12px',
              fontSize: 13,
              color: 'var(--status-danger)',
              background: 'var(--wash-subtle)',
              border: '1px solid var(--border-hairline)',
              borderRadius: 'var(--radius-md)',
              cursor: loading ? 'not-allowed' : 'pointer',
            }}
          >
            Stop
          </button>
        )}
      </div>

      {showStopConfirm && (
        <div
          style={{
            padding: 12,
            background: 'var(--wash-subtle)',
            border: '1px solid var(--border-hairline)',
            borderRadius: 'var(--radius-md)',
            display: 'flex',
            flexDirection: 'column',
            gap: 8,
          }}
        >
          <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
            Confirm stop - this will terminate the run and stop all workers.
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button
              onClick={handleStopConfirm}
              disabled={loading}
              style={{
                padding: '6px 12px',
                fontSize: 13,
                color: 'var(--text-primary)',
                background: 'var(--status-danger)',
                border: 'none',
                borderRadius: 'var(--radius-md)',
                cursor: loading ? 'not-allowed' : 'pointer',
              }}
            >
              {loading ? 'Stopping...' : 'Confirm'}
            </button>
            <button
              ref={cancelRef}
              onClick={handleStopCancel}
              disabled={loading}
              style={{
                padding: '6px 12px',
                fontSize: 13,
                color: 'var(--text-secondary)',
                background: 'transparent',
                border: '1px solid var(--border-hairline)',
                borderRadius: 'var(--radius-md)',
                cursor: loading ? 'not-allowed' : 'pointer',
              }}
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {error && (
        <div
          style={{
            padding: 8,
            fontSize: 13,
            color: 'var(--status-danger)',
            background: 'var(--wash-subtle)',
            border: '1px solid var(--border-hairline)',
            borderRadius: 'var(--radius-md)',
          }}
        >
          {error}
        </div>
      )}
    </div>
  );
}
