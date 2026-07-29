/**
 * TokenLogin - token input for remote/non-loopback deployments.
 * Phase D1b: shows only when remote + no token.
 */

import { useState } from 'react';
import { setToken, isRemote, hasToken } from '../api/auth';

type TokenLoginProps = {
  onAuthenticated: () => void;
};

export default function TokenLogin({ onAuthenticated }: TokenLoginProps) {
  const [input, setInput] = useState('');

  // Only show if remote AND no token
  if (!isRemote() || hasToken()) {
    return null;
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();

    const trimmed = input.trim();
    if (!trimmed) {
      return; // Don't submit empty input
    }

    setToken(trimmed);
    onAuthenticated();
  }

  return (
    <div
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'var(--bg)',
        zIndex: 100,
      }}
    >
      <form
        onSubmit={handleSubmit}
        style={{
          display: 'flex',
          flexDirection: 'column',
          gap: 16,
          padding: 24,
          background: 'var(--wash-subtle)',
          border: '1px solid var(--border-hairline)',
          borderRadius: 'var(--radius-lg)',
          maxWidth: 400,
          width: '100%',
        }}
      >
        <div style={{ fontSize: 16, color: 'var(--text-primary)' }}>
          Hermes - Remote Login
        </div>

        <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
          This is a non-loopback deployment. Please enter your API token.
        </div>

        <label
          htmlFor="token-input"
          style={{
            display: 'flex',
            flexDirection: 'column',
            gap: 6,
            fontSize: 13,
            color: 'var(--text-secondary)',
          }}
        >
          Token
          <input
            id="token-input"
            type="password"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Paste your API token"
            autoFocus
            style={{
              padding: '8px 12px',
              fontSize: 13,
              color: 'var(--text-primary)',
              background: 'var(--bg)',
              border: '1px solid var(--border-hairline)',
              borderRadius: 'var(--radius-md)',
              fontFamily: 'var(--font-mono)',
            }}
          />
        </label>

        <button
          type="submit"
          disabled={!input.trim()}
          style={{
            padding: '8px 16px',
            fontSize: 13,
            color: 'var(--text-primary)',
            background: input.trim() ? 'var(--status-ok)' : 'var(--wash-subtle)',
            border: '1px solid var(--border-hairline)',
            borderRadius: 'var(--radius-md)',
            cursor: input.trim() ? 'pointer' : 'not-allowed',
          }}
        >
          Login
        </button>
      </form>
    </div>
  );
}
