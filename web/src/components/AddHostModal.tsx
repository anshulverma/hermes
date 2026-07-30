/**
 * AddHostModal - modal for adding a new crew member with live health check.
 * Phase D2b: probe + checklist + add with failing-checks error handling.
 */

import { useState } from 'react';
import { Dialog, Input, Button, Badge } from '../ds';
import { probeCrew, addCrew, AuthError, type HealthChecklist } from '../api/client';

type AddHostModalProps = {
  isOpen: boolean;
  onClose: () => void;
  onAdded: () => void;
};

export default function AddHostModal({ isOpen, onClose, onAdded }: AddHostModalProps) {
  const [host, setHost] = useState('');
  const [site, setSite] = useState('');
  const [agent, setAgent] = useState('');
  const [baseRef, setBaseRef] = useState('');

  const [probing, setProbing] = useState(false);
  const [adding, setAdding] = useState(false);
  const [checklist, setChecklist] = useState<HealthChecklist | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleProbe = async () => {
    if (!host || !site) {
      setError('Host and site are required');
      return;
    }

    setProbing(true);
    setError(null);
    setChecklist(null);

    try {
      const result = await probeCrew({
        host,
        site,
        agent: agent || undefined,
      });
      setChecklist(result);
    } catch (err) {
      if (err instanceof AuthError) {
        setError('Authentication required. Please log in.');
      } else if (err instanceof Error) {
        setError(err.message);
      } else {
        setError('Failed to probe host');
      }
    } finally {
      setProbing(false);
    }
  };

  const handleAdd = async () => {
    if (!host || !site) {
      setError('Host and site are required');
      return;
    }

    setAdding(true);
    setError(null);

    try {
      await addCrew({
        host,
        site,
        agent: agent || undefined,
        base_ref: baseRef || undefined,
      });
      onAdded();
      onClose();
    } catch (err) {
      if (err instanceof AuthError) {
        setError('Authentication required. Please log in.');
      } else if (err instanceof Error) {
        setError(err.message);
      } else {
        setError('Failed to add host');
      }
    } finally {
      setAdding(false);
    }
  };

  const handleClose = () => {
    // Reset state on close
    setHost('');
    setSite('');
    setAgent('');
    setBaseRef('');
    setChecklist(null);
    setError(null);
    onClose();
  };

  if (!isOpen) {
    return null;
  }

  return (
    <Dialog open={isOpen} fixed onClose={handleClose} title="Add Host">
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        {/* Form inputs */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <Input
            value={host}
            onChange={(e: any) => setHost(e.target?.value ?? e)}
            placeholder="Host ID (e.g., worker-1)"
            disabled={probing || adding}
          />
          <Input
            value={site}
            onChange={(e: any) => setSite(e.target?.value ?? e)}
            placeholder="Site (e.g., local)"
            disabled={probing || adding}
          />
          <Input
            value={agent}
            onChange={(e: any) => setAgent(e.target?.value ?? e)}
            placeholder="Agent (optional, default: claude)"
            disabled={probing || adding}
          />
          <Input
            value={baseRef}
            onChange={(e: any) => setBaseRef(e.target?.value ?? e)}
            placeholder="Base ref (optional, default: main)"
            disabled={probing || adding}
          />
        </div>

        {/* Error message */}
        {error && (
          <div
            style={{
              padding: 12,
              background: 'var(--wash-danger)',
              border: '1px solid var(--border-danger)',
              borderRadius: 'var(--radius-md)',
              color: 'var(--status-danger)',
              fontSize: 13,
            }}
          >
            {error}
          </div>
        )}

        {/* Health checklist */}
        {checklist && (
          <div
            style={{
              padding: 12,
              background: 'var(--wash-subtle)',
              border: '1px solid var(--border-hairline)',
              borderRadius: 'var(--radius-md)',
            }}
          >
            <h3 style={{ margin: '0 0 12px 0', fontSize: 13, fontWeight: 500, color: 'var(--text-muted)' }}>
              Health Check Results
            </h3>

            {/* Overall status */}
            <div style={{ marginBottom: 12, display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>Overall:</span>
              <Badge variant="solid" tone={checklist.ok ? 'ok' : 'danger'} size="sm">
                {checklist.ok ? 'Healthy' : 'Unhealthy'}
              </Badge>
              <span style={{ fontSize: 12, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                {checklist.latency_ms}ms
              </span>
            </div>

            {/* Checks */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {checklist.checks.map((check, idx) => (
                <div
                  key={idx}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 8,
                    padding: 8,
                    background: 'var(--surface-bg)',
                    borderRadius: 'var(--radius-sm)',
                  }}
                >
                  <span
                    style={{
                      width: 8,
                      height: 8,
                      borderRadius: '50%',
                      background: check.ok ? 'var(--status-ok)' : 'var(--status-danger)',
                      flexShrink: 0,
                    }}
                  />
                  <span
                    style={{
                      fontSize: 12,
                      fontFamily: 'var(--font-mono)',
                      color: 'var(--text-secondary)',
                      minWidth: 120,
                    }}
                  >
                    {check.name}
                  </span>
                  <span style={{ fontSize: 12, color: 'var(--text-muted)', flex: 1 }}>
                    {check.detail}
                  </span>
                </div>
              ))}
            </div>

            {/* Resources */}
            {Object.keys(checklist.resources).length > 0 && (
              <div style={{ marginTop: 12 }}>
                <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>Resources: </span>
                {Object.entries(checklist.resources).map(([key, value]) => (
                  <span
                    key={key}
                    style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: 4,
                      padding: '2px 8px',
                      marginLeft: 6,
                      background: 'var(--surface-bg)',
                      borderRadius: 'var(--radius-md)',
                      fontSize: 11,
                      fontFamily: 'var(--font-mono)',
                      color: 'var(--text-secondary)',
                    }}
                  >
                    <span>{key}</span>
                    <span style={{ color: 'var(--text-primary)' }}>{value}</span>
                  </span>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Actions */}
        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          <Button variant="ghost" onClick={handleClose} disabled={probing || adding}>
            Cancel
          </Button>
          <Button
            variant="secondary"
            onClick={handleProbe}
            disabled={probing || adding || !host || !site}
          >
            {probing ? 'Probing...' : 'Run Health Check'}
          </Button>
          <Button
            variant="primary"
            onClick={handleAdd}
            disabled={adding || !host || !site}
          >
            {adding ? 'Adding...' : 'Add Host'}
          </Button>
        </div>
      </div>
    </Dialog>
  );
}
