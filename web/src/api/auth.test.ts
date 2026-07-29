/**
 * Tests for auth module.
 * Token management, bind detection, localStorage safety.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { getToken, setToken, isRemote, hasToken, clearToken } from './auth';

describe('auth module', () => {
  beforeEach(() => {
    // Clear any previous state
    clearToken();

    // Reset window globals
    delete (window as any).__HERMES_TOKEN__;
    delete (window as any).__HERMES_BIND__;
  });

  describe('getToken', () => {
    it('should return bootstrapped token from window.__HERMES_TOKEN__', () => {
      (window as any).__HERMES_TOKEN__ = 'test-token-123';

      const token = getToken();

      expect(token).toBe('test-token-123');
    });

    it('should return null when no token is set', () => {
      const token = getToken();

      expect(token).toBeNull();
    });

    it('should return token set via setToken', () => {
      setToken('manual-token-456');

      const token = getToken();

      expect(token).toBe('manual-token-456');
    });
  });

  describe('setToken', () => {
    it('should store token in memory for subsequent getToken calls', () => {
      setToken('new-token-789');

      expect(getToken()).toBe('new-token-789');
    });

    it('should overwrite previously set token', () => {
      setToken('first-token');
      setToken('second-token');

      expect(getToken()).toBe('second-token');
    });

    it('should NOT write token to localStorage', () => {
      const localStorageSetItemSpy = vi.spyOn(Storage.prototype, 'setItem');

      setToken('secret-token');

      expect(localStorageSetItemSpy).not.toHaveBeenCalled();
      localStorageSetItemSpy.mockRestore();
    });
  });

  describe('isRemote', () => {
    it('should return true when __HERMES_BIND__ is "remote"', () => {
      (window as any).__HERMES_BIND__ = 'remote';

      expect(isRemote()).toBe(true);
    });

    it('should return false when __HERMES_BIND__ is "loopback"', () => {
      (window as any).__HERMES_BIND__ = 'loopback';

      expect(isRemote()).toBe(false);
    });

    it('should return false when __HERMES_BIND__ is undefined (default loopback)', () => {
      expect(isRemote()).toBe(false);
    });
  });

  describe('hasToken', () => {
    it('should return true when token is bootstrapped', () => {
      (window as any).__HERMES_TOKEN__ = 'bootstrap-token';

      expect(hasToken()).toBe(true);
    });

    it('should return true when token was set manually', () => {
      setToken('manual-token');

      expect(hasToken()).toBe(true);
    });

    it('should return false when no token is available', () => {
      expect(hasToken()).toBe(false);
    });
  });

  describe('clearToken', () => {
    it('should clear manually set token', () => {
      setToken('to-be-cleared');
      expect(hasToken()).toBe(true);

      clearToken();

      expect(hasToken()).toBe(false);
      expect(getToken()).toBeNull();
    });
  });

  describe('localStorage safety', () => {
    it('should never read from localStorage', () => {
      const localStorageGetItemSpy = vi.spyOn(Storage.prototype, 'getItem');

      getToken();
      hasToken();

      expect(localStorageGetItemSpy).not.toHaveBeenCalled();
      localStorageGetItemSpy.mockRestore();
    });

    it('should never write to localStorage', () => {
      const localStorageSetItemSpy = vi.spyOn(Storage.prototype, 'setItem');

      setToken('test-token');
      getToken();
      hasToken();

      expect(localStorageSetItemSpy).not.toHaveBeenCalled();
      localStorageSetItemSpy.mockRestore();
    });
  });
});
