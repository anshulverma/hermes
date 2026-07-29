/**
 * RunControl - Pause/Resume/Stop controls for a run.
 * Phase D1b: legal-transitions-only, auth headers, 409 handling.
 */

import { useState } from 'react';
import { pauseRun, resumeRun, stopRun, AuthError } from '../api/client';

type RunControlProps = {
  runId: string;
  runState: string;
  onSuccess?: () => void;
};

export default function RunControl({ runId, runState, onSuccess }: RunControlProps) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showStopConfirm, setShowStopConfirm] = useState(false);

  // Determine legal actions based on run state
  const canPause = runState === 'running';
  const canResume = runState === 'paused';
  const canStop = runState === 'running' || runState === 'paused';

  // Terminal states have no actions
  const isTerminal = ['done', 'stopped', 'failed'].includes(runState);

  async function handlePause() {
    setLoading(true);
    setError(null);

    try {
      await pauseRun(runId);
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
    setShowStopConfirm(false);
  }

  if (isTerminal) {
    return null; // No controls for terminal runs
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ display: 'flex', gap: 8 }}>
        {canPause && (
          <button
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
