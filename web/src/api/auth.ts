/**
 * Auth module - token management for Hermes control plane.
 * Token held IN MEMORY ONLY (never localStorage/cookies).
 * Phase D1b.
 */

// In-memory token storage (survives setToken; cleared on tab close)
let token: string | null = null;

/**
 * Get the current token.
 * Returns bootstrapped token (window.__HERMES_TOKEN__) or manually set token.
 */
export function getToken(): string | null {
  // Check if token was set manually via setToken
  if (token !== null) {
    return token;
  }

  // Check if token was bootstrapped by server (loopback only)
  if (typeof window !== 'undefined' && (window as any).__HERMES_TOKEN__) {
    return (window as any).__HERMES_TOKEN__;
  }

  return null;
}

/**
 * Set token manually (for remote/non-loopback login).
 * Token is held in memory only.
 */
export function setToken(newToken: string): void {
  token = newToken;
}

/**
 * Check if we're in remote mode (non-loopback).
 * Returns true if __HERMES_BIND__ is "remote", false otherwise.
 */
export function isRemote(): boolean {
  if (typeof window === 'undefined') {
    return false;
  }

  return (window as any).__HERMES_BIND__ === 'remote';
}

/**
 * Check if a token is available (bootstrapped or manually set).
 */
export function hasToken(): boolean {
  return getToken() !== null;
}

/**
 * Clear manually set token (for logout / testing).
 */
export function clearToken(): void {
  token = null;
}
