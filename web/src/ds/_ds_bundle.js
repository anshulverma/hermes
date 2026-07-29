/* @ds-bundle: {"format":4,"namespace":"MonoDarkDashDesignSystem_66fdfe","components":[{"name":"Badge","sourcePath":"components/core/Badge.jsx"},{"name":"Button","sourcePath":"components/core/Button.jsx"},{"name":"Card","sourcePath":"components/core/Card.jsx"},{"name":"Divider","sourcePath":"components/core/Divider.jsx"},{"name":"IconButton","sourcePath":"components/core/IconButton.jsx"},{"name":"Table","sourcePath":"components/data/Table.jsx"},{"name":"Dialog","sourcePath":"components/feedback/Dialog.jsx"},{"name":"EmptyState","sourcePath":"components/feedback/EmptyState.jsx"},{"name":"Tooltip","sourcePath":"components/feedback/Tooltip.jsx"},{"name":"AttentionBanner","sourcePath":"components/foreman/AttentionBanner.jsx"},{"name":"BACKDROP_THEMES","sourcePath":"components/foreman/CrewBackdrop.jsx"},{"name":"CrewBackdrop","sourcePath":"components/foreman/CrewBackdrop.jsx"},{"name":"CREW_GRID","sourcePath":"components/foreman/CrewRow.jsx"},{"name":"CrewRow","sourcePath":"components/foreman/CrewRow.jsx"},{"name":"Drawer","sourcePath":"components/foreman/Drawer.jsx"},{"name":"EventRow","sourcePath":"components/foreman/EventRow.jsx"},{"name":"HealthBadge","sourcePath":"components/foreman/HealthBadge.jsx"},{"name":"KanbanColumn","sourcePath":"components/foreman/KanbanColumn.jsx"},{"name":"StatTile","sourcePath":"components/foreman/StatTile.jsx"},{"name":"TICKET_STATES","sourcePath":"components/foreman/StatusPill.jsx"},{"name":"TONES","sourcePath":"components/foreman/StatusPill.jsx"},{"name":"StatusPill","sourcePath":"components/foreman/StatusPill.jsx"},{"name":"TicketCard","sourcePath":"components/foreman/TicketCard.jsx"},{"name":"Checkbox","sourcePath":"components/forms/Checkbox.jsx"},{"name":"Input","sourcePath":"components/forms/Input.jsx"},{"name":"Select","sourcePath":"components/forms/Select.jsx"},{"name":"Switch","sourcePath":"components/forms/Switch.jsx"},{"name":"Header","sourcePath":"components/navigation/Header.jsx"},{"name":"Tabs","sourcePath":"components/navigation/Tabs.jsx"}],"sourceHashes":{"components/core/Badge.jsx":"154b2b536396","components/core/Button.jsx":"c3f84d17fc85","components/core/Card.jsx":"1302a5e510a4","components/core/Divider.jsx":"5fe82d66ff67","components/core/IconButton.jsx":"a19843a83730","components/data/Table.jsx":"119794e7bf5e","components/feedback/Dialog.jsx":"c6a93e78f974","components/feedback/EmptyState.jsx":"19ccaaa5718f","components/feedback/Tooltip.jsx":"8f413966a499","components/foreman/AttentionBanner.jsx":"7309a532d9b3","components/foreman/CrewBackdrop.jsx":"2106eafe9899","components/foreman/CrewRow.jsx":"b978fc973e40","components/foreman/Drawer.jsx":"92a25187e1e6","components/foreman/EventRow.jsx":"f9ec2482dd3b","components/foreman/HealthBadge.jsx":"22ff99c8656e","components/foreman/KanbanColumn.jsx":"0a5b123d2aa3","components/foreman/StatTile.jsx":"0f77a4b23194","components/foreman/StatusPill.jsx":"819866338b20","components/foreman/TicketCard.jsx":"ade21e8e8c3e","components/forms/Checkbox.jsx":"766c23872757","components/forms/Input.jsx":"9e9ebff0dec8","components/forms/Select.jsx":"944d0399c1cd","components/forms/Switch.jsx":"a4cc81b0bb58","components/navigation/Header.jsx":"4289eb1d3610","components/navigation/Tabs.jsx":"982b4aaec88d","ds-preview.js":"55f446a76cbd","ui_kits/console/App.jsx":"4f2677cd7a27","ui_kits/console/AppShell.jsx":"e5183a7b9904","ui_kits/console/DashboardScreen.jsx":"4eba130e9ad8","ui_kits/console/LoginScreen.jsx":"69b1e55f28ab","ui_kits/console/QueryScreen.jsx":"dcb755bac628","ui_kits/console/TableScreen.jsx":"07675b2774d9","ui_kits/console/data.js":"be7c5c7d7718","ui_kits/foreman/ActivityFeed.jsx":"b3e0bb6c19a8","ui_kits/foreman/CrewPanel.jsx":"8fede736a580","ui_kits/foreman/Findings.jsx":"59c2a0580882","ui_kits/foreman/ForemanApp.jsx":"c1eb9b85ee5e","ui_kits/foreman/RunOverview.jsx":"f4b48a042c1b","ui_kits/foreman/Shell.jsx":"3c68ff97fb13","ui_kits/foreman/TicketBoard.jsx":"c52186e54417","ui_kits/foreman/TicketDrawer.jsx":"fe9d70cd8cc2","ui_kits/foreman/data.js":"33547236091f","ui_kits/marketing/Landing.jsx":"5f58728c8cd1","ui_kits/marketing/Page.jsx":"d0a4033d5165"},"inlinedExternals":[],"unexposedExports":[]} */

(() => {

const __ds_ns = (window.MonoDarkDashDesignSystem_66fdfe = window.MonoDarkDashDesignSystem_66fdfe || {});

const __ds_scope = {};

(__ds_ns.__errors = __ds_ns.__errors || []);

// components/core/Badge.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
const TONES = {
  live: {
    fg: 'var(--status-live)',
    edge: 'var(--status-live-edge)',
    tint: 'var(--status-live-tint)'
  },
  ok: {
    fg: 'var(--status-ok)',
    edge: 'var(--status-ok-edge)',
    tint: 'var(--status-ok-tint)'
  },
  attention: {
    fg: 'var(--status-attention)',
    edge: 'var(--status-attention-edge)',
    tint: 'var(--status-attention-tint)'
  },
  danger: {
    fg: 'var(--status-danger)',
    edge: 'var(--status-danger-edge)',
    tint: 'var(--status-danger-tint)'
  }
};
function Badge({
  children,
  variant = 'subtle',
  tone,
  size = 'md',
  style,
  ...rest
}) {
  const sm = size === 'sm';
  const t = TONES[tone];
  const looks = t ? {
    subtle: {
      background: t.tint,
      border: '1px solid ' + t.edge,
      color: t.fg
    },
    outline: {
      background: 'transparent',
      border: '1px solid ' + t.edge,
      color: t.fg
    },
    solid: {
      background: t.fg,
      border: '1px solid ' + t.fg,
      color: 'var(--black)'
    }
  } : {
    subtle: {
      background: 'var(--wash-selected)',
      border: '1px solid transparent',
      color: 'var(--text-secondary)'
    },
    outline: {
      background: 'transparent',
      border: '1px solid var(--border-hairline)',
      color: 'var(--text-muted)'
    },
    solid: {
      background: 'var(--white)',
      border: '1px solid var(--white)',
      color: 'var(--black)'
    }
  };
  return /*#__PURE__*/React.createElement("span", _extends({
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      gap: 'var(--space-1)',
      height: sm ? 18 : 22,
      padding: sm ? '0 6px' : '0 8px',
      fontSize: 'var(--text-small-size)',
      lineHeight: 1,
      borderRadius: 'var(--radius-lg)',
      whiteSpace: 'nowrap',
      ...looks[variant],
      ...style
    }
  }, rest), children);
}
Object.assign(__ds_scope, { Badge });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Badge.jsx", error: String((e && e.message) || e) }); }

// components/core/Button.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
const {
  useState
} = React;
const SIZES = {
  sm: {
    padding: '0 10px',
    height: 32,
    fontSize: 'var(--text-small-size)',
    radius: 'var(--radius-lg)'
  },
  md: {
    padding: '0 14px',
    height: 36,
    fontSize: 'var(--text-body-size)',
    radius: 'var(--radius-lg)'
  },
  lg: {
    padding: '0 20px',
    height: 44,
    fontSize: 'var(--text-body-size)',
    radius: 'var(--radius-xl)'
  }
};
function Button({
  children,
  variant = 'outline',
  size = 'md',
  disabled = false,
  full = false,
  iconLeft = null,
  iconRight = null,
  href,
  onClick,
  style,
  ...rest
}) {
  const [hover, setHover] = useState(false);
  const s = SIZES[size] || SIZES.md;
  const lit = hover && !disabled;
  const base = {
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 'var(--space-2)',
    height: s.height,
    minHeight: 'var(--hit-target-min)',
    padding: s.padding,
    width: full ? '100%' : undefined,
    background: 'transparent',
    fontFamily: 'var(--font-sans)',
    fontSize: s.fontSize,
    fontWeight: 'var(--weight-regular)',
    lineHeight: 1,
    borderRadius: s.radius,
    cursor: disabled ? 'default' : 'pointer',
    opacity: disabled ? 0.35 : 1,
    textDecoration: 'none',
    transition: 'color var(--motion-fast) var(--ease-default), border-color var(--motion-fast) var(--ease-default), background var(--motion-fast) var(--ease-default)'
  };
  const variants = {
    outline: {
      border: '1px solid ' + (lit ? 'var(--border-control-hover)' : 'var(--border-control)'),
      color: lit ? 'var(--text-primary)' : 'var(--text-muted)'
    },
    ghost: {
      border: '1px solid transparent',
      color: lit ? 'var(--text-primary)' : 'var(--text-secondary)',
      background: lit ? 'var(--wash-hover)' : 'transparent'
    }
  };
  const Tag = href ? 'a' : 'button';
  return /*#__PURE__*/React.createElement(Tag, _extends({
    href: href,
    onClick: disabled ? undefined : onClick,
    disabled: Tag === 'button' ? disabled : undefined,
    onMouseEnter: () => setHover(true),
    onMouseLeave: () => setHover(false),
    style: {
      ...base,
      ...(variants[variant] || variants.outline),
      ...style
    }
  }, rest), iconLeft, children, iconRight);
}
Object.assign(__ds_scope, { Button });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Button.jsx", error: String((e && e.message) || e) }); }

// components/core/Card.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
const PAD = {
  none: 0,
  sm: 'var(--space-4)',
  md: 'var(--space-6)',
  lg: 'var(--space-8)'
};
function Card({
  children,
  title,
  subtitle,
  action,
  padding = 'md',
  radius = 'xl',
  bordered = false,
  style,
  ...rest
}) {
  return /*#__PURE__*/React.createElement("section", _extends({
    style: {
      background: 'var(--surface-card)',
      borderRadius: radius === 'lg' ? 'var(--radius-lg)' : radius === '2xl' ? 'var(--radius-2xl)' : 'var(--radius-xl)',
      border: bordered ? '1px solid var(--border-hairline)' : 'none',
      boxShadow: 'var(--shadow-none)',
      padding: PAD[padding] ?? PAD.md,
      color: 'var(--text-secondary)',
      ...style
    }
  }, rest), (title || action) && /*#__PURE__*/React.createElement("header", {
    style: {
      display: 'flex',
      alignItems: 'flex-start',
      justifyContent: 'space-between',
      gap: 'var(--space-4)',
      marginBottom: subtitle ? 'var(--space-1)' : 'var(--space-4)'
    }
  }, /*#__PURE__*/React.createElement("h3", {
    style: {
      color: 'var(--text-primary)',
      fontSize: 'var(--text-h3-size)',
      lineHeight: 'var(--text-h3-leading)'
    }
  }, title), action), subtitle && /*#__PURE__*/React.createElement("p", {
    style: {
      margin: '0 0 var(--space-4)',
      color: 'var(--text-muted)'
    }
  }, subtitle), children);
}
Object.assign(__ds_scope, { Card });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Card.jsx", error: String((e && e.message) || e) }); }

// components/core/Divider.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
function Divider({
  orientation = 'horizontal',
  inset = false,
  style,
  ...rest
}) {
  const v = orientation === 'vertical';
  return /*#__PURE__*/React.createElement("div", _extends({
    role: "separator",
    "aria-orientation": orientation,
    style: {
      background: 'var(--border-hairline)',
      width: v ? 1 : inset ? 'calc(100% - var(--space-6) * 2)' : '100%',
      height: v ? '100%' : 1,
      alignSelf: v ? 'stretch' : undefined,
      margin: v ? '0' : inset ? '0 var(--space-6)' : '0',
      flex: 'none',
      ...style
    }
  }, rest));
}
Object.assign(__ds_scope, { Divider });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Divider.jsx", error: String((e && e.message) || e) }); }

// components/core/IconButton.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
const {
  useState
} = React;
const SIZES = {
  sm: 28,
  md: 32,
  lg: 36
};
function IconButton({
  children,
  label,
  variant = 'ghost',
  size = 'md',
  active = false,
  disabled = false,
  onClick,
  style,
  ...rest
}) {
  const [hover, setHover] = useState(false);
  const d = SIZES[size] || SIZES.md;
  const lit = (hover || active) && !disabled;
  return /*#__PURE__*/React.createElement("button", _extends({
    "aria-label": label,
    title: label,
    onClick: disabled ? undefined : onClick,
    onMouseEnter: () => setHover(true),
    onMouseLeave: () => setHover(false),
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      justifyContent: 'center',
      width: d,
      height: d,
      padding: 0,
      borderRadius: 'var(--radius-lg)',
      border: '1px solid ' + (variant === 'outline' ? lit ? 'var(--border-control-hover)' : 'var(--border-control)' : 'transparent'),
      background: variant === 'ghost' && lit ? 'var(--wash-hover)' : 'transparent',
      color: lit ? 'var(--text-primary)' : 'var(--text-muted)',
      cursor: disabled ? 'default' : 'pointer',
      opacity: disabled ? 0.35 : 1,
      transition: 'color var(--motion-fast) var(--ease-default), border-color var(--motion-fast) var(--ease-default), background var(--motion-fast) var(--ease-default)',
      ...style
    }
  }, rest), children);
}
Object.assign(__ds_scope, { IconButton });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/IconButton.jsx", error: String((e && e.message) || e) }); }

// components/data/Table.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
const {
  useState
} = React;
function Table({
  columns = [],
  rows = [],
  selectable = false,
  dense = false,
  onRowClick,
  style,
  ...rest
}) {
  const [hoverRow, setHoverRow] = useState(-1);
  const h = dense ? 32 : 40;
  return /*#__PURE__*/React.createElement("div", _extends({
    style: {
      width: '100%',
      overflow: 'auto',
      ...style
    }
  }, rest), /*#__PURE__*/React.createElement("table", {
    style: {
      width: '100%',
      borderCollapse: 'collapse',
      fontSize: 'var(--text-body-size)'
    }
  }, /*#__PURE__*/React.createElement("thead", null, /*#__PURE__*/React.createElement("tr", null, selectable && /*#__PURE__*/React.createElement("th", {
    style: {
      width: 36,
      borderBottom: '1px solid var(--border-hairline)'
    }
  }), columns.map(c => {
    const col = typeof c === 'string' ? {
      key: c,
      label: c
    } : c;
    return /*#__PURE__*/React.createElement("th", {
      key: col.key,
      style: {
        textAlign: col.align || 'left',
        padding: dense ? 'var(--space-2) var(--space-3)' : 'var(--space-3)',
        color: 'var(--text-muted)',
        fontWeight: 'var(--weight-regular)',
        fontSize: 'var(--text-small-size)',
        borderBottom: '1px solid var(--border-hairline)',
        whiteSpace: 'nowrap'
      }
    }, col.label);
  }))), /*#__PURE__*/React.createElement("tbody", null, rows.map((r, i) => /*#__PURE__*/React.createElement("tr", {
    key: r.id ?? i,
    onMouseEnter: () => setHoverRow(i),
    onMouseLeave: () => setHoverRow(-1),
    onClick: onRowClick ? () => onRowClick(r, i) : undefined,
    style: {
      height: h,
      background: hoverRow === i ? 'var(--wash-hover)' : 'transparent',
      cursor: onRowClick ? 'pointer' : 'default',
      transition: 'background var(--motion-fast) var(--ease-default)'
    }
  }, selectable && /*#__PURE__*/React.createElement("td", {
    style: {
      padding: '0 var(--space-3)',
      borderBottom: '1px solid var(--border-hairline)'
    }
  }, /*#__PURE__*/React.createElement("input", {
    type: "checkbox",
    style: {
      accentColor: 'var(--white)'
    }
  })), columns.map(c => {
    const col = typeof c === 'string' ? {
      key: c,
      label: c
    } : c;
    return /*#__PURE__*/React.createElement("td", {
      key: col.key,
      style: {
        textAlign: col.align || 'left',
        padding: dense ? 'var(--space-2) var(--space-3)' : 'var(--space-3)',
        color: col.muted ? 'var(--text-muted)' : 'var(--text-secondary)',
        fontFamily: col.mono ? 'var(--font-mono)' : 'inherit',
        borderBottom: '1px solid var(--border-hairline)',
        whiteSpace: 'nowrap',
        maxWidth: 260,
        overflow: 'hidden',
        textOverflow: 'ellipsis'
      }
    }, col.render ? col.render(r) : r[col.key]);
  }))))));
}
Object.assign(__ds_scope, { Table });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/data/Table.jsx", error: String((e && e.message) || e) }); }

// components/feedback/Dialog.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
function Dialog({
  open = true,
  fixed = false,
  title,
  description,
  children,
  footer,
  onClose,
  width = 480,
  style,
  ...rest
}) {
  if (!open) return null;
  /* `absolute` centres against the positioning ancestor, which is only correct inside a
     viewport-height app shell. On a normally scrolling page pass `fixed`. */
  return /*#__PURE__*/React.createElement("div", {
    role: "dialog",
    "aria-modal": "true",
    style: {
      position: fixed ? 'fixed' : 'absolute',
      inset: 0,
      zIndex: 100,
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      padding: 'var(--space-6)',
      background: 'var(--surface-overlay)',
      backdropFilter: 'blur(var(--blur-overlay))',
      WebkitBackdropFilter: 'blur(var(--blur-overlay))'
    },
    onClick: onClose
  }, /*#__PURE__*/React.createElement("div", _extends({
    onClick: e => e.stopPropagation(),
    style: {
      width: '100%',
      maxWidth: width,
      background: 'var(--surface-card)',
      border: '1px solid var(--border-hairline)',
      borderRadius: 'var(--radius-2xl)',
      padding: 'var(--space-6)',
      boxShadow: 'var(--shadow-none)',
      ...style
    }
  }, rest), title && /*#__PURE__*/React.createElement("h3", {
    style: {
      color: 'var(--text-primary)',
      fontSize: 'var(--text-h3-size)',
      lineHeight: 'var(--text-h3-leading)'
    }
  }, title), description && /*#__PURE__*/React.createElement("p", {
    style: {
      margin: 'var(--space-2) 0 0',
      color: 'var(--text-muted)'
    }
  }, description), children && /*#__PURE__*/React.createElement("div", {
    style: {
      marginTop: 'var(--space-5)',
      color: 'var(--text-secondary)'
    }
  }, children), footer && /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      justifyContent: 'flex-end',
      gap: 'var(--space-2)',
      marginTop: 'var(--space-6)'
    }
  }, footer)));
}
Object.assign(__ds_scope, { Dialog });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/feedback/Dialog.jsx", error: String((e && e.message) || e) }); }

// components/feedback/EmptyState.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
function EmptyState({
  title = 'Nothing here yet',
  description,
  action,
  style,
  ...rest
}) {
  return /*#__PURE__*/React.createElement("div", _extends({
    style: {
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      gap: 'var(--space-3)',
      textAlign: 'center',
      padding: 'var(--space-16) var(--space-6)',
      ...style
    }
  }, rest), /*#__PURE__*/React.createElement("p", {
    style: {
      margin: 0,
      color: 'var(--text-secondary)',
      fontSize: 'var(--text-h3-size)',
      lineHeight: 'var(--text-h3-leading)'
    }
  }, title), description && /*#__PURE__*/React.createElement("p", {
    style: {
      margin: 0,
      maxWidth: 380,
      color: 'var(--text-muted)'
    }
  }, description), action && /*#__PURE__*/React.createElement("div", {
    style: {
      marginTop: 'var(--space-3)'
    }
  }, action));
}
Object.assign(__ds_scope, { EmptyState });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/feedback/EmptyState.jsx", error: String((e && e.message) || e) }); }

// components/feedback/Tooltip.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
const {
  useState
} = React;
function Tooltip({
  label,
  children,
  placement = 'top',
  style,
  ...rest
}) {
  const [show, setShow] = useState(false);
  const pos = {
    top: {
      bottom: '100%',
      left: '50%',
      transform: 'translate(-50%, -6px)'
    },
    bottom: {
      top: '100%',
      left: '50%',
      transform: 'translate(-50%, 6px)'
    },
    left: {
      right: '100%',
      top: '50%',
      transform: 'translate(-6px, -50%)'
    },
    right: {
      left: '100%',
      top: '50%',
      transform: 'translate(6px, -50%)'
    }
  }[placement];
  return /*#__PURE__*/React.createElement("span", _extends({
    onMouseEnter: () => setShow(true),
    onMouseLeave: () => setShow(false),
    style: {
      position: 'relative',
      display: 'inline-flex',
      ...style
    }
  }, rest), children, /*#__PURE__*/React.createElement("span", {
    role: "tooltip",
    style: {
      position: 'absolute',
      ...pos,
      opacity: show ? 1 : 0,
      pointerEvents: 'none',
      whiteSpace: 'nowrap',
      padding: '4px 8px',
      borderRadius: 'var(--radius-lg)',
      background: 'var(--surface-overlay)',
      backdropFilter: 'blur(var(--blur-overlay))',
      WebkitBackdropFilter: 'blur(var(--blur-overlay))',
      border: '1px solid var(--border-hairline)',
      color: 'var(--text-primary)',
      fontSize: 'var(--text-small-size)',
      lineHeight: 'var(--text-small-leading)',
      transition: 'opacity var(--motion-fast) var(--ease-default)',
      zIndex: 60
    }
  }, label));
}
Object.assign(__ds_scope, { Tooltip });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/feedback/Tooltip.jsx", error: String((e && e.message) || e) }); }

// components/foreman/AttentionBanner.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
function AttentionBanner({
  severity = 'warn',
  title,
  detail,
  actions,
  actionLabel,
  onAction,
  onAcknowledge,
  style,
  ...rest
}) {
  const critical = severity === 'critical';
  const tone = critical ? 'var(--status-danger)' : 'var(--status-attention)';
  return /*#__PURE__*/React.createElement("div", _extends({
    role: "status",
    style: {
      display: 'flex',
      alignItems: 'flex-start',
      gap: 'var(--space-3)',
      padding: 'var(--space-3) var(--space-4)',
      borderRadius: 'var(--radius-lg)',
      background: critical ? tone : 'var(--status-attention-tint)',
      border: '1px solid ' + (critical ? tone : 'var(--status-attention-edge)'),
      color: critical ? 'var(--black)' : 'var(--text-primary)',
      ...style
    }
  }, rest), /*#__PURE__*/React.createElement("span", {
    "aria-hidden": "true",
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      justifyContent: 'center',
      width: 18,
      height: 18,
      flex: 'none',
      marginTop: 1,
      borderRadius: 'var(--radius-full)',
      border: '1px solid currentColor',
      fontSize: 11,
      lineHeight: 1,
      color: critical ? 'var(--black)' : 'var(--status-attention)'
    }
  }, "!"), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      minWidth: 0,
      display: 'flex',
      flexDirection: 'column',
      gap: 2
    }
  }, /*#__PURE__*/React.createElement("span", null, title), detail && /*#__PURE__*/React.createElement("span", {
    style: {
      color: critical ? 'rgba(0,0,0,0.65)' : 'var(--text-muted)',
      fontSize: 'var(--text-small-size)'
    }
  }, detail)), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 'var(--space-2)',
      flex: 'none'
    }
  }, actions, actionLabel && /*#__PURE__*/React.createElement("button", {
    onClick: onAction,
    style: {
      height: 30,
      padding: '0 12px',
      background: 'transparent',
      border: '1px solid ' + (critical ? 'rgba(0,0,0,0.55)' : 'var(--status-attention-edge)'),
      borderRadius: 'var(--radius-lg)',
      color: critical ? 'var(--black)' : 'var(--status-attention)',
      font: '400 14px var(--font-sans)',
      cursor: 'pointer'
    }
  }, actionLabel), onAcknowledge && /*#__PURE__*/React.createElement("button", {
    onClick: onAcknowledge,
    style: {
      height: 26,
      padding: '0 10px',
      background: 'transparent',
      border: '1px solid ' + (critical ? 'rgba(0,0,0,0.45)' : 'var(--status-attention-edge)'),
      borderRadius: 'var(--radius-lg)',
      color: critical ? 'var(--black)' : 'var(--status-attention)',
      font: '400 12px var(--font-sans)',
      cursor: 'pointer'
    }
  }, "Acknowledge")));
}
Object.assign(__ds_scope, { AttentionBanner });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/foreman/AttentionBanner.jsx", error: String((e && e.message) || e) }); }

// components/foreman/CrewBackdrop.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/* Page-level texture for the control plane. Each theme is a generated grayscale PNG
   (white-on-transparent, so it composites over any ground lightness) built from
   geometric primitives plus film grain — abstract material, never an illustration.
   Regenerate with the canvas script documented in assets/backdrops/readme.md. */

const THEMES = {
  construction: {
    label: 'construction',
    hint: 'scaffold bays with diagonal bracing',
    src: 'construction.png'
  },
  robots: {
    label: 'robots',
    hint: 'trace runs and solder pads',
    src: 'robots.png'
  },
  farm: {
    label: 'farm',
    hint: 'plowed furrows receding to a headland',
    src: 'farm.png'
  },
  depot: {
    label: 'depot',
    hint: 'loading bays under overhead lamps',
    src: 'depot.png'
  },
  pipeline: {
    label: 'pipeline',
    hint: 'staged DAG of task cards, left to right',
    src: 'pipeline.png'
  },
  graph: {
    label: 'graph',
    hint: 'scattered regional clusters linked by trunk routes',
    src: 'graph.png'
  },
  tree: {
    label: 'tree',
    hint: 'recursive branching of decision nodes',
    src: 'tree.png'
  },
  neural: {
    label: 'neural',
    hint: 'layered network with weight bundles',
    src: 'neural.png'
  },
  none: {
    label: 'none',
    hint: 'flat ground, no texture',
    src: null
  }
};
const BACKDROP_THEMES = Object.keys(THEMES).map(k => ({
  value: k,
  label: THEMES[k].label,
  hint: THEMES[k].hint
}));
function CrewBackdrop({
  theme = 'construction',
  basePath = 'assets/backdrops/',
  fixed = true,
  style,
  ...rest
}) {
  const def = THEMES[theme] || THEMES.construction;
  const mask = 'radial-gradient(150% 105% at 50% 0%, transparent 14%, #000 72%)';
  return /*#__PURE__*/React.createElement("div", _extends({
    "aria-hidden": "true",
    style: {
      position: fixed ? 'fixed' : 'absolute',
      inset: 0,
      zIndex: 0,
      pointerEvents: 'none',
      backgroundColor: 'var(--color-background-1)',
      ...style
    }
  }, rest), def.src && /*#__PURE__*/React.createElement("div", {
    style: {
      position: 'absolute',
      inset: 0,
      backgroundImage: 'url(' + basePath + def.src + ')',
      backgroundSize: 'cover',
      backgroundPosition: 'center top',
      /* Textures are baked at full designed strength; the variable attenuates
         from there, so no re-render is needed to dial it. */
      opacity: 'var(--backdrop-strength, 1)',
      maskImage: mask,
      WebkitMaskImage: mask
    }
  }));
}
Object.assign(__ds_scope, { BACKDROP_THEMES, CrewBackdrop });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/foreman/CrewBackdrop.jsx", error: String((e && e.message) || e) }); }

// components/foreman/Drawer.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
function Drawer({
  open = false,
  fixed = false,
  title,
  subtitle,
  tabs,
  children,
  footer,
  onClose,
  width = 520,
  style,
  ...rest
}) {
  /* `absolute` only sizes correctly inside a viewport-height ancestor. On a normal
     scrolling page pass `fixed` so the panel is measured against the viewport. */
  const anchor = fixed ? 'fixed' : 'absolute';
  return /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("div", {
    onClick: onClose,
    style: {
      position: anchor,
      inset: 0,
      zIndex: 90,
      background: 'var(--surface-overlay)',
      backdropFilter: 'blur(var(--blur-overlay))',
      WebkitBackdropFilter: 'blur(var(--blur-overlay))',
      opacity: open ? 1 : 0,
      pointerEvents: open ? 'auto' : 'none',
      transition: 'opacity var(--motion-base) var(--ease-default)'
    }
  }), /*#__PURE__*/React.createElement("aside", _extends({
    role: "dialog",
    "aria-modal": "true",
    "aria-hidden": !open,
    style: {
      position: anchor,
      top: 0,
      right: 0,
      bottom: 0,
      zIndex: 91,
      width,
      maxWidth: '100%',
      display: 'flex',
      flexDirection: 'column',
      background: 'var(--surface-card)',
      borderLeft: '1px solid var(--border-hairline)',
      transform: open ? 'translateX(0)' : 'translateX(100%)',
      /* visibility:hidden also drops descendants from the tab order, so a closed
         drawer can never be focused into; it still animates. */
      visibility: open ? 'visible' : 'hidden',
      pointerEvents: open ? 'auto' : 'none',
      transition: 'transform var(--motion-base) var(--ease-default), visibility var(--motion-base) var(--ease-default)',
      ...style
    }
  }, rest), /*#__PURE__*/React.createElement("header", {
    style: {
      display: 'flex',
      alignItems: 'flex-start',
      gap: 'var(--space-3)',
      padding: 'var(--space-4) var(--space-5)',
      borderBottom: '1px solid var(--border-hairline)'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      minWidth: 0,
      display: 'flex',
      flexDirection: 'column',
      gap: 4
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      color: 'var(--text-primary)'
    }
  }, title), subtitle && /*#__PURE__*/React.createElement("span", {
    style: {
      color: 'var(--text-muted)',
      fontSize: 'var(--text-small-size)',
      fontFamily: 'var(--font-mono)'
    }
  }, subtitle)), /*#__PURE__*/React.createElement("button", {
    onClick: onClose,
    "aria-label": "Close",
    style: {
      width: 28,
      height: 28,
      flex: 'none',
      display: 'grid',
      placeItems: 'center',
      background: 'transparent',
      border: '1px solid transparent',
      borderRadius: 'var(--radius-lg)',
      color: 'var(--text-muted)',
      cursor: 'pointer',
      fontSize: 15,
      lineHeight: 1
    }
  }, "\xD7")), tabs && /*#__PURE__*/React.createElement("div", {
    style: {
      padding: '0 var(--space-5)'
    }
  }, tabs), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      minHeight: 0,
      overflow: 'auto',
      padding: 'var(--space-5)',
      display: 'flex',
      flexDirection: 'column',
      gap: 'var(--space-5)'
    }
  }, children), footer && /*#__PURE__*/React.createElement("footer", {
    style: {
      display: 'flex',
      justifyContent: 'flex-end',
      gap: 'var(--space-2)',
      padding: 'var(--space-4) var(--space-5)',
      borderTop: '1px solid var(--border-hairline)'
    }
  }, footer)));
}
Object.assign(__ds_scope, { Drawer });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/foreman/Drawer.jsx", error: String((e && e.message) || e) }); }

// components/foreman/EventRow.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
const KIND_LABEL = {
  ticket_claimed: 'claimed',
  result_recorded: 'result',
  phase_advanced: 'phase',
  host_down: 'host down',
  lease_acquired: 'lease',
  lease_released: 'lease',
  run_started: 'run'
};
function EventRow({
  event = {},
  style,
  ...rest
}) {
  const e = event;
  const loud = e.kind === 'host_down' || e.severity === 'critical';
  const TONE = {
    result_recorded: 'var(--status-ok)',
    phase_advanced: 'var(--status-live)',
    ticket_claimed: 'var(--status-live)',
    lease_acquired: 'var(--status-attention)',
    lease_released: 'var(--status-attention)'
  };
  const tone = TONE[e.kind];
  return /*#__PURE__*/React.createElement("div", _extends({
    style: {
      display: 'grid',
      gridTemplateColumns: '68px 84px 1fr auto',
      alignItems: 'baseline',
      gap: 'var(--space-3)',
      padding: '7px 0',
      borderBottom: '1px solid var(--border-hairline)',
      fontSize: 'var(--text-small-size)',
      ...style
    }
  }, rest), /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: 'var(--font-mono)',
      color: 'var(--text-muted)'
    }
  }, e.ts), /*#__PURE__*/React.createElement("span", {
    style: {
      justifySelf: 'start',
      padding: '0 6px',
      height: 18,
      display: 'inline-flex',
      alignItems: 'center',
      borderRadius: 'var(--radius-lg)',
      border: '1px solid ' + (loud ? 'var(--status-danger)' : tone ? 'color-mix(in oklab, ' + tone + ' 38%, transparent)' : 'var(--border-hairline)'),
      background: loud ? 'var(--status-danger)' : 'transparent',
      color: loud ? 'var(--black)' : tone || 'var(--text-muted)',
      whiteSpace: 'nowrap'
    }
  }, KIND_LABEL[e.kind] || e.kind), /*#__PURE__*/React.createElement("span", {
    style: {
      color: loud ? 'var(--text-primary)' : 'var(--text-secondary)',
      minWidth: 0
    }
  }, e.message), /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: 'var(--font-mono)',
      color: 'var(--text-muted)',
      whiteSpace: 'nowrap'
    }
  }, [e.host, e.ticket_id].filter(Boolean).join(' \u00b7 ')));
}
Object.assign(__ds_scope, { EventRow });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/foreman/EventRow.jsx", error: String((e && e.message) || e) }); }

// components/foreman/HealthBadge.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
const LABELS = {
  reachable: 'reachable',
  agent_ok: 'agent',
  auth_ok: 'auth',
  workspace_ready: 'workspace',
  guard_installed: 'guard'
};
function HealthBadge({
  health = {},
  keys,
  showLatency = true,
  style,
  ...rest
}) {
  const order = keys || Object.keys(LABELS);
  const failing = order.filter(k => health[k] === false);
  return /*#__PURE__*/React.createElement("div", _extends({
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      gap: 8,
      flexWrap: 'wrap',
      ...style
    }
  }, rest), order.map(k => {
    const ok = health[k] !== false;
    const pending = health[k] === null || health[k] === undefined;
    return /*#__PURE__*/React.createElement("span", {
      key: k,
      title: LABELS[k] + (pending ? ': checking' : ok ? ': ok' : ': failing'),
      style: {
        display: 'inline-flex',
        alignItems: 'center',
        gap: 4,
        color: pending ? 'var(--status-live)' : ok ? 'var(--status-ok)' : 'var(--status-danger)',
        fontSize: 'var(--text-small-size)'
      }
    }, /*#__PURE__*/React.createElement("span", {
      "aria-hidden": "true",
      style: {
        width: 7,
        height: 7,
        borderRadius: 'var(--radius-full)',
        boxSizing: 'border-box',
        border: '1px solid currentColor',
        background: pending ? 'transparent' : ok ? 'currentColor' : 'transparent',
        animation: pending ? 'fm-pulse 1.6s ease-out infinite' : 'none'
      }
    }), LABELS[k] || k, !ok && !pending && /*#__PURE__*/React.createElement("span", {
      "aria-hidden": "true"
    }, "\xD7"));
  }), showLatency && health.latency_ms !== undefined && /*#__PURE__*/React.createElement("span", {
    style: {
      color: 'var(--text-muted)',
      fontSize: 'var(--text-small-size)',
      fontFamily: 'var(--font-mono)'
    }
  }, health.latency_ms, "ms"), failing.length > 0 && /*#__PURE__*/React.createElement("span", {
    style: {
      color: 'var(--status-danger)',
      fontSize: 'var(--text-small-size)'
    }
  }, failing.length, " failing"));
}
Object.assign(__ds_scope, { HealthBadge });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/foreman/HealthBadge.jsx", error: String((e && e.message) || e) }); }

// components/foreman/StatTile.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
const TILE_TONE = {
  live: 'var(--status-live)',
  ok: 'var(--status-ok)',
  attention: 'var(--status-attention)',
  danger: 'var(--status-danger)'
};
function StatTile({
  label,
  value,
  delta,
  sparkline,
  tone,
  emphasis = false,
  live = false,
  style,
  ...rest
}) {
  const hue = TILE_TONE[tone];
  return /*#__PURE__*/React.createElement("div", _extends({
    style: {
      background: 'var(--surface-card)',
      borderRadius: 'var(--radius-xl)',
      border: '1px solid ' + (emphasis ? hue ? 'color-mix(in oklab, ' + hue + ' 45%, transparent)' : 'var(--border-control)' : 'transparent'),
      padding: 'var(--space-4)',
      display: 'flex',
      flexDirection: 'column',
      gap: 6,
      minWidth: 0,
      ...style
    }
  }, rest), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 6
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      color: 'var(--text-muted)',
      fontSize: 'var(--text-small-size)'
    }
  }, label), live && /*#__PURE__*/React.createElement("span", {
    "aria-label": "live",
    style: {
      width: 6,
      height: 6,
      borderRadius: 'var(--radius-full)',
      background: hue || 'var(--status-live)',
      animation: 'fm-pulse 1.6s ease-out infinite'
    }
  })), /*#__PURE__*/React.createElement("span", {
    style: {
      color: hue || 'var(--text-primary)',
      fontSize: 30,
      lineHeight: '34px',
      fontFamily: 'var(--font-mono)'
    }
  }, value), delta && /*#__PURE__*/React.createElement("span", {
    style: {
      color: 'var(--text-muted)',
      fontSize: 'var(--text-small-size)'
    }
  }, delta), sparkline);
}
Object.assign(__ds_scope, { StatTile });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/foreman/StatTile.jsx", error: String((e && e.message) || e) }); }

// components/foreman/StatusPill.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/* Status is never carried by hue in this system. Each state gets an alpha tier,
   a distinct marker shape, and a literal label — three redundant signals. */
const TICKET_STATES = {
  queued: {
    label: 'queued',
    tone: 'neutral',
    marker: 'hollow'
  },
  dispatched: {
    label: 'dispatched',
    tone: 'neutral',
    marker: 'half'
  },
  running: {
    label: 'running',
    tone: 'live',
    marker: 'live'
  },
  reducing: {
    label: 'reducing',
    tone: 'live',
    marker: 'half'
  },
  done: {
    label: 'done',
    tone: 'ok',
    marker: 'check'
  },
  parked: {
    label: 'parked',
    tone: 'attention',
    marker: 'dashed'
  },
  failed: {
    label: 'failed',
    tone: 'danger',
    marker: 'cross',
    solid: true
  },
  'needs-human': {
    label: 'needs human',
    tone: 'danger',
    marker: 'bang',
    solid: true
  },
  idle: {
    label: 'idle',
    tone: 'neutral',
    marker: 'hollow'
  },
  busy: {
    label: 'busy',
    tone: 'live',
    marker: 'live'
  },
  draining: {
    label: 'draining',
    tone: 'attention',
    marker: 'half'
  },
  down: {
    label: 'down',
    tone: 'danger',
    marker: 'cross',
    solid: true
  }
};
const TONES = {
  neutral: {
    fg: 'var(--text-muted)',
    edge: 'var(--border-hairline)',
    tint: 'transparent'
  },
  live: {
    fg: 'var(--status-live)',
    edge: 'var(--status-live-edge)',
    tint: 'var(--status-live-tint)'
  },
  ok: {
    fg: 'var(--status-ok)',
    edge: 'var(--status-ok-edge)',
    tint: 'var(--status-ok-tint)'
  },
  attention: {
    fg: 'var(--status-attention)',
    edge: 'var(--status-attention-edge)',
    tint: 'var(--status-attention-tint)'
  },
  danger: {
    fg: 'var(--status-danger)',
    edge: 'var(--status-danger-edge)',
    tint: 'var(--status-danger-tint)'
  }
};
const GLYPH = {
  check: '\u2713',
  cross: '\u00d7',
  bang: '!'
};
function Marker({
  marker
}) {
  const color = 'currentColor';
  if (marker === 'check' || marker === 'cross' || marker === 'bang') {
    return /*#__PURE__*/React.createElement("span", {
      "aria-hidden": "true",
      style: {
        fontSize: 11,
        lineHeight: 1,
        color
      }
    }, GLYPH[marker]);
  }
  const base = {
    width: 7,
    height: 7,
    borderRadius: 'var(--radius-full)',
    flex: 'none',
    boxSizing: 'border-box'
  };
  if (marker === 'hollow') return /*#__PURE__*/React.createElement("span", {
    "aria-hidden": "true",
    style: {
      ...base,
      border: '1px solid ' + color
    }
  });
  if (marker === 'dashed') return /*#__PURE__*/React.createElement("span", {
    "aria-hidden": "true",
    style: {
      ...base,
      border: '1px dashed ' + color
    }
  });
  if (marker === 'half') return /*#__PURE__*/React.createElement("span", {
    "aria-hidden": "true",
    style: {
      ...base,
      border: '1px solid ' + color,
      background: 'linear-gradient(90deg, ' + color + ' 50%, transparent 50%)'
    }
  });
  return /*#__PURE__*/React.createElement("span", {
    "aria-hidden": "true",
    style: {
      ...base,
      background: color,
      animation: 'fm-pulse 1.6s ease-out infinite'
    }
  });
}
function StatusPill({
  state,
  label,
  size = 'md',
  style,
  ...rest
}) {
  const def = TICKET_STATES[state] || {
    label: state,
    tone: 'neutral',
    marker: 'hollow'
  };
  const tone = TONES[def.tone] || TONES.neutral;
  const solid = !!def.solid;
  const sm = size === 'sm';
  return /*#__PURE__*/React.createElement("span", _extends({
    title: label || def.label,
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      gap: 6,
      height: sm ? 18 : 22,
      padding: sm ? '0 6px' : '0 8px',
      borderRadius: 'var(--radius-lg)',
      border: '1px solid ' + (solid ? tone.fg : tone.edge),
      background: solid ? tone.fg : tone.tint,
      color: solid ? 'var(--black)' : tone.fg,
      fontSize: 'var(--text-small-size)',
      lineHeight: 1,
      whiteSpace: 'nowrap',
      ...style
    }
  }, rest), /*#__PURE__*/React.createElement(Marker, {
    marker: def.marker
  }), label || def.label);
}
Object.assign(__ds_scope, { TICKET_STATES, TONES, StatusPill });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/foreman/StatusPill.jsx", error: String((e && e.message) || e) }); }

// components/foreman/CrewRow.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
const {
  useState
} = React;
/* Shared with the crew panel's header strip — keep both in sync via this export. */
const CREW_GRID = 'minmax(160px, 1.1fr) 96px minmax(220px, 1.6fr) 130px 110px 96px 150px';
function CrewRow({
  member = {},
  actions,
  onClick,
  style,
  ...rest
}) {
  const [hover, setHover] = useState(false);
  const m = member;
  const res = m.resources || {};
  return /*#__PURE__*/React.createElement("div", _extends({
    onClick: onClick,
    onMouseEnter: () => setHover(true),
    onMouseLeave: () => setHover(false),
    style: {
      display: 'grid',
      gridTemplateColumns: CREW_GRID,
      alignItems: 'center',
      gap: 'var(--space-4)',
      padding: 'var(--space-3) var(--space-4)',
      borderBottom: '1px solid var(--border-hairline)',
      background: hover ? 'var(--wash-hover)' : 'transparent',
      cursor: onClick ? 'pointer' : 'default',
      transition: 'background var(--motion-fast) var(--ease-default)',
      ...style
    }
  }, rest), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 2,
      minWidth: 0
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: 'var(--font-mono)',
      color: 'var(--text-primary)'
    }
  }, m.id), /*#__PURE__*/React.createElement("span", {
    style: {
      color: 'var(--text-muted)',
      fontSize: 'var(--text-small-size)'
    }
  }, m.site)), /*#__PURE__*/React.createElement(__ds_scope.StatusPill, {
    state: m.state,
    size: "sm"
  }), /*#__PURE__*/React.createElement(__ds_scope.HealthBadge, {
    health: m.health
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: 'var(--text-small-size)',
      color: 'var(--text-secondary)'
    }
  }, Object.keys(res).map(k => res[k] + '\u00d7 ' + k).join(' \u00b7 ')), /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: 'var(--text-small-size)',
      color: m.current_ticket ? 'var(--text-secondary)' : 'var(--text-muted)'
    }
  }, m.current_ticket || '\u2014'), /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: 'var(--text-small-size)',
      color: 'var(--text-muted)'
    }
  }, m.throughput_per_min, "/min"), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'flex-end',
      gap: 'var(--space-2)'
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      color: 'var(--text-muted)',
      fontSize: 'var(--text-small-size)',
      fontFamily: 'var(--font-mono)'
    }
  }, m.last_heartbeat), actions));
}
Object.assign(__ds_scope, { CREW_GRID, CrewRow });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/foreman/CrewRow.jsx", error: String((e && e.message) || e) }); }

// components/foreman/KanbanColumn.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
function KanbanColumn({
  state,
  title,
  count,
  children,
  empty = 'No tickets',
  width = 268,
  style,
  ...rest
}) {
  const items = React.Children.toArray(children);
  return /*#__PURE__*/React.createElement("section", _extends({
    style: {
      width,
      flex: 'none',
      display: 'flex',
      flexDirection: 'column',
      gap: 'var(--space-3)',
      minHeight: 0,
      ...style
    }
  }, rest), /*#__PURE__*/React.createElement("header", {
    style: {
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      gap: 8,
      paddingBottom: 'var(--space-2)',
      borderBottom: '1px solid var(--border-hairline)'
    }
  }, /*#__PURE__*/React.createElement(__ds_scope.StatusPill, {
    state: state,
    label: title,
    size: "sm"
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: 'var(--text-small-size)',
      color: 'var(--text-muted)'
    }
  }, count !== undefined ? count : items.length)), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 'var(--space-2)',
      overflow: 'auto',
      minHeight: 0,
      paddingBottom: 'var(--space-4)'
    }
  }, items.length ? items : /*#__PURE__*/React.createElement("div", {
    style: {
      padding: 'var(--space-6) var(--space-3)',
      textAlign: 'center',
      color: 'var(--text-muted)',
      fontSize: 'var(--text-small-size)',
      border: '1px dashed var(--border-hairline)',
      borderRadius: 'var(--radius-lg)'
    }
  }, empty)));
}
Object.assign(__ds_scope, { KanbanColumn });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/foreman/KanbanColumn.jsx", error: String((e && e.message) || e) }); }

// components/foreman/TicketCard.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
const {
  useState
} = React;
function TicketCard({
  ticket = {},
  selected = false,
  onClick,
  style,
  ...rest
}) {
  const [hover, setHover] = useState(false);
  const t = ticket;
  return /*#__PURE__*/React.createElement("article", _extends({
    onClick: onClick,
    onMouseEnter: () => setHover(true),
    onMouseLeave: () => setHover(false),
    tabIndex: 0,
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 8,
      padding: 'var(--space-3)',
      borderRadius: 'var(--radius-lg)',
      background: selected ? 'var(--wash-selected)' : hover ? 'var(--wash-hover)' : 'var(--surface-card)',
      border: '1px solid ' + (selected ? 'var(--border-control)' : 'var(--border-hairline)'),
      cursor: onClick ? 'pointer' : 'default',
      transition: 'background var(--motion-fast) var(--ease-default), border-color var(--motion-fast) var(--ease-default)',
      ...style
    }
  }, rest), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      gap: 8
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: 'var(--text-small-size)',
      color: 'var(--text-muted)'
    }
  }, t.id), /*#__PURE__*/React.createElement(__ds_scope.StatusPill, {
    state: t.state,
    size: "sm"
  })), /*#__PURE__*/React.createElement("span", {
    style: {
      color: 'var(--text-primary)',
      fontSize: 13,
      lineHeight: '18px',
      wordBreak: 'break-word'
    }
  }, t.subject), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 8,
      flexWrap: 'wrap',
      color: 'var(--text-muted)',
      fontSize: 'var(--text-small-size)'
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      gap: 4,
      padding: '0 6px',
      height: 18,
      border: '1px solid var(--border-hairline)',
      borderRadius: 'var(--radius-lg)',
      fontFamily: 'var(--font-mono)'
    }
  }, t.resource_req), /*#__PURE__*/React.createElement("span", null, t.phase), t.host && /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: 'var(--font-mono)'
    }
  }, t.host)), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 10,
      color: 'var(--text-muted)',
      fontSize: 'var(--text-small-size)',
      fontFamily: 'var(--font-mono)'
    }
  }, /*#__PURE__*/React.createElement("span", null, "try ", t.attempts), /*#__PURE__*/React.createElement("span", null, t.elapsed_s, "s"), t.priority !== undefined && /*#__PURE__*/React.createElement("span", null, "p", t.priority)));
}
Object.assign(__ds_scope, { TicketCard });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/foreman/TicketCard.jsx", error: String((e && e.message) || e) }); }

// components/forms/Checkbox.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
const {
  useState
} = React;
function Checkbox({
  label,
  checked,
  defaultChecked,
  onChange,
  disabled = false,
  style,
  ...rest
}) {
  const [hover, setHover] = useState(false);
  const [internal, setInternal] = useState(!!defaultChecked);
  const isOn = checked === undefined ? internal : checked;
  const toggle = e => {
    if (disabled) return;
    if (checked === undefined) setInternal(!isOn);
    onChange && onChange(!isOn, e);
  };
  return /*#__PURE__*/React.createElement("label", {
    onMouseEnter: () => setHover(true),
    onMouseLeave: () => setHover(false),
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      gap: 'var(--space-2)',
      minHeight: 'var(--hit-target-min)',
      cursor: disabled ? 'default' : 'pointer',
      opacity: disabled ? 0.35 : 1,
      color: isOn ? 'var(--text-primary)' : 'var(--text-secondary)',
      ...style
    }
  }, /*#__PURE__*/React.createElement("input", _extends({
    type: "checkbox",
    checked: isOn,
    onChange: toggle,
    disabled: disabled,
    style: {
      position: 'absolute',
      opacity: 0,
      width: 16,
      height: 16,
      margin: 0
    }
  }, rest)), /*#__PURE__*/React.createElement("span", {
    "aria-hidden": "true",
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      justifyContent: 'center',
      width: 16,
      height: 16,
      flex: 'none',
      borderRadius: 4,
      border: '1px solid ' + (isOn || hover ? 'var(--border-control-hover)' : 'var(--border-control)'),
      background: isOn ? 'var(--white)' : 'transparent',
      color: 'var(--black)',
      fontSize: 11,
      lineHeight: 1,
      transition: 'all var(--motion-fast) var(--ease-default)'
    }
  }, isOn ? '\u2713' : ''), label);
}
Object.assign(__ds_scope, { Checkbox });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/forms/Checkbox.jsx", error: String((e && e.message) || e) }); }

// components/forms/Input.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
const {
  useState
} = React;
function Input({
  label,
  hint,
  placeholder,
  value,
  defaultValue,
  onChange,
  type = 'text',
  disabled = false,
  prefix = null,
  suffix = null,
  id,
  style,
  ...rest
}) {
  const [hover, setHover] = useState(false);
  const inputId = id || (label ? 'in-' + label.replace(/\s+/g, '-').toLowerCase() : undefined);
  return /*#__PURE__*/React.createElement("label", {
    htmlFor: inputId,
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 'var(--space-2)',
      opacity: disabled ? 0.35 : 1,
      ...style
    }
  }, label && /*#__PURE__*/React.createElement("span", {
    style: {
      color: 'var(--text-secondary)',
      fontSize: 'var(--text-small-size)'
    }
  }, label), /*#__PURE__*/React.createElement("span", {
    onMouseEnter: () => setHover(true),
    onMouseLeave: () => setHover(false),
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 'var(--space-2)',
      height: 36,
      padding: '0 var(--space-3)',
      borderRadius: 'var(--radius-lg)',
      border: '1px solid ' + (hover && !disabled ? 'var(--border-control-hover)' : 'var(--border-control)'),
      transition: 'border-color var(--motion-fast) var(--ease-default)',
      color: 'var(--text-muted)'
    }
  }, prefix, /*#__PURE__*/React.createElement("input", _extends({
    id: inputId,
    type: type,
    placeholder: placeholder,
    value: value,
    defaultValue: defaultValue,
    onChange: onChange,
    disabled: disabled,
    style: {
      flex: 1,
      minWidth: 0,
      border: 'none',
      outline: 'none',
      background: 'transparent',
      color: 'var(--text-primary)',
      fontFamily: 'var(--font-sans)',
      fontSize: 'var(--text-body-size)',
      lineHeight: 'var(--text-body-leading)'
    }
  }, rest)), suffix), hint && /*#__PURE__*/React.createElement("span", {
    style: {
      color: 'var(--text-muted)',
      fontSize: 'var(--text-small-size)'
    }
  }, hint));
}
Object.assign(__ds_scope, { Input });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/forms/Input.jsx", error: String((e && e.message) || e) }); }

// components/forms/Select.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
const {
  useState
} = React;
function Select({
  label,
  options = [],
  value,
  defaultValue,
  onChange,
  disabled = false,
  id,
  style,
  ...rest
}) {
  const [hover, setHover] = useState(false);
  const selectId = id || (label ? 'sel-' + label.replace(/\s+/g, '-').toLowerCase() : undefined);
  return /*#__PURE__*/React.createElement("label", {
    htmlFor: selectId,
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 'var(--space-2)',
      opacity: disabled ? 0.35 : 1,
      ...style
    }
  }, label && /*#__PURE__*/React.createElement("span", {
    style: {
      color: 'var(--text-secondary)',
      fontSize: 'var(--text-small-size)'
    }
  }, label), /*#__PURE__*/React.createElement("select", _extends({
    id: selectId,
    value: value,
    defaultValue: defaultValue,
    onChange: onChange,
    disabled: disabled,
    onMouseEnter: () => setHover(true),
    onMouseLeave: () => setHover(false),
    style: {
      height: 36,
      padding: '0 var(--space-3)',
      borderRadius: 'var(--radius-lg)',
      border: '1px solid ' + (hover && !disabled ? 'var(--border-control-hover)' : 'var(--border-control)'),
      background: 'transparent',
      color: 'var(--text-primary)',
      fontFamily: 'var(--font-sans)',
      fontSize: 'var(--text-body-size)',
      transition: 'border-color var(--motion-fast) var(--ease-default)'
    }
  }, rest), options.map(o => {
    const opt = typeof o === 'string' ? {
      value: o,
      label: o
    } : o;
    return /*#__PURE__*/React.createElement("option", {
      key: opt.value,
      value: opt.value,
      style: {
        background: 'var(--surface-card)',
        color: 'var(--text-primary)'
      }
    }, opt.label);
  })));
}
Object.assign(__ds_scope, { Select });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/forms/Select.jsx", error: String((e && e.message) || e) }); }

// components/forms/Switch.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
const {
  useState
} = React;
function Switch({
  label,
  checked,
  defaultChecked,
  onChange,
  disabled = false,
  style,
  ...rest
}) {
  const [internal, setInternal] = useState(!!defaultChecked);
  const isOn = checked === undefined ? internal : checked;
  const toggle = () => {
    if (disabled) return;
    if (checked === undefined) setInternal(!isOn);
    onChange && onChange(!isOn);
  };
  return /*#__PURE__*/React.createElement("label", {
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      gap: 'var(--space-3)',
      minHeight: 'var(--hit-target-min)',
      cursor: disabled ? 'default' : 'pointer',
      opacity: disabled ? 0.35 : 1,
      color: 'var(--text-secondary)',
      ...style
    }
  }, /*#__PURE__*/React.createElement("button", _extends({
    type: "button",
    role: "switch",
    "aria-checked": isOn,
    onClick: toggle,
    disabled: disabled,
    style: {
      position: 'relative',
      width: 36,
      height: 20,
      flex: 'none',
      padding: 0,
      borderRadius: 'var(--radius-full)',
      border: '1px solid ' + (isOn ? 'var(--white)' : 'var(--border-control)'),
      background: isOn ? 'var(--white)' : 'transparent',
      cursor: 'inherit',
      transition: 'all var(--motion-base) var(--ease-default)'
    }
  }, rest), /*#__PURE__*/React.createElement("span", {
    style: {
      position: 'absolute',
      top: 2,
      left: isOn ? 18 : 2,
      width: 14,
      height: 14,
      borderRadius: 'var(--radius-full)',
      background: isOn ? 'var(--black)' : 'var(--border-control)',
      transition: 'left var(--motion-base) var(--ease-default), background var(--motion-base) var(--ease-default)'
    }
  })), label);
}
Object.assign(__ds_scope, { Switch });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/forms/Switch.jsx", error: String((e && e.message) || e) }); }

// components/navigation/Header.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
function Header({
  brand = 'Brandmark',
  links = [],
  actions = null,
  sticky = true,
  style,
  ...rest
}) {
  return /*#__PURE__*/React.createElement("header", _extends({
    style: {
      position: sticky ? 'sticky' : 'relative',
      top: 0,
      zIndex: 50,
      height: 'var(--header-height)',
      display: 'flex',
      alignItems: 'center',
      gap: 'var(--space-8)',
      padding: '0 var(--space-6)',
      background: 'var(--surface-header)',
      backdropFilter: 'blur(var(--blur-overlay))',
      WebkitBackdropFilter: 'blur(var(--blur-overlay))',
      borderBottom: '1px solid var(--border-hairline)',
      ...style
    }
  }, rest), /*#__PURE__*/React.createElement("span", {
    style: {
      color: 'var(--text-primary)',
      fontSize: 'var(--text-body-size)'
    }
  }, brand), /*#__PURE__*/React.createElement("nav", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 'var(--space-5)',
      flex: 1
    }
  }, links.map(l => /*#__PURE__*/React.createElement("a", {
    key: l.label,
    href: l.href || '#',
    style: {
      color: l.active ? 'var(--text-primary)' : 'var(--text-secondary)',
      fontSize: 'var(--text-body-size)'
    }
  }, l.label))), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 'var(--space-2)'
    }
  }, actions));
}
Object.assign(__ds_scope, { Header });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/navigation/Header.jsx", error: String((e && e.message) || e) }); }

// components/navigation/Tabs.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
const {
  useState
} = React;
function Tabs({
  items = [],
  value,
  defaultValue,
  onChange,
  style,
  ...rest
}) {
  const [internal, setInternal] = useState(defaultValue ?? (items[0] && (items[0].value || items[0])));
  const current = value === undefined ? internal : value;
  const norm = items.map(i => typeof i === 'string' ? {
    value: i,
    label: i
  } : i);
  return /*#__PURE__*/React.createElement("div", _extends({
    role: "tablist",
    style: {
      display: 'flex',
      alignItems: 'stretch',
      gap: 'var(--space-5)',
      borderBottom: '1px solid var(--border-hairline)',
      ...style
    }
  }, rest), norm.map(t => {
    const on = t.value === current;
    return /*#__PURE__*/React.createElement("button", {
      key: t.value,
      role: "tab",
      "aria-selected": on,
      onClick: () => {
        if (value === undefined) setInternal(t.value);
        onChange && onChange(t.value);
      },
      style: {
        display: 'inline-flex',
        alignItems: 'center',
        gap: 'var(--space-2)',
        padding: 'var(--space-3) 0',
        background: 'transparent',
        border: 'none',
        borderBottom: '1px solid ' + (on ? 'var(--white)' : 'transparent'),
        marginBottom: -1,
        color: on ? 'var(--text-primary)' : 'var(--text-muted)',
        fontFamily: 'var(--font-sans)',
        fontSize: 'var(--text-body-size)',
        cursor: 'pointer',
        transition: 'color var(--motion-fast) var(--ease-default)'
      }
    }, t.label, t.count !== undefined && /*#__PURE__*/React.createElement("span", {
      style: {
        color: 'var(--text-muted)'
      }
    }, t.count));
  }));
}
Object.assign(__ds_scope, { Tabs });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/navigation/Tabs.jsx", error: String((e && e.message) || e) }); }

// ds-preview.js
try { (() => {
/* Preview-only loader. Uses the generated design-system bundle when it exists,
   otherwise transpiles the component sources in the browser so every card and
   UI kit renders standalone. Not for production consumers. */
(function () {
  var FILES = ["components/core/Button.jsx", "components/core/IconButton.jsx", "components/core/Card.jsx", "components/core/Badge.jsx", "components/core/Divider.jsx", "components/forms/Input.jsx", "components/forms/Select.jsx", "components/forms/Checkbox.jsx", "components/forms/Switch.jsx", "components/navigation/Header.jsx", "components/navigation/Tabs.jsx", "components/feedback/Dialog.jsx", "components/feedback/Tooltip.jsx", "components/feedback/EmptyState.jsx", "components/data/Table.jsx", "components/foreman/StatusPill.jsx", "components/foreman/StatTile.jsx", "components/foreman/HealthBadge.jsx", "components/foreman/AttentionBanner.jsx", "components/foreman/TicketCard.jsx", "components/foreman/KanbanColumn.jsx", "components/foreman/CrewRow.jsx", "components/foreman/EventRow.jsx", "components/foreman/Drawer.jsx", "components/foreman/CrewBackdrop.jsx"];
  function fromBundle() {
    for (var k in window) {
      try {
        var v = window[k];
        if (v && typeof v === 'object' && !Array.isArray(v) && typeof v.Button === 'function' && typeof v.Table === 'function') return v;
      } catch (e) {}
    }
    return null;
  }
  function loadScript(src) {
    return new Promise(function (res) {
      var s = document.createElement('script');
      s.src = src;
      s.onload = res;
      s.onerror = res;
      document.head.appendChild(s);
    });
  }
  function transpile(code) {
    return Babel.transform(code, {
      presets: [['react', {
        runtime: 'classic'
      }]]
    }).code;
  }

  /* Loads sibling .jsx files (plain function declarations, no exports) and
     evaluates them in global scope with the classic JSX runtime. */
  window.DSScripts = function (rel, files) {
    return Promise.all(files.map(function (f) {
      return fetch(rel + f).then(function (r) {
        return r.text();
      });
    })).then(function (srcs) {
      (0, eval)(transpile(srcs.join('\n')));
    });
  };

  /* Evaluates the JSX inside <script type="text/x-jsx" id="..."> */
  window.DSInline = function (id) {
    (0, eval)(transpile(document.getElementById(id).textContent));
  };
  window.DSReady = function (rootRel) {
    rootRel = rootRel || './';
    return fetch(rootRel + '_ds_bundle.js').then(function (r) {
      return r.ok ? loadScript(rootRel + '_ds_bundle.js') : null;
    }, function () {
      return null;
    }).then(function () {
      var ns = fromBundle();
      if (ns) return ns;
      return Promise.all(FILES.map(function (f) {
        return fetch(rootRel + f).then(function (r) {
          return r.text();
        });
      })).then(function (srcs) {
        window.__dsreg = {};
        var codes = srcs.map(function (src, i) {
          var name = FILES[i].split('/').pop().replace('.jsx', '');
          var body = src.replace(/^\s*import[^\n]*\n/gm, '').replace(/^export\s+/gm, '');
          var siblings = FILES.map(function (g) {
            return g.split('/').pop().replace('.jsx', '');
          }).filter(function (n) {
            return n !== name;
          }).map(function (n) {
            return 'var ' + n + ' = window.__dsreg["' + n + '"];';
          }).concat(name === 'CrewRow' ? [] : ['var CREW_GRID = window.__dsreg.CREW_GRID;']).join(' ');
          return '(function(){ var useState = React.useState, useEffect = React.useEffect, useRef = React.useRef, useMemo = React.useMemo, Fragment = React.Fragment; ' + siblings + '\n' + body + '\nwindow.__dsreg["' + name + '"] = ' + name + ';\n' + 'if (typeof CREW_GRID !== "undefined") window.__dsreg.CREW_GRID = CREW_GRID;\n' + 'if (typeof TICKET_STATES !== "undefined") window.__dsreg.TICKET_STATES = TICKET_STATES;\n' + 'if (typeof BACKDROP_THEMES !== "undefined") window.__dsreg.BACKDROP_THEMES = BACKDROP_THEMES; })();';
        });
        codes.forEach(function (piece) {
          (0, eval)(Babel.transform(piece, {
            presets: [['react', {
              runtime: 'classic'
            }]]
          }).code);
        });
        return window.__dsreg;
      });
    });
  };
})();
})(); } catch (e) { __ds_ns.__errors.push({ path: "ds-preview.js", error: String((e && e.message) || e) }); }

// ui_kits/console/App.jsx
try { (() => {
const {
  Dialog,
  Button
} = window.DSNS;
function App() {
  const [signedIn, setSignedIn] = React.useState(false);
  const [route, setRoute] = React.useState('dashboard');
  const [newQuery, setNewQuery] = React.useState(false);
  React.useEffect(() => {
    if (window.lucide) lucide.createIcons();
  });
  if (!signedIn) return /*#__PURE__*/React.createElement(LoginScreen, {
    onSignIn: () => setSignedIn(true)
  });
  const isTable = route.startsWith('table:');
  const table = isTable ? route.slice(6) : null;
  const title = isTable ? table : route === 'queries' ? 'Churn by plan' : 'Overview';
  const crumb = isTable ? 'public.' + table : route === 'queries' ? 'saved query' : 'northlake';
  return /*#__PURE__*/React.createElement("div", {
    style: {
      position: 'relative',
      display: 'flex',
      height: '100vh',
      overflow: 'hidden'
    }
  }, /*#__PURE__*/React.createElement(Sidebar, {
    active: route,
    onSelect: setRoute
  }), /*#__PURE__*/React.createElement("main", {
    style: {
      flex: 1,
      minWidth: 0,
      display: 'flex',
      flexDirection: 'column',
      overflow: 'hidden'
    }
  }, /*#__PURE__*/React.createElement(TopBar, {
    title: title,
    crumb: crumb,
    onNew: () => setNewQuery(true)
  }), isTable && /*#__PURE__*/React.createElement(TableScreen, {
    table: table
  }), route === 'dashboard' && /*#__PURE__*/React.createElement(DashboardScreen, {
    onOpenTable: t => setRoute('table:' + t)
  }), route === 'queries' && /*#__PURE__*/React.createElement(QueryScreen, null)), /*#__PURE__*/React.createElement(Dialog, {
    open: newQuery,
    title: "New query",
    description: "Name it now or leave it as a draft.",
    onClose: () => setNewQuery(false),
    footer: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement(Button, {
      variant: "ghost",
      size: "sm",
      onClick: () => setNewQuery(false)
    }, "Cancel"), /*#__PURE__*/React.createElement(Button, {
      size: "sm",
      onClick: () => {
        setNewQuery(false);
        setRoute('queries');
      }
    }, "Create"))
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      color: 'var(--text-muted)'
    }
  }, "Queries run against the connected Postgres source.")));
}
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/console/App.jsx", error: String((e && e.message) || e) }); }

// ui_kits/console/AppShell.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
function Sidebar({
  active,
  onSelect
}) {
  const {
    Divider,
    IconButton
  } = window.DSNS;
  const groups = [{
    label: 'workspace',
    items: [{
      id: 'dashboard',
      icon: 'layout-dashboard',
      label: 'Overview'
    }, {
      id: 'queries',
      icon: 'terminal',
      label: 'Queries'
    }]
  }];
  return /*#__PURE__*/React.createElement("aside", {
    style: {
      width: 232,
      flex: 'none',
      display: 'flex',
      flexDirection: 'column',
      borderRight: '1px solid var(--border-hairline)',
      padding: '16px 12px',
      gap: 18
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      padding: '0 4px'
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      color: 'var(--text-primary)'
    }
  }, "Northlake"), /*#__PURE__*/React.createElement(IconButton, {
    label: "Workspace settings"
  }, /*#__PURE__*/React.createElement("i", {
    "data-lucide": "chevrons-up-down",
    style: {
      width: 14,
      height: 14
    }
  }))), groups.map(g => /*#__PURE__*/React.createElement("div", {
    key: g.label,
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 2
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      padding: '0 4px 6px',
      color: 'var(--text-muted)',
      fontSize: 12
    }
  }, g.label), g.items.map(it => /*#__PURE__*/React.createElement(NavItem, _extends({
    key: it.id
  }, it, {
    active: active === it.id,
    onClick: () => onSelect(it.id)
  }))))), /*#__PURE__*/React.createElement(Divider, null), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 2,
      minHeight: 0,
      overflow: 'auto'
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      padding: '0 4px 6px',
      color: 'var(--text-muted)',
      fontSize: 12
    }
  }, "tables"), window.KIT_DATA.tables.map(t => /*#__PURE__*/React.createElement(NavItem, {
    key: t.name,
    id: t.name,
    icon: "table-2",
    label: t.name,
    meta: t.rows,
    active: active === 'table:' + t.name,
    onClick: () => onSelect('table:' + t.name)
  }))));
}
function NavItem({
  icon,
  label,
  meta,
  active,
  onClick
}) {
  const [hover, setHover] = React.useState(false);
  return /*#__PURE__*/React.createElement("button", {
    onClick: onClick,
    onMouseEnter: () => setHover(true),
    onMouseLeave: () => setHover(false),
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 8,
      height: 32,
      padding: '0 8px',
      background: active ? 'var(--wash-selected)' : hover ? 'var(--wash-hover)' : 'transparent',
      border: 'none',
      borderRadius: 'var(--radius-lg)',
      color: active || hover ? 'var(--text-primary)' : 'var(--text-secondary)',
      font: '400 14px var(--font-sans)',
      cursor: 'pointer',
      textAlign: 'left',
      transition: 'background 120ms ease-out, color 120ms ease-out'
    }
  }, /*#__PURE__*/React.createElement("i", {
    "data-lucide": icon,
    style: {
      width: 15,
      height: 15,
      flex: 'none',
      opacity: 0.8
    }
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      flex: 1,
      overflow: 'hidden',
      textOverflow: 'ellipsis',
      whiteSpace: 'nowrap'
    }
  }, label), meta && /*#__PURE__*/React.createElement("span", {
    style: {
      color: 'var(--text-muted)',
      fontSize: 12,
      fontFamily: 'var(--font-mono)'
    }
  }, meta));
}
function TopBar({
  title,
  crumb,
  onNew
}) {
  const {
    Button,
    IconButton,
    Tooltip
  } = window.DSNS;
  return /*#__PURE__*/React.createElement("header", {
    style: {
      position: 'sticky',
      top: 0,
      zIndex: 40,
      height: 56,
      flex: 'none',
      display: 'flex',
      alignItems: 'center',
      gap: 16,
      padding: '0 20px',
      background: 'oklab(0 0 0 / 0.85)',
      backdropFilter: 'blur(12px)',
      borderBottom: '1px solid var(--border-hairline)'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'baseline',
      gap: 8,
      flex: 1,
      minWidth: 0
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      color: 'var(--text-primary)'
    }
  }, title), crumb && /*#__PURE__*/React.createElement("span", {
    style: {
      color: 'var(--text-muted)',
      fontSize: 12,
      fontFamily: 'var(--font-mono)'
    }
  }, crumb)), /*#__PURE__*/React.createElement(Tooltip, {
    label: "Refresh"
  }, /*#__PURE__*/React.createElement(IconButton, {
    label: "Refresh"
  }, /*#__PURE__*/React.createElement("i", {
    "data-lucide": "refresh-cw",
    style: {
      width: 15,
      height: 15
    }
  }))), /*#__PURE__*/React.createElement(Button, {
    size: "sm",
    iconLeft: /*#__PURE__*/React.createElement("i", {
      "data-lucide": "plus",
      style: {
        width: 14,
        height: 14
      }
    }),
    onClick: onNew
  }, "New query"));
}
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/console/AppShell.jsx", error: String((e && e.message) || e) }); }

// ui_kits/console/DashboardScreen.jsx
try { (() => {
function DashboardScreen({
  onOpenTable
}) {
  const {
    Card,
    Button,
    Badge,
    Divider,
    Table
  } = window.DSNS;
  const metrics = [{
    label: 'MRR',
    value: '$48,210',
    delta: '+4.1% vs last month'
  }, {
    label: 'Active workspaces',
    value: '412',
    delta: '+18 this week'
  }, {
    label: 'Rows synced',
    value: '1.4M',
    delta: 'last sync 2m ago'
  }];
  return /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      overflow: 'auto',
      padding: 20,
      display: 'flex',
      flexDirection: 'column',
      gap: 16
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'grid',
      gridTemplateColumns: 'repeat(3, minmax(0, 1fr))',
      gap: 16
    }
  }, metrics.map(m => /*#__PURE__*/React.createElement(Card, {
    key: m.label,
    padding: "md"
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      color: 'var(--text-muted)',
      fontSize: 12
    }
  }, m.label), /*#__PURE__*/React.createElement("div", {
    style: {
      color: 'var(--text-primary)',
      fontSize: 30,
      lineHeight: '34px',
      marginTop: 6
    }
  }, m.value), /*#__PURE__*/React.createElement("div", {
    style: {
      color: 'var(--text-muted)',
      fontSize: 12,
      marginTop: 6
    }
  }, m.delta)))), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'grid',
      gridTemplateColumns: 'minmax(0, 2fr) minmax(0, 1fr)',
      gap: 16,
      alignItems: 'start'
    }
  }, /*#__PURE__*/React.createElement(Card, {
    title: "Recent rows",
    subtitle: "users",
    action: /*#__PURE__*/React.createElement(Button, {
      size: "sm",
      onClick: () => onOpenTable('users')
    }, "Open table"),
    padding: "md"
  }, /*#__PURE__*/React.createElement(Table, {
    dense: true,
    rows: window.KIT_DATA.users.slice(0, 5),
    columns: [{
      key: 'id',
      label: 'id',
      mono: true,
      muted: true
    }, {
      key: 'email',
      label: 'email'
    }, {
      key: 'plan',
      label: 'plan',
      render: r => /*#__PURE__*/React.createElement(Badge, {
        size: "sm"
      }, r.plan)
    }, {
      key: 'mrr',
      label: 'mrr',
      align: 'right',
      mono: true
    }]
  })), /*#__PURE__*/React.createElement(Card, {
    title: "Saved queries",
    padding: "md"
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column'
    }
  }, window.KIT_DATA.queries.map((q, i) => /*#__PURE__*/React.createElement(React.Fragment, {
    key: q.name
  }, i > 0 && /*#__PURE__*/React.createElement(Divider, null), /*#__PURE__*/React.createElement("div", {
    style: {
      padding: '12px 0'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      color: 'var(--text-primary)'
    }
  }, q.name), /*#__PURE__*/React.createElement("div", {
    style: {
      color: 'var(--text-muted)',
      fontSize: 12,
      marginTop: 2
    }
  }, q.owner, " \xB7 ran ", q.run))))))));
}
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/console/DashboardScreen.jsx", error: String((e && e.message) || e) }); }

// ui_kits/console/LoginScreen.jsx
try { (() => {
function LoginScreen({
  onSignIn
}) {
  const {
    Button,
    Input,
    Checkbox
  } = window.DSNS;
  return /*#__PURE__*/React.createElement("div", {
    style: {
      minHeight: '100%',
      display: 'grid',
      placeItems: 'center',
      padding: 24
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      width: 360,
      display: 'flex',
      flexDirection: 'column',
      gap: 24
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 10
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      color: 'var(--text-primary)'
    }
  }, "Northlake"), /*#__PURE__*/React.createElement("h1", {
    style: {
      fontSize: 48,
      lineHeight: '48px',
      fontWeight: 400,
      color: 'var(--text-primary)'
    }
  }, "Sign in"), /*#__PURE__*/React.createElement("p", {
    style: {
      margin: 0,
      color: 'var(--text-muted)'
    }
  }, "Use your work email. We\u2019ll send a link.")), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 14
    }
  }, /*#__PURE__*/React.createElement(Input, {
    label: "Work email",
    placeholder: "you@company.com",
    type: "email"
  }), /*#__PURE__*/React.createElement(Checkbox, {
    label: "Keep me signed in",
    defaultChecked: true
  }), /*#__PURE__*/React.createElement(Button, {
    full: true,
    size: "lg",
    onClick: onSignIn
  }, "Continue"))));
}
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/console/LoginScreen.jsx", error: String((e && e.message) || e) }); }

// ui_kits/console/QueryScreen.jsx
try { (() => {
function QueryScreen() {
  const {
    Button,
    Badge,
    Table,
    Switch,
    Divider,
    EmptyState
  } = window.DSNS;
  const sql = 'select plan, count(*) as accounts, sum(seats) as seats\nfrom users\nwhere created_at > now() - interval \'30 days\'\ngroup by 1\norder by accounts desc';
  const [ran, setRan] = React.useState(false);
  const [live, setLive] = React.useState(false);
  const result = [{
    plan: 'Pro',
    accounts: 148,
    seats: 1204
  }, {
    plan: 'Team',
    accounts: 96,
    seats: 402
  }, {
    plan: 'Free',
    accounts: 168,
    seats: 168
  }];
  return /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      minHeight: 0,
      display: 'flex',
      flexDirection: 'column',
      padding: 20,
      gap: 16
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      background: 'var(--surface-card)',
      borderRadius: 'var(--radius-xl)',
      overflow: 'hidden'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 10,
      padding: '10px 14px',
      borderBottom: '1px solid var(--border-hairline)'
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      color: 'var(--text-secondary)'
    }
  }, "Churn by plan"), /*#__PURE__*/React.createElement(Badge, {
    size: "sm",
    variant: "outline"
  }, "draft"), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1
    }
  }), /*#__PURE__*/React.createElement(Switch, {
    label: "Live",
    checked: live,
    onChange: setLive
  }), /*#__PURE__*/React.createElement(Button, {
    size: "sm",
    onClick: () => setRan(true),
    iconLeft: /*#__PURE__*/React.createElement("i", {
      "data-lucide": "play",
      style: {
        width: 13,
        height: 13
      }
    })
  }, "Run")), /*#__PURE__*/React.createElement("pre", {
    style: {
      margin: 0,
      padding: 16,
      fontFamily: 'var(--font-mono)',
      fontSize: 13,
      lineHeight: '20px',
      color: 'var(--text-secondary)',
      whiteSpace: 'pre-wrap'
    }
  }, sql)), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      minHeight: 0,
      overflow: 'auto'
    }
  }, ran ? /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'baseline',
      gap: 10,
      marginBottom: 8
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      color: 'var(--text-primary)'
    }
  }, "3 rows"), /*#__PURE__*/React.createElement("span", {
    style: {
      color: 'var(--text-muted)',
      fontSize: 12,
      fontFamily: 'var(--font-mono)'
    }
  }, "412ms \xB7 12,480 scanned")), /*#__PURE__*/React.createElement(Divider, null), /*#__PURE__*/React.createElement(Table, {
    rows: result,
    columns: [{
      key: 'plan',
      label: 'plan'
    }, {
      key: 'accounts',
      label: 'accounts',
      align: 'right',
      mono: true
    }, {
      key: 'seats',
      label: 'seats',
      align: 'right',
      mono: true
    }]
  })) : /*#__PURE__*/React.createElement(EmptyState, {
    title: "No results yet",
    description: "Run the query to see rows.",
    action: /*#__PURE__*/React.createElement(Button, {
      size: "sm",
      onClick: () => setRan(true)
    }, "Run query")
  })));
}
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/console/QueryScreen.jsx", error: String((e && e.message) || e) }); }

// ui_kits/console/TableScreen.jsx
try { (() => {
function TableScreen({
  table
}) {
  const {
    Tabs,
    Input,
    Select,
    Button,
    IconButton,
    Badge,
    Table,
    Checkbox,
    Divider,
    EmptyState,
    Tooltip
  } = window.DSNS;
  const [view, setView] = React.useState('rows');
  const [q, setQ] = React.useState('');
  const rows = window.KIT_DATA.users.filter(r => r.email.includes(q.toLowerCase()));
  const columns = [{
    key: 'id',
    label: 'id',
    mono: true,
    muted: true,
    type: 'text'
  }, {
    key: 'email',
    label: 'email',
    type: 'text'
  }, {
    key: 'plan',
    label: 'plan',
    type: 'enum',
    render: r => /*#__PURE__*/React.createElement(Badge, {
      size: "sm",
      variant: r.plan === 'Free' ? 'outline' : 'subtle'
    }, r.plan)
  }, {
    key: 'seats',
    label: 'seats',
    align: 'right',
    mono: true,
    type: 'numeric'
  }, {
    key: 'mrr',
    label: 'mrr',
    align: 'right',
    mono: true,
    type: 'numeric'
  }, {
    key: 'updated',
    label: 'updated_at',
    muted: true,
    align: 'right',
    type: 'timestamp'
  }];
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      minHeight: 0
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      padding: '20px 20px 0'
    }
  }, /*#__PURE__*/React.createElement(Tabs, {
    value: view,
    onChange: setView,
    items: [{
      value: 'rows',
      label: 'Rows',
      count: rows.length
    }, {
      value: 'schema',
      label: 'Schema'
    }, {
      value: 'history',
      label: 'History'
    }]
  })), view === 'rows' && /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 10,
      padding: '14px 20px'
    }
  }, /*#__PURE__*/React.createElement(Input, {
    placeholder: 'Search ' + table,
    value: q,
    onChange: e => setQ(e.target.value),
    prefix: /*#__PURE__*/React.createElement("i", {
      "data-lucide": "search",
      style: {
        width: 14,
        height: 14
      }
    }),
    style: {
      width: 240
    }
  }), /*#__PURE__*/React.createElement(Button, {
    variant: "ghost",
    size: "sm",
    iconLeft: /*#__PURE__*/React.createElement("i", {
      "data-lucide": "filter",
      style: {
        width: 14,
        height: 14
      }
    })
  }, "Filter"), /*#__PURE__*/React.createElement(Button, {
    variant: "ghost",
    size: "sm",
    iconLeft: /*#__PURE__*/React.createElement("i", {
      "data-lucide": "arrow-up-down",
      style: {
        width: 14,
        height: 14
      }
    })
  }, "Sort"), /*#__PURE__*/React.createElement(Button, {
    variant: "ghost",
    size: "sm",
    iconLeft: /*#__PURE__*/React.createElement("i", {
      "data-lucide": "columns-3",
      style: {
        width: 14,
        height: 14
      }
    })
  }, "Columns"), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1
    }
  }), /*#__PURE__*/React.createElement(Select, {
    options: ['25 rows', '50 rows', '100 rows'],
    defaultValue: "50 rows"
  }), /*#__PURE__*/React.createElement(Tooltip, {
    label: "Export CSV",
    placement: "left"
  }, /*#__PURE__*/React.createElement(IconButton, {
    label: "Export",
    variant: "outline"
  }, /*#__PURE__*/React.createElement("i", {
    "data-lucide": "download",
    style: {
      width: 15,
      height: 15
    }
  })))), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      minHeight: 0,
      overflow: 'auto',
      padding: view === 'rows' ? '0 20px 20px' : '16px 20px 20px'
    }
  }, view === 'rows' && (rows.length ? /*#__PURE__*/React.createElement(Table, {
    selectable: true,
    rows: rows,
    columns: columns
  }) : /*#__PURE__*/React.createElement(EmptyState, {
    title: "No rows match",
    description: 'Nothing in ' + table + ' contains “' + q + '”.',
    action: /*#__PURE__*/React.createElement(Button, {
      size: "sm",
      onClick: () => setQ('')
    }, "Clear search")
  })), view === 'schema' && /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 0
    }
  }, columns.map((c, i) => /*#__PURE__*/React.createElement("div", {
    key: c.key,
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 12,
      height: 44,
      borderBottom: '1px solid var(--border-hairline)'
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: 'var(--font-mono)',
      color: 'var(--text-primary)',
      width: 160
    }
  }, c.label), /*#__PURE__*/React.createElement(Badge, {
    size: "sm",
    variant: "outline"
  }, c.type), i === 0 && /*#__PURE__*/React.createElement(Badge, {
    size: "sm"
  }, "primary key"), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1
    }
  }), /*#__PURE__*/React.createElement(Checkbox, {
    label: "nullable",
    defaultChecked: i > 2
  })))), view === 'history' && /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column'
    }
  }, ['schema changed — seats added', 'sync completed — 12,480 rows', 'connection created'].map((h, i) => /*#__PURE__*/React.createElement(React.Fragment, {
    key: h
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      justifyContent: 'space-between',
      padding: '14px 0',
      color: 'var(--text-secondary)'
    }
  }, /*#__PURE__*/React.createElement("span", null, h), /*#__PURE__*/React.createElement("span", {
    style: {
      color: 'var(--text-muted)',
      fontSize: 12
    }
  }, ['2m ago', '4h ago', 'Mar 14'][i])), /*#__PURE__*/React.createElement(Divider, null))))));
}
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/console/TableScreen.jsx", error: String((e && e.message) || e) }); }

// ui_kits/console/data.js
try { (() => {
window.KIT_DATA = {
  tables: [{
    name: 'users',
    rows: '12,480'
  }, {
    name: 'orders',
    rows: '84,201'
  }, {
    name: 'invoices',
    rows: '9,338'
  }, {
    name: 'events',
    rows: '1.2M'
  }, {
    name: 'workspaces',
    rows: '412'
  }],
  users: [{
    id: 'usr_8fa21',
    email: 'dana@northlake.io',
    plan: 'Pro',
    seats: 12,
    mrr: '$348',
    updated: '2m ago'
  }, {
    id: 'usr_3c910',
    email: 'ravi@meterhouse.com',
    plan: 'Team',
    seats: 4,
    mrr: '$96',
    updated: '18m ago'
  }, {
    id: 'usr_bb47d',
    email: 'lin@ferrousworks.dev',
    plan: 'Free',
    seats: 1,
    mrr: '$0',
    updated: '1h ago'
  }, {
    id: 'usr_20e6c',
    email: 'omar@quietstack.co',
    plan: 'Pro',
    seats: 9,
    mrr: '$261',
    updated: '3h ago'
  }, {
    id: 'usr_71b3f',
    email: 'yuki@paperlane.jp',
    plan: 'Team',
    seats: 6,
    mrr: '$144',
    updated: '5h ago'
  }, {
    id: 'usr_ff042',
    email: 'noor@stonefield.ae',
    plan: 'Pro',
    seats: 21,
    mrr: '$609',
    updated: '8h ago'
  }, {
    id: 'usr_5d8a0',
    email: 'ellis@thirdrail.co.uk',
    plan: 'Free',
    seats: 2,
    mrr: '$0',
    updated: '1d ago'
  }, {
    id: 'usr_c1e77',
    email: 'marta@vallecorp.es',
    plan: 'Team',
    seats: 5,
    mrr: '$120',
    updated: '1d ago'
  }],
  queries: [{
    name: 'Weekly signups',
    owner: 'dana',
    run: '4m ago'
  }, {
    name: 'Churn by plan',
    owner: 'ravi',
    run: '2h ago'
  }, {
    name: 'Seat expansion',
    owner: 'lin',
    run: 'yesterday'
  }]
};
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/console/data.js", error: String((e && e.message) || e) }); }

// ui_kits/foreman/ActivityFeed.jsx
try { (() => {
function ActivityFeed() {
  const {
    EventRow,
    Select,
    Button,
    Card
  } = window.DSNS;
  const F = window.FOREMAN;
  const [kind, setKind] = React.useState('all events');
  const kinds = ['all events', 'ticket_claimed', 'result_recorded', 'phase_advanced', 'host_down', 'lease_acquired'];
  const rows = F.events.filter(e => kind === 'all events' || e.kind === kind);
  return /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      overflow: 'auto',
      padding: 20,
      display: 'flex',
      flexDirection: 'column',
      gap: 16
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 12
    }
  }, /*#__PURE__*/React.createElement(SectionHead, {
    title: "Activity"
  }), /*#__PURE__*/React.createElement(LiveDot, {
    label: "streaming"
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1
    }
  }), /*#__PURE__*/React.createElement(Select, {
    options: kinds,
    value: kind,
    onChange: e => setKind(e.target.value)
  }), /*#__PURE__*/React.createElement(Button, {
    variant: "ghost",
    size: "sm"
  }, "Pause")), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'grid',
      gridTemplateColumns: 'minmax(0, 2fr) minmax(0, 1fr)',
      gap: 16,
      alignItems: 'start'
    }
  }, /*#__PURE__*/React.createElement("div", null, rows.map(e => /*#__PURE__*/React.createElement(EventRow, {
    key: e.ts,
    event: e
  }))), /*#__PURE__*/React.createElement(Card, {
    title: "Leases",
    subtitle: "Scarce-resource claims",
    padding: "md"
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 10
    }
  }, F.leases.map(l => /*#__PURE__*/React.createElement("div", {
    key: l.id,
    style: {
      display: 'flex',
      justifyContent: 'space-between',
      gap: 10,
      fontFamily: 'var(--font-mono)',
      fontSize: 12
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      color: 'var(--text-secondary)'
    }
  }, l.resource_class, " \xB7 ", l.host), /*#__PURE__*/React.createElement("span", {
    style: {
      color: 'var(--text-muted)'
    }
  }, l.holder_ticket, " \xB7 ", Math.round(l.ttl_s / 60), "m ttl")))))));
}
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/foreman/ActivityFeed.jsx", error: String((e && e.message) || e) }); }

// ui_kits/foreman/CrewPanel.jsx
try { (() => {
function AddHostModal({
  open,
  onClose
}) {
  const {
    Dialog,
    Input,
    Button,
    HealthBadge
  } = window.DSNS;
  const [step, setStep] = React.useState(0);
  const probes = ['reachable', 'agent_ok', 'auth_ok', 'workspace_ready', 'guard_installed'];
  React.useEffect(() => {
    if (!open) {
      setStep(0);
      return;
    }
    const id = setInterval(() => setStep(s => s >= probes.length ? s : s + 1), 700);
    return () => clearInterval(id);
  }, [open]);
  const health = {};
  probes.forEach((p, i) => {
    health[p] = i < step ? true : null;
  });
  return /*#__PURE__*/React.createElement(Dialog, {
    open: open,
    title: "Add crew member",
    description: "Foreman probes the host before it joins the pool.",
    onClose: onClose,
    footer: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement(Button, {
      variant: "ghost",
      size: "sm",
      onClick: onClose
    }, "Cancel"), /*#__PURE__*/React.createElement(Button, {
      size: "sm",
      disabled: step < probes.length,
      onClick: onClose
    }, "Add host"))
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 16
    }
  }, /*#__PURE__*/React.createElement(Input, {
    label: "Hostname",
    defaultValue: "node-e02"
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 8
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      color: 'var(--text-muted)',
      fontSize: 12
    }
  }, "health check"), /*#__PURE__*/React.createElement(HealthBadge, {
    health: health,
    showLatency: false,
    style: {
      gap: 12
    }
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      color: 'var(--text-muted)',
      fontSize: 12,
      fontFamily: 'var(--font-mono)'
    }
  }, step < probes.length ? step + ' of ' + probes.length + ' probes complete' : 'all probes passed'))));
}
function CrewPanel({
  onOpenHost
}) {
  const {
    CrewRow,
    CREW_GRID,
    Button,
    IconButton,
    Tooltip,
    StatTile
  } = window.DSNS;
  const F = window.FOREMAN;
  const [adding, setAdding] = React.useState(false);
  const online = F.crew.filter(m => m.state !== 'down').length;
  return /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      minHeight: 0,
      display: 'flex',
      flexDirection: 'column',
      overflow: 'auto'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'grid',
      gridTemplateColumns: 'repeat(4, minmax(0, 1fr))',
      gap: 12,
      padding: 20
    }
  }, /*#__PURE__*/React.createElement(StatTile, {
    label: "crew online",
    value: online + ' / ' + F.crew.length,
    delta: "1 draining, 1 down",
    tone: "attention"
  }), /*#__PURE__*/React.createElement(StatTile, {
    label: "gpu leases",
    value: F.leases.length + ' / 2',
    delta: "both held over 40m"
  }), /*#__PURE__*/React.createElement(StatTile, {
    label: "cpu capacity",
    value: "304",
    delta: "cores across 6 hosts"
  }), /*#__PURE__*/React.createElement(StatTile, {
    label: "mean latency",
    value: "35ms",
    tone: "live",
    live: true
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 12,
      padding: '0 20px 12px'
    }
  }, /*#__PURE__*/React.createElement(SectionHead, {
    title: "Crew",
    meta: F.crew.length + ' hosts'
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1
    }
  }), /*#__PURE__*/React.createElement(Tooltip, {
    label: "Re-probe all",
    placement: "left"
  }, /*#__PURE__*/React.createElement(IconButton, {
    label: "Re-probe all"
  }, /*#__PURE__*/React.createElement("i", {
    "data-lucide": "refresh-cw",
    style: {
      width: 15,
      height: 15
    }
  }))), /*#__PURE__*/React.createElement(Button, {
    size: "sm",
    iconLeft: /*#__PURE__*/React.createElement("i", {
      "data-lucide": "plus",
      style: {
        width: 14,
        height: 14
      }
    }),
    onClick: () => setAdding(true)
  }, "Add host")), /*#__PURE__*/React.createElement("div", {
    style: {
      borderTop: '1px solid var(--border-hairline)'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'grid',
      gridTemplateColumns: CREW_GRID,
      gap: 'var(--space-4)',
      padding: '10px var(--space-4)',
      borderBottom: '1px solid var(--border-hairline)',
      color: 'var(--text-muted)',
      fontSize: 12
    }
  }, /*#__PURE__*/React.createElement("span", null, "host"), /*#__PURE__*/React.createElement("span", null, "state"), /*#__PURE__*/React.createElement("span", null, "health"), /*#__PURE__*/React.createElement("span", null, "resources"), /*#__PURE__*/React.createElement("span", null, "current ticket"), /*#__PURE__*/React.createElement("span", null, "throughput"), /*#__PURE__*/React.createElement("span", {
    style: {
      textAlign: 'right'
    }
  }, "heartbeat")), F.crew.map(m => /*#__PURE__*/React.createElement(CrewRow, {
    key: m.id,
    member: m,
    onClick: () => onOpenHost(m),
    actions: /*#__PURE__*/React.createElement("div", {
      style: {
        display: 'flex',
        gap: 4
      }
    }, /*#__PURE__*/React.createElement(Tooltip, {
      label: "Drain",
      placement: "left"
    }, /*#__PURE__*/React.createElement(IconButton, {
      label: "Drain"
    }, /*#__PURE__*/React.createElement("i", {
      "data-lucide": "arrow-down-to-line",
      style: {
        width: 14,
        height: 14
      }
    }))), /*#__PURE__*/React.createElement(Tooltip, {
      label: "Remove",
      placement: "left"
    }, /*#__PURE__*/React.createElement(IconButton, {
      label: "Remove"
    }, /*#__PURE__*/React.createElement("i", {
      "data-lucide": "minus",
      style: {
        width: 14,
        height: 14
      }
    }))))
  }))), /*#__PURE__*/React.createElement(AddHostModal, {
    open: adding,
    onClose: () => setAdding(false)
  }));
}
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/foreman/CrewPanel.jsx", error: String((e && e.message) || e) }); }

// ui_kits/foreman/Findings.jsx
try { (() => {
function Findings() {
  const {
    Card,
    Badge,
    Button,
    Divider,
    StatusPill
  } = window.DSNS;
  const F = window.FOREMAN;
  const FIX_LABEL = {
    diff_published: 'diff published',
    proposed: 'change proposed',
    needs_human: 'needs human'
  };
  return /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      overflow: 'auto',
      padding: 20,
      display: 'flex',
      flexDirection: 'column',
      gap: 16
    }
  }, /*#__PURE__*/React.createElement(SectionHead, {
    title: "Findings",
    meta: F.findings.length + ' unique root causes from 96 results'
  }), F.findings.map(fd => /*#__PURE__*/React.createElement(Card, {
    key: fd.id,
    padding: "md"
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'flex-start',
      gap: 12
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      minWidth: 0,
      display: 'flex',
      flexDirection: 'column',
      gap: 6
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 8
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: 12,
      color: 'var(--text-muted)'
    }
  }, fd.id), /*#__PURE__*/React.createElement(Badge, {
    size: "sm",
    variant: "outline"
  }, fd.category), fd.fix_state === 'needs_human' ? /*#__PURE__*/React.createElement(StatusPill, {
    state: "needs-human",
    size: "sm",
    label: FIX_LABEL[fd.fix_state]
  }) : /*#__PURE__*/React.createElement(Badge, {
    size: "sm",
    tone: fd.fix_state === 'diff_published' ? 'ok' : 'attention',
    variant: fd.fix_state === 'diff_published' ? 'solid' : 'subtle'
  }, FIX_LABEL[fd.fix_state])), /*#__PURE__*/React.createElement("span", {
    style: {
      color: 'var(--text-primary)',
      fontSize: 20,
      lineHeight: '26px'
    }
  }, fd.title)), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      gap: 8,
      flex: 'none'
    }
  }, /*#__PURE__*/React.createElement(Button, {
    variant: "ghost",
    size: "sm"
  }, "Open diff"), /*#__PURE__*/React.createElement(Button, {
    size: "sm"
  }, "Review"))), /*#__PURE__*/React.createElement(Divider, {
    style: {
      margin: '16px 0 12px'
    }
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 8,
      flexWrap: 'wrap'
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      color: 'var(--text-muted)',
      fontSize: 12
    }
  }, fd.member_ticket_ids.length, " member tickets"), fd.member_ticket_ids.map(id => /*#__PURE__*/React.createElement("span", {
    key: id,
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: 12,
      color: 'var(--text-secondary)',
      padding: '2px 6px',
      border: '1px solid var(--border-hairline)',
      borderRadius: 'var(--radius-lg)'
    }
  }, id))))));
}
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/foreman/Findings.jsx", error: String((e && e.message) || e) }); }

// ui_kits/foreman/ForemanApp.jsx
try { (() => {
function ForemanApp() {
  const F = window.FOREMAN;
  const [view, setView] = React.useState('overview');
  const [ticket, setTicket] = React.useState(null);
  const [host, setHost] = React.useState(null);
  const [stopping, setStopping] = React.useState(false);
  const {
    Dialog,
    Button,
    CrewBackdrop
  } = window.DSNS;
  const [theme, setTheme] = React.useState('construction');
  React.useEffect(() => {
    if (window.lucide) lucide.createIcons();
  });
  return /*#__PURE__*/React.createElement("div", {
    style: {
      position: 'relative',
      display: 'flex',
      flexDirection: 'column',
      height: '100vh',
      overflow: 'hidden'
    }
  }, /*#__PURE__*/React.createElement(CrewBackdrop, {
    theme: theme,
    fixed: false,
    basePath: "../../assets/backdrops/"
  }), /*#__PURE__*/React.createElement(TopBar, {
    run: F.run,
    view: view,
    onView: setView,
    onStop: () => setStopping(true),
    theme: theme,
    onTheme: setTheme
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      position: 'relative',
      zIndex: 1,
      flex: 1,
      minHeight: 0,
      display: 'flex',
      flexDirection: 'column'
    }
  }, view === 'overview' && /*#__PURE__*/React.createElement(RunOverview, {
    onView: setView
  }), view === 'board' && /*#__PURE__*/React.createElement(TicketBoard, {
    onOpen: setTicket
  }), view === 'crew' && /*#__PURE__*/React.createElement(CrewPanel, {
    onOpenHost: setHost
  }), view === 'findings' && /*#__PURE__*/React.createElement(Findings, null), view === 'activity' && /*#__PURE__*/React.createElement(ActivityFeed, null)), /*#__PURE__*/React.createElement(TicketDrawer, {
    ticket: ticket,
    onClose: () => setTicket(null)
  }), /*#__PURE__*/React.createElement(HostDrawer, {
    member: host,
    onClose: () => setHost(null)
  }), /*#__PURE__*/React.createElement(Dialog, {
    open: stopping,
    title: "Stop this run?",
    description: "In-flight tickets finish; nothing new is dispatched.",
    onClose: () => setStopping(false),
    footer: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement(Button, {
      variant: "ghost",
      size: "sm",
      onClick: () => setStopping(false)
    }, "Keep running"), /*#__PURE__*/React.createElement(Button, {
      size: "sm",
      onClick: () => setStopping(false)
    }, "Stop run"))
  }));
}
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/foreman/ForemanApp.jsx", error: String((e && e.message) || e) }); }

// ui_kits/foreman/RunOverview.jsx
try { (() => {
function ProgressBar({
  done,
  total
}) {
  const pct = Math.round(done / total * 100);
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 8
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      justifyContent: 'space-between',
      color: 'var(--text-muted)',
      fontSize: 12,
      fontFamily: 'var(--font-mono)'
    }
  }, /*#__PURE__*/React.createElement("span", null, done, " / ", total, " tickets"), /*#__PURE__*/React.createElement("span", null, pct, "%")), /*#__PURE__*/React.createElement("div", {
    style: {
      height: 6,
      borderRadius: 'var(--radius-full)',
      background: 'var(--wash-active)',
      overflow: 'hidden'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      width: pct + '%',
      height: '100%',
      background: 'var(--status-ok)',
      transition: 'width 160ms ease-out'
    }
  })));
}
function PhaseTimeline({
  phases
}) {
  const {
    StatusPill
  } = window.DSNS;
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 10
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      gap: 4
    }
  }, phases.map(p => /*#__PURE__*/React.createElement("div", {
    key: p.name,
    style: {
      flex: p.share,
      display: 'flex',
      flexDirection: 'column',
      gap: 6
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      height: 6,
      borderRadius: 'var(--radius-full)',
      background: p.state === 'running' ? 'var(--status-live)' : 'var(--wash-active)',
      animation: p.state === 'running' ? 'fm-pulse 1.6s ease-out infinite' : 'none'
    }
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 6
    }
  }, /*#__PURE__*/React.createElement(StatusPill, {
    state: p.state,
    label: p.name,
    size: "sm"
  }))))));
}
function Sparkline({
  points
}) {
  const max = Math.max.apply(null, points);
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'flex-end',
      gap: 2,
      height: 24,
      marginTop: 4
    }
  }, points.map((p, i) => /*#__PURE__*/React.createElement("span", {
    key: i,
    style: {
      flex: 1,
      height: Math.max(2, p / max * 24),
      background: i === points.length - 1 ? 'var(--status-live)' : 'var(--wash-active)',
      borderRadius: 1
    }
  })));
}
function RunOverview({
  onView
}) {
  const {
    StatTile,
    AttentionBanner,
    Card,
    Button,
    Divider,
    EventRow,
    StatusPill
  } = window.DSNS;
  const F = window.FOREMAN;
  const run = F.run;
  const [acked, setAcked] = React.useState(false);
  return /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      overflow: 'auto',
      padding: 20,
      display: 'flex',
      flexDirection: 'column',
      gap: 16
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 8
    }
  }, /*#__PURE__*/React.createElement(AttentionBanner, {
    severity: "critical",
    title: "Crew member node-b04 is down",
    detail: "No heartbeat in 4m 12s. 2 tickets were requeued.",
    actionLabel: "Open crew",
    onAction: () => onView('crew')
  }), !acked && /*#__PURE__*/React.createElement(AttentionBanner, {
    title: "No progress in 31m on 4 parked tickets",
    detail: "All four are waiting on a gpu lease.",
    onAcknowledge: () => setAcked(true)
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'grid',
      gridTemplateColumns: 'repeat(6, minmax(0, 1fr))',
      gap: 12
    }
  }, /*#__PURE__*/React.createElement(StatTile, {
    label: "tickets",
    value: run.tickets.total,
    delta: "214 in batch"
  }), /*#__PURE__*/React.createElement(StatTile, {
    label: "done",
    value: run.tickets.done,
    delta: "+12 in last 5m",
    tone: "ok"
  }), /*#__PURE__*/React.createElement(StatTile, {
    label: "in flight",
    value: run.tickets.running,
    tone: "live",
    live: true,
    emphasis: true
  }), /*#__PURE__*/React.createElement(StatTile, {
    label: "parked",
    value: run.tickets.parked,
    delta: "4 on gpu lease",
    tone: "attention"
  }), /*#__PURE__*/React.createElement(StatTile, {
    label: "failed",
    value: run.tickets.failed,
    delta: "2 need a human",
    tone: "danger"
  }), /*#__PURE__*/React.createElement(StatTile, {
    label: "throughput",
    value: "4.2",
    delta: "tickets / min",
    sparkline: /*#__PURE__*/React.createElement(Sparkline, {
      points: [2, 3, 3, 5, 4, 6, 4, 5, 7, 6]
    })
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'grid',
      gridTemplateColumns: 'minmax(0, 1.5fr) minmax(0, 1fr)',
      gap: 16,
      alignItems: 'start'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 16
    }
  }, /*#__PURE__*/React.createElement(Card, {
    padding: "md",
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 18
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 10
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      color: 'var(--text-primary)',
      fontSize: 20,
      lineHeight: '26px'
    }
  }, run.playbook, " run"), /*#__PURE__*/React.createElement(StatusPill, {
    state: run.state
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1
    }
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      color: 'var(--text-muted)',
      fontSize: 12,
      fontFamily: 'var(--font-mono)'
    }
  }, "started ", run.started_at, " \xB7 ", run.eta)), /*#__PURE__*/React.createElement(ProgressBar, {
    done: run.tickets.done,
    total: run.tickets.total
  }), /*#__PURE__*/React.createElement(Divider, null), /*#__PURE__*/React.createElement(PhaseTimeline, {
    phases: F.phases
  })), /*#__PURE__*/React.createElement(Card, {
    title: "Crew",
    subtitle: "4 of 6 online, 1 draining, 1 down",
    action: /*#__PURE__*/React.createElement(Button, {
      size: "sm",
      onClick: () => onView('crew')
    }, "Open crew"),
    padding: "md"
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexWrap: 'wrap',
      gap: 8
    }
  }, F.crew.map(m => /*#__PURE__*/React.createElement("div", {
    key: m.id,
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 8,
      padding: '6px 10px',
      border: '1px solid var(--border-hairline)',
      borderRadius: 'var(--radius-lg)'
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: 12,
      color: 'var(--text-secondary)'
    }
  }, m.id), /*#__PURE__*/React.createElement(StatusPill, {
    state: m.state,
    size: "sm"
  })))))), /*#__PURE__*/React.createElement(Card, {
    title: "Live activity",
    action: /*#__PURE__*/React.createElement(Button, {
      size: "sm",
      onClick: () => onView('activity')
    }, "All events"),
    padding: "md"
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column'
    }
  }, F.events.slice(0, 6).map(e => /*#__PURE__*/React.createElement("div", {
    key: e.ts,
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 2,
      padding: '9px 0',
      borderBottom: '1px solid var(--border-hairline)'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      gap: 8,
      alignItems: 'baseline'
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: 12,
      color: 'var(--text-muted)'
    }
  }, e.ts), /*#__PURE__*/React.createElement("span", {
    style: {
      color: e.severity === 'critical' ? 'var(--status-danger)' : 'var(--text-secondary)',
      fontSize: 13
    }
  }, e.message)), (e.host || e.ticket_id) && /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: 12,
      color: 'var(--text-muted)'
    }
  }, [e.host, e.ticket_id].filter(Boolean).join(' \u00b7 '))))))));
}
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/foreman/RunOverview.jsx", error: String((e && e.message) || e) }); }

// ui_kits/foreman/Shell.jsx
try { (() => {
function LiveDot({
  label
}) {
  return /*#__PURE__*/React.createElement("span", {
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      gap: 6,
      color: 'var(--text-muted)',
      fontSize: 12
    }
  }, /*#__PURE__*/React.createElement("span", {
    "aria-hidden": "true",
    style: {
      width: 6,
      height: 6,
      borderRadius: 'var(--radius-full)',
      background: 'var(--status-live)',
      animation: 'fm-pulse 1.6s ease-out infinite'
    }
  }), label || 'live');
}
function BackdropPicker({
  theme,
  onTheme
}) {
  const {
    BACKDROP_THEMES,
    Tooltip
  } = window.DSNS;
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 2,
      padding: 2,
      border: '1px solid var(--border-hairline)',
      borderRadius: 'var(--radius-lg)'
    }
  }, BACKDROP_THEMES.map(t => /*#__PURE__*/React.createElement(Tooltip, {
    key: t.value,
    label: t.hint,
    placement: "bottom"
  }, /*#__PURE__*/React.createElement("button", {
    onClick: () => onTheme(t.value),
    style: {
      height: 22,
      padding: '0 8px',
      background: theme === t.value ? 'var(--wash-selected)' : 'transparent',
      border: 'none',
      borderRadius: 'var(--radius-lg)',
      color: theme === t.value ? 'var(--text-primary)' : 'var(--text-muted)',
      font: '400 11px var(--font-mono)',
      cursor: 'pointer'
    }
  }, t.label))));
}
function TopBar({
  run,
  view,
  onView,
  onStop,
  theme,
  onTheme
}) {
  const {
    Button,
    IconButton,
    Tooltip
  } = window.DSNS;
  const views = [{
    id: 'overview',
    label: 'Run'
  }, {
    id: 'board',
    label: 'Tickets'
  }, {
    id: 'crew',
    label: 'Crew'
  }, {
    id: 'findings',
    label: 'Findings'
  }, {
    id: 'activity',
    label: 'Activity'
  }];
  return /*#__PURE__*/React.createElement("header", {
    style: {
      position: 'sticky',
      top: 0,
      zIndex: 40,
      flex: 'none',
      height: 56,
      display: 'flex',
      alignItems: 'center',
      gap: 24,
      padding: '0 20px',
      background: 'oklab(0 0 0 / 0.85)',
      backdropFilter: 'blur(12px)',
      borderBottom: '1px solid var(--border-hairline)'
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      color: 'var(--text-primary)'
    }
  }, "Foreman"), /*#__PURE__*/React.createElement("nav", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 4
    }
  }, views.map(v => /*#__PURE__*/React.createElement("button", {
    key: v.id,
    onClick: () => onView(v.id),
    style: {
      height: 30,
      padding: '0 10px',
      background: view === v.id ? 'var(--wash-selected)' : 'transparent',
      border: '1px solid transparent',
      borderRadius: 'var(--radius-lg)',
      color: view === v.id ? 'var(--text-primary)' : 'var(--text-secondary)',
      font: '400 14px var(--font-sans)',
      cursor: 'pointer'
    }
  }, v.label))), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1
    }
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      color: 'var(--text-muted)',
      fontSize: 12,
      fontFamily: 'var(--font-mono)'
    }
  }, run.playbook, " \xB7 ", run.site, " \xB7 ", run.base_ref), /*#__PURE__*/React.createElement(BackdropPicker, {
    theme: theme,
    onTheme: onTheme
  }), /*#__PURE__*/React.createElement(LiveDot, null), /*#__PURE__*/React.createElement(Tooltip, {
    label: "Re-probe crew",
    placement: "bottom"
  }, /*#__PURE__*/React.createElement(IconButton, {
    label: "Re-probe crew"
  }, /*#__PURE__*/React.createElement("i", {
    "data-lucide": "activity",
    style: {
      width: 15,
      height: 15
    }
  }))), /*#__PURE__*/React.createElement(Button, {
    size: "sm",
    onClick: onStop
  }, "Stop run"));
}
function SectionHead({
  title,
  meta,
  actions
}) {
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'flex-end',
      gap: 12,
      paddingBottom: 4
    }
  }, /*#__PURE__*/React.createElement("h3", {
    style: {
      color: 'var(--text-primary)',
      fontSize: 20,
      lineHeight: '26px',
      fontWeight: 400
    }
  }, title), meta && /*#__PURE__*/React.createElement("span", {
    style: {
      color: 'var(--text-muted)',
      fontSize: 12,
      fontFamily: 'var(--font-mono)'
    }
  }, meta), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1
    }
  }), actions);
}
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/foreman/Shell.jsx", error: String((e && e.message) || e) }); }

// ui_kits/foreman/TicketBoard.jsx
try { (() => {
function TicketBoard({
  onOpen
}) {
  const {
    KanbanColumn,
    TicketCard,
    Input,
    Select,
    Button,
    IconButton,
    Tooltip
  } = window.DSNS;
  const F = window.FOREMAN;
  const [q, setQ] = React.useState('');
  const [phase, setPhase] = React.useState('all phases');
  const [resource, setResource] = React.useState('all resources');
  const match = t => (!q || (t.subject + ' ' + t.id + ' ' + (t.host || '')).toLowerCase().includes(q.toLowerCase())) && (phase === 'all phases' || t.phase === phase) && (resource === 'all resources' || t.resource_req === resource);
  const visible = F.tickets.filter(match);
  return /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      minHeight: 0,
      display: 'flex',
      flexDirection: 'column'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 10,
      padding: '16px 20px',
      borderBottom: '1px solid var(--border-hairline)'
    }
  }, /*#__PURE__*/React.createElement(Input, {
    placeholder: "Search tickets, hosts",
    value: q,
    onChange: e => setQ(e.target.value),
    prefix: /*#__PURE__*/React.createElement("i", {
      "data-lucide": "search",
      style: {
        width: 14,
        height: 14
      }
    }),
    style: {
      width: 260
    }
  }), /*#__PURE__*/React.createElement(Select, {
    options: ['all phases', 'diagnose', 'reduce', 'fix'],
    value: phase,
    onChange: e => setPhase(e.target.value)
  }), /*#__PURE__*/React.createElement(Select, {
    options: ['all resources', 'cpu', 'gpu'],
    value: resource,
    onChange: e => setResource(e.target.value)
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      color: 'var(--text-muted)',
      fontSize: 12,
      fontFamily: 'var(--font-mono)'
    }
  }, visible.length, " of ", F.tickets.length, " shown"), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1
    }
  }), /*#__PURE__*/React.createElement(Tooltip, {
    label: "Column layout",
    placement: "left"
  }, /*#__PURE__*/React.createElement(IconButton, {
    label: "Column layout"
  }, /*#__PURE__*/React.createElement("i", {
    "data-lucide": "columns-3",
    style: {
      width: 15,
      height: 15
    }
  }))), /*#__PURE__*/React.createElement(Button, {
    variant: "ghost",
    size: "sm",
    onClick: () => {
      setQ('');
      setPhase('all phases');
      setResource('all resources');
    }
  }, "Clear")), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      minHeight: 0,
      overflowX: 'auto',
      overflowY: 'hidden',
      padding: '16px 20px 0'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      gap: 16,
      height: '100%',
      alignItems: 'stretch'
    }
  }, F.states.map(st => {
    const rows = visible.filter(t => t.state === st);
    return /*#__PURE__*/React.createElement(KanbanColumn, {
      key: st,
      state: st,
      title: st,
      count: rows.length,
      empty: q || phase !== 'all phases' || resource !== 'all resources' ? 'Nothing matches here' : 'No tickets'
    }, rows.map(t => /*#__PURE__*/React.createElement(TicketCard, {
      key: t.id,
      ticket: t,
      onClick: () => onOpen(t)
    })));
  }))));
}
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/foreman/TicketBoard.jsx", error: String((e && e.message) || e) }); }

// ui_kits/foreman/TicketDrawer.jsx
try { (() => {
function TicketDrawer({
  ticket,
  onClose
}) {
  const {
    Drawer,
    Button,
    Tabs,
    StatusPill,
    Badge,
    Divider
  } = window.DSNS;
  const F = window.FOREMAN;
  const [tab, setTab] = React.useState('payload');
  const t = ticket || {};
  const mono = {
    fontFamily: 'var(--font-mono)',
    fontSize: 12,
    lineHeight: '18px'
  };
  return /*#__PURE__*/React.createElement(Drawer, {
    open: !!ticket,
    title: t.id,
    subtitle: t.host ? t.host + ' \u00b7 ' + t.phase : t.phase,
    onClose: onClose,
    tabs: /*#__PURE__*/React.createElement(Tabs, {
      value: tab,
      onChange: setTab,
      items: [{
        value: 'payload',
        label: 'Payload'
      }, {
        value: 'result',
        label: 'Result'
      }, {
        value: 'history',
        label: 'History'
      }, {
        value: 'log',
        label: 'Log'
      }]
    }),
    footer: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement(Button, {
      variant: "ghost",
      size: "sm",
      onClick: onClose
    }, "Park"), /*#__PURE__*/React.createElement(Button, {
      variant: "ghost",
      size: "sm"
    }, "Reprioritize"), /*#__PURE__*/React.createElement(Button, {
      size: "sm"
    }, "Requeue"))
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 8,
      flexWrap: 'wrap'
    }
  }, /*#__PURE__*/React.createElement(StatusPill, {
    state: t.state
  }), /*#__PURE__*/React.createElement(Badge, {
    size: "sm",
    variant: "outline"
  }, t.resource_req), /*#__PURE__*/React.createElement("span", {
    style: {
      ...mono,
      color: 'var(--text-muted)'
    }
  }, "try ", t.attempts, " \xB7 ", t.elapsed_s, "s \xB7 p", t.priority)), /*#__PURE__*/React.createElement("span", {
    style: {
      color: 'var(--text-primary)',
      fontSize: 13,
      lineHeight: '18px',
      wordBreak: 'break-word'
    }
  }, t.subject), /*#__PURE__*/React.createElement(Divider, null), tab === 'payload' && /*#__PURE__*/React.createElement("pre", {
    style: {
      ...mono,
      margin: 0,
      color: 'var(--text-secondary)',
      whiteSpace: 'pre-wrap'
    }
  }, JSON.stringify({
    ticket_id: t.id,
    run_id: t.run_id,
    playbook: 'mechanic',
    phase: t.phase,
    target: t.subject,
    resource_req: t.resource_req,
    budget_s: 900,
    base_ref: 'a1b2c3d'
  }, null, 2)), tab === 'result' && /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 12
    }
  }, /*#__PURE__*/React.createElement("pre", {
    style: {
      ...mono,
      margin: 0,
      color: 'var(--text-secondary)',
      whiteSpace: 'pre-wrap'
    }
  }, JSON.stringify({
    verdict: 'reproduced',
    confidence: 0.82,
    finding_id: 'f-31',
    category: 'test isolation'
  }, null, 2)), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      gap: 8
    }
  }, /*#__PURE__*/React.createElement(Button, {
    variant: "ghost",
    size: "sm"
  }, "Open evidence"), /*#__PURE__*/React.createElement(Button, {
    variant: "ghost",
    size: "sm"
  }, "Open finding f-31"))), tab === 'history' && /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column'
    }
  }, [['attempt 1', 'timed out after 900s on node-a11'], ['attempt 2', 'reproduced on gpu-c07'], ['reduction', 'merged into finding f-31']].map((h, i) => /*#__PURE__*/React.createElement("div", {
    key: h[0],
    style: {
      display: 'flex',
      gap: 12,
      padding: '10px 0',
      borderBottom: '1px solid var(--border-hairline)'
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      ...mono,
      color: 'var(--text-muted)',
      width: 74,
      flex: 'none'
    }
  }, h[0]), /*#__PURE__*/React.createElement("span", {
    style: {
      color: 'var(--text-secondary)',
      fontSize: 13
    }
  }, h[1])))), tab === 'log' && /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 6
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 8
    }
  }, /*#__PURE__*/React.createElement(LiveDot, {
    label: "tailing"
  })), /*#__PURE__*/React.createElement("pre", {
    style: {
      ...mono,
      margin: 0,
      color: 'var(--text-secondary)',
      whiteSpace: 'pre-wrap'
    }
  }, F.logTail.join('\n'))));
}
function HostDrawer({
  member,
  onClose
}) {
  const {
    Drawer,
    Button,
    StatusPill,
    HealthBadge,
    Divider
  } = window.DSNS;
  const m = member || {};
  const res = m.resources || {};
  const mono = {
    fontFamily: 'var(--font-mono)',
    fontSize: 12,
    lineHeight: '18px'
  };
  return /*#__PURE__*/React.createElement(Drawer, {
    open: !!member,
    title: m.id,
    subtitle: m.site,
    onClose: onClose,
    footer: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement(Button, {
      variant: "ghost",
      size: "sm"
    }, "Remove"), /*#__PURE__*/React.createElement(Button, {
      variant: "ghost",
      size: "sm"
    }, "Re-probe"), /*#__PURE__*/React.createElement(Button, {
      size: "sm"
    }, "Drain"))
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 8
    }
  }, /*#__PURE__*/React.createElement(StatusPill, {
    state: m.state
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      ...mono,
      color: 'var(--text-muted)'
    }
  }, "heartbeat ", m.last_heartbeat)), /*#__PURE__*/React.createElement(HealthBadge, {
    health: m.health,
    style: {
      gap: 12
    }
  }), /*#__PURE__*/React.createElement(Divider, null), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 8,
      ...mono,
      color: 'var(--text-secondary)'
    }
  }, /*#__PURE__*/React.createElement("span", null, "resources: ", Object.keys(res).map(k => res[k] + '\u00d7 ' + k).join(' \u00b7 ') || '\u2014'), /*#__PURE__*/React.createElement("span", null, "current ticket: ", m.current_ticket || '\u2014'), /*#__PURE__*/React.createElement("span", null, "throughput: ", m.throughput_per_min, "/min")));
}
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/foreman/TicketDrawer.jsx", error: String((e && e.message) || e) }); }

// ui_kits/foreman/data.js
try { (() => {
(function () {
  var SUBJECTS = ['core//search/index:index_test - testShardRotation', 'core//net/rpc:client_test - testRetryBackoff', 'core//store/kv:compaction_test - testTombstones', 'core//auth/session:session_test - testExpiry', 'core//ml/loader:batch_test - testPrefetchStall', 'core//api/gateway:limit_test - testBurstWindow', 'core//store/wal:replay_test - testTornWrite', 'core//ml/train:sched_test - testGpuAffinity', 'core//net/dns:resolve_test - testNegativeCache', 'core//search/rank:score_test - testTieBreak'];
  var PHASES = ['diagnose', 'reduce', 'fix'];
  var HOSTS = ['node-a11', 'node-a12', 'node-b04', 'gpu-c07', 'gpu-c08', 'node-d21'];
  var STATES = ['queued', 'dispatched', 'running', 'reducing', 'done', 'parked', 'failed', 'needs-human'];
  function ticket(i, state) {
    var gpu = i % 3 === 0;
    return {
      id: 't-' + (1100 + i),
      run_id: 'r-4821',
      state: state,
      phase: PHASES[i % PHASES.length],
      subject: SUBJECTS[i % SUBJECTS.length],
      resource_req: gpu ? 'gpu' : 'cpu',
      host: state === 'queued' ? null : HOSTS[i % HOSTS.length],
      attempts: i % 3 + 1,
      elapsed_s: 18 + i * 37 % 900,
      priority: 20 + i * 13 % 78
    };
  }
  var tickets = [];
  var perState = {
    queued: 6,
    dispatched: 3,
    running: 5,
    reducing: 2,
    done: 6,
    parked: 4,
    failed: 2,
    'needs-human': 2
  };
  var n = 0;
  STATES.forEach(function (st) {
    for (var i = 0; i < perState[st]; i++) tickets.push(ticket(n++, st));
  });
  window.FOREMAN = {
    run: {
      id: 'r-4821',
      playbook: 'mechanic',
      site: 'primary',
      base_ref: 'a1b2c3d',
      state: 'running',
      phase: 'diagnose',
      started_at: '1h 42m ago',
      tickets: {
        total: 214,
        done: 96,
        running: 12,
        parked: 8,
        failed: 3,
        queued: 95
      },
      eta: '~38m remaining'
    },
    phases: [{
      name: 'diagnose',
      state: 'running',
      share: 46
    }, {
      name: 'reduce',
      state: 'queued',
      share: 34
    }, {
      name: 'fix',
      state: 'queued',
      share: 20
    }],
    tickets: tickets,
    states: STATES,
    crew: [{
      id: 'gpu-c07',
      site: 'primary',
      state: 'busy',
      resources: {
        gpu: 8,
        cpu: 96
      },
      current_ticket: 't-1207',
      throughput_per_min: 0.7,
      last_heartbeat: '3s ago',
      health: {
        reachable: true,
        agent_ok: true,
        auth_ok: true,
        workspace_ready: true,
        guard_installed: true,
        latency_ms: 41
      }
    }, {
      id: 'gpu-c08',
      site: 'primary',
      state: 'busy',
      resources: {
        gpu: 8,
        cpu: 96
      },
      current_ticket: 't-1211',
      throughput_per_min: 0.6,
      last_heartbeat: '4s ago',
      health: {
        reachable: true,
        agent_ok: true,
        auth_ok: true,
        workspace_ready: true,
        guard_installed: true,
        latency_ms: 38
      }
    }, {
      id: 'node-a11',
      site: 'primary',
      state: 'idle',
      resources: {
        cpu: 64
      },
      current_ticket: null,
      throughput_per_min: 0.0,
      last_heartbeat: '2s ago',
      health: {
        reachable: true,
        agent_ok: true,
        auth_ok: true,
        workspace_ready: true,
        guard_installed: true,
        latency_ms: 12
      }
    }, {
      id: 'node-a12',
      site: 'primary',
      state: 'draining',
      resources: {
        cpu: 64
      },
      current_ticket: 't-1188',
      throughput_per_min: 0.4,
      last_heartbeat: '5s ago',
      health: {
        reachable: true,
        agent_ok: true,
        auth_ok: true,
        workspace_ready: true,
        guard_installed: false,
        latency_ms: 19
      }
    }, {
      id: 'node-b04',
      site: 'secondary',
      state: 'down',
      resources: {
        cpu: 32
      },
      current_ticket: null,
      throughput_per_min: 0.0,
      last_heartbeat: '4m 12s ago',
      health: {
        reachable: false,
        agent_ok: false,
        auth_ok: true,
        workspace_ready: true,
        guard_installed: true,
        latency_ms: 0
      }
    }, {
      id: 'node-d21',
      site: 'secondary',
      state: 'busy',
      resources: {
        cpu: 48
      },
      current_ticket: 't-1194',
      throughput_per_min: 0.9,
      last_heartbeat: '1s ago',
      health: {
        reachable: true,
        agent_ok: true,
        auth_ok: true,
        workspace_ready: true,
        guard_installed: true,
        latency_ms: 67
      }
    }],
    findings: [{
      id: 'f-31',
      kind: 'root_cause',
      title: 'Shared fixture leaks a temp dir between shards',
      category: 'test isolation',
      member_ticket_ids: ['t-1100', 't-1104', 't-1112', 't-1119', 't-1127'],
      fix_state: 'diff_published',
      diff_url: '#'
    }, {
      id: 'f-32',
      kind: 'root_cause',
      title: 'Retry backoff races the 500ms client deadline',
      category: 'flaky timing',
      member_ticket_ids: ['t-1101', 't-1108', 't-1131'],
      fix_state: 'proposed',
      diff_url: '#'
    }, {
      id: 'f-33',
      kind: 'root_cause',
      title: 'GPU affinity pin ignored when 2 leases land on one host',
      category: 'resource',
      member_ticket_ids: ['t-1106', 't-1122'],
      fix_state: 'needs_human',
      diff_url: '#'
    }],
    events: [{
      ts: '19:44:02',
      kind: 'host_down',
      host: 'node-b04',
      message: 'No heartbeat in 4m — 2 tickets requeued',
      severity: 'critical'
    }, {
      ts: '19:43:58',
      kind: 'result_recorded',
      host: 'gpu-c07',
      ticket_id: 't-1207',
      message: 'Reduction matched finding f-31'
    }, {
      ts: '19:43:41',
      kind: 'phase_advanced',
      host: null,
      ticket_id: 't-1188',
      message: 'diagnose to reduce'
    }, {
      ts: '19:43:22',
      kind: 'lease_acquired',
      host: 'gpu-c08',
      ticket_id: 't-1211',
      message: 'gpu lease, ttl 90m'
    }, {
      ts: '19:43:04',
      kind: 'ticket_claimed',
      host: 'node-d21',
      ticket_id: 't-1194',
      message: 'Claimed at priority 74'
    }, {
      ts: '19:42:47',
      kind: 'result_recorded',
      host: 'node-a12',
      ticket_id: 't-1188',
      message: 'Strict result: reproduced in 2 of 3 attempts'
    }, {
      ts: '19:42:11',
      kind: 'ticket_claimed',
      host: 'gpu-c07',
      ticket_id: 't-1207',
      message: 'Claimed at priority 57'
    }, {
      ts: '19:41:55',
      kind: 'lease_released',
      host: 'gpu-c08',
      ticket_id: 't-1180',
      message: 'gpu lease released after 41m'
    }],
    leases: [{
      id: 'l-9',
      resource_class: 'gpu',
      holder_ticket: 't-1207',
      host: 'gpu-c07',
      ttl_s: 5400
    }, {
      id: 'l-10',
      resource_class: 'gpu',
      holder_ticket: 't-1211',
      host: 'gpu-c08',
      ttl_s: 4980
    }],
    logTail: ['[19:43:58] agent: reduced 3 candidate causes to 1', '[19:43:44] agent: reran target 3x with --stress=8', '[19:43:12] agent: parsed 1,204 lines of failure output', '[19:42:11] engine: payload delivered (2.1kb)']
  };
})();
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/foreman/data.js", error: String((e && e.message) || e) }); }

// ui_kits/marketing/Landing.jsx
try { (() => {
function Placeholder({
  label,
  height = 380
}) {
  return /*#__PURE__*/React.createElement("div", {
    style: {
      height,
      borderRadius: 'var(--radius-2xl)',
      background: 'var(--surface-card)',
      display: 'grid',
      placeItems: 'center',
      position: 'relative',
      overflow: 'hidden'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      position: 'absolute',
      inset: 0,
      opacity: 0.5,
      backgroundImage: 'repeating-linear-gradient(135deg, rgba(255,255,255,0.05) 0 1px, transparent 1px 9px)'
    }
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: 12,
      color: 'var(--text-muted)',
      position: 'relative'
    }
  }, label));
}
function Hero() {
  const {
    Button
  } = window.DSNS;
  return /*#__PURE__*/React.createElement("section", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 32,
      padding: '96px 0 48px'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 20,
      maxWidth: 720
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      color: 'var(--text-muted)',
      fontFamily: 'var(--font-mono)',
      fontSize: 12
    }
  }, "admin panels & internal tools"), /*#__PURE__*/React.createElement("h1", {
    style: {
      fontSize: 48,
      lineHeight: '48px',
      fontWeight: 400,
      color: 'var(--text-primary)',
      textWrap: 'pretty'
    }
  }, "Your database, readable by the whole team"), /*#__PURE__*/React.createElement("p", {
    style: {
      margin: 0,
      maxWidth: 560,
      color: 'var(--text-secondary)'
    }
  }, "Connect Postgres and get a fast, permissioned interface over every table \u2014 no dashboard building, no schema migrations, no seats you don\u2019t need.")), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      gap: 12,
      flexWrap: 'wrap'
    }
  }, /*#__PURE__*/React.createElement(Button, {
    size: "lg"
  }, "Start free"), /*#__PURE__*/React.createElement(Button, {
    size: "lg",
    variant: "ghost"
  }, "Book a walkthrough")), /*#__PURE__*/React.createElement(Placeholder, {
    label: "product screenshot \u2014 console, users table"
  }));
}
function Features() {
  const {
    Card
  } = window.DSNS;
  const items = [{
    t: 'Read like a spreadsheet',
    d: 'Filters, sorts, and saved views over live rows. Nobody writes SQL to answer a support ticket.'
  }, {
    t: 'Write with guardrails',
    d: 'Column-level permissions and audited edits, so the team can fix data without a migration.'
  }, {
    t: 'Queries when you need them',
    d: 'Drop into SQL, save the result as a view, and share it at the same URL.'
  }];
  return /*#__PURE__*/React.createElement("section", {
    style: {
      display: 'grid',
      gridTemplateColumns: 'repeat(3, minmax(0, 1fr))',
      gap: 16,
      padding: '48px 0'
    }
  }, items.map(i => /*#__PURE__*/React.createElement(Card, {
    key: i.t,
    padding: "lg",
    radius: "xl"
  }, /*#__PURE__*/React.createElement("h3", {
    style: {
      color: 'var(--text-primary)',
      fontSize: 20,
      lineHeight: '26px',
      fontWeight: 400
    }
  }, i.t), /*#__PURE__*/React.createElement("p", {
    style: {
      margin: '10px 0 0',
      color: 'var(--text-muted)'
    }
  }, i.d))));
}
function Pricing() {
  const {
    Button,
    Divider,
    Badge
  } = window.DSNS;
  const tiers = [{
    name: 'Free',
    price: '$0',
    line: '1 editor, 2 tables',
    cta: 'Start free'
  }, {
    name: 'Team',
    price: '$24',
    line: 'per editor / month',
    cta: 'Start free',
    tag: 'most teams'
  }, {
    name: 'Enterprise',
    price: 'Talk to us',
    line: 'SSO, audit export, on-prem',
    cta: 'Contact sales'
  }];
  return /*#__PURE__*/React.createElement("section", {
    style: {
      padding: '48px 0',
      display: 'flex',
      flexDirection: 'column',
      gap: 24
    }
  }, /*#__PURE__*/React.createElement("h2", {
    style: {
      fontSize: 30,
      lineHeight: '34px',
      fontWeight: 400,
      color: 'var(--text-primary)'
    }
  }, "Pricing"), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column'
    }
  }, tiers.map((t, i) => /*#__PURE__*/React.createElement(React.Fragment, {
    key: t.name
  }, i > 0 && /*#__PURE__*/React.createElement(Divider, null), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 20,
      padding: '22px 0',
      flexWrap: 'wrap'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 10,
      width: 200
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      color: 'var(--text-primary)'
    }
  }, t.name), t.tag && /*#__PURE__*/React.createElement(Badge, {
    size: "sm"
  }, t.tag)), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'baseline',
      gap: 8,
      flex: 1,
      minWidth: 200
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      color: 'var(--text-primary)',
      fontSize: 20
    }
  }, t.price), /*#__PURE__*/React.createElement("span", {
    style: {
      color: 'var(--text-muted)',
      fontSize: 12
    }
  }, t.line)), /*#__PURE__*/React.createElement(Button, {
    size: "sm"
  }, t.cta))))));
}
function Footer() {
  const cols = [{
    h: 'Product',
    l: ['Tables', 'Queries', 'Permissions', 'Changelog']
  }, {
    h: 'Company',
    l: ['About', 'Careers', 'Security']
  }, {
    h: 'Resources',
    l: ['Docs', 'API', 'Status']
  }];
  return /*#__PURE__*/React.createElement("footer", {
    style: {
      borderTop: '1px solid var(--border-hairline)',
      padding: '40px 0 64px',
      display: 'flex',
      gap: 64,
      flexWrap: 'wrap'
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      color: 'var(--text-primary)',
      width: 160
    }
  }, "Northlake"), cols.map(c => /*#__PURE__*/React.createElement("div", {
    key: c.h,
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 10
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      color: 'var(--text-muted)',
      fontSize: 12
    }
  }, c.h), c.l.map(l => /*#__PURE__*/React.createElement("a", {
    key: l,
    href: "#"
  }, l)))));
}
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/marketing/Landing.jsx", error: String((e && e.message) || e) }); }

// ui_kits/marketing/Page.jsx
try { (() => {
const {
  Header,
  Button
} = window.DSNS;
function Page() {
  return /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement(Header, {
    brand: "Northlake",
    links: [{
      label: 'Product',
      active: true
    }, {
      label: 'Pricing'
    }, {
      label: 'Docs'
    }, {
      label: 'Changelog'
    }],
    actions: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement(Button, {
      variant: "ghost",
      size: "sm"
    }, "Sign in"), /*#__PURE__*/React.createElement(Button, {
      size: "sm"
    }, "Start free"))
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      maxWidth: 'var(--container-max)',
      margin: '0 auto',
      padding: '0 24px'
    }
  }, /*#__PURE__*/React.createElement(Hero, null), /*#__PURE__*/React.createElement(Features, null), /*#__PURE__*/React.createElement(Placeholder, {
    label: "dashboard screenshot \u2014 query result + chart",
    height: 320
  }), /*#__PURE__*/React.createElement(Pricing, null), /*#__PURE__*/React.createElement(Footer, null)));
}
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/marketing/Page.jsx", error: String((e && e.message) || e) }); }

__ds_ns.Badge = __ds_scope.Badge;

__ds_ns.Button = __ds_scope.Button;

__ds_ns.Card = __ds_scope.Card;

__ds_ns.Divider = __ds_scope.Divider;

__ds_ns.IconButton = __ds_scope.IconButton;

__ds_ns.Table = __ds_scope.Table;

__ds_ns.Dialog = __ds_scope.Dialog;

__ds_ns.EmptyState = __ds_scope.EmptyState;

__ds_ns.Tooltip = __ds_scope.Tooltip;

__ds_ns.AttentionBanner = __ds_scope.AttentionBanner;

__ds_ns.BACKDROP_THEMES = __ds_scope.BACKDROP_THEMES;

__ds_ns.CrewBackdrop = __ds_scope.CrewBackdrop;

__ds_ns.CREW_GRID = __ds_scope.CREW_GRID;

__ds_ns.CrewRow = __ds_scope.CrewRow;

__ds_ns.Drawer = __ds_scope.Drawer;

__ds_ns.EventRow = __ds_scope.EventRow;

__ds_ns.HealthBadge = __ds_scope.HealthBadge;

__ds_ns.KanbanColumn = __ds_scope.KanbanColumn;

__ds_ns.StatTile = __ds_scope.StatTile;

__ds_ns.TICKET_STATES = __ds_scope.TICKET_STATES;

__ds_ns.TONES = __ds_scope.TONES;

__ds_ns.StatusPill = __ds_scope.StatusPill;

__ds_ns.TicketCard = __ds_scope.TicketCard;

__ds_ns.Checkbox = __ds_scope.Checkbox;

__ds_ns.Input = __ds_scope.Input;

__ds_ns.Select = __ds_scope.Select;

__ds_ns.Switch = __ds_scope.Switch;

__ds_ns.Header = __ds_scope.Header;

__ds_ns.Tabs = __ds_scope.Tabs;

})();
