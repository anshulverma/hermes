/**
 * Markdown - renders agent prose as markdown, styled to the dashboard's tokens.
 *
 * Agents write markdown: headings, bullets, fenced code, tables. Rendered as
 * flat pre-wrap text that arrives as literal `##` and `- ` noise, and a fenced
 * diff reads as one grey wall. This maps every element to the same CSS
 * variables the rest of the UI uses, so a rendered answer still looks native.
 *
 * Every element is overridden explicitly rather than left to browser defaults:
 * the app sets no global stylesheet for prose, so an unstyled <h1> or <table>
 * would arrive with Times New Roman and 2em margins.
 *
 * Raw HTML in the source is NOT rendered (react-markdown's default). Agent
 * output is untrusted, and escaping it correctly is not worth the one case
 * where someone wanted a <details>.
 */

import ReactMarkdown, { type Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';

const codeFont = 'var(--font-mono)';

/** Inline `code` and fenced blocks share a look; only the box differs. */
const inlineCode: React.CSSProperties = {
  fontFamily: codeFont,
  fontSize: '0.9em',
  background: 'var(--wash-subtle)',
  border: '1px solid var(--border-hairline)',
  borderRadius: 'var(--radius-sm)',
  padding: '1px 5px',
  wordBreak: 'break-word',
};

const heading = (size: number, top: number): React.CSSProperties => ({
  margin: `${top}px 0 6px`,
  fontSize: size,
  fontWeight: 600,
  color: 'var(--text-primary)',
  lineHeight: 1.3,
});

const components: Components = {
  h1: ({ children }) => <div style={heading(17, 14)}>{children}</div>,
  h2: ({ children }) => <div style={heading(15, 14)}>{children}</div>,
  h3: ({ children }) => <div style={heading(14, 12)}>{children}</div>,
  h4: ({ children }) => <div style={heading(13, 12)}>{children}</div>,
  h5: ({ children }) => <div style={heading(13, 10)}>{children}</div>,
  h6: ({ children }) => <div style={heading(13, 10)}>{children}</div>,

  p: ({ children }) => (
    <p style={{ margin: '0 0 8px', lineHeight: 1.55, color: 'var(--text-primary)' }}>{children}</p>
  ),

  a: ({ children, href }) => (
    <a
      href={href}
      target="_blank"
      rel="noreferrer noopener"
      style={{ color: 'var(--text-link, #6ea8fe)', textDecoration: 'underline' }}
    >
      {children}
    </a>
  ),

  ul: ({ children }) => (
    <ul style={{ margin: '0 0 8px', paddingLeft: 20, lineHeight: 1.55 }}>{children}</ul>
  ),
  ol: ({ children }) => (
    <ol style={{ margin: '0 0 8px', paddingLeft: 20, lineHeight: 1.55 }}>{children}</ol>
  ),
  li: ({ children }) => <li style={{ margin: '2px 0' }}>{children}</li>,

  strong: ({ children }) => (
    <strong style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{children}</strong>
  ),
  em: ({ children }) => <em style={{ fontStyle: 'italic' }}>{children}</em>,
  del: ({ children }) => (
    <del style={{ textDecoration: 'line-through', color: 'var(--text-muted)' }}>{children}</del>
  ),

  blockquote: ({ children }) => (
    <blockquote
      style={{
        margin: '0 0 8px',
        padding: '2px 0 2px 10px',
        borderLeft: '3px solid var(--border-hairline)',
        color: 'var(--text-secondary)',
      }}
    >
      {children}
    </blockquote>
  ),

  hr: () => (
    <hr style={{ border: 'none', borderTop: '1px solid var(--border-hairline)', margin: '12px 0' }} />
  ),

  // react-markdown hands fenced blocks to `code` wrapped in `pre`. Styling the
  // box on `pre` and the text on `code` keeps inline code from inheriting it.
  pre: ({ children }) => (
    <pre
      style={{
        margin: '0 0 8px',
        padding: 10,
        background: 'var(--wash-subtle)',
        border: '1px solid var(--border-hairline)',
        borderRadius: 'var(--radius-sm)',
        overflow: 'auto',
        maxHeight: 320,
      }}
    >
      {children}
    </pre>
  ),

  code: ({ className, children, ...props }) => {
    // A fenced block carries a language class and is already inside <pre>;
    // anything else is inline and needs its own box.
    const fenced = typeof className === 'string' && className.startsWith('language-');
    if (fenced) {
      return (
        <code
          className={className}
          style={{
            fontFamily: codeFont,
            fontSize: 11.5,
            lineHeight: 1.5,
            color: 'var(--text-secondary)',
            background: 'none',
            border: 'none',
            padding: 0,
            whiteSpace: 'pre',
          }}
          {...props}
        >
          {children}
        </code>
      );
    }
    return (
      <code style={inlineCode} {...props}>
        {children}
      </code>
    );
  },

  table: ({ children }) => (
    <div style={{ overflowX: 'auto', margin: '0 0 8px' }}>
      <table style={{ borderCollapse: 'collapse', fontSize: 12, width: '100%' }}>{children}</table>
    </div>
  ),
  th: ({ children }) => (
    <th
      style={{
        border: '1px solid var(--border-hairline)',
        padding: '4px 8px',
        textAlign: 'left',
        color: 'var(--text-primary)',
        background: 'var(--wash-subtle)',
        fontWeight: 600,
      }}
    >
      {children}
    </th>
  ),
  td: ({ children }) => (
    <td
      style={{
        border: '1px solid var(--border-hairline)',
        padding: '4px 8px',
        color: 'var(--text-secondary)',
        verticalAlign: 'top',
      }}
    >
      {children}
    </td>
  ),

  img: ({ src, alt }) => (
    <img src={typeof src === 'string' ? src : undefined} alt={alt} style={{ maxWidth: '100%' }} />
  ),
};

/**
 * `maxHeight` bounds the scroll area; pass null when the caller owns scrolling.
 * The trailing margin on the last block is trimmed so the container's own
 * padding is what sets the bottom gap.
 */
export default function Markdown({
  children,
  maxHeight = null,
  fontSize = 13,
  'data-testid': testId,
}: {
  children: string;
  maxHeight?: number | null;
  fontSize?: number;
  'data-testid'?: string;
}) {
  return (
    <div
      data-testid={testId}
      style={{
        fontSize,
        color: 'var(--text-primary)',
        wordBreak: 'break-word',
        ...(maxHeight == null ? {} : { maxHeight, overflowY: 'auto' }),
      }}
      className="md-body"
    >
      <style>{'.md-body > *:last-child { margin-bottom: 0 !important; }'}</style>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {children}
      </ReactMarkdown>
    </div>
  );
}
