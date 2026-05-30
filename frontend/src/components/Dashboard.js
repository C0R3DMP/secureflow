import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useState, useCallback, useEffect } from 'react';
import { AgentMessages } from './AgentMessages';
import { LogViewer } from './LogViewer';
import { ProgressPhases } from './ProgressPhases';
import { ProviderStatus } from './ProviderStatus';
import { SettingsModal } from './SettingsModal';
import { ScanHistory } from './ScanHistory';
import { useSSE } from '../hooks/useSSE';
function uuidv4() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
        const r = (Math.random() * 16) | 0;
        return (c === 'x' ? r : (r & 0x3) | 0x8).toString(16);
    });
}
/* ── Radar SVG for scan animation ─────────────────────────────── */
function RadarIcon({ active }) {
    return (_jsxs("svg", { width: "36", height: "36", viewBox: "0 0 36 36", fill: "none", children: [_jsx("circle", { cx: "18", cy: "18", r: "16", className: "cb-radar-ring" }), _jsx("circle", { cx: "18", cy: "18", r: "11", className: "cb-radar-ring", strokeOpacity: 0.18 }), _jsx("circle", { cx: "18", cy: "18", r: "6", className: "cb-radar-ring", strokeOpacity: 0.12 }), active && (_jsx("line", { x1: "18", y1: "18", x2: "18", y2: "2", stroke: "var(--cyan)", strokeWidth: "1.5", className: "cb-radar-sweep", strokeLinecap: "round" })), _jsx("circle", { cx: "18", cy: "18", r: "2", fill: "var(--cyan)", opacity: active ? 1 : 0.3 })] }));
}
/* ── Header bar ───────────────────────────────────────────────── */
function Header({ isScanning, onHistory, onSettings, }) {
    return (_jsxs("header", { style: {
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '0.6rem 1.2rem',
            borderBottom: '1px solid var(--border-cyan)',
            background: 'var(--panel)',
            backdropFilter: 'blur(16px)',
            position: 'relative',
            zIndex: 40,
            flexShrink: 0,
        }, children: [_jsxs("div", { style: { display: 'flex', alignItems: 'center', gap: '0.8rem' }, children: [_jsx(RadarIcon, { active: isScanning }), _jsxs("div", { children: [_jsx("div", { className: "glitch-text neon-cyan", style: {
                                    fontFamily: 'var(--font-mono)',
                                    fontWeight: 900,
                                    fontSize: '1.1rem',
                                    letterSpacing: '0.25em',
                                    lineHeight: 1,
                                }, children: "SECUREFLOW" }), _jsx("div", { style: {
                                    fontFamily: 'var(--font-mono)',
                                    fontSize: '0.52rem',
                                    letterSpacing: '0.3em',
                                    color: 'var(--text-dim)',
                                    textTransform: 'uppercase',
                                }, children: "NEURAL RECON SYSTEM v2.0" })] })] }), _jsxs("div", { style: { display: 'flex', alignItems: 'center', gap: '0.5rem' }, children: [_jsx("span", { className: `status-dot ${isScanning ? 'ok' : 'off'}` }), _jsx("span", { style: {
                            fontFamily: 'var(--font-mono)',
                            fontSize: '0.6rem',
                            letterSpacing: '0.2em',
                            color: isScanning ? 'var(--green)' : 'var(--text-dim)',
                            textTransform: 'uppercase',
                        }, children: isScanning ? 'SCAN ACTIVE' : 'STANDBY' })] }), _jsxs("div", { style: { display: 'flex', gap: '0.4rem' }, children: [_jsx("button", { className: "cb-icon-btn", onClick: onHistory, title: "Scan history", style: { clipPath: 'none' }, children: _jsxs("svg", { width: "14", height: "14", viewBox: "0 0 14 14", fill: "none", stroke: "currentColor", strokeWidth: "1.5", children: [_jsx("circle", { cx: "7", cy: "7", r: "5.5" }), _jsx("polyline", { points: "7,4 7,7 9,9" })] }) }), _jsx("button", { className: "cb-icon-btn", onClick: onSettings, title: "Settings", style: { clipPath: 'none' }, children: _jsxs("svg", { width: "14", height: "14", viewBox: "0 0 14 14", fill: "none", stroke: "currentColor", strokeWidth: "1.5", children: [_jsx("circle", { cx: "7", cy: "7", r: "2.5" }), _jsx("path", { d: "M7 1v2M7 11v2M1 7h2M11 7h2M3.1 3.1l1.4 1.4M9.5 9.5l1.4 1.4M3.1 10.9l1.4-1.4M9.5 4.5l1.4-1.4" })] }) })] })] }));
}
/* ── Control panel (left column) ─────────────────────────────── */
function ControlPanel({ target, setTarget, isScanning, onStart, onClear, onDownload, hasReport, phases, providers, }) {
    return (_jsxs("div", { style: {
            width: '22%',
            minWidth: '200px',
            display: 'flex',
            flexDirection: 'column',
            gap: '0.6rem',
            overflowY: 'auto',
            flexShrink: 0,
        }, children: [_jsxs("div", { className: "cb-panel cb-corner", style: { padding: '0.75rem' }, children: [_jsx("div", { className: "cb-label", style: { marginBottom: '0.5rem' }, children: "TARGET ACQUISITION" }), _jsx("input", { type: "text", className: "cb-input", value: target, onChange: (e) => setTarget(e.target.value), onKeyDown: (e) => e.key === 'Enter' && !isScanning && target.trim() && onStart(), placeholder: "host / IP / URL", disabled: isScanning, style: { marginBottom: '0.5rem' } }), _jsxs("button", { className: "cb-btn cb-btn-primary", onClick: onStart, disabled: isScanning || !target.trim(), style: { width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.4rem' }, children: [_jsx("span", { style: { fontSize: '0.8rem' }, children: isScanning ? '⊙' : '▶' }), isScanning ? 'SCANNING...' : 'LAUNCH SCAN'] })] }), _jsxs("div", { className: "cb-panel cb-corner", style: { padding: '0.75rem' }, children: [_jsx("div", { className: "cb-label", style: { marginBottom: '0.6rem' }, children: "MISSION PHASES" }), _jsx(ProgressPhases, { phases: phases })] }), _jsxs("div", { className: "cb-panel cb-corner", style: { padding: '0.75rem' }, children: [_jsx("div", { className: "cb-label", style: { marginBottom: '0.6rem' }, children: "AI NODE GRID" }), _jsx(ProviderStatus, { providers: providers })] }), _jsxs("div", { style: { display: 'flex', flexDirection: 'column', gap: '0.4rem' }, children: [_jsxs("button", { className: "cb-btn cb-btn-primary", onClick: onDownload, disabled: !hasReport, style: { width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.4rem' }, children: [_jsx("span", { children: "\u2193" }), " DOWNLOAD REPORT"] }), _jsxs("button", { className: "cb-btn cb-btn-danger", onClick: onClear, style: { width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.4rem' }, children: [_jsx("span", { children: "\u2297" }), " CLEAR FEED"] })] })] }));
}
/* ── Main Dashboard ──────────────────────────────────────────── */
export function Dashboard() {
    const [target, setTarget] = useState('');
    const [isScanning, setScanning] = useState(false);
    const [messages, setMessages] = useState([
        {
            id: uuidv4(),
            agent: 'system',
            message: 'Neural recon system initialized. Awaiting target acquisition.',
            timestamp: new Date(),
        },
    ]);
    const [logs, setLogs] = useState([
        { id: uuidv4(), timestamp: new Date(), level: 'info', message: 'SecureFlow kernel loaded' },
    ]);
    const [phases, setPhases] = useState([
        { name: 'reconnaissance', status: 'pending' },
        { name: 'analysis', status: 'pending' },
        { name: 'reporting', status: 'pending' },
    ]);
    const [providers, setProviders] = useState([
        { name: 'claude', status: 'unavailable', priority: 1 },
        { name: 'gemini', status: 'available', priority: 2, lastCheck: new Date() },
        { name: 'openrouter', status: 'unavailable', priority: 2, lastCheck: new Date() },
        { name: 'ollama', status: 'available', priority: 3, lastCheck: new Date() },
        { name: 'opencode', status: 'unavailable', priority: 4 },
    ]);
    const [showSettings, setShowSettings] = useState(false);
    const [showHistory, setShowHistory] = useState(false);
    const [history, setHistory] = useState([]);
    const [report, setReport] = useState(null);
    const addLog = useCallback((level, message) => {
        setLogs((prev) => [...prev, { id: uuidv4(), timestamp: new Date(), level, message }]);
    }, []);
    const addMessage = useCallback((agent, message) => {
        setMessages((prev) => [...prev, { id: uuidv4(), agent, message, timestamp: new Date() }]);
    }, []);
    const loadHistory = useCallback(async () => {
        try {
            const res = await fetch('/api/history');
            const data = await res.json();
            if (data.sessions) {
                setHistory(data.sessions.map((s) => ({
                    id: s.id,
                    target: s.target,
                    type: s.type || 'security',
                    status: s.status,
                    startedAt: new Date(s.timestamp),
                    summary: s.summary,
                })));
            }
        }
        catch {
            addLog('warning', 'Could not load history');
        }
    }, [addLog]);
    const handleSSEEvent = useCallback((event) => {
        if (event.event === 'start') {
            addLog('info', `Scan started: ${event.target}`);
        }
        else if (event.event === 'agent_message') {
            addMessage(event.agent || 'system', event.message || '');
            addLog('info', `[${event.agent}] ${event.message}`);
        }
        else if (event.event === 'phase_complete') {
            const phaseMap = {
                'Reconnaissance': 'reconnaissance',
                'Vulnerability Analysis': 'analysis',
                'Report Generation': 'reporting',
            };
            const phaseName = phaseMap[event.phase || ''];
            if (phaseName) {
                setPhases((prev) => prev.map((p) => (p.name === phaseName ? { ...p, status: 'completed' } : p)));
            }
            addMessage('system', `✓ ${event.phase} complete (${event.n}/${event.total})`);
            addLog('success', `Phase ${event.n}/${event.total}: ${event.phase}`);
        }
        else if (event.event === 'report_ready') {
            if (event.report) {
                setReport(event.report);
                addLog('success', 'Report generated — ready for download');
                addMessage('system', 'Report ready for download.');
            }
        }
        else if (event.event === 'complete') {
            addLog('success', 'Security assessment complete');
            addMessage('system', 'Assessment complete.');
            setScanning(false);
            loadHistory();
        }
        else if (event.event === 'error') {
            addLog('error', event.message || 'Unknown error');
            setScanning(false);
        }
    }, [addLog, addMessage, loadHistory]);
    const handleSSEError = useCallback((error) => {
        addLog('error', error.message);
        setScanning(false);
    }, [addLog]);
    useSSE(isScanning ? target : null, handleSSEEvent, handleSSEError);
    const startScan = () => {
        if (!target.trim()) {
            addLog('warning', 'Target required');
            return;
        }
        setScanning(true);
        setMessages([]);
        setLogs([]);
        setReport(null);
        setPhases([
            { name: 'reconnaissance', status: 'pending', startTime: new Date() },
            { name: 'analysis', status: 'pending' },
            { name: 'reporting', status: 'pending' },
        ]);
        addLog('info', `Initiating scan: ${target}`);
        addMessage('system', `Target acquired: ${target}`);
    };
    const downloadReport = () => {
        if (!report) {
            addLog('warning', 'No report available');
            return;
        }
        const a = document.createElement('a');
        a.href = URL.createObjectURL(new Blob([report], { type: 'text/html' }));
        a.download = `secureflow-${target}-${new Date().toISOString().split('T')[0]}.html`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        addLog('info', 'Report downloaded');
    };
    const clearFeed = () => {
        setMessages([]);
        setLogs([{ id: uuidv4(), timestamp: new Date(), level: 'info', message: 'Feed cleared' }]);
    };
    useEffect(() => { loadHistory(); }, [loadHistory]);
    useEffect(() => {
        const fetchProviders = async () => {
            try {
                const res = await fetch('/api/providers');
                if (!res.ok)
                    return;
                const data = await res.json();
                setProviders((prev) => prev.map((p) => {
                    const s = data[p.name];
                    return s ? { ...p, status: s.available ? 'available' : 'unavailable', mode: s.mode, lastCheck: new Date() } : p;
                }));
            }
            catch { }
        };
        fetchProviders();
        const id = setInterval(fetchProviders, 5000);
        return () => clearInterval(id);
    }, []);
    return (_jsxs("div", { style: { display: 'flex', flexDirection: 'column', height: '100vh', overflow: 'hidden' }, children: [_jsx(Header, { isScanning: isScanning, onHistory: () => setShowHistory(true), onSettings: () => setShowSettings(true) }), _jsxs("div", { style: {
                    flex: 1,
                    display: 'flex',
                    gap: '0.6rem',
                    padding: '0.6rem',
                    overflow: 'hidden',
                    minHeight: 0,
                }, children: [_jsx(ControlPanel, { target: target, setTarget: setTarget, isScanning: isScanning, onStart: startScan, onClear: clearFeed, onDownload: downloadReport, hasReport: !!report, phases: phases, providers: providers }), _jsxs("div", { className: "cb-panel cb-corner", style: {
                            flex: 1,
                            display: 'flex',
                            flexDirection: 'column',
                            padding: '0.75rem',
                            minHeight: 0,
                            overflow: 'hidden',
                        }, children: [_jsxs("div", { style: {
                                    display: 'flex',
                                    alignItems: 'center',
                                    justifyContent: 'space-between',
                                    marginBottom: '0.6rem',
                                    flexShrink: 0,
                                }, children: [_jsx("div", { className: "cb-label", children: "NEURAL AGENT FEED" }), _jsxs("div", { style: { display: 'flex', alignItems: 'center', gap: '0.4rem' }, children: [_jsx("span", { className: `status-dot ${isScanning ? 'ok' : 'off'}` }), _jsxs("span", { style: {
                                                    fontFamily: 'var(--font-mono)',
                                                    fontSize: '0.55rem',
                                                    color: 'var(--text-dim)',
                                                    letterSpacing: '0.15em',
                                                }, children: [messages.length, " TRANSMISSIONS"] })] })] }), _jsx(AgentMessages, { messages: messages })] }), _jsxs("div", { className: "cb-panel cb-corner", style: {
                            width: '26%',
                            minWidth: '180px',
                            display: 'flex',
                            flexDirection: 'column',
                            padding: '0.75rem',
                            flexShrink: 0,
                            minHeight: 0,
                            overflow: 'hidden',
                        }, children: [_jsxs("div", { style: {
                                    display: 'flex',
                                    alignItems: 'center',
                                    justifyContent: 'space-between',
                                    marginBottom: '0.6rem',
                                    flexShrink: 0,
                                }, children: [_jsx("div", { className: "cb-label", children: "SYSTEM TERMINAL" }), _jsxs("span", { style: {
                                            fontFamily: 'var(--font-mono)',
                                            fontSize: '0.55rem',
                                            color: 'var(--text-dim)',
                                            letterSpacing: '0.12em',
                                        }, children: ["[", logs.length, "]"] })] }), _jsx(LogViewer, { logs: logs })] })] }), showSettings && _jsx(SettingsModal, { onClose: () => setShowSettings(false) }), showHistory && _jsx(ScanHistory, { sessions: history, onClose: () => setShowHistory(false) })] }));
}
