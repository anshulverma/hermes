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
globalThis.window.HermesUI = { Markdown, getToken };
