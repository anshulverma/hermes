import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import * as React from 'react'
import * as ReactDOM from 'react-dom'
import './index.css'

// CRITICAL: Set React on global BEFORE importing DS (the bundle expects it)
window.React = React;
window.ReactDOM = ReactDOM;

// Now import the DS (side-effect loads the bundle + tokens)
import './ds/index';

import App from './App.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
