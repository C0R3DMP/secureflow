import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
import { useState } from 'react';
const PROVIDER_GLYPHS = {
    claude: '◈',
    gemini: '◆',
    openrouter: '○',
    ollama: '◉',
    opencode: '▣',
};
const PRIORITY_LABEL = ['', 'PRIMARY', 'SECONDARY', 'TERTIARY', 'FALLBACK'];
function dotClass(status) {
    if (status === 'available')
        return 'ok';
    if (status === 'limited')
        return 'warn';
    return 'off';
}
export function ProviderStatus({ providers, onTest }) {
    const [testing, setTesting] = useState(null);
    const [starting, setStarting] = useState(false);
    const [stopping, setStopping] = useState(false);
    const handleTest = async (name) => {
        setTesting(name);
        onTest?.(name);
        setTimeout(() => setTesting(null), 2000);
    };
    const handleStartOpenCode = async () => {
        setStarting(true);
        try {
            await fetch('/api/opencode/start', { method: 'POST' });
            setTimeout(() => window.location.reload(), 1000);
        }
        finally {
            setStarting(false);
        }
    };
    const handleStopOpenCode = async () => {
        setStopping(true);
        try {
            await fetch('/api/opencode/stop', { method: 'POST' });
            setTimeout(() => window.location.reload(), 1000);
        }
        finally {
            setStopping(false);
        }
    };
    return (_jsx("div", { style: { display: 'flex', flexDirection: 'column', gap: '0.35rem' }, children: providers.map((p) => {
            const glyph = PROVIDER_GLYPHS[p.name] ?? '◌';
            const isAvail = p.status === 'available';
            const isLimited = p.status === 'limited';
            const nodeColor = isAvail ? 'var(--green)' : isLimited ? 'var(--amber)' : 'var(--text-dim)';
            const borderColor = isAvail
                ? 'rgba(0,255,110,0.2)'
                : isLimited
                    ? 'rgba(255,179,0,0.2)'
                    : 'var(--border-dim)';
            return (_jsxs("div", { style: {
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.5rem',
                    padding: '0.35rem 0.5rem',
                    border: `1px solid ${borderColor}`,
                    background: isAvail
                        ? 'rgba(0,255,110,0.03)'
                        : isLimited
                            ? 'rgba(255,179,0,0.03)'
                            : 'transparent',
                    transition: 'all 0.2s',
                }, children: [_jsx("span", { className: `status-dot ${dotClass(p.status)}` }), _jsx("span", { style: {
                            color: nodeColor,
                            fontFamily: 'var(--font-mono)',
                            fontSize: '0.85rem',
                            width: '14px',
                            textAlign: 'center',
                            flexShrink: 0,
                            textShadow: isAvail ? `0 0 6px ${nodeColor}` : 'none',
                        }, children: glyph }), _jsxs("div", { style: { flex: 1, minWidth: 0 }, children: [_jsxs("div", { style: {
                                    fontFamily: 'var(--font-mono)',
                                    fontSize: '0.62rem',
                                    fontWeight: 700,
                                    letterSpacing: '0.12em',
                                    color: isAvail ? 'var(--text-primary)' : 'var(--text-secondary)',
                                    textTransform: 'uppercase',
                                }, children: [p.name, p.mode && (_jsxs("span", { style: { fontWeight: 400, marginLeft: '0.4rem', color: 'var(--text-dim)', fontSize: '0.55rem' }, children: ["[", p.mode, "]"] }))] }), _jsx("div", { style: {
                                    fontFamily: 'var(--font-mono)',
                                    fontSize: '0.52rem',
                                    color: 'var(--text-dim)',
                                    letterSpacing: '0.08em',
                                }, children: PRIORITY_LABEL[p.priority] ?? `P${p.priority}` })] }), _jsxs("div", { style: { display: 'flex', gap: '0.2rem', flexShrink: 0 }, children: [_jsx("button", { className: "cb-icon-btn", onClick: () => handleTest(p.name), disabled: testing === p.name, title: "Test connection", style: {
                                    width: '1.6rem',
                                    height: '1.6rem',
                                    fontSize: '0.7rem',
                                    animation: testing === p.name ? 'spin-ring 1s linear infinite' : 'none',
                                }, children: "\u21BB" }), p.name === 'opencode' && (_jsxs(_Fragment, { children: [_jsx("button", { className: "cb-icon-btn", onClick: handleStartOpenCode, disabled: starting, title: "Start OpenCode", style: { width: '1.6rem', height: '1.6rem', fontSize: '0.7rem', color: 'var(--green)' }, children: "\u25B6" }), _jsx("button", { className: "cb-icon-btn", onClick: handleStopOpenCode, disabled: stopping, title: "Stop OpenCode", style: { width: '1.6rem', height: '1.6rem', fontSize: '0.7rem', color: 'var(--pink)' }, children: "\u25A0" })] }))] })] }, p.name));
        }) }));
}
