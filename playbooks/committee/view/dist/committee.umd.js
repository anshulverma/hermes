(function(global, factory) {
	typeof exports === "object" && typeof module !== "undefined" ? module.exports = factory(require("react"), require("react/jsx-runtime")) : typeof define === "function" && define.amd ? define(["react", "react/jsx-runtime"], factory) : (global = typeof globalThis !== "undefined" ? globalThis : global || self, global.HermesView_committee = factory(global.React, global.ReactJSXRuntime));
})(this, function(react, react_jsx_runtime) {
	//#region ../playbooks/committee/view/src/host.tsx
	function Markdown(props) {
		const Host = window.HermesUI?.Markdown;
		if (Host) return /* @__PURE__ */ (0, react_jsx_runtime.jsx)(Host, { ...props });
		return /* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
			style: {
				whiteSpace: "pre-wrap",
				fontSize: props.fontSize ?? 13,
				lineHeight: 1.55,
				color: "var(--text-primary)"
			},
			children: props.children
		});
	}
	function authHeaders() {
		const token = window.HermesUI?.getToken?.() ?? null;
		return token ? { Authorization: `Bearer ${token}` } : {};
	}
	async function readBody(res) {
		if (!res.ok) {
			let detail = `HTTP ${res.status}`;
			try {
				const parsed = await res.json();
				if (parsed && parsed.detail) detail = String(parsed.detail);
			} catch {}
			throw new Error(detail);
		}
		return res.json();
	}
	async function apiGet(path) {
		return readBody(await fetch(path, { headers: authHeaders() }));
	}
	async function apiPost(path) {
		return readBody(await fetch(path, {
			method: "POST",
			headers: authHeaders()
		}));
	}
	/**
	* The run's own image, through the per-run file route, with the token when there
	* is one. `sha256` pins the bytes the master checked: a file a later worker
	* overwrote is then a 404, not someone else's picture under this caption.
	*/
	function imageUrl(runId, name, sha256) {
		let url = `/api/runs/${encodeURIComponent(runId)}/view/artifact?path=${encodeURIComponent("images/" + name)}`;
		if (sha256) url += `&sha256=${encodeURIComponent(sha256)}`;
		const token = window.HermesUI?.getToken?.() ?? null;
		return token ? `${url}&token=${encodeURIComponent(token)}` : url;
	}
	/** SVG markup for mermaid `source`, or null when the host publishes no renderer. */
	function renderMermaid(source) {
		const render = window.HermesUI?.renderMermaid;
		return typeof render === "function" ? new Promise((resolve) => resolve(render(source))) : null;
	}
	//#endregion
	//#region ../playbooks/committee/view/src/Voice.tsx
	/**
	* A turn as the room reads it: its prose, at most one figure, and what the
	* voice rules made of it.
	*
	* `Segments` is the only renderer of a turn body or a verdict. A body is never
	* handed to Markdown whole: Markdown passes an image's `src` through raw, so a
	* relative `images/x.svg` resolves against the SPA's own path and an http src
	* makes the operator's browser fetch whatever a worker wrote. `view_data`
	* splits every image reference out of the prose first (voice.segments), so
	* Markdown here only ever receives text. A file image is drawn only when the
	* master checked it (`ok`) and only from this run's images/ folder, through
	* `imageUrl`. A mermaid figure is rendered by the host and shown as an <img> of
	* a blob, never as inline markup, so a diagram cannot run script.
	*/
	/** The hard rules in plain words: voice.note's phrasing without the numbers. */
	var VIOLATION_LABEL = {
		over_cap: "over the word cap",
		multi_line: "more than one line",
		multi_sentence: "more than one sentence",
		headers: "headers",
		bold: "bold",
		tables: "tables",
		nested: "nested bullets",
		too_many_bullets: "too many bullets",
		too_many_images: "too many images",
		image_uncaptioned: "an image caption or description missing or too long",
		image_missing: "an image missing or not your own file",
		action_too_long: "an action over 200 characters",
		stance_too_long: "a stance over its cap",
		filler: "filler phrases",
		retake_failed: "the retake delivered nothing, so an earlier take was kept"
	};
	function violationText(violations) {
		return violations.map((v) => VIOLATION_LABEL[v] ?? v).join("; ");
	}
	var figure = {
		margin: 0,
		padding: 8,
		display: "flex",
		flexDirection: "column",
		gap: 6,
		border: "1px solid var(--border-hairline)",
		borderRadius: "var(--radius-sm)",
		background: "var(--wash-subtle)"
	};
	var muted$1 = {
		fontSize: 11.5,
		fontStyle: "italic",
		color: "var(--text-muted)"
	};
	var code = {
		margin: 0,
		fontFamily: "var(--font-mono)",
		fontSize: 11,
		whiteSpace: "pre-wrap",
		color: "var(--text-secondary)"
	};
	/** Plain text, never Markdown: a caption is worker-written too. */
	function Caption({ caption, description }) {
		return /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("figcaption", {
			style: {
				fontSize: 11.5,
				lineHeight: 1.45,
				color: "var(--text-secondary)"
			},
			children: [caption && /* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
				style: {
					fontWeight: 600,
					color: "var(--text-primary)"
				},
				children: caption
			}), description && /* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", { children: description })]
		});
	}
	function FileFigure({ runId, seg }) {
		return /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("figure", {
			"data-testid": "figure-image",
			style: figure,
			children: [seg.ok === true ? /* @__PURE__ */ (0, react_jsx_runtime.jsx)("img", {
				src: imageUrl(runId, seg.name, seg.sha256),
				alt: seg.caption,
				style: { maxWidth: "100%" }
			}) : /* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
				"data-testid": "image-unavailable",
				style: muted$1,
				children: "image unavailable"
			}), /* @__PURE__ */ (0, react_jsx_runtime.jsx)(Caption, {
				caption: seg.caption,
				description: seg.description
			})]
		});
	}
	function MermaidFigure({ seg }) {
		const [drawing, setDrawing] = (0, react.useState)({ state: "pending" });
		(0, react.useEffect)(() => {
			const pending = renderMermaid(seg.source);
			if (pending === null) {
				setDrawing({ state: "absent" });
				return;
			}
			setDrawing({ state: "pending" });
			let live = true;
			let url = null;
			pending.then((svg) => {
				if (!live) return;
				url = URL.createObjectURL(new Blob([svg], { type: "image/svg+xml" }));
				setDrawing({
					state: "drawn",
					url
				});
			}, (err) => {
				if (live) setDrawing({
					state: "failed",
					error: err instanceof Error ? err.message : String(err)
				});
			});
			return () => {
				live = false;
				if (url) URL.revokeObjectURL(url);
			};
		}, [seg.source]);
		const source = /* @__PURE__ */ (0, react_jsx_runtime.jsx)("pre", {
			"data-testid": "mermaid-source",
			style: code,
			children: /* @__PURE__ */ (0, react_jsx_runtime.jsx)("code", { children: seg.source })
		});
		return /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("figure", {
			"data-testid": "figure-mermaid",
			style: figure,
			children: [
				drawing.state === "pending" && /* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
					role: "status",
					style: muted$1,
					children: "rendering diagram…"
				}),
				drawing.state === "drawn" && /* @__PURE__ */ (0, react_jsx_runtime.jsx)("img", {
					src: drawing.url,
					alt: seg.caption,
					style: { maxWidth: "100%" }
				}),
				drawing.state === "absent" && source,
				drawing.state === "failed" && /* @__PURE__ */ (0, react_jsx_runtime.jsxs)(react_jsx_runtime.Fragment, { children: [source, /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
					"data-testid": "mermaid-error",
					role: "status",
					style: muted$1,
					children: ["diagram failed to render: ", drawing.error]
				})] }),
				/* @__PURE__ */ (0, react_jsx_runtime.jsx)(Caption, {
					caption: seg.caption,
					description: seg.description
				})
			]
		});
	}
	function Segments({ segments, runId, fontSize = 12 }) {
		return /* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
			style: {
				display: "flex",
				flexDirection: "column",
				gap: 8
			},
			children: segments.map((seg, i) => seg.kind === "text" ? /* @__PURE__ */ (0, react_jsx_runtime.jsx)(Markdown, {
				fontSize,
				children: seg.text.replaceAll("![", "!​[")
			}, i) : seg.kind === "image" ? /* @__PURE__ */ (0, react_jsx_runtime.jsx)(FileFigure, {
				runId,
				seg
			}, i) : /* @__PURE__ */ (0, react_jsx_runtime.jsx)(MermaidFigure, { seg }, i))
		});
	}
	//#endregion
	//#region ../playbooks/committee/view/src/Verdict.tsx
	/**
	* The chair's ruling, read in the order a person needs it.
	*
	* The ruling itself is 8 KB of structured markdown, so the two things a reader
	* must not scroll past go above it: that this is a simulation, and what the
	* independent re-checks actually found. The prose follows, expanded, in a
	* <details> so it can be collapsed to reach the diff below.
	*
	* `text` is the assembled decision text the playbook banks — the chair's prose
	* with the re-check lines and the disclaimer appended (playbook.py:_reduce_decision).
	* The card never renders it: the prose comes from `segments`, that text split
	* the way a turn body is (view._verdict), so no image reference the chair wrote
	* ever reaches Markdown. The re-checks are rendered from `checks` as well,
	* because a list of six outcomes is a table, not a paragraph.
	*/
	var card = {
		background: "var(--surface-card)",
		border: "1px solid var(--border-hairline)",
		borderRadius: "var(--radius-md)",
		padding: 16,
		display: "flex",
		flexDirection: "column",
		gap: 12
	};
	var note$1 = (tone) => ({
		padding: "8px 12px",
		borderRadius: "var(--radius-sm)",
		fontSize: 12.5,
		lineHeight: 1.5,
		color: "var(--text-primary)",
		background: tone === "muted" ? "var(--wash-subtle)" : `var(--status-${tone}-tint)`,
		border: `1px solid ${tone === "muted" ? "var(--border-hairline)" : `var(--status-${tone}-edge)`}`
	});
	/**
	* The drops the verdict footer lists (playbook `_decision`): a pair the budget
	* or the end of the meeting stopped, unless that pair met in another 1:1. The
	* rest (a malformed line, an unknown role, a duplicate) were refused when they
	* were asked for, so no 1:1 was ever owed. Met is the footer's
	* `one_on_ones_met`: a finished 1:1 in which both members spoke, so one that
	* ended 'not delivered' counts only once it reached exchange 3.
	*/
	function neverMet(drops, oneOnOnes) {
		const pair = (roles) => [...roles].sort().join(" ");
		const met = new Set(oneOnOnes.filter((g) => g.ended !== null && (g.ended !== "not delivered" || g.exchanges.some((x) => (x.exchange ?? 0) >= 3))).map((g) => pair(g.members.map((m) => m.role))));
		return drops.filter((d) => (d.reason === "budget" || d.reason === "meeting ended") && !(d.members && met.has(pair(d.members))));
	}
	function Rechecks({ checks }) {
		if (checks.length === 0) return /* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
			"data-testid": "rechecks-none",
			style: note$1("muted"),
			children: "No edit was delegated, so there was nothing to re-check."
		});
		return /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
			style: {
				display: "flex",
				flexDirection: "column",
				gap: 6
			},
			children: [/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
				style: {
					fontSize: 12,
					color: "var(--text-muted)"
				},
				children: [
					checks.length,
					" delegated ",
					checks.length === 1 ? "edit" : "edits",
					", each re-checked master-side by comparing the revised copy’s digest before and after the turn. The worker’s own claim is not what is reported here."
				]
			}), checks.map((check) => {
				const applied = check.verified === true;
				const outcome = check.verified === null ? "NOT CHECKED" : applied ? "APPLIED" : "DID NOT APPLY";
				return /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
					"data-testid": `verdict-recheck-${check.turn}`,
					style: {
						...note$1(check.verified === null ? "muted" : applied ? "ok" : "danger"),
						display: "flex",
						gap: 10,
						alignItems: "baseline"
					},
					children: [
						/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("span", {
							style: {
								fontFamily: "var(--font-mono)",
								fontSize: 11.5,
								whiteSpace: "nowrap"
							},
							children: [
								"turn ",
								String(check.turn).padStart(2, "0"),
								" · junior_ic"
							]
						}),
						/* @__PURE__ */ (0, react_jsx_runtime.jsx)("strong", {
							style: {
								fontSize: 11.5,
								whiteSpace: "nowrap"
							},
							children: outcome
						}),
						/* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", {
							style: { color: "var(--text-secondary)" },
							children: check.action
						})
					]
				}, check.turn);
			})]
		});
	}
	function Stamp({ runId }) {
		const [stamp, setStamp] = (0, react.useState)(null);
		const [lookupError, setLookupError] = (0, react.useState)(null);
		const [actionError, setActionError] = (0, react.useState)(null);
		const [busy, setBusy] = (0, react.useState)(false);
		const [reloads, setReloads] = (0, react.useState)(0);
		(0, react.useEffect)(() => {
			let live = true;
			apiGet(`/api/runs/${runId}/reductions`).then((rows) => {
				const row = [...rows].reverse().find((r) => r.kind === "decision");
				if (!live) return;
				if (row) setStamp({
					id: row.id,
					review_state: row.review_state,
					delivered: Boolean(row.json?.delivered)
				});
				else setLookupError("no decision reduction is banked for this run");
			}).catch((err) => {
				if (live) setLookupError(err instanceof Error ? err.message : String(err));
			});
			return () => {
				live = false;
			};
		}, [runId, reloads]);
		const decide = async (accept) => {
			if (!stamp || busy) return;
			setBusy(true);
			setActionError(null);
			try {
				const res = await apiPost(`/api/reductions/${stamp.id}/${accept ? "accept" : "reject"}`);
				setStamp({
					...stamp,
					review_state: res.review_state
				});
			} catch (err) {
				setActionError(err instanceof Error ? err.message : "Could not record the decision");
				setReloads((n) => n + 1);
			} finally {
				setBusy(false);
			}
		};
		if (lookupError) return /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
			"data-testid": "stamp-error",
			style: note$1("muted"),
			children: ["Could not read this verdict’s review state: ", lookupError]
		});
		if (!stamp) return null;
		if (!stamp.delivered) return /* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
			"data-testid": "stamp-undelivered",
			style: note$1("muted"),
			children: "The chair delivered no verdict, so there is nothing to accept or reject."
		});
		return /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
			style: {
				display: "flex",
				flexDirection: "column",
				gap: 8
			},
			children: [
				/* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
					"data-testid": "stamp-note",
					style: {
						fontSize: 12,
						color: "var(--text-muted)",
						lineHeight: 1.5
					},
					children: "Accepting settles the chair’s ticket and ends the run done; rejecting ends it failed. Either way it stamps this reduction in the audit trail and emits an event, and it lands nothing and reverts nothing."
				}),
				stamp.review_state && stamp.review_state !== "pending" ? /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
					"data-testid": "stamp-state",
					style: note$1(stamp.review_state === "accepted" ? "ok" : "attention"),
					children: [
						"Recorded as ",
						stamp.review_state,
						"."
					]
				}) : /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
					style: {
						display: "flex",
						gap: 8
					},
					children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("button", {
						type: "button",
						disabled: busy,
						onClick: () => decide(true),
						style: {
							padding: "6px 14px",
							fontSize: 12.5,
							borderRadius: "var(--radius-sm)",
							border: "1px solid var(--status-ok-edge)",
							background: "var(--status-ok-tint)",
							color: "var(--text-primary)",
							cursor: busy ? "default" : "pointer"
						},
						children: "Accept"
					}), /* @__PURE__ */ (0, react_jsx_runtime.jsx)("button", {
						type: "button",
						disabled: busy,
						onClick: () => decide(false),
						style: {
							padding: "6px 14px",
							fontSize: 12.5,
							borderRadius: "var(--radius-sm)",
							border: "1px solid var(--status-danger-edge)",
							background: "var(--status-danger-tint)",
							color: "var(--text-primary)",
							cursor: busy ? "default" : "pointer"
						},
						children: "Reject"
					})]
				}),
				actionError && /* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
					"data-testid": "stamp-action-error",
					style: note$1("danger"),
					children: actionError
				})
			]
		});
	}
	function Verdict({ runId, verdict, oneOnOnes = [], derived = /* @__PURE__ */ new Set() }) {
		if (!verdict) return /* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
			style: card,
			children: /* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
				"data-testid": "verdict-pending",
				style: note$1("muted"),
				children: "The chair has not ruled yet. A verdict appears here once the meeting ends — when the owner closes it, the queue empties, or the turn cap is reached."
			})
		});
		const takes = verdict.takes ?? 1;
		const broke = verdict.violations ?? [];
		const unmet = neverMet(verdict.dropped_one_on_ones ?? [], oneOnOnes);
		const seat = (role) => derived.has(role) ? `${role} · derived seat` : role;
		return /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
			style: card,
			children: [
				/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
					"data-testid": "verdict-simulation",
					style: note$1("attention"),
					children: [
						/* @__PURE__ */ (0, react_jsx_runtime.jsx)("strong", { children: "Simulation — not an approval." }),
						" This verdict is a simulation produced by AI personas reading one file. It is not an approval, not a sign-off, and carries no authority: a human decides.",
						" ",
						verdict.artifact_intact === false ? "A repository file DID change during this review — see below. Nothing was landed," : "No repository was written to, nothing was landed,",
						" ",
						"and nothing here binds any person, team or budget."
					]
				}),
				(takes > 1 || broke.length > 0) && /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
					"data-testid": "verdict-voice",
					style: note$1(broke.length > 0 ? "attention" : "muted"),
					children: [takes > 1 && `The chair took ${takes} takes. `, broke.length > 0 && `The kept verdict broke the ground rules: ${violationText(broke)}.`]
				}),
				/* @__PURE__ */ (0, react_jsx_runtime.jsx)(Rechecks, { checks: verdict.checks }),
				verdict.artifact_intact !== null && /* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
					"data-testid": "artifact-intact",
					style: note$1(verdict.artifact_intact ? "ok" : "danger"),
					children: verdict.artifact_intact ? "Original artifact unchanged — re-checked by digest at the decision, against the digest taken before the meeting opened." : "Original artifact CHANGED DURING THE REVIEW — it was promised untouched. Treat every re-check above as unreliable and read the diff."
				}),
				verdict.dropped_delegation && /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
					"data-testid": "dropped-delegation",
					style: note$1("attention"),
					children: [
						/* @__PURE__ */ (0, react_jsx_runtime.jsx)("strong", { children: "Dropped delegation" }),
						" — the turn cap cut it off and no edit was made:",
						" ",
						verdict.dropped_delegation
					]
				}),
				verdict.dropped_floor_requests.length > 0 && /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
					"data-testid": "dropped-floor-requests",
					style: note$1("attention"),
					children: [
						/* @__PURE__ */ (0, react_jsx_runtime.jsx)("strong", { children: "Dropped floor requests" }),
						" — the review ended before their turn came:",
						" ",
						verdict.dropped_floor_requests.join(", ")
					]
				}),
				unmet.length > 0 && /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
					"data-testid": "dropped-one-on-ones",
					style: note$1("attention"),
					children: [
						/* @__PURE__ */ (0, react_jsx_runtime.jsx)("strong", { children: "1:1s that never met" }),
						" — the review ended or ran out of 1:1 exchanges first:",
						" ",
						unmet.map((d) => `${d.members ? d.members.map(seat).join(" ↔ ") : d.text} (${d.reason})`).join(", ")
					]
				}),
				/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("details", {
					open: true,
					children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("summary", {
						style: {
							cursor: "pointer",
							fontSize: 12,
							color: "var(--text-muted)"
						},
						children: "The chair’s ruling in full"
					}), /* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
						"data-testid": "verdict-prose",
						style: { marginTop: 8 },
						children: /* @__PURE__ */ (0, react_jsx_runtime.jsx)(Segments, {
							segments: verdict.segments ?? [],
							runId,
							fontSize: 13
						})
					})]
				}),
				/* @__PURE__ */ (0, react_jsx_runtime.jsx)(Stamp, { runId })
			]
		});
	}
	//#endregion
	//#region ../playbooks/committee/view/src/Diff.tsx
	/**
	* The document as the committee changed it: the original, each junior-IC edit
	* as its own diff with who asked for it and why, then the final version.
	*
	* The first live run's chair read the unchanged repository file as proof the
	* edits had failed, so this card still leads with the invariant: the original
	* is never modified. A later run showed nothing at all, because the control
	* plane opened the master's host paths inside a container that mounts only the
	* home. So every version here is a snapshot under the run's own directory,
	* named by `view_data` and read through the run-file route.
	*
	* Text is fetched on demand, one selected step at a time, never with the view
	* data: the view refetches on every reduction.
	*/
	/**
	* Past this the LCS table is not worth allocating.
	*
	* ponytail: 4M cells is ~16 MB as an Int32Array, which covers any artifact a
	* committee reviews (the measured run needs 70k). Beyond it the changed middle
	* is reported as one whole-block replacement — true, just coarse. Upgrade to a
	* Myers diff only if a real artifact ever trips it.
	*/
	var MAX_CELLS = 4e6;
	function diffLines(original, revised) {
		const a = original.split("\n");
		const b = revised.split("\n");
		let head = 0;
		while (head < a.length && head < b.length && a[head] === b[head]) head++;
		let tail = 0;
		while (tail < a.length - head && tail < b.length - head && a[a.length - 1 - tail] === b[b.length - 1 - tail]) tail++;
		const rows = [];
		for (let i = 0; i < head; i++) rows.push({
			kind: "same",
			text: a[i]
		});
		const am = a.slice(head, a.length - tail);
		const bm = b.slice(head, b.length - tail);
		if (am.length * bm.length > MAX_CELLS) {
			for (const line of am) rows.push({
				kind: "del",
				text: line
			});
			for (const line of bm) rows.push({
				kind: "add",
				text: line
			});
		} else {
			const w = bm.length + 1;
			const lcs = new Int32Array((am.length + 1) * w);
			for (let i = am.length - 1; i >= 0; i--) for (let j = bm.length - 1; j >= 0; j--) lcs[i * w + j] = am[i] === bm[j] ? lcs[(i + 1) * w + j + 1] + 1 : Math.max(lcs[(i + 1) * w + j], lcs[i * w + j + 1]);
			let i = 0;
			let j = 0;
			while (i < am.length && j < bm.length) if (am[i] === bm[j]) {
				rows.push({
					kind: "same",
					text: am[i]
				});
				i++;
				j++;
			} else if (lcs[(i + 1) * w + j] >= lcs[i * w + j + 1]) {
				rows.push({
					kind: "del",
					text: am[i]
				});
				i++;
			} else {
				rows.push({
					kind: "add",
					text: bm[j]
				});
				j++;
			}
			while (i < am.length) rows.push({
				kind: "del",
				text: am[i++]
			});
			while (j < bm.length) rows.push({
				kind: "add",
				text: bm[j++]
			});
		}
		for (let i = b.length - tail; i < b.length; i++) rows.push({
			kind: "same",
			text: b[i]
		});
		return rows;
	}
	/**
	* The same rows, side by side. A `same` row fills both columns; each run of
	* removals followed by a run of additions pairs up line by line, the shorter
	* side padded with an empty cell; a lone run leaves the other column empty.
	*/
	function splitRows(rows) {
		const out = [];
		let i = 0;
		while (i < rows.length) {
			if (rows[i].kind === "same") {
				out.push([rows[i], rows[i]]);
				i++;
				continue;
			}
			const dels = [];
			while (i < rows.length && rows[i].kind === "del") dels.push(rows[i++]);
			const adds = [];
			while (i < rows.length && rows[i].kind === "add") adds.push(rows[i++]);
			for (let k = 0; k < Math.max(dels.length, adds.length); k++) out.push([dels[k] ?? null, adds[k] ?? null]);
		}
		return out;
	}
	/** Unchanged lines kept either side of a change; the rest of a run folds away. */
	var CONTEXT = 3;
	/**
	* What an edit diff draws: every change with CONTEXT unchanged lines either
	* side, and each longer unchanged run as one Fold -- unless its `start` is in
	* `opened`. A committee edit is a few lines deep in a long document, and
	* unfolded the pane opened on the document's title every time.
	*
	* Returns runs of rows between folds, so the side-by-side layout pairs each run
	* on its own: a fold only ever replaces `same` rows, which pair with
	* themselves, so both layouts fold the same lines.
	*/
	function foldRows(rows, opened) {
		const out = [];
		let shown = [];
		for (let i = 0; i < rows.length;) {
			let j = i;
			while (j < rows.length && rows[j].kind === "same") j++;
			if (j === i) {
				shown.push(rows[i++]);
				continue;
			}
			const from = i === 0 ? 0 : i + CONTEXT;
			const to = j === rows.length ? j : j - CONTEXT;
			if (to > from && !opened.has(from)) {
				shown.push(...rows.slice(i, from));
				if (shown.length) out.push(shown);
				out.push({
					start: from,
					count: to - from
				});
				shown = rows.slice(to, j);
			} else shown.push(...rows.slice(i, j));
			i = j;
		}
		if (shown.length) out.push(shown);
		return out;
	}
	/**
	* How many diff rows to put in the DOM.
	*
	* ponytail: `diffLines` is hard-bounded and fast (415 rows in 1.9 ms on the real
	* pair); the RENDER is what does not scale — one <div> per line, measured at
	* 20,001 nodes and 3.4 s to mount for a 20,000-line artifact. A cap plus a
	* footer beats virtualization until a real artifact trips it.
	*/
	var MAX_ROWS = 5e3;
	var FINAL_LABEL = {
		in_session: "Latest so far — no verdict yet (in session, or stopped before the chair ruled)",
		awaiting_ruling: "Proposed — awaiting your ruling",
		accepted: "Accepted",
		rejected: "Rejected",
		no_ruling: "The meeting ended without a ruling"
	};
	var ROW_STYLE = {
		same: {
			sign: " ",
			background: "transparent",
			color: "var(--text-muted)"
		},
		del: {
			sign: "-",
			background: "var(--status-danger-tint)",
			color: "var(--text-primary)"
		},
		add: {
			sign: "+",
			background: "var(--status-ok-tint)",
			color: "var(--text-primary)"
		}
	};
	var tNN = (n) => `t${String(n).padStart(2, "0")}`;
	var cacheKey = (v) => `${v.path}:${v.bytes}`;
	var mono$1 = { fontFamily: "var(--font-mono)" };
	var pane = {
		...mono$1,
		fontSize: 11.5,
		lineHeight: 1.5,
		maxHeight: 420,
		overflow: "auto",
		border: "1px solid var(--border-hairline)",
		borderRadius: "var(--radius-sm)"
	};
	var muted = {
		fontSize: 12.5,
		color: "var(--text-muted)",
		lineHeight: 1.5
	};
	var heading = {
		fontSize: 13,
		fontWeight: 600,
		color: "var(--text-primary)"
	};
	var note = (tone) => ({
		padding: "8px 12px",
		borderRadius: "var(--radius-sm)",
		background: `var(--status-${tone}-tint)`,
		border: `1px solid var(--status-${tone}-edge)`,
		fontSize: 12.5,
		lineHeight: 1.55,
		color: "var(--text-primary)"
	});
	var chip = (active) => ({
		padding: "3px 10px",
		fontSize: 12,
		borderRadius: "var(--radius-sm)",
		border: "1px solid var(--border-hairline)",
		background: active ? "var(--wash-subtle)" : "transparent",
		color: "var(--text-primary)",
		fontWeight: active ? 600 : 400,
		cursor: "pointer"
	});
	/**
	* Fetch each version through the run-file route, once, cached by path and size.
	*
	* ponytail: a re-settled turn whose snapshot keeps the same size is served
	* stale until reload; key on a digest in `view_data` if that ever matters.
	*/
	function useCopies(runId, versions) {
		const [copies, setCopies] = (0, react.useState)({});
		const [failures, setFailures] = (0, react.useState)({});
		const asked = (0, react.useRef)(/* @__PURE__ */ new Set());
		const [attempt, setAttempt] = (0, react.useState)(0);
		const wanted = versions.map(cacheKey).join("\n");
		(0, react.useEffect)(() => {
			for (const key of wanted ? wanted.split("\n") : []) {
				if (asked.current.has(key)) continue;
				asked.current.add(key);
				apiGet(`/api/runs/${runId}/view/artifact?path=${key.slice(0, key.lastIndexOf(":"))}`).then((copy) => setCopies((prev) => ({
					...prev,
					[key]: copy
				}))).catch((err) => setFailures((prev) => ({
					...prev,
					[key]: err instanceof Error ? err.message : String(err)
				})));
			}
		}, [
			runId,
			wanted,
			attempt
		]);
		const retry = (key) => {
			asked.current.delete(key);
			setFailures((prev) => {
				const next = { ...prev };
				delete next[key];
				return next;
			});
			setAttempt((n) => n + 1);
		};
		return {
			copies,
			failures,
			retry
		};
	}
	function Goto({ n, onOpenTurn }) {
		return /* @__PURE__ */ (0, react_jsx_runtime.jsx)("button", {
			type: "button",
			"data-testid": `goto-${tNN(n)}`,
			"aria-label": `Open ${tNN(n)} in the transcript`,
			onClick: () => onOpenTurn(n),
			style: {
				...mono$1,
				...chip(false),
				padding: "0 6px",
				fontSize: 11
			},
			children: tNN(n)
		});
	}
	/** Who raised it, who delegated it, what the junior said, what the re-check found. */
	function StepContext({ step, timeline, onOpenTurn, derived, oneOnOnes, onOpenOneOnOne }) {
		const at = (n) => n === null ? void 0 : timeline.findLast((e) => e.n === n);
		const reviewer = at(step.reviewer_turn);
		const owner = at(step.owner_turn);
		const junior = at(step.turn);
		const confirmation = junior?.body.split("\n").find((l) => l.trim()) ?? "";
		const oneOnOneSeq = typeof step.origin_one_on_one === "number" ? step.origin_one_on_one : null;
		const oneOnOne = oneOnOnes.find((g) => g.seq === oneOnOneSeq);
		const member = (p) => derived?.has(p.role) ? `${p.name} (${p.role} · derived seat)` : p.name;
		const line = {
			fontSize: 12.5,
			color: "var(--text-secondary)",
			lineHeight: 1.5
		};
		const inferred = step.provenance === "inferred" && /* @__PURE__ */ (0, react_jsx_runtime.jsxs)(react_jsx_runtime.Fragment, { children: [" ", /* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", {
			"data-testid": "step-provenance",
			style: {
				...muted,
				fontSize: 11.5
			},
			children: "(inferred from turn order)"
		})] });
		return /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
			"data-testid": "step-context",
			style: {
				display: "flex",
				flexDirection: "column",
				gap: 4
			},
			children: [
				/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
					"data-testid": "step-verdict",
					style: {
						fontSize: 12,
						fontWeight: 600,
						color: step.verified === true ? "var(--status-ok, #7ee787)" : step.verified === false ? "var(--status-danger, #f85149)" : "var(--text-muted)"
					},
					children: [
						"re-check:",
						" ",
						step.verified === true ? "APPLIED" : step.verified === false ? "DID NOT APPLY" : "not recorded"
					]
				}),
				oneOnOneSeq !== null ? /* @__PURE__ */ (0, react_jsx_runtime.jsxs)(react_jsx_runtime.Fragment, { children: [
					/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
						"data-testid": "step-raised",
						style: line,
						children: [
							"raised in 1:1",
							" ",
							oneOnOne ? `${member(oneOnOne.members[0])} ↔ ${member(oneOnOne.members[1])}` : oneOnOneSeq,
							" ",
							/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("button", {
								type: "button",
								"data-testid": `goto-one-on-one-${oneOnOneSeq}`,
								"aria-label": `Open 1:1 ${oneOnOneSeq} in the transcript`,
								onClick: () => onOpenOneOnOne(oneOnOneSeq),
								style: {
									...mono$1,
									...chip(false),
									padding: "0 6px",
									fontSize: 11
								},
								children: ["1:1 ", oneOnOneSeq]
							})
						]
					}),
					oneOnOne && /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
						"data-testid": "step-why",
						style: line,
						children: ["why: ", oneOnOne.topic]
					}),
					/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
						"data-testid": "step-delegated",
						style: line,
						children: ["delegated: ", oneOnOne?.delegated_action ?? "no action recorded"]
					})
				] }) : /* @__PURE__ */ (0, react_jsx_runtime.jsxs)(react_jsx_runtime.Fragment, { children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
					"data-testid": "step-raised",
					style: line,
					children: step.reviewer_turn !== null ? /* @__PURE__ */ (0, react_jsx_runtime.jsxs)(react_jsx_runtime.Fragment, { children: [
						"raised by ",
						reviewer?.name ?? "a seat the transcript does not name",
						reviewer && derived?.has(reviewer.role) && ` (${reviewer.role} · derived seat)`,
						reviewer?.stance ? ` — ${reviewer.stance}` : "",
						" ",
						/* @__PURE__ */ (0, react_jsx_runtime.jsx)(Goto, {
							n: step.reviewer_turn,
							onOpenTurn
						}),
						inferred
					] }) : "who raised this was not recorded"
				}), step.owner_turn !== null && /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
					"data-testid": "step-delegated",
					style: line,
					children: [
						owner ? `delegated by ${owner.name}: ` : "delegated: ",
						owner?.action ?? "no action recorded",
						" ",
						/* @__PURE__ */ (0, react_jsx_runtime.jsx)(Goto, {
							n: step.owner_turn,
							onOpenTurn
						}),
						inferred
					]
				})] }),
				/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
					"data-testid": "step-confirmed",
					style: line,
					children: [
						junior ? `${junior.name}: ` : "",
						step.delivered ? confirmation || "no prose recorded for this turn" : "no turn delivered",
						" ",
						/* @__PURE__ */ (0, react_jsx_runtime.jsx)(Goto, {
							n: step.turn,
							onOpenTurn
						})
					]
				})
			]
		});
	}
	function UnifiedRow({ row, ref }) {
		const style = ROW_STYLE[row.kind];
		return /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
			ref,
			style: {
				background: style.background,
				color: style.color,
				padding: "0 8px",
				whiteSpace: "pre-wrap",
				wordBreak: "break-word"
			},
			children: [
				style.sign,
				" ",
				row.text
			]
		});
	}
	function SplitCell({ row, side, ref }) {
		const style = row ? ROW_STYLE[row.kind] : null;
		return /* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
			ref,
			"data-testid": `split-${side}`,
			style: {
				background: style ? style.background : "transparent",
				color: style ? style.color : void 0,
				padding: "0 8px",
				whiteSpace: "pre-wrap",
				wordBreak: "break-word",
				borderLeft: side === "right" ? "1px solid var(--border-hairline)" : void 0
			},
			children: row && style ? `${style.sign} ${row.text}` : ""
		});
	}
	function FoldRow({ fold, onOpen }) {
		return /* @__PURE__ */ (0, react_jsx_runtime.jsx)("button", {
			type: "button",
			"data-testid": "diff-fold",
			onClick: () => onOpen(fold.start),
			style: {
				gridColumn: "1 / -1",
				display: "block",
				width: "100%",
				textAlign: "left",
				padding: "0 8px",
				font: "inherit",
				color: "var(--text-muted)",
				background: "var(--wash-subtle)",
				border: "none",
				cursor: "pointer"
			},
			children: `⋯ ${fold.count} unchanged ${fold.count === 1 ? "line" : "lines"}`
		});
	}
	var DiffView = (0, react.memo)(function DiffView({ before, after, mode }) {
		const [opened, setOpened] = (0, react.useState)(/* @__PURE__ */ new Set());
		const first = (0, react.useRef)(null);
		(0, react.useEffect)(() => {
			first.current?.scrollIntoView?.({ block: "nearest" });
		}, []);
		const rows = diffLines(before, after);
		const adds = rows.filter((r) => r.kind === "add").length;
		const dels = rows.filter((r) => r.kind === "del").length;
		if (adds === 0 && dels === 0) return /* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
			"data-testid": "diff-none",
			style: muted,
			children: "No changes between these two versions."
		});
		const open = (start) => setOpened((prev) => new Set(prev).add(start));
		const lines = foldRows(rows, opened).flatMap((run) => Array.isArray(run) ? mode === "split" ? splitRows(run) : run : [run]);
		const firstRow = rows.find((r) => r.kind !== "same");
		const mark = (row) => row !== null && row === firstRow ? first : void 0;
		const total = lines.length;
		const capped = total > MAX_ROWS && /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
			"data-testid": "diff-rows-capped",
			style: {
				gridColumn: "1 / -1",
				padding: "4px 8px",
				color: "var(--text-muted)"
			},
			children: [
				"… ",
				total - MAX_ROWS,
				" more rows are in the diff and not on screen. The counts above are the whole diff; this pane stops at ",
				MAX_ROWS,
				"."
			]
		});
		const drawn = lines.slice(0, MAX_ROWS);
		return /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
			style: {
				display: "flex",
				flexDirection: "column",
				gap: 8
			},
			children: [/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
				"data-testid": "diff-counts",
				style: {
					fontSize: 12,
					color: "var(--text-muted)"
				},
				children: [
					adds,
					" ",
					adds === 1 ? "line" : "lines",
					" added, ",
					dels,
					" removed.",
					" ",
					/* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", {
						style: mono$1,
						children: "-"
					}),
					" is a line only the earlier version has,",
					" ",
					/* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", {
						style: mono$1,
						children: "+"
					}),
					" a line only the later one has."
				]
			}), mode === "split" ? /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
				"data-testid": "diff-split",
				style: {
					...pane,
					display: "grid",
					gridTemplateColumns: "minmax(0, 1fr) minmax(0, 1fr)"
				},
				children: [drawn.flatMap((line, i) => Array.isArray(line) ? [/* @__PURE__ */ (0, react_jsx_runtime.jsx)(SplitCell, {
					row: line[0],
					side: "left",
					ref: mark(line[0])
				}, `${i}-l`), /* @__PURE__ */ (0, react_jsx_runtime.jsx)(SplitCell, {
					row: line[1],
					side: "right",
					ref: mark(line[1])
				}, `${i}-r`)] : "start" in line ? [/* @__PURE__ */ (0, react_jsx_runtime.jsx)(FoldRow, {
					fold: line,
					onOpen: open
				}, i)] : []), capped]
			}) : /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
				"data-testid": "diff-rows",
				style: pane,
				children: [drawn.map((line, i) => Array.isArray(line) ? null : "start" in line ? /* @__PURE__ */ (0, react_jsx_runtime.jsx)(FoldRow, {
					fold: line,
					onOpen: open
				}, i) : /* @__PURE__ */ (0, react_jsx_runtime.jsx)(UnifiedRow, {
					row: line,
					ref: mark(line)
				}, i)), capped]
			})]
		});
	});
	/**
	* A whole version: rendered markdown for a markdown file, preformatted
	* otherwise. Memoised like DiffView, so a data tick does not re-parse it.
	*/
	var WholeDocument = (0, react.memo)(function WholeDocument({ name, text }) {
		const frame = {
			maxHeight: 480,
			overflow: "auto",
			border: "1px solid var(--border-hairline)",
			borderRadius: "var(--radius-sm)",
			padding: "8px 12px"
		};
		return /\.(md|markdown)$/i.test(name) ? /* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
			"data-testid": "doc-markdown",
			style: frame,
			children: /* @__PURE__ */ (0, react_jsx_runtime.jsx)(Markdown, {
				fontSize: 12.5,
				children: text.replaceAll("![", "!​[")
			})
		}) : /* @__PURE__ */ (0, react_jsx_runtime.jsx)("pre", {
			"data-testid": "doc-plain",
			style: {
				...frame,
				...mono$1,
				fontSize: 11.5,
				whiteSpace: "pre-wrap",
				margin: 0
			},
			children: text
		});
	});
	function DocumentHistory({ runId, document: doc, timeline, intact, legacy, selected, onSelect, diffMode, onDiffMode, onOpenTurn, derived, oneOnOnes, onOpenOneOnOne }) {
		const [finalDiff, setFinalDiff] = (0, react.useState)(false);
		const { name, captured, original, steps, final } = doc;
		const ids = original ? [
			"original",
			...steps.map((s) => s.turn),
			...final ? ["final"] : []
		] : [];
		const current = ids.includes(selected) ? selected : "original";
		const index = ids.indexOf(current);
		const step = typeof current === "number" ? steps.find((s) => s.turn === current) ?? null : null;
		const previous = step ? index > 1 ? steps[index - 2] : original : null;
		const versions = !name || !captured || !original ? [] : step && previous ? [previous, step] : current === "final" && final ? finalDiff ? [original, final] : [final] : [original];
		const unreadable = versions.find((v) => v.bytes === null);
		const { copies, failures, retry } = useCopies(runId, unreadable ? [] : versions);
		const shell = {
			display: "flex",
			flexDirection: "column",
			gap: 12
		};
		if (!name || !original) return /* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
			style: shell,
			children: /* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
				"data-testid": "diff-no-artifacts",
				style: muted,
				children: legacy ? "This run predates the committee view: its reductions never recorded which file the committee was handed, so there is nothing to show either side of. The record does not say the file is gone — it says nothing about it." : "No artifact has been recorded for this run yet. The committee names the file it is reviewing on its first reduction; until then there is nothing to show either side of."
			})
		});
		const fileName = /* @__PURE__ */ (0, react_jsx_runtime.jsx)("code", {
			style: {
				...mono$1,
				fontSize: 11.5
			},
			children: name
		});
		const label = (id) => id === "original" ? "Original" : id === "final" ? "Final" : `Edit ${steps.findIndex((s) => s.turn === id) + 1} (${tNN(id)})`;
		const go = (delta) => {
			const next = ids[index + delta];
			if (next !== void 0) onSelect(next);
		};
		const pending = versions.find((v) => !copies[cacheKey(v)] && failures[cacheKey(v)] === void 0);
		const failed = versions.find((v) => failures[cacheKey(v)] !== void 0);
		const texts = versions.map((v) => copies[cacheKey(v)]);
		let body = null;
		if (versions.length === 0) body = null;
		else if (unreadable) body = /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
			"data-testid": "doc-unreadable",
			style: note("danger"),
			children: [
				"Could not read ",
				/* @__PURE__ */ (0, react_jsx_runtime.jsx)("code", {
					style: mono$1,
					children: unreadable.path
				}),
				" on the server."
			]
		});
		else if (pending) body = /* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
			"data-testid": "doc-loading",
			style: muted,
			children: "Loading…"
		});
		else if (failed) body = /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
			"data-testid": "doc-error",
			style: note("danger"),
			children: [
				"Could not load ",
				/* @__PURE__ */ (0, react_jsx_runtime.jsx)("code", {
					style: mono$1,
					children: failed.path
				}),
				": ",
				failures[cacheKey(failed)],
				" ",
				/* @__PURE__ */ (0, react_jsx_runtime.jsx)("button", {
					type: "button",
					"data-testid": "doc-retry",
					onClick: () => retry(cacheKey(failed)),
					style: chip(false),
					children: "Retry"
				})
			]
		});
		else body = /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
			style: {
				display: "flex",
				flexDirection: "column",
				gap: 8
			},
			children: [texts.some((t) => t.truncated) && /* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
				"data-testid": "diff-truncated",
				style: note("attention"),
				children: "The server cut at least one version short at its read cap, so what follows is a prefix and any counts below are not the whole file."
			}), texts.length === 2 ? /* @__PURE__ */ (0, react_jsx_runtime.jsx)(DiffView, {
				before: texts[0].text,
				after: texts[1].text,
				mode: diffMode
			}, versions.map(cacheKey).join(" ")) : /* @__PURE__ */ (0, react_jsx_runtime.jsx)(WholeDocument, {
				name,
				text: texts[0].text
			})]
		});
		return /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
			style: shell,
			children: [intact === false ? /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
				"data-testid": "diff-original-changed",
				style: note("danger"),
				children: [
					/* @__PURE__ */ (0, react_jsx_runtime.jsx)("strong", { children: "The original CHANGED during this review." }),
					" ",
					fileName,
					" is not byte-for-byte what the committee was handed: the playbook re-checked its digest at the decision and it did not match. The safety guarantee this card normally states did not hold on this run, so read every version below against a file that moved under it, and treat every re-check in the verdict as unreliable."
				]
			}) : /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
				"data-testid": "diff-original-untouched",
				style: note("live"),
				children: [
					/* @__PURE__ */ (0, react_jsx_runtime.jsx)("strong", { children: "The original is never modified." }),
					" ",
					fileName,
					" ",
					intact === true ? "is" : "is meant to be",
					" byte-for-byte what the committee was handed; the playbook re-checks its digest at the decision and says so in the verdict. Every delegated edit lands in the revised copy, which the committee offers as a recommendation, not a landed change. Reading the repository file and finding it unchanged does not mean the edits failed."
				]
			}), !captured ? /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
				"data-testid": "doc-not-captured",
				style: muted,
				children: [
					"No snapshot of this document is readable on the server — not the original's (",
					/* @__PURE__ */ (0, react_jsx_runtime.jsx)("code", {
						style: mono$1,
						children: original.path
					}),
					") nor any edit's — so there is nothing to step through."
				]
			}) : /* @__PURE__ */ (0, react_jsx_runtime.jsxs)(react_jsx_runtime.Fragment, { children: [
				/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
					role: "group",
					"aria-label": "Versions of the document",
					"data-testid": "doc-stepper",
					tabIndex: 0,
					onKeyDown: (e) => {
						if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
						e.preventDefault();
						const next = ids[index + (e.key === "ArrowLeft" ? -1 : 1)];
						if (next === void 0) return;
						onSelect(next);
						e.currentTarget.querySelector(`[data-testid="step-${next}"]`)?.focus();
					},
					style: {
						display: "flex",
						gap: 6,
						alignItems: "center",
						flexWrap: "wrap"
					},
					children: [
						/* @__PURE__ */ (0, react_jsx_runtime.jsx)("button", {
							type: "button",
							"data-testid": "step-prev",
							disabled: index <= 0,
							onClick: () => go(-1),
							style: chip(false),
							children: "‹ Prev"
						}),
						ids.map((id) => /* @__PURE__ */ (0, react_jsx_runtime.jsx)("button", {
							type: "button",
							"data-testid": `step-${id}`,
							"aria-current": id === current ? "step" : void 0,
							onClick: () => onSelect(id),
							style: chip(id === current),
							children: label(id)
						}, String(id))),
						/* @__PURE__ */ (0, react_jsx_runtime.jsx)("button", {
							type: "button",
							"data-testid": "step-next",
							disabled: index >= ids.length - 1,
							onClick: () => go(1),
							style: chip(false),
							children: "Next ›"
						})
					]
				}),
				versions.length === 2 && /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
					role: "group",
					"aria-label": "Diff layout",
					style: {
						display: "flex",
						gap: 4
					},
					children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("button", {
						type: "button",
						"data-testid": "diff-mode-unified",
						"aria-pressed": diffMode === "unified",
						onClick: () => onDiffMode("unified"),
						style: chip(diffMode === "unified"),
						children: "Unified"
					}), /* @__PURE__ */ (0, react_jsx_runtime.jsx)("button", {
						type: "button",
						"data-testid": "diff-mode-split",
						"aria-pressed": diffMode === "split",
						onClick: () => onDiffMode("split"),
						style: chip(diffMode === "split"),
						children: "Side by side"
					})]
				}),
				steps.length === 0 && /* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
					"data-testid": "doc-no-edits",
					style: muted,
					children: "No edit was made. The original stands as it was."
				}),
				doc.dropped_delegation && /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
					"data-testid": "doc-dropped",
					style: note("attention"),
					children: [
						"The turn cap dropped a delegation",
						doc.dropped_delegation.owner_turn !== null ? ` from ${tNN(doc.dropped_delegation.owner_turn)}` : "",
						": ",
						doc.dropped_delegation.action
					]
				}),
				current === "original" && /* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
					"data-testid": "original-label",
					style: heading,
					children: "Original — as the committee was handed it"
				}),
				step && /* @__PURE__ */ (0, react_jsx_runtime.jsx)(StepContext, {
					step,
					timeline,
					onOpenTurn,
					derived,
					oneOnOnes,
					onOpenOneOnOne
				}),
				current === "final" && final && /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
					"data-testid": "final-label",
					style: heading,
					children: [
						FINAL_LABEL[final.ruling],
						/* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", {
							style: {
								fontWeight: 400,
								color: "var(--text-muted)"
							},
							children: final.turn === null ? " — no edit applied, so this is the original" : ` — as the last applied edit (${tNN(final.turn)}) left it`
						}),
						" ",
						/* @__PURE__ */ (0, react_jsx_runtime.jsx)("button", {
							type: "button",
							"data-testid": "final-diff-toggle",
							"aria-pressed": finalDiff,
							onClick: () => setFinalDiff(!finalDiff),
							style: chip(finalDiff),
							children: "Original → final diff"
						})
					]
				}),
				body
			] })]
		});
	}
	//#endregion
	//#region ../playbooks/committee/view/src/CommitteeView.tsx
	/**
	* CommitteeView — a committee run read as the meeting it was.
	*
	* Three surfaces, in the order a reader needs them: where the meeting got to
	* and why it stopped, who is in the room and where each of them stands, and
	* then the conversation itself.
	*
	* The timeline reads OLDEST-FIRST. `web/src/views/Outputs.tsx` sorts newest-id
	* first and is right to: a pipeline's newest reduction is its most aggregated.
	* A conversation is the opposite — turn 1 is the premise every later turn
	* argues with — and reading it backwards is the confusion this view exists to
	* remove.
	*
	* Entries are collapsed to their first line by default. The measured run is
	* 130 KB of prose across twenty turns; expanded by default it is a wall nobody
	* scrolls, and the turn numbers, the badges and the re-check outcomes — the
	* things a reader scans for — are what the collapsed row shows.
	*
	* The host's React, design system and Markdown all arrive on globals and this
	* bundle imports none of them. A second React copy breaks hooks, a second
	* design-system copy doubles 146 KB of vendored bundle, and importing Markdown
	* would inline react-markdown, remark-gfm and the whole unified stack into a
	* committed, unminified artifact.
	*/
	/**
	* What a missing design system degrades to.
	*
	* `web/src/ds/index.ts:getComponent` warns and returns `() => null`, and
	* `host.tsx` falls back to preformatted text rather than throwing. This mirrors
	* that: an unstyled view beats a throw into `PlaybookView`'s error boundary,
	* which is set once and never cleared, so one missing global would leave the
	* pane red for the session.
	*/
	var PLAIN = {
		Card: ({ children }) => /* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", { children }),
		Badge: ({ children }) => /* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", { children }),
		EmptyState: ({ title, description }) => /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", { children: [
			/* @__PURE__ */ (0, react_jsx_runtime.jsx)("strong", { children: title }),
			" ",
			description
		] })
	};
	/**
	* The design-system namespace, resolved exactly as `web/src/ds/index.ts` does.
	* The bundle publishes the hashed name and nothing publishes `DSNS`, so the
	* fallback is the compatibility half of the same expression, not a guess.
	*/
	function ds() {
		const w = window;
		const found = w.MonoDarkDashDesignSystem_66fdfe || w.DSNS;
		if (found) return found;
		console.warn("[committee view] design-system globals missing; rendering unstyled");
		return PLAIN;
	}
	var BADGE_LABEL = {
		request_floor: "asked for the floor",
		delegate: "delegated an edit",
		close: "moved to close",
		signals_only: "signals only, no prose",
		no_turn: "no turn delivered",
		unattributed: "speaker not identified",
		error: "error on this turn",
		voice_flag: "broke the ground rules",
		retaken: "retaken",
		no_pointer: "no pointer",
		no_example: "no example",
		tells: "AI tells"
	};
	var BADGE_TONE = {
		no_turn: "danger",
		error: "danger",
		unattributed: "danger",
		signals_only: "attention",
		voice_flag: "attention"
	};
	/** voice.tells' non-zero counts as plain text, "process 2, turn refs 1": the tells badge's title. */
	function tellsText(voice) {
		const tells = voice?.tells;
		if (!tells || typeof tells !== "object") return void 0;
		return Object.entries(tells).filter(([, n]) => typeof n === "number" && n > 0).map(([kind, n]) => `${kind.replaceAll("_", " ")} ${n}`).join(", ");
	}
	/** spoke · holds_floor · queued · idle · in_one_on_one, as a reader would say it. */
	var ROSTER_STATE = {
		holds_floor: "has the floor",
		queued: "waiting to speak",
		spoke: "spoke",
		idle: "has not spoken",
		in_one_on_one: "in a 1:1"
	};
	/** Drawn solid and live: the seat is speaking now, in the room or in a 1:1. */
	var LIVE_STATES = /* @__PURE__ */ new Set(["holds_floor", "in_one_on_one"]);
	var ENDED_NOTE = {
		"owner closed": "The owner moved to close and the chair ruled.",
		"queue empty": "Everyone who asked for the floor got it.",
		"turn cap": "The meeting ran out of turns before anyone closed it.",
		"chair turn failed": "The chair produced no decision, so the run ended failed.",
		"chair retake failed": "The chair's retake failed, so its earlier take is recorded unruled and the run ended failed."
	};
	var mono = { fontFamily: "var(--font-mono)" };
	function Section({ title, children }) {
		const { Card } = ds();
		return /* @__PURE__ */ (0, react_jsx_runtime.jsx)(Card, {
			padding: "md",
			children: /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
				style: {
					display: "flex",
					flexDirection: "column",
					gap: 10,
					minWidth: 0
				},
				children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
					style: {
						fontSize: 13,
						fontWeight: 600,
						color: "var(--text-primary)"
					},
					children: title
				}), children]
			})
		});
	}
	function ProgressBar({ progress, legacy, derived }) {
		const { Badge } = ds();
		const { turn, cap, holder, queue, ended } = progress;
		const paused = progress.paused ?? null;
		const pct = cap > 0 ? Math.min(100, Math.round(turn / cap * 100)) : 0;
		const outOfTurns = ended === "turn cap" || ended === null && cap > 0 && turn >= cap;
		return /* @__PURE__ */ (0, react_jsx_runtime.jsxs)(Section, {
			title: "Progress",
			children: [
				/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
					style: {
						display: "flex",
						alignItems: "center",
						gap: 10,
						flexWrap: "wrap"
					},
					children: [
						/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("span", {
							"data-testid": "turn-count",
							style: {
								...mono,
								fontSize: 13,
								color: "var(--text-primary)"
							},
							children: [
								"turn ",
								turn,
								" of ",
								cap
							]
						}),
						/* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
							"aria-hidden": true,
							style: {
								flex: 1,
								minWidth: 120,
								height: 4,
								borderRadius: 2,
								background: "var(--wash-subtle)",
								overflow: "hidden"
							},
							children: /* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
								"data-testid": "turn-bar",
								style: {
									width: `${pct}%`,
									height: "100%",
									background: outOfTurns ? "var(--status-attention, #e3b341)" : "var(--status-live, #6ea8fe)"
								}
							})
						}),
						holder ? /* @__PURE__ */ (0, react_jsx_runtime.jsxs)(Badge, {
							size: "sm",
							variant: "solid",
							tone: "live",
							"data-testid": "floor-holder",
							children: [holder, " has the floor"]
						}) : null,
						paused ? /* @__PURE__ */ (0, react_jsx_runtime.jsx)(Badge, {
							size: "sm",
							variant: "outline",
							tone: "live",
							"data-testid": "paused-for-one-on-ones",
							children: pausedLabel(paused, derived)
						}) : null
					]
				}),
				queue.length > 0 && /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
					"data-testid": "floor-queue",
					style: {
						fontSize: 12,
						color: "var(--text-secondary)"
					},
					children: ["Waiting to speak: ", /* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", {
						style: mono,
						children: queue.join(" · ")
					})]
				}),
				ended ? /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
					"data-testid": "ended-reason",
					style: {
						fontSize: 12,
						padding: "6px 8px",
						borderRadius: "var(--radius-md)",
						background: "var(--wash-subtle)",
						border: "1px solid var(--border-hairline)",
						color: ended === "turn cap" || ended === "chair turn failed" || ended === "chair retake failed" ? "var(--status-attention, #e3b341)" : "var(--text-secondary)"
					},
					children: [
						"Ended: ",
						ended,
						". ",
						ENDED_NOTE[ended] ?? ""
					]
				}) : /* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
					"data-testid": "ended-reason",
					style: {
						fontSize: 12,
						color: "var(--text-muted)"
					},
					children: legacy ? "This run predates the committee view: its reductions never recorded why the meeting ended, so the record does not say." : "No ending recorded — the meeting is either still in session or stopped before the chair ruled."
				})
			]
		});
	}
	/** Who put a seat forward, as the roster says it. Null when the row records nobody. */
	function nominated(p) {
		if (p.nominated_by === "fixed") return "fixed seat";
		if (p.nominated_by === "default") return "default seat";
		if (p.nominated_by) return `put forward by ${p.nominated_by_name ?? p.nominated_by}`;
		return null;
	}
	function Roster({ roster, legacy }) {
		const { Badge } = ds();
		return /* @__PURE__ */ (0, react_jsx_runtime.jsx)(Section, {
			title: `Committee — ${roster.length}`,
			children: /* @__PURE__ */ (0, react_jsx_runtime.jsx)("ul", {
				"aria-label": "Committee",
				style: {
					display: "flex",
					flexDirection: "column",
					listStyle: "none",
					margin: 0,
					padding: 0
				},
				children: roster.map((p) => /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("li", {
					"data-testid": `roster-${p.role}`,
					style: {
						display: "flex",
						gap: 10,
						alignItems: "baseline",
						padding: "6px 0",
						borderTop: "1px solid var(--border-hairline)",
						flexWrap: "wrap"
					},
					children: [
						/* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", {
							style: {
								fontSize: 13,
								color: "var(--text-primary)",
								fontWeight: 600
							},
							children: p.name
						}),
						/* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", {
							style: {
								fontSize: 11,
								color: "var(--text-muted)"
							},
							children: p.title
						}),
						/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("span", {
							style: {
								...mono,
								fontSize: 10,
								color: "var(--text-muted)"
							},
							children: [p.role, p.source === "derived" && " · derived seat"]
						}),
						/* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", {
							style: {
								marginLeft: "auto",
								flex: "none"
							},
							children: /* @__PURE__ */ (0, react_jsx_runtime.jsx)(Badge, {
								size: "sm",
								variant: LIVE_STATES.has(p.state) ? "solid" : "outline",
								tone: LIVE_STATES.has(p.state) ? "live" : p.state === "queued" ? "attention" : void 0,
								children: ROSTER_STATE[p.state] ?? p.state
							})
						}),
						p.rationale != null && /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
							style: {
								flexBasis: "100%",
								display: "flex",
								gap: 8,
								flexWrap: "wrap",
								fontSize: 12
							},
							children: [/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("span", {
								"data-testid": `roster-why-${p.role}`,
								style: { color: "var(--text-secondary)" },
								children: ["why: ", p.rationale]
							}), nominated(p) !== null && /* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", {
								"data-testid": `roster-nominated-${p.role}`,
								style: { color: "var(--text-muted)" },
								children: nominated(p)
							})]
						}),
						/* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
							"data-testid": `stance-${p.role}`,
							style: {
								flexBasis: "100%",
								fontSize: 12,
								color: p.stance ? "var(--text-secondary)" : "var(--text-muted)",
								fontStyle: p.stance ? "normal" : "italic"
							},
							children: p.stance ?? (legacy ? "stance not recorded — this run predates the signal" : "no stance stated")
						})
					]
				}, p.role))
			})
		});
	}
	var STAGE_VERB = {
		1: "proposes",
		2: "amends",
		3: "ratifies"
	};
	var selectionNotice = {
		fontSize: 12,
		padding: "6px 8px",
		borderRadius: "var(--radius-md)",
		background: "var(--wash-subtle)",
		border: "1px solid var(--border-hairline)",
		color: "var(--status-attention, #e3b341)"
	};
	var selectionHeading = {
		margin: 0,
		fontSize: 13,
		fontWeight: 600,
		color: "var(--text-primary)"
	};
	var selectionList = {
		margin: 0,
		paddingLeft: 18,
		fontSize: 12,
		color: "var(--text-secondary)"
	};
	var selectionCount = {
		fontSize: 11.5,
		fontStyle: "italic",
		color: "var(--text-muted)"
	};
	/** A derived seat's marker (decision 12): its name is a selector's words, the slug is not. */
	var derivedSeat = (role) => `${role} · derived seat`;
	/**
	* cast.label: "Name, Title", or the title alone for a seat named from its
	* title, so a nameless derived seat never reads "Crew Owner, Crew Owner".
	* Trailing full stops are ignored, and a name ending "…" is the title clipped.
	*/
	function seatLabel(name, title) {
		const bare = (s) => s.replace(/[. ]+$/, "");
		const stem = bare(name.replace(/…$/, ""));
		return bare(name) === bare(title) || name.endsWith("…") && stem !== "" && title.startsWith(stem) ? title : `${name}, ${title}`;
	}
	/**
	* Who speaks for a stakeholder nobody seated, or that nobody does. The name
	* check is exact, so a lookalike name passes it: a derived seat's slug is the defence.
	*/
	function represented(slug, name, isDerived) {
		if (!slug) return "Not represented.";
		return `Represented by ${name ?? slug}${isDerived ? ` (${derivedSeat(slug)})` : ""}.`;
	}
	/** selection.fallback_words: a stage or fallback code as thread.md says it; an unknown code is itself. */
	var WORDS = {
		chair_failed: "the chair gave no usable list",
		no_block: "no hermes-selection block",
		unparseable: "a hermes-selection block that did not parse",
		too_few: "no valid seats"
	};
	/** "kept take 2 of 2; broke: …" when a take was retaken or kept flagged, else nothing. */
	function KeptTake({ take, takes, violations, testId }) {
		if (take == null || takes == null || takes <= 1 && violations.length === 0) return null;
		return /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
			"data-testid": testId,
			style: {
				fontSize: 11.5,
				marginBottom: 6,
				color: "var(--text-muted)"
			},
			children: [
				"kept take ",
				take,
				" of ",
				takes,
				violations.length > 0 && `; broke: ${violationText(violations)}`
			]
		});
	}
	function SelectionCard({ selection, runId, derived }) {
		const { Badge } = ds();
		const settled = selection.state === "seated" || selection.state === "fallback";
		const considered = selection.considered_dropped ?? 0;
		const invalid = selection.invalid_dropped ?? 0;
		return /* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
			"data-testid": "selection-card",
			children: /* @__PURE__ */ (0, react_jsx_runtime.jsxs)(Section, {
				title: "Selection",
				children: [
					selection.fallback && /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
						"data-testid": "selection-fallback",
						style: selectionNotice,
						children: [
							"Default committee: selection fell back (",
							WORDS[selection.fallback] ?? selection.fallback,
							")"
						]
					}),
					selection.state === "lost" && /* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
						"data-testid": "selection-lost",
						style: selectionNotice,
						children: "Selection stopped: the meeting was lost."
					}),
					selection.stages.map((st, i) => /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
						"data-testid": `selection-stage-${st.stage}`,
						style: {
							display: "flex",
							flexDirection: "column",
							gap: 6,
							paddingTop: 8,
							borderTop: "1px solid var(--border-hairline)"
						},
						children: [
							/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
								style: {
									display: "flex",
									gap: 8,
									alignItems: "baseline",
									flexWrap: "wrap"
								},
								children: [/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
									style: selectionHeading,
									children: [
										st.name,
										" (",
										st.role,
										") ",
										STAGE_VERB[st.stage] ?? ""
									]
								}), st.badges.map((b) => /* @__PURE__ */ (0, react_jsx_runtime.jsx)(Badge, {
									size: "sm",
									variant: "outline",
									tone: BADGE_TONE[b],
									children: BADGE_LABEL[b] ?? b
								}, b))]
							}),
							/* @__PURE__ */ (0, react_jsx_runtime.jsx)(KeptTake, {
								take: st.take,
								takes: st.takes,
								violations: st.violations,
								testId: `selection-kept-take-${st.stage}`
							}),
							/* @__PURE__ */ (0, react_jsx_runtime.jsx)(Segments, {
								segments: st.segments,
								runId
							}),
							st.proposed.length > 0 && /* @__PURE__ */ (0, react_jsx_runtime.jsx)("ul", {
								"data-testid": `selection-proposed-${st.stage}`,
								"aria-label": `Seats ${st.name} listed`,
								style: selectionList,
								children: st.proposed.map((p, j) => /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("li", { children: [
									p.source === "derived" || derived.has(p.role) ? derivedSeat(p.role) : p.role,
									":",
									" ",
									seatLabel(p.name, p.title),
									". Why: ",
									p.rationale
								] }, j))
							}),
							(st.proposed_dropped ?? 0) > 0 && /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
								style: selectionCount,
								children: [st.proposed_dropped, " more not listed."]
							}),
							!!st.not_seated?.length && /* @__PURE__ */ (0, react_jsx_runtime.jsx)("ul", {
								"data-testid": `selection-left-out-${st.stage}`,
								"aria-label": `Left out by ${st.name}`,
								style: selectionList,
								children: st.not_seated.map((n, j) => /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("li", { children: [
									"Left out: ",
									n.stakeholder,
									": ",
									n.reason.replace(/\.$/, ""),
									".",
									" ",
									represented(n.represented_by, n.represented_by_name, derived.has(n.represented_by ?? "") || st.proposed.some((p) => p.role === n.represented_by && p.source === "derived"))
								] }, j))
							}),
							(st.not_seated_dropped ?? 0) > 0 && /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
								style: selectionCount,
								children: [st.not_seated_dropped, " more left out, not listed."]
							}),
							(st.invalid_count ?? 0) > 0 && /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
								style: selectionCount,
								children: [st.invalid_count, " invalid entries, not listed."]
							}),
							st.code && st.code !== "no_answer" && /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
								"data-testid": `selection-code-${st.stage}`,
								style: selectionCount,
								children: ["no usable seat list: ", WORDS[st.code] ?? st.code]
							})
						]
					}, i)),
					selection.current && /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
						"data-testid": "selection-current",
						style: {
							fontSize: 12,
							color: "var(--text-secondary)"
						},
						children: [
							selection.current.name,
							" is ",
							selection.current.verb,
							" the committee."
						]
					}),
					settled && /* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
						"data-testid": "selection-considered",
						style: {
							display: "flex",
							flexDirection: "column",
							gap: 4,
							fontSize: 12,
							color: "var(--text-secondary)"
						},
						children: selection.considered.length === 0 && considered + invalid === 0 ? "Everyone considered was seated." : /* @__PURE__ */ (0, react_jsx_runtime.jsxs)(react_jsx_runtime.Fragment, { children: [
							/* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
								style: selectionHeading,
								children: "Considered, not seated"
							}),
							selection.considered.length > 0 && /* @__PURE__ */ (0, react_jsx_runtime.jsx)("ul", {
								"aria-label": "Considered, not seated",
								style: selectionList,
								children: selection.considered.map((c, j) => /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("li", { children: [
									c.stakeholder,
									": ",
									c.reason.replace(/\.$/, ""),
									".",
									" ",
									represented(c.represented_by, c.represented_by_name, derived.has(c.represented_by ?? ""))
								] }, j))
							}),
							considered > 0 && /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
								style: selectionCount,
								children: [considered, " more considered, not listed."]
							}),
							invalid > 0 && /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
								style: selectionCount,
								children: [invalid, " more invalid entries, not listed."]
							})
						] })
					})
				]
			})
		});
	}
	/** playbook.ONE_ON_ONE_MAX_EXCHANGES: member exchanges per 1:1, the closing one aside. */
	var MAX_EXCHANGES = 4;
	/**
	* `Host ↔ Guest`, or `A ↔ B, hosted by H` when the host sits in neither seat.
	* A derived seat's name carries its marker, as on every other surface.
	*/
	function pairLabel({ host, members }, derived = /* @__PURE__ */ new Set()) {
		const who = (p) => derived.has(p.role) ? `${p.name} (${derivedSeat(p.role)})` : p.name;
		const [a, b] = members;
		if (a.role !== host.role && b.role !== host.role) return `${who(a)} ↔ ${who(b)}, hosted by ${who(host)}`;
		return `${who(host)} ↔ ${who(a.role === host.role ? b : a)}`;
	}
	function pausedLabel({ pairs, current }, derived = /* @__PURE__ */ new Set()) {
		const now = current ? pairs.find((p) => p.seq === current.seq) : void 0;
		if (current && now) {
			const at = current.exchange === null ? "closing" : `exchange ${current.exchange} of ${MAX_EXCHANGES}`;
			return `Paused for 1:1s: ${pairLabel(now, derived)} (${at})`;
		}
		return `1:1s next: ${pairs.map((p) => pairLabel(p, derived)).join(", ")}`;
	}
	/** The collapsed header's word on the 1:1. */
	function outcomeLine(g) {
		if (g.ended === null) return "in progress";
		return g.aligned ? "aligned" : `not aligned (${g.ended})`;
	}
	/**
	* What the room reads, worded as thread.md's outcome entry words it. The
	* payload carries no `closing_delivered`, but the closing exchange is kept
	* either way, so an undelivered one is visible in `exchanges`.
	*/
	function outcomeLines(g) {
		if (g.ended === null) return ["in progress"];
		const lines = [];
		if (g.agreed !== null) lines.push(`Agreed: ${g.agreed}`);
		if (g.still_open !== null) lines.push(`Still open: ${g.still_open}`);
		if (lines.length > 0) return lines;
		return [`no outcome recorded: ${g.exchanges.some((x) => x.closing && !x.delivered) ? "the host's closing exchange was not delivered" : g.ended}`];
	}
	function OneOnOneGroup({ g, runId, open, onToggle, derived, edit, onSeeEdit }) {
		const { Badge } = ds();
		return /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
			"data-testid": `one-on-one-${g.seq}`,
			style: {
				borderTop: "1px solid var(--border-hairline)",
				padding: "8px 0"
			},
			children: [
				/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("button", {
					type: "button",
					"aria-expanded": open,
					onClick: onToggle,
					style: {
						display: "flex",
						gap: 8,
						alignItems: "baseline",
						width: "100%",
						textAlign: "left",
						background: "none",
						border: "none",
						padding: 0,
						cursor: "pointer",
						flexWrap: "wrap"
					},
					children: [
						/* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", {
							"aria-hidden": true,
							style: {
								color: "var(--text-muted)",
								fontSize: 10,
								width: 10
							},
							children: open ? "▾" : "▸"
						}),
						/* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", {
							style: {
								fontSize: 13,
								fontWeight: 600,
								color: "var(--text-primary)"
							},
							children: `1:1 ${g.seq}: ${pairLabel(g, derived)} · ${outcomeLine(g)}`
						}),
						/* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", {
							style: {
								fontSize: 11,
								color: "var(--text-muted)"
							},
							children: g.topic
						})
					]
				}),
				/* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
					"data-testid": `one-on-one-outcome-${g.seq}`,
					style: {
						marginTop: 4,
						marginLeft: 18,
						fontSize: 11.5,
						lineHeight: 1.45,
						color: "var(--text-secondary)"
					},
					children: outcomeLines(g).map((line) => /* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", { children: line }, line))
				}),
				edit !== void 0 && /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("button", {
					type: "button",
					"data-testid": `see-edit-one-on-one-${g.seq}`,
					onClick: onSeeEdit,
					style: {
						marginTop: 4,
						marginLeft: 18,
						padding: "0 6px",
						fontSize: 11,
						color: "var(--text-primary)",
						background: "none",
						border: "1px solid var(--border-hairline)",
						borderRadius: "var(--radius-sm)",
						cursor: "pointer"
					},
					children: ["see edit ", edit]
				}),
				open && /* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
					style: {
						display: "flex",
						flexDirection: "column",
						gap: 8,
						marginTop: 6,
						paddingLeft: 18
					},
					children: g.exchanges.map((x, i) => /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", { children: [/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
						style: {
							display: "flex",
							gap: 8,
							alignItems: "baseline",
							flexWrap: "wrap"
						},
						children: [
							/* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", {
								style: {
									...mono,
									fontSize: 11,
									color: "var(--text-muted)"
								},
								children: x.closing ? "outcome" : `exchange ${x.exchange}`
							}),
							/* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", {
								style: {
									fontSize: 12,
									fontWeight: 600,
									color: "var(--text-primary)"
								},
								children: x.name
							}),
							/* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", {
								style: {
									...mono,
									fontSize: 10,
									color: "var(--text-muted)"
								},
								children: derived.has(x.speaker) ? derivedSeat(x.speaker) : x.speaker
							}),
							x.badges.map((b) => /* @__PURE__ */ (0, react_jsx_runtime.jsx)(Badge, {
								size: "sm",
								variant: "outline",
								tone: BADGE_TONE[b],
								children: BADGE_LABEL[b] ?? b
							}, b))
						]
					}), x.segments.length > 0 ? /* @__PURE__ */ (0, react_jsx_runtime.jsx)(Segments, {
						segments: x.segments,
						runId
					}) : /* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", {
						style: {
							fontSize: 12,
							fontStyle: "italic",
							color: "var(--text-muted)"
						},
						children: "no prose recorded for this exchange"
					})] }, i))
				})
			]
		});
	}
	function TimelineEntry({ runId, entry, open, onToggle, edit, onSeeEdit, derived }) {
		const { Badge } = ds();
		const segments = entry.segments ?? (entry.body ? [{
			kind: "text",
			text: entry.body
		}] : []);
		const firstText = segments.find((seg) => seg.kind === "text");
		const firstLine = (firstText?.kind === "text" ? firstText.text : "").split("\n").find((l) => l.trim()) ?? "";
		const violations = entry.violations ?? [];
		const noProse = /* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", {
			style: { fontStyle: "italic" },
			children: "no prose recorded for this turn"
		});
		return /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
			"data-testid": `entry-${entry.n}`,
			style: {
				borderTop: "1px solid var(--border-hairline)",
				padding: "8px 0"
			},
			children: [
				/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("button", {
					type: "button",
					"aria-expanded": open,
					onClick: onToggle,
					style: {
						display: "flex",
						gap: 8,
						alignItems: "baseline",
						width: "100%",
						textAlign: "left",
						background: "none",
						border: "none",
						padding: 0,
						cursor: "pointer",
						flexWrap: "wrap"
					},
					children: [
						/* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", {
							"aria-hidden": true,
							style: {
								color: "var(--text-muted)",
								fontSize: 10,
								width: 10
							},
							children: open ? "▾" : "▸"
						}),
						/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("span", {
							style: {
								...mono,
								fontSize: 11,
								color: "var(--text-muted)"
							},
							children: ["t", String(entry.n).padStart(2, "0")]
						}),
						/* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", {
							style: {
								fontSize: 13,
								fontWeight: 600,
								color: "var(--text-primary)"
							},
							children: entry.name
						}),
						/* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", {
							style: {
								fontSize: 11,
								color: "var(--text-muted)"
							},
							children: entry.title
						}),
						derived && /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("span", {
							style: {
								...mono,
								fontSize: 10,
								color: "var(--text-muted)"
							},
							children: [entry.role, " · derived seat"]
						}),
						entry.badges.map((b) => /* @__PURE__ */ (0, react_jsx_runtime.jsx)(Badge, {
							size: "sm",
							variant: "outline",
							tone: BADGE_TONE[b],
							title: b === "tells" ? tellsText(entry.voice) : void 0,
							children: BADGE_LABEL[b] ?? b
						}, b)),
						entry.verified !== null && /* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", {
							"data-testid": `timeline-recheck-${entry.n}`,
							style: {
								fontSize: 11,
								fontWeight: 600,
								color: entry.verified ? "var(--status-ok, #7ee787)" : "var(--status-danger, #f85149)"
							},
							children: entry.verified ? "re-check: APPLIED" : "re-check: DID NOT APPLY"
						})
					]
				}),
				entry.action !== null && /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
					"data-testid": `action-${entry.n}`,
					style: {
						marginTop: 4,
						marginLeft: 18,
						padding: "4px 8px",
						fontSize: 11.5,
						lineHeight: 1.45,
						color: "var(--text-secondary)",
						background: "var(--wash-subtle)",
						borderLeft: "2px solid var(--border-hairline)",
						borderRadius: "var(--radius-sm)"
					},
					children: ["delegated: ", entry.action]
				}),
				edit !== void 0 && /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("button", {
					type: "button",
					"data-testid": `see-edit-${entry.n}`,
					onClick: onSeeEdit,
					style: {
						marginTop: 4,
						marginLeft: 18,
						padding: "0 6px",
						fontSize: 11,
						color: "var(--text-primary)",
						background: "none",
						border: "1px solid var(--border-hairline)",
						borderRadius: "var(--radius-sm)",
						cursor: "pointer"
					},
					children: ["see edit ", edit]
				}),
				open ? /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
					style: {
						marginTop: 6,
						paddingLeft: 18,
						color: "var(--text-muted)"
					},
					children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)(KeptTake, {
						take: entry.take,
						takes: entry.takes,
						violations,
						testId: `kept-take-${entry.n}`
					}), segments.length > 0 ? /* @__PURE__ */ (0, react_jsx_runtime.jsx)(Segments, {
						segments,
						runId
					}) : noProse]
				}) : /* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
					style: {
						marginTop: 2,
						paddingLeft: 18,
						fontSize: 12,
						color: "var(--text-muted)",
						overflow: "hidden",
						textOverflow: "ellipsis",
						whiteSpace: "nowrap"
					},
					children: firstLine || noProse
				})
			]
		});
	}
	function Timeline({ runId, timeline, open, setOpen, edits, onSeeEdit, derived, oneOnOnes, group }) {
		const allOpen = timeline.length > 0 && open.size === timeline.length;
		const ordered = [...timeline].sort((a, b) => a.n - b.n);
		const between = (lo, hi) => oneOnOnes.filter((g) => g.after_turn >= lo && g.after_turn < hi).map(group);
		return /* @__PURE__ */ (0, react_jsx_runtime.jsxs)(Section, {
			title: `Transcript — ${timeline.length} turns, oldest first`,
			children: [
				/* @__PURE__ */ (0, react_jsx_runtime.jsx)("button", {
					type: "button",
					"data-testid": "expand-all",
					onClick: () => setOpen(allOpen ? /* @__PURE__ */ new Set() : new Set(ordered.map((e) => e.n))),
					style: {
						alignSelf: "flex-start",
						padding: "2px 8px",
						fontSize: 11,
						color: "var(--text-primary)",
						background: "var(--wash-subtle)",
						border: "1px solid var(--border-hairline)",
						borderRadius: "var(--radius-md)",
						cursor: "pointer"
					},
					children: allOpen ? "Collapse all" : "Expand all"
				}),
				between(-Infinity, ordered[0]?.n ?? Infinity),
				ordered.map((entry, i) => /* @__PURE__ */ (0, react_jsx_runtime.jsxs)(react.Fragment, { children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)(TimelineEntry, {
					runId,
					entry,
					open: open.has(entry.n),
					edit: edits.get(entry.n)?.[0],
					onSeeEdit: () => onSeeEdit(edits.get(entry.n)[1]),
					derived: derived.has(entry.role),
					onToggle: () => setOpen((prev) => {
						const next = new Set(prev);
						if (next.has(entry.n)) next.delete(entry.n);
						else next.add(entry.n);
						return next;
					})
				}), between(entry.n, ordered[i + 1]?.n ?? Infinity)] }, entry.n))
			]
		});
	}
	function Bar({ value, max }) {
		return /* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
			"aria-hidden": true,
			style: {
				flex: 1,
				height: 4,
				borderRadius: 2,
				background: "var(--wash-subtle)"
			},
			children: /* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", { style: {
				width: `${max > 0 ? value / max * 100 : 0}%`,
				height: "100%",
				borderRadius: 2,
				background: "var(--status-live, #6ea8fe)"
			} })
		});
	}
	var quiet = {
		fontSize: 12,
		color: "var(--text-secondary)"
	};
	var row = {
		display: "flex",
		alignItems: "center",
		gap: 8,
		fontSize: 12
	};
	/** Every voice.summary key, in C11 order, as a reader would say it. */
	var VOICE_LABEL = [
		["owner_reviewer_median_words", "median words, owner and reviewers"],
		["owner_reviewer_pct_within_cap", "% owner and reviewer turns within the cap"],
		["median_words_by_role", "median words by role"],
		["chair_words", "chair words"],
		["chair_headers", "chair headers"],
		["chair_tables", "chair tables"],
		["junior_turns", "junior IC reports"],
		["junior_pct_compliant", "% junior IC reports in one sentence of 40 words or fewer"],
		["pct_clean_format", "% turns with no bold, headers, tables or nesting"],
		["pct_first_line_le_25", "% owner and reviewer first lines of 25 words or fewer"],
		["unquoted_dashes", "dashes outside quotes"],
		["reviewer_pct_with_pointer", "% reviewer turns with a pointer"],
		["max_turn_refs", "most turn-number references in one turn"],
		["unchanged_mentions_junior_chair", "mentions of the original being unchanged, junior IC and chair"],
		["total_takes", "takes dispatched"],
		["retakes_by_role", "retakes by role"],
		["kept_flagged", "turns kept with broken rules"]
	];
	/** A number as itself, a missing one as a dash, a per-role map as `role n, role n`. */
	function voiceValue(value) {
		if (value === null || value === void 0) return "—";
		if (typeof value === "object") return Object.entries(value).map(([role, n]) => `${role} ${n ?? "—"}`).join(", ");
		return String(value);
	}
	/**
	* The Metrics '1:1s' line. It is never hidden: a run whose 1:1s were off, or
	* one that predates them, says which rather than dropping the section. It
	* names no seat, so it needs no derived-seat marker.
	*/
	function oneOnOneCount(data) {
		const tally = data.progress.one_on_one ?? null;
		if (tally === null) return "1:1s not recorded for this run";
		if (tally.budget < 2) return "1:1s were off for this run";
		const groups = data.one_on_ones ?? [];
		const finished = groups.filter((g) => g.ended !== null).length;
		const aligned = groups.filter((g) => g.aligned === true).length;
		return `${finished} 1:1s · ${tally.used} of ${tally.budget} exchanges · ${aligned} aligned`;
	}
	function MeetingMetrics({ data, derived }) {
		const turns = [...data.timeline].sort((a, b) => a.n - b.n);
		const delivered = (e) => !e.badges.includes("no_turn");
		const over = data.verdict !== null;
		const voice = data.voice ?? null;
		const seats = [...data.roster.map((p) => ({
			key: p.role,
			name: p.name,
			derived: p.source === "derived",
			of: (e) => e.role === p.role
		})), {
			key: "unattributed",
			name: "speaker not identified",
			derived: false,
			of: (e) => e.badges.includes("unattributed")
		}].map((s) => ({
			...s,
			took: turns.filter(s.of)
		})).filter((s) => s.key !== "unattributed" || s.took.length > 0);
		const most = Math.max(...seats.map((s) => s.took.length));
		const ownerTurns = turns.filter((e) => e.role === "owner" && delivered(e));
		const delegated = ownerTurns.filter((e) => e.badges.includes("delegate") && e.action !== null);
		const checked = turns.filter((e) => e.verified !== null);
		const applied = checked.filter((e) => e.verified).length;
		const asks = [];
		for (const e of turns) {
			if (e.badges.includes("unattributed")) continue;
			const waiting = asks.find((a) => a.role === e.role && a.got === null);
			if (waiting) waiting.got = e.n;
			if (delivered(e) && e.badges.includes("request_floor") && !["owner", "junior_ic"].includes(e.role)) asks.push({
				name: e.name,
				role: e.role,
				asked: e.n,
				got: null
			});
		}
		let sofar = 0;
		const growth = turns.map((e) => {
			if (delivered(e) && !e.badges.includes("signals_only")) sofar += Array.from(e.body).length;
			return {
				n: e.n,
				sofar
			};
		});
		return /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
			"data-testid": "committee-metrics",
			style: {
				display: "flex",
				flexDirection: "column",
				gap: 16
			},
			children: [
				!over && /* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
					"data-testid": "metrics-partial",
					style: quiet,
					children: turns.length > 0 ? `Through turn ${turns[turns.length - 1].n}; no verdict yet.` : "Before the first turn; no verdict yet."
				}),
				/* @__PURE__ */ (0, react_jsx_runtime.jsx)(Section, {
					title: "Turns taken",
					children: seats.map((s) => {
						const missed = s.took.filter((e) => !delivered(e)).length;
						return /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
							"data-testid": `turns-${s.key}`,
							style: row,
							children: [
								/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("span", {
									style: {
										width: 130,
										flex: "none",
										color: "var(--text-primary)"
									},
									children: [s.name, s.derived && /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("span", {
										style: {
											...mono,
											display: "block",
											fontSize: 10,
											color: "var(--text-muted)"
										},
										children: [s.key, " · derived seat"]
									})]
								}),
								/* @__PURE__ */ (0, react_jsx_runtime.jsx)(Bar, {
									value: s.took.length,
									max: most
								}),
								/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("span", {
									style: {
										...mono,
										flex: "none"
									},
									children: [s.took.length, missed > 0 && ` · ${missed} not delivered`]
								})
							]
						}, s.key);
					})
				}),
				/* @__PURE__ */ (0, react_jsx_runtime.jsxs)(Section, {
					title: "Delegated edits",
					children: [
						/* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
							"data-testid": "delegation-rate",
							style: quiet,
							children: ownerTurns.length > 0 ? `${delegated.length} of ${ownerTurns.length} delivered owner turns delegated an edit` : "The owner has not spoken yet."
						}),
						/* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
							"data-testid": "edit-rechecks",
							style: quiet,
							children: checked.length > 0 ? `${checked.length} re-checked: ${applied} applied · ${checked.length - applied} did not apply` : "No edit has been re-checked yet."
						}),
						data.verdict?.dropped_delegation && /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
							"data-testid": "edit-dropped",
							style: quiet,
							children: ["Cut off by the turn cap: ", data.verdict.dropped_delegation]
						})
					]
				}),
				/* @__PURE__ */ (0, react_jsx_runtime.jsx)(Section, {
					title: "1:1s",
					children: /* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
						"data-testid": "one-on-one-count",
						style: quiet,
						children: oneOnOneCount(data)
					})
				}),
				/* @__PURE__ */ (0, react_jsx_runtime.jsxs)(Section, {
					title: "Floor requests",
					children: [/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
						"data-testid": "floor-asks",
						style: {
							display: "flex",
							flexDirection: "column",
							gap: 4
						},
						children: [asks.length === 0 && /* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
							style: quiet,
							children: "Nobody asked for the floor."
						}), asks.map((a) => /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
							"data-testid": `floor-ask-${a.asked}`,
							style: quiet,
							children: [
								a.name,
								derived.has(a.role) && ` (${derivedSeat(a.role)})`,
								" asked on turn ",
								a.asked,
								" ·",
								" ",
								a.got !== null ? `got the floor on turn ${a.got}, ${a.got - a.asked} turns later` : over ? "the meeting ended first" : "still waiting"
							]
						}, a.asked))]
					}), /* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
						style: {
							fontSize: 11,
							color: "var(--text-muted)"
						},
						children: "Counted in turns: the record keeps no clock."
					})]
				}),
				/* @__PURE__ */ (0, react_jsx_runtime.jsx)(Section, {
					title: "Voice",
					children: voice ? /* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
						"data-testid": "voice-metrics",
						style: {
							display: "flex",
							flexDirection: "column",
							gap: 4
						},
						children: VOICE_LABEL.map(([key, label]) => /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
							"data-testid": `voice-metric-${key}`,
							style: row,
							children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", {
								style: {
									flex: 1,
									color: "var(--text-secondary)"
								},
								children: label
							}), /* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", {
								style: {
									...mono,
									flex: "none"
								},
								children: voiceValue(voice[key])
							})]
						}, key))
					}) : /* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
						"data-testid": "voice-not-measured",
						style: quiet,
						children: "not measured for this run"
					})
				}),
				/* @__PURE__ */ (0, react_jsx_runtime.jsx)(Section, {
					title: "Thread growth",
					children: /* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
						"data-testid": "thread-growth",
						style: {
							display: "flex",
							flexDirection: "column",
							gap: 8
						},
						children: sofar === 0 ? /* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
							style: quiet,
							children: "No prose recorded for these turns."
						}) : /* @__PURE__ */ (0, react_jsx_runtime.jsxs)(react_jsx_runtime.Fragment, { children: [/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
							style: quiet,
							children: [
								sofar.toLocaleString("en-US"),
								" characters of prose over ",
								turns.length,
								" turns"
							]
						}), /* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
							style: {
								display: "flex",
								alignItems: "flex-end",
								gap: 2,
								height: 48
							},
							children: growth.map((g) => /* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
								"data-testid": `growth-${g.n}`,
								title: `turn ${g.n}: ${g.sofar.toLocaleString("en-US")} characters so far`,
								style: {
									flex: 1,
									height: `${g.sofar / sofar * 100}%`,
									minHeight: 1,
									background: "var(--status-live, #6ea8fe)"
								}
							}, g.n))
						})] })
					})
				})
			]
		});
	}
	/** D5, the rubric's order: the three judge dimensions, then the three deterministic ones. */
	var EVAL_ORDER = [
		"verdict_grounded",
		"edits_address_concerns",
		"concern_coverage",
		"efficiency",
		"concision",
		"verdict_consistency"
	];
	var cell = {
		padding: "4px 10px 4px 0",
		borderTop: "1px solid var(--border-hairline)",
		textAlign: "left",
		verticalAlign: "baseline"
	};
	function EvaluationBlock({ runId, evaluation, scorable }) {
		const { Badge } = ds();
		const command = /* @__PURE__ */ (0, react_jsx_runtime.jsx)("code", {
			style: mono,
			children: `.venv/bin/python -m playbooks.committee.eval_cli run ${runId}`
		});
		let body;
		if (evaluation === null && !scorable) body = /* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
			"data-testid": "evaluation-empty",
			style: quiet,
			children: "Not evaluated: a run can be scored once the chair has delivered its verdict."
		});
		else if (evaluation === null) body = /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
			"data-testid": "evaluation-empty",
			style: quiet,
			children: [
				"Not evaluated. Score it with ",
				command,
				" from the hermes checkout, with HERMES_HOME set to this control plane's home."
			]
		});
		else if (evaluation.state === "error") body = /* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
			"data-testid": "evaluation-error",
			style: {
				...quiet,
				color: "var(--status-danger, #f85149)"
			},
			children: evaluation.error
		});
		else {
			const dims = evaluation.dimensions;
			const ids = [...EVAL_ORDER.filter((id) => id in dims), ...Object.keys(dims).filter((id) => !EVAL_ORDER.includes(id))];
			const flags = /* @__PURE__ */ new Map();
			for (const f of evaluation.flags) flags.set(f, (flags.get(f) ?? 0) + 1);
			body = /* @__PURE__ */ (0, react_jsx_runtime.jsxs)(react_jsx_runtime.Fragment, { children: [
				/* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
					"data-testid": "evaluation-headline",
					style: {
						fontSize: 12,
						color: "var(--text-primary)"
					},
					children: evaluation.headline
				}),
				evaluation.judge_status !== "ok" && /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
					"data-testid": "evaluation-judge-status",
					style: {
						...quiet,
						color: "var(--status-attention, #e3b341)"
					},
					children: [
						"Judge ",
						evaluation.judge_status ?? "status unknown",
						evaluation.judge_error ? `: ${evaluation.judge_error}` : ""
					]
				}),
				/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("table", {
					"aria-label": "Evaluation scores",
					style: {
						borderCollapse: "collapse",
						width: "100%",
						fontSize: 12
					},
					children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("thead", { children: /* @__PURE__ */ (0, react_jsx_runtime.jsx)("tr", { children: [
						"dimension",
						"score",
						"scorer",
						"evidence"
					].map((h) => /* @__PURE__ */ (0, react_jsx_runtime.jsx)("th", {
						style: {
							...cell,
							borderTop: "none",
							fontSize: 11,
							fontWeight: 500,
							color: "var(--text-muted)"
						},
						children: h
					}, h)) }) }), /* @__PURE__ */ (0, react_jsx_runtime.jsx)("tbody", { children: ids.map((id) => {
						const d = dims[id];
						return /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("tr", {
							"data-testid": `eval-dim-${id}`,
							children: [
								/* @__PURE__ */ (0, react_jsx_runtime.jsx)("td", {
									style: {
										...cell,
										whiteSpace: "nowrap",
										color: "var(--text-primary)"
									},
									children: id.replace(/_/g, " ")
								}),
								/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("td", {
									style: {
										...cell,
										whiteSpace: "nowrap"
									},
									children: [/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("span", {
										"data-testid": `eval-score-${id}`,
										style: mono,
										children: [d.score === null ? /* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", {
											"aria-label": "not scored",
											children: "—"
										}) : d.score, d.stale && "*"]
									}), d.scorer === "judge" && d.calibration !== "calibrated" && /* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", {
										style: { marginLeft: 6 },
										children: /* @__PURE__ */ (0, react_jsx_runtime.jsx)(Badge, {
											"data-testid": `eval-uncalibrated-${id}`,
											size: "sm",
											variant: "outline",
											tone: "attention",
											children: d.calibration ?? "uncalibrated"
										})
									})]
								}),
								/* @__PURE__ */ (0, react_jsx_runtime.jsx)("td", {
									style: {
										...cell,
										color: "var(--text-muted)"
									},
									children: d.scorer
								}),
								/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("td", {
									style: {
										...cell,
										width: "100%",
										overflowWrap: "anywhere",
										color: d.quote ? "var(--text-secondary)" : "var(--text-muted)"
									},
									children: [d.quote ?? "no verified quote", d.rationale && /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("details", {
										"data-testid": `eval-why-${id}`,
										children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("summary", {
											style: {
												cursor: "pointer",
												color: "var(--text-muted)"
											},
											children: "why"
										}), /* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
											style: {
												whiteSpace: "pre-wrap",
												color: "var(--text-secondary)"
											},
											children: d.rationale
										})]
									})]
								})
							]
						}, id);
					}) })]
				}),
				ids.some((id) => dims[id].stale) && /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
					"data-testid": "eval-stale-note",
					style: quiet,
					children: ["* older definition; re-run ", command]
				}),
				/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
					"data-testid": "eval-flags",
					style: quiet,
					children: [
						"Flags:",
						" ",
						flags.size === 0 ? "none" : [...flags].map(([id, n]) => n > 1 ? `${id} ×${n}` : id).join(" · ")
					]
				}),
				/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
					"data-testid": "evaluation-rubric",
					style: {
						...mono,
						fontSize: 11,
						color: "var(--text-muted)"
					},
					children: ["rubric ", evaluation.rubric_version ?? "unknown"]
				})
			] });
		}
		return /* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
			"data-testid": "evaluation",
			children: /* @__PURE__ */ (0, react_jsx_runtime.jsx)(Section, {
				title: "Evaluation",
				children: body
			})
		});
	}
	function CommitteeView({ runId, data, variant }) {
		const { EmptyState } = ds();
		const [selected, setSelected] = (0, react.useState)("original");
		const [open, setOpen] = (0, react.useState)(/* @__PURE__ */ new Set());
		const [diffMode, setDiffMode] = (0, react.useState)("unified");
		const [openGroups, setOpenGroups] = (0, react.useState)(/* @__PURE__ */ new Set());
		const openOneOnOne = (seq) => {
			setOpenGroups((prev) => new Set(prev).add(seq));
			window.document.querySelector(`[data-testid="one-on-one-${seq}"]`)?.scrollIntoView?.({ block: "center" });
		};
		const legacy = data.timeline.length > 0 && data.document.name === null || data.verdict !== null && data.progress.ended === null;
		const derived = new Set(data.roster.filter((p) => p.source === "derived").map((p) => p.role));
		const oneOnOnes = [...data.one_on_ones ?? []].sort((a, b) => a.seq - b.seq);
		const oneOnOneEdits = /* @__PURE__ */ new Map();
		if (data.document.captured) data.document.steps.forEach((step, i) => {
			if (typeof step.origin_one_on_one === "number") oneOnOneEdits.set(step.origin_one_on_one, [i + 1, step.turn]);
		});
		const group = (g) => /* @__PURE__ */ (0, react_jsx_runtime.jsx)(OneOnOneGroup, {
			g,
			runId,
			open: openGroups.has(g.seq),
			edit: oneOnOneEdits.get(g.seq)?.[0],
			onSeeEdit: () => {
				const e = oneOnOneEdits.get(g.seq);
				if (e) seeEdit(e[1]);
			},
			onToggle: () => setOpenGroups((prev) => {
				const next = new Set(prev);
				if (next.has(g.seq)) next.delete(g.seq);
				else next.add(g.seq);
				return next;
			}),
			derived
		}, `oneonone-${g.seq}`);
		const openTurn = (n) => {
			setOpen((prev) => new Set(prev).add(n));
			const rows = window.document.querySelectorAll(`[data-testid="entry-${n}"]`);
			rows[rows.length - 1]?.scrollIntoView?.({ block: "center" });
		};
		const edited = data.document.steps.length;
		const history = /* @__PURE__ */ (0, react_jsx_runtime.jsx)(Section, {
			title: data.document.name ? `Document — ${data.document.name} · ${edited === 0 ? "no edits" : edited === 1 ? "1 edit" : `${edited} edits`}` : "Document",
			children: /* @__PURE__ */ (0, react_jsx_runtime.jsx)(DocumentHistory, {
				runId,
				document: data.document,
				timeline: data.timeline,
				intact: data.verdict?.artifact_intact ?? null,
				legacy,
				selected,
				onSelect: setSelected,
				diffMode,
				onDiffMode: setDiffMode,
				onOpenTurn: openTurn,
				derived,
				oneOnOnes,
				onOpenOneOnOne: openOneOnOne
			})
		});
		if (variant === "metrics" && data.timeline.length === 0 && oneOnOnes.length > 0) return /* @__PURE__ */ (0, react_jsx_runtime.jsx)(MeetingMetrics, {
			data,
			derived
		});
		if (data.timeline.length === 0 && (data.selection == null && oneOnOnes.length === 0 || variant === "metrics")) {
			const empty = /* @__PURE__ */ (0, react_jsx_runtime.jsx)(EmptyState, {
				title: "Nothing said yet",
				description: "The committee view fills in as each member takes the floor.",
				icon: "inbox"
			});
			if (!data.document.captured || variant === "metrics") return empty;
			return /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
				style: {
					display: "flex",
					flexDirection: "column",
					gap: 16
				},
				children: [empty, history]
			});
		}
		if (variant === "metrics") return /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
			style: {
				display: "flex",
				flexDirection: "column",
				gap: 16
			},
			children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)(MeetingMetrics, {
				data,
				derived
			}), /* @__PURE__ */ (0, react_jsx_runtime.jsx)(EvaluationBlock, {
				runId,
				evaluation: data.evaluation ?? null,
				scorable: !!data.verdict?.text
			})]
		});
		if (data.timeline.length === 0) {
			const current = data.selection?.current;
			const roster = data.roster.map((p) => p.role === current?.role ? {
				...p,
				state: "holds_floor"
			} : p);
			const upfront = oneOnOnes.filter((g) => g.after_turn === 0);
			return /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
				"data-testid": "committee-view",
				style: {
					display: "flex",
					flexDirection: "column",
					gap: 16
				},
				children: [
					/* @__PURE__ */ (0, react_jsx_runtime.jsx)(ProgressBar, {
						progress: data.progress,
						legacy,
						derived
					}),
					/* @__PURE__ */ (0, react_jsx_runtime.jsx)(Roster, {
						roster,
						legacy
					}),
					data.selection != null && /* @__PURE__ */ (0, react_jsx_runtime.jsx)(SelectionCard, {
						selection: data.selection,
						runId,
						derived
					}),
					upfront.length > 0 && /* @__PURE__ */ (0, react_jsx_runtime.jsx)(Section, {
						title: "1:1s before the opening round",
						children: upfront.map(group)
					})
				]
			});
		}
		const edits = /* @__PURE__ */ new Map();
		if (data.document.captured) data.document.steps.forEach((step, i) => {
			if (step.reviewer_turn !== null) edits.set(step.reviewer_turn, [i + 1, step.turn]);
			if (step.owner_turn !== null) edits.set(step.owner_turn, [i + 1, step.turn]);
			edits.set(step.turn, [i + 1, step.turn]);
		});
		const seeEdit = (turn) => {
			setSelected(turn);
			const stepper = window.document.querySelector("[data-testid=\"doc-stepper\"]");
			stepper?.scrollIntoView?.({ block: "start" });
			stepper?.focus({ preventScroll: true });
		};
		return /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
			"data-testid": "committee-view",
			style: {
				display: "flex",
				flexDirection: "column",
				gap: 16
			},
			children: [
				/* @__PURE__ */ (0, react_jsx_runtime.jsx)(ProgressBar, {
					progress: data.progress,
					legacy,
					derived
				}),
				/* @__PURE__ */ (0, react_jsx_runtime.jsx)(Roster, {
					roster: data.roster,
					legacy
				}),
				data.selection != null && /* @__PURE__ */ (0, react_jsx_runtime.jsx)(SelectionCard, {
					selection: data.selection,
					runId,
					derived
				}),
				/* @__PURE__ */ (0, react_jsx_runtime.jsx)(Timeline, {
					runId,
					timeline: data.timeline,
					open,
					setOpen,
					edits,
					onSeeEdit: seeEdit,
					derived,
					oneOnOnes,
					group
				}),
				/* @__PURE__ */ (0, react_jsx_runtime.jsx)(Verdict, {
					runId,
					verdict: data.verdict,
					oneOnOnes,
					derived
				}),
				history
			]
		});
	}
	CommitteeView.variants = ["metrics"];
	//#endregion
	return CommitteeView;
});
