import '@testing-library/jest-dom';
import * as React from 'react';
import * as ReactDOM from 'react-dom';
import * as ReactJSXRuntime from 'react/jsx-runtime';
import Markdown from '../components/Markdown';
import { getToken } from '../api/auth';

// The same globals ds/_globals.ts sets in the browser: the DS bundle and any
// playbook view bundle read React off the window, in tests as in production.
globalThis.window.React = React;
globalThis.window.ReactDOM = ReactDOM;
globalThis.window.ReactJSXRuntime = ReactJSXRuntime;
// renderMermaid is a stand-in for tests that do not import '../ds' (a test that
// does gets the real one from _globals); tests that draw a diagram replace it
// on the shelf. ds-load.test.ts checks the real one.
globalThis.window.HermesUI = {
  Markdown,
  getToken,
  renderMermaid: async () => '<svg xmlns="http://www.w3.org/2000/svg"></svg>',
};

// jsdom has no scrollIntoView. RunRail scrolls the selected row with it, so
// every test gets this no-op; a test that checks the call spies on it.
Element.prototype.scrollIntoView = function scrollIntoView() {};
