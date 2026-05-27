import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useState, useCallback, useEffect } from 'react';
import { Play, Download, Settings, History } from 'lucide-react';
import { AgentMessages } from './AgentMessages';
import { LogViewer } from './LogViewer';
import { ProgressPhases } from './ProgressPhases';
import { ProviderStatus } from './ProviderStatus';
import { SettingsModal } from './SettingsModal';
import { ScanHistory } from './ScanHistory';
import { useSSE } from '../hooks/useSSE';
// UUID helper
function uuidv4() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
        const r = (Math.random() * 16) | 0;
        const v = c === 'x' ? r : (r & 0x3) | 0x8;
        return v.toString(16);
    });
}
export function Dashboard() {
    const [target, setTarget] = useState('');
    const [isScanning, setIsScanning] = useState(false);
    const [messages, setMessages] = useState([
        {
            id: uuidv4(),
            agent: 'system',
            message: 'Dashboard initialized. Ready for security assessment.',
            timestamp: new Date(),
        },
    ]);
    const [logs, setLogs] = useState([
        {
            id: uuidv4(),
            timestamp: new Date(),
            level: 'info',
            message: 'SecureFlow Dashboard loaded',
        },
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
        setLogs((prev) => [
            ...prev,
            {
                id: uuidv4(),
                timestamp: new Date(),
                level,
                message,
            },
        ]);
    }, []);
    const addMessage = useCallback((agent, message) => {
        setMessages((prev) => [
            ...prev,
            {
                id: uuidv4(),
                agent,
                message,
                timestamp: new Date(),
            },
        ]);
    }, []);
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
                setPhases((prev) => prev.map((p) => p.name === phaseName ? { ...p, status: 'completed' } : p));
            }
            addMessage('system', `✓ ${event.phase} complete (${event.n}/${event.total})`);
            addLog('success', `Phase ${event.n}/${event.total}: ${event.phase}`);
        }
        else if (event.event === 'report_ready') {
            if (event.report) {
                setReport(event.report);
                addLog('success', 'Report generated and ready for download');
                addMessage('system', '✅ Professional report generated!');
            }
        }
        else if (event.event === 'complete') {
            addLog('success', 'Security assessment complete');
            addMessage('system', 'Assessment complete! Report ready for download.');
            setIsScanning(false);
            loadHistory();
        }
        else if (event.event === 'error') {
            addLog('error', event.message || 'Unknown error occurred');
            setIsScanning(false);
        }
    }, [addLog, addMessage]);
    const handleSSEError = useCallback((error) => {
        addLog('error', error.message);
        setIsScanning(false);
    }, [addLog]);
    useSSE(isScanning ? target : null, handleSSEEvent, handleSSEError);
    const startScan = async () => {
        if (!target.trim()) {
            addLog('warning', 'Please enter a target');
            return;
        }
        setIsScanning(true);
        setMessages([]);
        setLogs([]);
        setReport(null);
        setPhases([
            { name: 'reconnaissance', status: 'pending', startTime: new Date() },
            { name: 'analysis', status: 'pending' },
            { name: 'reporting', status: 'pending' },
        ]);
        addLog('info', `Starting scan on target: ${target}`);
        addMessage('system', `Initializing security assessment for ${target}`);
    };
    const downloadReport = () => {
        if (!report) {
            addLog('warning', 'No report available');
            return;
        }
        const element = document.createElement('a');
        const file = new Blob([report], { type: 'text/html' });
        element.href = URL.createObjectURL(file);
        element.download = `secureflow-report-${target}-${new Date().toISOString().split('T')[0]}.html`;
        document.body.appendChild(element);
        element.click();
        document.body.removeChild(element);
        addLog('info', 'Report downloaded');
    };
    const loadHistory = async () => {
        try {
            const response = await fetch('/api/history');
            const data = await response.json();
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
        catch (e) {
            addLog('warning', 'Could not load history');
        }
    };
    useEffect(() => {
        loadHistory();
    }, []);
    useEffect(() => {
        // Fetch provider status from API
        const fetchProviderStatus = async () => {
            try {
                const response = await fetch('/api/providers');
                if (!response.ok)
                    throw new Error('Failed to fetch provider status');
                const data = await response.json();
                setProviders((prev) => prev.map((provider) => {
                    const statusData = data[provider.name];
                    if (statusData) {
                        return {
                            ...provider,
                            status: statusData.available ? 'available' : 'unavailable',
                            mode: statusData.mode,
                            lastCheck: new Date(),
                        };
                    }
                    return provider;
                }));
            }
            catch (error) {
                console.warn('Could not fetch provider status:', error);
            }
        };
        fetchProviderStatus();
        // Refresh every 5 seconds for near-real-time updates
        const interval = setInterval(fetchProviderStatus, 5000);
        return () => clearInterval(interval);
    }, []);
    return (_jsxs("div", { className: "flex flex-col h-screen bg-background text-foreground", children: [_jsx("header", { className: "glass border-b border-white/10 p-6 sticky top-0 z-40", children: _jsxs("div", { className: "flex items-center justify-between", children: [_jsxs("div", { children: [_jsx("h1", { className: "text-3xl md:text-4xl font-bold", children: _jsx("span", { className: "bg-gradient-to-r from-blue-400 via-purple-500 to-pink-500 bg-clip-text text-transparent", children: "SecureFlow" }) }), _jsx("p", { className: "text-xs md:text-sm text-muted-foreground mt-1", children: "Distributed Security Assessment Engine" })] }), _jsxs("div", { className: "flex gap-3", children: [_jsx("button", { onClick: () => setShowHistory(true), className: "p-2 rounded-lg hover:bg-white/10 transition-all duration-300 group", title: "View scan history", children: _jsx(History, { className: "h-5 w-5 group-hover:text-accent transition-colors" }) }), _jsx("button", { onClick: () => setShowSettings(true), className: "p-2 rounded-lg hover:bg-white/10 transition-all duration-300 group", title: "Settings", children: _jsx(Settings, { className: "h-5 w-5 group-hover:text-accent transition-colors" }) })] })] }) }), _jsxs("div", { className: "flex-1 overflow-hidden flex gap-4 p-4 md:p-6", children: [_jsxs("div", { className: "flex-1 flex flex-col gap-4 min-h-0", children: [_jsxs("div", { className: "flex-1 flex flex-col min-h-0 glass rounded-xl p-4 md:p-6", children: [_jsx("h2", { className: "text-lg md:text-xl font-semibold text-accent mb-4 uppercase tracking-wider", children: "\uD83E\uDD16 Agent Activity" }), _jsx(AgentMessages, { messages: messages })] }), _jsxs("div", { className: "flex-1 flex flex-col min-h-0 glass rounded-xl p-4 md:p-6", children: [_jsx("h2", { className: "text-lg md:text-xl font-semibold text-accent mb-4 uppercase tracking-wider", children: "\uD83D\uDCCB Live Logs" }), _jsx(LogViewer, { logs: logs })] })] }), _jsx("div", { className: "w-full md:w-[30%] flex flex-col gap-4 min-h-0", children: _jsxs("div", { className: "sticky top-24 space-y-4 overflow-y-auto max-h-[calc(100vh-8rem)] pr-2", children: [_jsxs("div", { className: "glass rounded-xl p-4 md:p-5", children: [_jsx("label", { className: "text-xs font-semibold text-muted-foreground uppercase tracking-wider block mb-3", children: "\uD83C\uDFAF Target" }), _jsx("input", { type: "text", value: target, onChange: (e) => setTarget(e.target.value), placeholder: "IP, hostname, URL", className: "input-glass w-full mb-3", disabled: isScanning }), _jsxs("button", { onClick: startScan, disabled: isScanning || !target.trim(), className: "w-full btn-primary flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed", children: [_jsx(Play, { className: "h-4 w-4" }), isScanning ? 'Scanning...' : 'Start Scan'] })] }), _jsxs("div", { className: "glass rounded-xl p-4 md:p-5", children: [_jsx("h3", { className: "text-sm font-semibold text-accent uppercase tracking-wider mb-4", children: "\uD83D\uDCCA Progress" }), _jsx(ProgressPhases, { phases: phases })] }), _jsxs("div", { className: "glass rounded-xl p-4 md:p-5", children: [_jsx("h3", { className: "text-sm font-semibold text-accent uppercase tracking-wider mb-4", children: "\u26A1 Providers" }), _jsx(ProviderStatus, { providers: providers })] }), _jsxs("div", { className: "space-y-2", children: [_jsxs("button", { onClick: downloadReport, disabled: !report, className: "w-full flex items-center justify-center gap-2 btn-primary disabled:opacity-50 disabled:cursor-not-allowed", children: [_jsx(Download, { className: "h-4 w-4" }), "Download"] }), _jsx("button", { onClick: () => {
                                                setMessages([]);
                                                setLogs([
                                                    {
                                                        id: uuidv4(),
                                                        timestamp: new Date(),
                                                        level: 'info',
                                                        message: 'Logs cleared',
                                                    },
                                                ]);
                                            }, className: "w-full px-4 py-2 glass rounded-lg hover:bg-white/20 font-semibold text-sm transition-all text-destructive", children: "Clear" })] })] }) })] }), showSettings && _jsx(SettingsModal, { onClose: () => setShowSettings(false) }), showHistory && (_jsx(ScanHistory, { sessions: history, onClose: () => setShowHistory(false) }))] }));
}
