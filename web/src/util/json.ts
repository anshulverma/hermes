/**
 * Parses text that is expected to be JSON, for callers holding a string rather
 * than a value (trace tool calls arrive as serialised text).
 *
 * Returns undefined when it is not JSON, or when it is a bare scalar: a tree
 * adds nothing over the raw line for `"ok"` or `42`, and wrapping those in a
 * viewer just adds chrome.
 */
export function tryParseJson(text: string): { value: unknown } | undefined {
  const trimmed = text.trim();
  if (!trimmed) return undefined;
  const first = trimmed[0];
  if (first !== '{' && first !== '[') return undefined;
  try {
    return { value: JSON.parse(trimmed) };
  } catch {
    return undefined;
  }
}
