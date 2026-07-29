// Side-effect import to load the UMD/IIFE bundle
// The bundle expects React on the global and assigns window.MonoDarkDashDesignSystem_66fdfe
import './_ds_bundle.js';

// Re-export the namespace for type safety
declare global {
  interface Window {
    React: typeof import('react');
    ReactDOM: typeof import('react-dom');
    MonoDarkDashDesignSystem_66fdfe: any;
    DSNS: any;
  }
}

export {};
