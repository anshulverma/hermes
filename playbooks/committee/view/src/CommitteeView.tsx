/**
 * Placeholder. Task 8 replaces every line of this with the real committee view.
 *
 * It exists to prove the boundary before anything is built on top of it: compiled
 * to UMD with react, react-dom and react/jsx-runtime external, loaded
 * by a <script> tag, it has to render with the host SPA's own React. useState is
 * the proof — a second React instance throws "Invalid hook call" on exactly that
 * line, and nothing cheaper detects it.
 *
 * Default export only: rolldown emits `return CommitteeView` for a single default
 * export, so window.HermesView_committee is the component itself. Add a named
 * export and the global silently becomes a namespace object instead.
 */
import { useState } from 'react';

export default function CommitteeView({ runId }: { runId: string }) {
  const [clicks, setClicks] = useState(0);
  return (
    <button type="button" onClick={() => setClicks(clicks + 1)}>
      placeholder view for {runId} clicks: {clicks}
    </button>
  );
}
