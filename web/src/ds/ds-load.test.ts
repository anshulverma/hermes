import { describe, it, expect } from 'vitest';
// Import this module's own source text via Vite's ?raw (a string) — no Node fs, so the
// production `tsc` build type-checks cleanly.
import dsIndexSource from './index?raw';

describe('DS bundle load-order regression test', () => {
  it('enforces _globals is imported FIRST in index.ts (source-order invariant)', () => {
    const lines = (dsIndexSource as string).split('\n');
    let firstImportIdx = -1;
    let globalsImportIdx = -1;
    let bundleImportIdx = -1;

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i].trim();
      if (line.startsWith('import ') && !line.startsWith('import type')) {
        if (firstImportIdx === -1) {
          firstImportIdx = i;
        }
        if (line.includes('./_globals')) {
          globalsImportIdx = i;
        }
        if (line.includes('./bundle')) {
          bundleImportIdx = i;
        }
      }
    }

    expect(globalsImportIdx, '_globals import must exist').toBeGreaterThan(-1);
    expect(bundleImportIdx, 'bundle import must exist').toBeGreaterThan(-1);
    expect(firstImportIdx, 'at least one import must exist').toBeGreaterThan(-1);

    expect(globalsImportIdx).toBe(firstImportIdx);
    expect(globalsImportIdx).toBeLessThan(bundleImportIdx);
  });

  it('loads the real DS bundle and resolves components', async () => {
    // src/test/setup.ts publishes the same four globals _globals.ts does, which
    // made every assertion below vacuous -- deleting the ReactJSXRuntime and
    // HermesUI lines from _globals.ts left the whole web suite green, and the
    // SPA-host half is the one that actually ships. Clear them first, so what
    // is checked afterwards is the production path and not the harness. This
    // also enforces the file's own cycle warning: if Markdown ever imported
    // '../ds', HermesUI would come back undefined here.
    for (const key of ['React', 'ReactDOM', 'ReactJSXRuntime', 'HermesUI']) {
      delete (window as any)[key];
    }

    const ds = await import('./index');

    expect(typeof window.React, 'window.React must be set by _globals').toBe('object');
    expect(typeof window.ReactDOM, 'window.ReactDOM must be set by _globals').toBe('object');
    expect(
      typeof window.ReactJSXRuntime,
      'window.ReactJSXRuntime must be set by _globals -- a view bundle built with the automatic JSX transform references it on its first render',
    ).toBe('object');
    expect((window as any).HermesUI?.Markdown, 'HermesUI.Markdown must be set by _globals').toBeTruthy();
    expect(
      typeof (window as any).HermesUI?.getToken,
      'HermesUI.getToken must be set by _globals -- a view bundle cannot import ../api/auth',
    ).toBe('function');

    const ns = (window as any).MonoDarkDashDesignSystem_66fdfe || (window as any).DSNS;
    expect(ns, 'DS namespace must be populated by bundle').toBeTruthy();
    expect(typeof ns.Button, 'namespace.Button must be a function').toBe('function');

    expect(typeof ds.Button, 'ds.Button must resolve to a function').toBe('function');
    expect(typeof ds.Table, 'ds.Table must resolve to a function').toBe('function');
  });
});
