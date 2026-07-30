// Sets window.React / window.ReactDOM before the DS UMD bundle evaluates.
//
// The vendored design-system bundle is a UMD that expects React and ReactDOM as
// globals when it runs. This module must be imported FIRST in ds/index.ts (before
// ./bundle.ts) so that static-import evaluation order guarantees the globals exist
// before the bundle registers its component namespace. Importing this from the DS
// layer keeps the ordering self-contained here, independent of the app entry point.
import * as React from 'react';
import * as ReactDOM from 'react-dom';

window.React = React;
window.ReactDOM = ReactDOM;
