import { describe, it, expect } from 'vitest';
import { readFileSync } from 'fs';
import { join } from 'path';

describe('DS bundle load-order regression test', () => {
  it('enforces _globals is imported FIRST in index.ts (source-order invariant)', () => {
    const indexPath = join(__dirname, 'index.ts');
    const source = readFileSync(indexPath, 'utf-8');

    const lines = source.split('\n');
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
    const ds = await import('./index');

    expect(typeof window.React, 'window.React must be set by _globals').toBe('object');
    expect(typeof window.ReactDOM, 'window.ReactDOM must be set by _globals').toBe('object');

    const ns = (window as any).MonoDarkDashDesignSystem_66fdfe || (window as any).DSNS;
    expect(ns, 'DS namespace must be populated by bundle').toBeTruthy();
    expect(typeof ns.Button, 'namespace.Button must be a function').toBe('function');

    expect(typeof ds.Button, 'ds.Button must resolve to a function').toBe('function');
    expect(typeof ds.Table, 'ds.Table must resolve to a function').toBe('function');
  });
});
