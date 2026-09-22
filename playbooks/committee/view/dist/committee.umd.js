(function(global, factory) {
	typeof exports === "object" && typeof module !== "undefined" ? module.exports = factory(require("react"), require("react/jsx-runtime")) : typeof define === "function" && define.amd ? define(["react", "react/jsx-runtime"], factory) : (global = typeof globalThis !== "undefined" ? globalThis : global || self, global.HermesView_committee = factory(global.React, global.ReactJSXRuntime));
})(this, function(react, react_jsx_runtime) {
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
	function hostMarkdown() {
		return window.HermesUI.Markdown;
	}
	/**
	* The design-system namespace, resolved exactly as `web/src/ds/index.ts` does.
	* The bundle publishes the hashed name and nothing publishes `DSNS`, so the
	* fallback is the compatibility half of the same expression, not a guess.
	*/
	function ds() {
		const w = window;
		return w.MonoDarkDashDesignSystem_66fdfe || w.DSNS;
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
	function ProgressBar({ progress }) {
		const { Badge } = ds();
		const { turn, cap, holder, queue, ended } = progress;
		const pct = cap > 0 ? Math.min(100, Math.round(turn / cap * 100)) : 0;
		const atCap = cap > 0 && turn >= cap;
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
							children: /* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", { style: {
								width: `${pct}%`,
								height: "100%",
								background: atCap ? "var(--status-attention, #e3b341)" : "var(--status-live, #6ea8fe)"
							} })
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
					children: "Still in session."
				})
			]
		});
	}
	function Roster({ roster }) {
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
							children: p.stance ?? "no stance stated"
						})
					]
				}, p.role))
			})
		});
	}
	function TimelineEntry({ entry, open, onToggle }) {
		const { Badge } = ds();
		const Markdown = hostMarkdown();
		const firstLine = entry.body.split("\n").find((l) => l.trim()) ?? "";
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
						paddingLeft: 18
					},
					children: /* @__PURE__ */ (0, react_jsx_runtime.jsx)(Markdown, {
						fontSize: 12,
						children: entry.body
					})
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
					children: firstLine
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
	function CommitteeView({ data }) {
		const { EmptyState } = ds();
		if (data.timeline.length === 0) return /* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
			style: { padding: 32 },
			children: /* @__PURE__ */ (0, react_jsx_runtime.jsx)(EmptyState, {
				title: "Nothing said yet",
				description: "The committee view fills in as each member takes the floor.",
				icon: "inbox"
			})
		});
		return /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
			"data-testid": "committee-view",
			style: {
				display: "flex",
				flexDirection: "column",
				gap: 16
			},
			children: [
				/* @__PURE__ */ (0, react_jsx_runtime.jsx)(ProgressBar, { progress: data.progress }),
				/* @__PURE__ */ (0, react_jsx_runtime.jsx)(Roster, { roster: data.roster }),
				/* @__PURE__ */ (0, react_jsx_runtime.jsx)(Timeline, { timeline: data.timeline })
			]
		});
	}
	//#endregion
	return CommitteeView;
});
