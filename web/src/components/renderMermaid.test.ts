import { describe, it, expect, vi } from 'vitest';

const mermaid = vi.hoisted(() => ({ initialize: vi.fn(), render: vi.fn() }));
vi.mock('mermaid', () => ({ default: mermaid }));

import renderMermaid from './renderMermaid';

const CLEAN = '<svg xmlns="http://www.w3.org/2000/svg"><g><text>Configuration=on</text></g></svg>';

describe('renderMermaid', () => {
  it('draws with strict security and no HTML labels, returning the SVG markup', async () => {
    mermaid.render.mockResolvedValueOnce({ svg: CLEAN });

    await expect(renderMermaid('graph TD; A-->B')).resolves.toBe(CLEAN);
    expect(mermaid.initialize).toHaveBeenCalledWith({
      startOnLoad: false,
      securityLevel: 'strict',
      htmlLabels: false,
    });
  });

  it('rejects drawn markup that could run script, so the view shows the source instead', async () => {
    const unsafe = [
      '<svg><script>alert(1)</script></svg>',
      '<svg><a href="JavaScript:alert(1)"><text>x</text></a></svg>',
      '<svg><rect onload="alert(1)"/></svg>',
      '<svg/onclick=alert(1)></svg>',
      '<svg><foreignObject><div>x</div></foreignObject></svg>',
    ];
    for (const svg of unsafe) {
      mermaid.render.mockResolvedValueOnce({ svg });
      await expect(renderMermaid('graph TD; A-->B'), svg).rejects.toThrow(/unsafe markup/);
    }
  });
});
