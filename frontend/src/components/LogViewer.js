import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useEffect, useRef } from 'react';
const LEVEL_CFG = {
    info: { color: 'var(--cyan)', prefix: 'INFO ', glow: 'rgba(0,240,255,0.25)' },
    warning: { color: 'var(--amber)', prefix: 'WARN ', glow: 'rgba(255,179,0,0.25)' },
    error: { color: 'var(--pink)', prefix: 'ERR  ', glow: 'rgba(255,0,122,0.25)' },
    success: { color: 'var(--green)', prefix: 'OK   ', glow: 'rgba(0,255,110,0.25)' },
};
function formatTime(d) {
    return d.toLocaleTimeString('en-US', { hour12: false });
}
export function LogViewer({ logs }) {
    const scrollRef = useRef(null);
    useEffect(() => {
        if (scrollRef.current) {
            scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
        }
    }, [logs]);
    return (_jsxs("div", { ref: scrollRef, className: "flex-1 overflow-y-auto", style: {
            fontFamily: 'var(--font-mono)',
            fontSize: '0.67rem',
            lineHeight: 1.6,
            background: 'rgba(0,0,0,0.4)',
            border: '1px solid var(--border-dim)',
            padding: '0.5rem',
        }, children: [logs.length === 0 ? (_jsx("div", { style: { color: 'var(--text-dim)', textAlign: 'center', padding: '2rem', letterSpacing: '0.1em' }, children: "\u2014 NO LOG ENTRIES \u2014" })) : (logs.map((log) => {
                const cfg = LEVEL_CFG[log.level];
                return (_jsxs("div", { className: "new-msg", style: {
                        display: 'flex',
                        gap: '0.5rem',
                        padding: '0.1rem 0.25rem',
                        borderRadius: '1px',
                    }, children: [_jsxs("span", { style: { color: 'var(--text-dim)', flexShrink: 0 }, children: ["[", formatTime(log.timestamp), "]"] }), _jsx("span", { style: {
                                color: cfg.color,
                                flexShrink: 0,
                                textShadow: `0 0 6px ${cfg.glow}`,
                                fontWeight: 700,
                                minWidth: '3.5rem',
                            }, children: cfg.prefix }), _jsx("span", { style: { color: 'var(--text-primary)', wordBreak: 'break-word', flex: 1 }, children: log.message })] }, log.id));
            })), logs.length > 0 && (_jsx("div", { style: { color: 'var(--cyan)', display: 'inline' }, children: _jsx("span", { className: "cb-cursor" }) }))] }));
}
