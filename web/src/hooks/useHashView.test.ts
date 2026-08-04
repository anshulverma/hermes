import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useHashView, VIEWS, parseViewHash } from './useHashView';

function setHash(h: string) {
  window.location.hash = h;
}

describe('parseViewHash', () => {
  it('reads a known view from the hash', () => {
    expect(parseViewHash('#board')).toBe('board');
    expect(parseViewHash('#/board')).toBe('board');
    expect(parseViewHash('board')).toBe('board');
  });

  it('accepts every declared view', () => {
    for (const v of VIEWS) {
      expect(parseViewHash(`#${v}`)).toBe(v);
    }
  });

  it('falls back to the default for empty/unknown/garbage hashes', () => {
    expect(parseViewHash('')).toBe('overview');
    expect(parseViewHash('#')).toBe('overview');
    expect(parseViewHash('#nope')).toBe('overview');
    expect(parseViewHash('#../../etc/passwd')).toBe('overview');
  });

  it('is case-insensitive and tolerates surrounding slashes', () => {
    expect(parseViewHash('#/Crew/')).toBe('crew');
  });
});

describe('useHashView', () => {
  beforeEach(() => setHash(''));
  afterEach(() => setHash(''));

  it('initialises from the hash so a refresh restores the tab', () => {
    setHash('#crew');
    const { result } = renderHook(() => useHashView());
    expect(result.current[0]).toBe('crew');
  });

  it('defaults to overview with no hash', () => {
    const { result } = renderHook(() => useHashView());
    expect(result.current[0]).toBe('overview');
  });

  it('writes the hash when the view changes', () => {
    const { result } = renderHook(() => useHashView());
    act(() => result.current[1]('metrics'));
    expect(result.current[0]).toBe('metrics');
    expect(window.location.hash).toBe('#metrics');
  });

  it('follows browser back/forward (hashchange)', () => {
    const { result } = renderHook(() => useHashView());
    act(() => {
      setHash('#findings');
      window.dispatchEvent(new HashChangeEvent('hashchange'));
    });
    expect(result.current[0]).toBe('findings');
  });

  it('normalises a hash that does not name the tab on screen', () => {
    setHash('#bogus');
    renderHook(() => useHashView());
    expect(window.location.hash).toBe('#overview');
  });

  it('canonicalises a valid but untidy hash', () => {
    setHash('#/Crew/');
    const { result } = renderHook(() => useHashView());
    expect(result.current[0]).toBe('crew');
    expect(window.location.hash).toBe('#crew');
  });

  it('leaves a clean URL alone when there is no hash', () => {
    const { result } = renderHook(() => useHashView());
    expect(result.current[0]).toBe('overview');
    expect(window.location.hash).toBe('');
  });

  it('corrects a stale hash when the default tab is selected', () => {
    setHash('#bogus');
    const { result } = renderHook(() => useHashView());
    act(() => result.current[1]('overview'));
    expect(window.location.hash).toBe('#overview');
  });

  it('ignores a hashchange to an unknown view by falling back to the default', () => {
    setHash('#board');
    const { result } = renderHook(() => useHashView());
    act(() => {
      setHash('#bogus');
      window.dispatchEvent(new HashChangeEvent('hashchange'));
    });
    expect(result.current[0]).toBe('overview');
  });
});
