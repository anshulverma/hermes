// Builds a playbook-owned view into a UMD bundle the control plane loads with a
// <script> tag. Library mode with React external: the host SPA already carries
// React in its app chunk, and a second copy makes every hook in the view throw.
//
// Run it from web/:
//
//   cd web && ./node_modules/.bin/vite build --config vite.playbook-view.config.ts
//
// The cwd is load-bearing. `entry` and `outDir` below are relative to the
// process cwd, so a build launched from the repo root cannot resolve the entry
// at all -- it fails with UNRESOLVED_ENTRY rather than emitting different
// bytes. (From a sibling directory it is byte-identical.) Either way,
// tests/unit/test_committee_view_build.py is what notices.
//
// This config must live in web/ — outside it, `@vitejs/plugin-react` does not
// resolve, because web/node_modules is the only node_modules in the repo.
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  // Without this, Vite copies web/public/* — favicon.svg, icons.svg — into the
  // playbook package next to the bundle.
  publicDir: false,
  build: {
    // A committed artifact has to be reviewable in a diff.
    minify: false,
    // outDir is outside the project root, so Vite leaves it alone unless asked.
    emptyOutDir: true,
    outDir: '../playbooks/committee/view/dist',
    lib: {
      entry: '../playbooks/committee/view/src/CommitteeView.tsx',
      // window.HermesView_committee — where the SPA loader reads the component.
      name: 'HermesView_committee',
      formats: ['umd'],
      // A function, because a bare string fileName emits committee.umd.umd.cjs
      // -- Vite appends the format and its own extension to the name given.
      fileName: () => 'committee.umd.js',
    },
    rollupOptions: {
      // React and nothing else. The host's other shelves -- the design system
      // and Markdown -- are read off `window` at RENDER time (see
      // playbooks/committee/view/src/host.tsx), so they need no external entry
      // here: a module specifier only has to be externalised if some file
      // actually imports it, and none does. Importing Markdown for real would
      // inline react-markdown, remark-gfm and unified into a committed,
      // unminified artifact, which is why nothing imports it.
      external: ['react', 'react-dom', 'react/jsx-runtime'],
      output: {
        globals: {
          react: 'React',
          'react-dom': 'ReactDOM',
          // Required. Omit it and the automatic JSX runtime is emitted as
          // global.react_jsx_runtime, which is undefined in the browser.
          'react/jsx-runtime': 'ReactJSXRuntime',
        },
      },
    },
  },
});
