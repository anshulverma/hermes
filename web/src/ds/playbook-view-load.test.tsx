import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
// The BUILT artifact, not the source. This test is only worth anything if it
// exercises the same bytes the server hands the browser.
//
// ?raw keeps it a string so Vite never turns the UMD into a module: the file
// lives outside the Vite root, so an ordinary import is externalised and loaded
// by Node as CommonJS, which takes the UMD's require("react") branch. Evaluating
// the string below is what a <script src> does instead.
import umdSource from '../../../playbooks/committee/view/dist/committee.umd.js?raw';

describe('playbook view UMD boundary', () => {
  it('publishes the globals a playbook bundle reads off window', () => {
    expect(typeof window.React.useState).toBe('function');
    expect(typeof window.ReactJSXRuntime.jsx).toBe('function');
    expect(typeof window.HermesUI.Markdown).toBe('function');
    // The one shelf entry a view bundle cannot get any other way: on a remote
    // bind the token is in auth.ts's module memory, not on window.
    expect(typeof window.HermesUI.getToken).toBe('function');
  });

  it('renders the built artifact against the host React, hooks and all', () => {
    // No `module`/`exports` in scope, so the UMD takes its browser-global branch
    // and reads React off the window, exactly as a <script src> would.
    new Function(umdSource).call(window);

    const CommitteeView = (window as any).HermesView_committee;
    expect(typeof CommitteeView).toBe('function');

    render(<CommitteeView runId="run-2" />);
    const button = screen.getByRole('button');
    expect(button).toHaveTextContent('placeholder view for run-2 clicks: 0');

    // The whole point. A second React instance throws "Invalid hook call" here;
    // an unset ReactJSXRuntime global throws before this line ever runs.
    fireEvent.click(button);
    expect(button).toHaveTextContent('placeholder view for run-2 clicks: 1');
  });
});
