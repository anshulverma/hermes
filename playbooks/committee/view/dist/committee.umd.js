(function(global, factory) {
	typeof exports === "object" && typeof module !== "undefined" ? module.exports = factory(require("react"), require("react/jsx-runtime")) : typeof define === "function" && define.amd ? define(["react", "react/jsx-runtime"], factory) : (global = typeof globalThis !== "undefined" ? globalThis : global || self, global.HermesView_committee = factory(global.React, global.ReactJSXRuntime));
})(this, function(react, react_jsx_runtime) {
	//#region ../playbooks/committee/view/src/CommitteeView.tsx
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
	function CommitteeView({ runId }) {
		const [clicks, setClicks] = (0, react.useState)(0);
		return /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("button", {
			type: "button",
			onClick: () => setClicks(clicks + 1),
			children: [
				"placeholder view for ",
				runId,
				" clicks: ",
				clicks
			]
		});
	}
	//#endregion
	return CommitteeView;
});
