import '@testing-library/jest-dom';
import * as React from 'react';
import * as ReactDOM from 'react-dom';

// Set React on global for the DS bundle (UMD expects it)
globalThis.window.React = React;
globalThis.window.ReactDOM = ReactDOM;
