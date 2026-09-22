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
	* The re-checks are rendered from `checks` as well, because a list of six
	* outcomes is a table, not a paragraph.
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
	var note = (tone) => ({
		padding: "8px 12px",
		borderRadius: "var(--radius-sm)",
		fontSize: 12.5,
		lineHeight: 1.5,
		color: "var(--text-primary)",
		background: tone === "muted" ? "var(--wash-subtle)" : `var(--status-${tone}-tint)`,
		border: `1px solid ${tone === "muted" ? "var(--border-hairline)" : `var(--status-${tone}-edge)`}`
	});
	function Rechecks({ checks }) {
		if (checks.length === 0) return /* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
			"data-testid": "rechecks-none",
			style: note("muted"),
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
						...note(check.verified === null ? "muted" : applied ? "ok" : "danger"),
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
			apiGet(`/api/runs/${runId}/reductions?phase=decision`).then((rows) => {
				const row = [...rows].reverse().find((r) => r.kind === "decision");
				if (!live) return;
				if (row) setStamp({
					id: row.id,
					review_state: row.review_state
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
					id: stamp.id,
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
			style: note("muted"),
			children: ["Could not read this verdict’s review state: ", lookupError]
		});
		if (!stamp) return null;
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
					children: "Accepting or rejecting stamps this reduction in the audit trail and emits an event. It settles no tickets and changes no run state — the committee’s decision holds no needs_human ticket — and it lands nothing and reverts nothing. It records that a person read the verdict."
				}),
				stamp.review_state && stamp.review_state !== "pending" ? /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
					"data-testid": "stamp-state",
					style: note(stamp.review_state === "accepted" ? "ok" : "attention"),
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
					style: note("danger"),
					children: actionError
				})
			]
		});
	}
	function Verdict({ runId, verdict }) {
		if (!verdict) return /* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
			style: card,
			children: /* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
				"data-testid": "verdict-pending",
				style: note("muted"),
				children: "The chair has not ruled yet. A verdict appears here once the meeting ends — when the owner closes it, the queue empties, or the turn cap is reached."
			})
		});
		return /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
			style: card,
			children: [
				/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
					"data-testid": "verdict-simulation",
					style: note("attention"),
					children: [
						/* @__PURE__ */ (0, react_jsx_runtime.jsx)("strong", { children: "Simulation — not an approval." }),
						" This verdict is a simulation produced by AI personas reading one file. It is not an approval, not a sign-off, and carries no authority: a human decides.",
						" ",
						verdict.artifact_intact === false ? "A repository file DID change during this review — see below. Nothing was landed," : "No repository was written to, nothing was landed,",
						" ",
						"and nothing here binds any person, team or budget."
					]
				}),
				/* @__PURE__ */ (0, react_jsx_runtime.jsx)(Rechecks, { checks: verdict.checks }),
				verdict.artifact_intact !== null && /* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
					"data-testid": "artifact-intact",
					style: note(verdict.artifact_intact ? "ok" : "danger"),
					children: verdict.artifact_intact ? "Original artifact unchanged — re-checked by digest at the decision, against the digest taken before the meeting opened." : "Original artifact CHANGED DURING THE REVIEW — it was promised untouched. Treat every re-check above as unreliable and read the diff."
				}),
				verdict.dropped_delegation && /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
					"data-testid": "dropped-delegation",
					style: note("attention"),
					children: [
						/* @__PURE__ */ (0, react_jsx_runtime.jsx)("strong", { children: "Dropped delegation" }),
						" — the turn cap cut it off and no edit was made:",
						" ",
						verdict.dropped_delegation
					]
				}),
				verdict.dropped_floor_requests.length > 0 && /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
					"data-testid": "dropped-floor-requests",
					style: note("attention"),
					children: [
						/* @__PURE__ */ (0, react_jsx_runtime.jsx)("strong", { children: "Dropped floor requests" }),
						" — the review ended before their turn came:",
						" ",
						verdict.dropped_floor_requests.join(", ")
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
						children: /* @__PURE__ */ (0, react_jsx_runtime.jsx)(Markdown, { children: verdict.text })
					})]
				}),
				/* @__PURE__ */ (0, react_jsx_runtime.jsx)(Stamp, { runId })
			]
		});
	}
	//#endregion
	//#region ../playbooks/committee/view/src/Diff.tsx
	/**
	* The revised copy against the original — the surface the first live run got
	* wrong, and the reason this exists.
	*
	* The chair opened the repository file, found it unchanged, wrote "six
	* delegations, zero bytes" and partly ruled on that basis. All six had landed:
	* the revised copy went 11,397 → 19,100 bytes and every re-check reports
	* APPLIED. The original is unchanged because that is the playbook's central
	* safety guarantee, not because the edits failed. So this leads with the
	* invariant and puts the diff second.
	*
	* Fetched on demand, never with the view data: the pair is ~30 KB for the
	* measured run and the view refetches on every reduction.
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
	* How many diff rows to put in the DOM.
	*
	* ponytail: `diffLines` is hard-bounded and fast (415 rows in 1.9 ms on the real
	* pair); the RENDER is what does not scale — one <div> per line, measured at
	* 20,001 nodes and 3.4 s to mount for a 20,000-line artifact. A cap plus a
	* footer beats virtualization until a real artifact trips it.
	*/
	var MAX_ROWS = 5e3;
	var kb = (bytes) => `${(bytes / 1024).toFixed(1)} KB`;
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
	function ArtifactDiff({ runId, artifacts, intact, legacy }) {
		const [rows, setRows] = (0, react.useState)(null);
		const [cut, setCut] = (0, react.useState)(false);
		const [loading, setLoading] = (0, react.useState)(false);
		const [error, setError] = (0, react.useState)(null);
		const { original, revised } = artifacts;
		const load = () => {
			if (!revised) return;
			setLoading(true);
			setError(null);
			Promise.all([apiGet(`/api/runs/${runId}/view/artifact?which=original`), apiGet(`/api/runs/${runId}/view/artifact?which=revised`)]).then(([a, b]) => {
				setCut(Boolean(a.truncated || b.truncated));
				setRows(diffLines(a.text, b.text));
			}).catch((err) => setError(err instanceof Error ? err.message : String(err))).finally(() => setLoading(false));
		};
		const adds = rows ? rows.filter((r) => r.kind === "add").length : 0;
		const dels = rows ? rows.filter((r) => r.kind === "del").length : 0;
		const shell = {
			background: "var(--surface-card)",
			border: "1px solid var(--border-hairline)",
			borderRadius: "var(--radius-md)",
			padding: 16,
			display: "flex",
			flexDirection: "column",
			gap: 12
		};
		if (!original) return /* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
			style: shell,
			children: /* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
				"data-testid": "diff-no-artifacts",
				style: {
					fontSize: 12.5,
					color: "var(--text-muted)",
					lineHeight: 1.5
				},
				children: legacy ? "This run predates the committee view: its reductions never recorded which file the committee was handed, so there is nothing to show either side of. The record does not say the file is gone — it says nothing about it." : "No artifact has been recorded for this run yet. The committee names the file it is reviewing on its first reduction; until then there is nothing to show either side of."
			})
		});
		const name = (a) => /* @__PURE__ */ (0, react_jsx_runtime.jsx)("code", {
			style: {
				fontFamily: "var(--font-mono)",
				fontSize: 11.5
			},
			children: a.name
		});
		return /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
			style: shell,
			children: [intact === false ? /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
				"data-testid": "diff-original-changed",
				style: {
					padding: "8px 12px",
					borderRadius: "var(--radius-sm)",
					background: "var(--status-danger-tint)",
					border: "1px solid var(--status-danger-edge)",
					fontSize: 12.5,
					lineHeight: 1.55,
					color: "var(--text-primary)"
				},
				children: [
					/* @__PURE__ */ (0, react_jsx_runtime.jsx)("strong", { children: "The original CHANGED during this review." }),
					" ",
					name(original),
					" is not byte-for-byte what the committee was handed: the playbook re-checked its digest at the decision and it did not match. The safety guarantee this card normally states did not hold on this run, so read the diff below against a file that moved under it, and treat every re-check in the verdict as unreliable."
				]
			}) : /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
				"data-testid": "diff-original-untouched",
				style: {
					padding: "8px 12px",
					borderRadius: "var(--radius-sm)",
					background: "var(--status-live-tint)",
					border: "1px solid var(--status-live-edge)",
					fontSize: 12.5,
					lineHeight: 1.55,
					color: "var(--text-primary)"
				},
				children: [
					/* @__PURE__ */ (0, react_jsx_runtime.jsx)("strong", { children: "The original is never modified." }),
					" ",
					name(original),
					" ",
					intact === true ? "is" : "is meant to be",
					" byte-for-byte what the committee was handed; the playbook re-checks its digest at the decision and says so in the verdict. Every delegated edit lands in the revised copy,",
					" ",
					revised ? name(revised) : "which does not exist yet",
					", which the committee offers as a recommendation, not a landed change. Reading the repository file and finding it unchanged does not mean the edits failed."
				]
			}), !revised ? /* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
				"data-testid": "diff-no-revised",
				style: {
					fontSize: 12.5,
					color: "var(--text-muted)",
					lineHeight: 1.5
				},
				children: "No edit has been delegated yet, so there is no revised copy to compare. The original stands as it was."
			}) : rows === null ? /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
				style: {
					display: "flex",
					flexDirection: "column",
					gap: 8,
					alignItems: "flex-start"
				},
				children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("button", {
					type: "button",
					disabled: loading,
					onClick: load,
					style: {
						padding: "6px 14px",
						fontSize: 12.5,
						borderRadius: "var(--radius-sm)",
						border: "1px solid var(--border-hairline)",
						background: "var(--wash-subtle)",
						color: "var(--text-primary)",
						cursor: loading ? "default" : "pointer"
					},
					children: loading ? "Loading both copies…" : `Show the diff (${kb(original.bytes)} → ${kb(revised.bytes)})`
				}), error && /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
					"data-testid": "diff-error",
					style: {
						padding: "8px 12px",
						borderRadius: "var(--radius-sm)",
						background: "var(--status-danger-tint)",
						border: "1px solid var(--status-danger-edge)",
						fontSize: 12.5,
						color: "var(--text-primary)"
					},
					children: ["Could not load the two copies: ", error]
				})]
			}) : /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
				style: {
					display: "flex",
					flexDirection: "column",
					gap: 8
				},
				children: [
					cut && /* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
						"data-testid": "diff-truncated",
						style: {
							padding: "8px 12px",
							borderRadius: "var(--radius-sm)",
							background: "var(--status-attention-tint)",
							border: "1px solid var(--status-attention-edge)",
							fontSize: 12.5,
							color: "var(--text-primary)"
						},
						children: "The server cut at least one of the two copies short at its read cap, so this is a diff of two prefixes and the counts below are not the whole file."
					}),
					/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
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
							" removed — all of it in the revised copy.",
							" ",
							/* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", {
								style: { fontFamily: "var(--font-mono)" },
								children: "-"
							}),
							" is a line only the original has, ",
							/* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", {
								style: { fontFamily: "var(--font-mono)" },
								children: "+"
							}),
							" a line only the revised copy has."
						]
					}),
					/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
						"data-testid": "diff-rows",
						style: {
							fontFamily: "var(--font-mono)",
							fontSize: 11.5,
							lineHeight: 1.5,
							maxHeight: 420,
							overflow: "auto",
							border: "1px solid var(--border-hairline)",
							borderRadius: "var(--radius-sm)"
						},
						children: [rows.slice(0, MAX_ROWS).map((row, i) => {
							const style = ROW_STYLE[row.kind];
							return /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
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
							}, i);
						}), rows.length > MAX_ROWS && /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
							"data-testid": "diff-rows-capped",
							style: {
								padding: "4px 8px",
								color: "var(--text-muted)"
							},
							children: [
								"… ",
								rows.length - MAX_ROWS,
								" more rows are in the diff and not on screen. The counts above are the whole diff; this pane stops at ",
								MAX_ROWS,
								"."
							]
						})]
					})
				]
			})]
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
		error: "error on this turn"
	};
	var BADGE_TONE = {
		no_turn: "danger",
		error: "danger",
		unattributed: "danger",
		signals_only: "attention"
	};
	/** spoke · holds_floor · queued · idle, as a reader would say it. */
	var ROSTER_STATE = {
		holds_floor: "has the floor",
		queued: "waiting to speak",
		spoke: "spoke",
		idle: "has not spoken"
	};
	var ENDED_NOTE = {
		"owner closed": "The owner moved to close and the chair ruled.",
		"queue empty": "Everyone who asked for the floor got it.",
		"turn cap": "The meeting ran out of turns before anyone closed it.",
		"chair turn failed": "The chair produced no decision, so the run ended failed."
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
	function ProgressBar({ progress, legacy }) {
		const { Badge } = ds();
		const { turn, cap, holder, queue, ended } = progress;
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
						color: ended === "turn cap" || ended === "chair turn failed" ? "var(--status-attention, #e3b341)" : "var(--text-secondary)"
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
	function Roster({ roster, legacy }) {
		const { Badge } = ds();
		return /* @__PURE__ */ (0, react_jsx_runtime.jsx)(Section, {
			title: `Committee — ${roster.length}`,
			children: /* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
				style: {
					display: "flex",
					flexDirection: "column"
				},
				children: roster.map((p) => /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
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
						/* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", {
							style: {
								...mono,
								fontSize: 10,
								color: "var(--text-muted)"
							},
							children: p.role
						}),
						/* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", {
							style: {
								marginLeft: "auto",
								flex: "none"
							},
							children: /* @__PURE__ */ (0, react_jsx_runtime.jsx)(Badge, {
								size: "sm",
								variant: p.state === "holds_floor" ? "solid" : "outline",
								tone: p.state === "holds_floor" ? "live" : p.state === "queued" ? "attention" : void 0,
								children: ROSTER_STATE[p.state] ?? p.state
							})
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
	function TimelineEntry({ entry, open, onToggle }) {
		const { Badge } = ds();
		const firstLine = entry.body.split("\n").find((l) => l.trim()) ?? "";
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
						entry.badges.map((b) => /* @__PURE__ */ (0, react_jsx_runtime.jsx)(Badge, {
							size: "sm",
							variant: "outline",
							tone: BADGE_TONE[b],
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
				open ? /* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
					style: {
						marginTop: 6,
						paddingLeft: 18,
						color: "var(--text-muted)"
					},
					children: entry.body ? /* @__PURE__ */ (0, react_jsx_runtime.jsx)(Markdown, {
						fontSize: 12,
						children: entry.body
					}) : noProse
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
	function Timeline({ timeline }) {
		const [open, setOpen] = (0, react.useState)(/* @__PURE__ */ new Set());
		const allOpen = timeline.length > 0 && open.size === timeline.length;
		const ordered = [...timeline].sort((a, b) => a.n - b.n);
		return /* @__PURE__ */ (0, react_jsx_runtime.jsxs)(Section, {
			title: `Transcript — ${timeline.length} turns, oldest first`,
			children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("button", {
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
			}), ordered.map((entry) => /* @__PURE__ */ (0, react_jsx_runtime.jsx)(TimelineEntry, {
				entry,
				open: open.has(entry.n),
				onToggle: () => setOpen((prev) => {
					const next = new Set(prev);
					if (next.has(entry.n)) next.delete(entry.n);
					else next.add(entry.n);
					return next;
				})
			}, entry.n))]
		});
	}
	function CommitteeView({ runId, data }) {
		const { EmptyState } = ds();
		if (data.timeline.length === 0) return /* @__PURE__ */ (0, react_jsx_runtime.jsx)(EmptyState, {
			title: "Nothing said yet",
			description: "The committee view fills in as each member takes the floor.",
			icon: "inbox"
		});
		const legacy = data.timeline.length > 0 && data.artifacts.original === null || data.verdict !== null && data.progress.ended === null;
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
					legacy
				}),
				/* @__PURE__ */ (0, react_jsx_runtime.jsx)(Roster, {
					roster: data.roster,
					legacy
				}),
				/* @__PURE__ */ (0, react_jsx_runtime.jsx)(Timeline, { timeline: data.timeline }),
				/* @__PURE__ */ (0, react_jsx_runtime.jsx)(Verdict, {
					runId,
					verdict: data.verdict
				}),
				/* @__PURE__ */ (0, react_jsx_runtime.jsx)(ArtifactDiff, {
					runId,
					artifacts: data.artifacts,
					intact: data.verdict?.artifact_intact ?? null,
					legacy
				})
			]
		});
	}
	//#endregion
	return CommitteeView;
});
