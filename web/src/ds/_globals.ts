// Sets the globals a UMD bundle reads before that bundle evaluates.
//
// The vendored design-system bundle is a UMD that expects React and ReactDOM as
// globals when it runs. This module must be imported FIRST in ds/index.ts (before
// ./bundle.ts) so that static-import evaluation order guarantees the globals exist
// before the bundle registers its component namespace. Importing this from the DS
// layer keeps the ordering self-contained here, independent of the app entry point.
//
// ReactJSXRuntime and HermesUI are here for playbook-owned view bundles, which are
// built the same way and loaded by <script> tag at runtime. The jsx-runtime global
// is not optional: the automatic JSX transform emits a third external, and a bundle
// built without it references an undefined global on its first render. HermesUI is
// the host's component shelf, so a view can render Markdown without inlining
// react-markdown into a committed artifact.
//
// getToken is on that shelf for the same reason and one more. A view bundle cannot
// import ../api/auth -- that module lives in the host's app chunk, not in the
// bundle -- and it must not read window.__HERMES_TOKEN__ instead: the server
// injects that global on a LOOPBACK bind only (server/app.py:1951). On a remote
// bind the token is typed into TokenLogin and held in auth.ts's module memory, so
// a bundle reading the raw global would send no Authorization header and 401 on
// every fetch. getToken() answers correctly on both binds.
//
// Markdown must stay free of any '../ds' import: ds/index -> _globals -> Markdown
// would become a cycle back through ds/index. ../api/auth imports nothing at all.
import * as React from 'react';
import * as ReactDOM from 'react-dom';
import * as ReactJSXRuntime from 'react/jsx-runtime';
import Markdown from '../components/Markdown';
import { getToken } from '../api/auth';

window.React = React;
window.ReactDOM = ReactDOM;
window.ReactJSXRuntime = ReactJSXRuntime;
window.HermesUI = { Markdown, getToken };
