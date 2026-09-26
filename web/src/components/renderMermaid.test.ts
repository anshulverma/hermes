import { describe, it, expect, vi } from 'vitest';

const mermaid = vi.hoisted(() => ({ initialize: vi.fn(), render: vi.fn() }));
vi.mock('mermaid', () => ({ default: mermaid }));

import renderMermaid from './renderMermaid';

const CLEAN = '<svg xmlns="http://www.w3.org/2000/svg"><g><text>Configuration=on</text></g></svg>';

describe('renderMermaid', () => {
  it('draws with strict security, no HTML labels and no error graphic, locked against directives', async () => {
    mermaid.render.mockResolvedValueOnce({ svg: CLEAN });

    await expect(renderMermaid('graph TD; A-->B')).resolves.toBe(CLEAN);
    expect(mermaid.initialize).toHaveBeenCalledWith({
      startOnLoad: false,
      securityLevel: 'strict',
      htmlLabels: false,
      suppressErrorRendering: true,
      journey: { textPlacement: 'tspan' },
      secure: [
        'secure',
        'securityLevel',
        'startOnLoad',
        'maxTextSize',
        'suppressErrorRendering',
        'maxEdges',
        'themeCSS',
        'fontFamily',
        'altFontFamily',
        'htmlLabels',
      ],
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

  it('rejects markup an <img> could not decode, so the view shows the source, not a broken image', async () => {
    // What a click/link diagram draws: xlink:href with no xmlns:xlink declared.
    mermaid.render.mockResolvedValueOnce({
      svg: '<svg xmlns="http://www.w3.org/2000/svg"><a xlink:href="https://example.com"><text>x</text></a></svg>',
    });
    await expect(renderMermaid('graph TD; A-->B')).rejects.toThrow(/not well-formed/);
  });

  it('loads mermaid again on the next diagram after its chunk failed to load', async () => {
    vi.resetModules();
    let imports = 0;
    vi.doMock('mermaid', () => {
      imports += 1;
      if (imports === 1) throw new Error('chunk load failed');
      return { default: mermaid };
    });
    const { default: fresh } = await import('./renderMermaid');

    await expect(fresh('graph TD; A-->B')).rejects.toThrow(); // vitest wraps the factory's error
    mermaid.render.mockResolvedValueOnce({ svg: CLEAN });
    await expect(fresh('graph TD; A-->B')).resolves.toBe(CLEAN);
  });
});
