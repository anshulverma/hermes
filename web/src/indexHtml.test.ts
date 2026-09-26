import { it, expect } from 'vitest';
// ?raw: the page's own source text, no Node fs.
import indexHtml from '../index.html?raw';

// A diagram's <style> applies to the whole page while mermaid draws it, so
// worker text could make the browser fetch any image URL. The page loads
// images only from itself, blobs and data: URLs.
it('the page allows images only from its own origin, blobs and data: URLs', () => {
  const doc = new DOMParser().parseFromString(indexHtml, 'text/html');
  const policies = [...doc.head.querySelectorAll('meta[http-equiv="Content-Security-Policy"]')].map((m) =>
    m.getAttribute('content'),
  );
  expect(policies).toEqual(["img-src 'self' blob: data:"]);
});
