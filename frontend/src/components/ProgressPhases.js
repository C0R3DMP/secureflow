import { jsxs as _jsxs, jsx as _jsx } from "react/jsx-runtime";
import { useState, useEffect } from 'react';
const PHASE_CFG = {
    reconnaissance: { icon: '◉', code: 'RECON' },
    analysis: { icon: '◈', code: 'ANALYZ' },
    reporting: { icon: '◆', code: 'REPORT' },
};
function Timer({ startTime, isRunning }) {
    const [elapsed, setElapsed] = useState(0);
    useEffect(() => {
        if (!isRunning)
            return;
        const id = setInterval(() => {
            setElapsed(Math.floor((Date.now() - startTime.getTime()) / 1000));
        }, 1000);
        return () => clearInterval(id);
    }, [isRunning, startTime]);
    const m = Math.floor(elapsed / 60).toString().padStart(2, '0');
    const s = (elapsed % 60).toString().padStart(2, '0');
    return (_jsxs("span", { style: { color: 'var(--cyan)', fontFamily: 'var(--font-mono)', fontSize: '0.65rem' }, children: [m, ":", s] }));
}
export function ProgressPhases({ phases }) {
    return (_jsx("div", { style: { display: 'flex', flexDirection: 'column', gap: '0.5rem' }, children: phases.map((phase, idx) => {
            const cfg = PHASE_CFG[phase.name];
            const isRunning = phase.status === 'running';
            const isCompleted = phase.status === 'completed';
            const isPending = phase.status === 'pending';
            const borderColor = isRunning ? 'var(--cyan)' : isCompleted ? 'var(--green)' : 'var(--border-dim)';
            const iconColor = isRunning ? 'var(--cyan)' : isCompleted ? 'var(--green)' : 'var(--text-dim)';
            const labelColor = isRunning ? 'var(--cyan)' : isCompleted ? 'var(--green)' : 'var(--text-secondary)';
            const bgColor = isRunning ? 'rgba(0,240,255,0.05)' : isCompleted ? 'rgba(0,255,110,0.04)' : 'transparent';
            const boxShadow = isRunning ? '0 0 12px rgba(0,240,255,0.2), inset 0 0 6px rgba(0,240,255,0.05)' : 'none';
            return (_jsxs("div", { children: [_jsxs("div", { style: {
                            display: 'flex',
                            alignItems: 'center',
                            gap: '0.6rem',
                            padding: '0.5rem 0.6rem',
                            border: `1px solid ${borderColor}`,
                            background: bgColor,
                            boxShadow,
                            transition: 'all 0.3s',
                            animation: isRunning ? 'border-flow 2s ease-in-out infinite' : 'none',
                        }, children: [_jsx("div", { style: {
                                    width: '20px',
                                    height: '20px',
                                    border: `1px solid ${borderColor}`,
                                    display: 'flex',
                                    alignItems: 'center',
                                    justifyContent: 'center',
                                    flexShrink: 0,
                                    fontSize: '0.55rem',
                                    fontWeight: 700,
                                    color: iconColor,
                                    fontFamily: 'var(--font-mono)',
                                }, children: idx + 1 }), _jsx("span", { style: {
                                    fontSize: '0.9rem',
                                    color: iconColor,
                                    textShadow: isRunning ? `0 0 8px ${iconColor}` : isCompleted ? `0 0 6px var(--green)` : 'none',
                                    animation: isRunning ? 'neon-pulse 1.5s ease-in-out infinite' : 'none',
                                }, children: cfg.icon }), _jsxs("div", { style: { flex: 1 }, children: [_jsx("div", { style: {
                                            fontFamily: 'var(--font-mono)',
                                            fontSize: '0.62rem',
                                            fontWeight: 700,
                                            letterSpacing: '0.15em',
                                            color: labelColor,
                                            textTransform: 'uppercase',
                                        }, children: cfg.code }), _jsxs("div", { style: {
                                            fontFamily: 'var(--font-mono)',
                                            fontSize: '0.55rem',
                                            color: 'var(--text-dim)',
                                            letterSpacing: '0.08em',
                                        }, children: [isPending && 'STANDBY', isRunning && 'PROCESSING...', isCompleted && '[ COMPLETE ]'] })] }), _jsxs("div", { children: [isRunning && phase.startTime && (_jsx(Timer, { startTime: phase.startTime, isRunning: true })), isCompleted && (_jsx("span", { style: { color: 'var(--green)', fontSize: '0.9rem', textShadow: '0 0 6px var(--green)' }, children: "\u2713" })), isPending && (_jsx("span", { style: { color: 'var(--text-dim)', fontSize: '0.8rem' }, children: "\u25CB" }))] })] }), idx < phases.length - 1 && (_jsx("div", { style: {
                            width: '1px',
                            height: '6px',
                            marginLeft: '25px',
                            background: isCompleted
                                ? 'linear-gradient(180deg, var(--green), var(--border-dim))'
                                : 'var(--border-dim)',
                        } }))] }, phase.name));
        }) }));
}
