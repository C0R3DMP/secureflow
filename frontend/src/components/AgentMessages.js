import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useEffect, useRef } from 'react';
import { MessageCircle } from 'lucide-react';
import clsx from 'clsx';
const agentColors = {
    recon: 'border-l-blue-500 bg-blue-500/5',
    analyst: 'border-l-purple-500 bg-purple-500/5',
    reporter: 'border-l-green-500 bg-green-500/5',
    architect: 'border-l-indigo-500 bg-indigo-500/5',
    developer: 'border-l-cyan-500 bg-cyan-500/5',
    reviewer: 'border-l-amber-500 bg-amber-500/5',
    system: 'border-l-yellow-500 bg-yellow-500/5',
};
const agentLabels = {
    recon: 'Reconnaissance',
    analyst: 'Analyst',
    reporter: 'Reporter',
    architect: 'Architect',
    developer: 'Developer',
    reviewer: 'Reviewer',
    system: 'System',
};
export function AgentMessages({ messages }) {
    const scrollRef = useRef(null);
    useEffect(() => {
        if (scrollRef.current) {
            scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
        }
    }, [messages]);
    return (_jsx("div", { ref: scrollRef, className: "flex-1 overflow-y-auto space-y-3 p-4 bg-card/50 rounded-lg border border-border", children: messages.length === 0 ? (_jsxs("div", { className: "flex flex-col items-center justify-center h-full text-muted-foreground", children: [_jsx(MessageCircle, { className: "h-12 w-12 mb-2 opacity-50" }), _jsx("p", { children: "Waiting for agent collaboration..." })] })) : (messages.map((msg) => (_jsxs("div", { className: clsx('rounded border-l-4 p-3 backdrop-blur-sm', agentColors[msg.agent]), children: [_jsxs("div", { className: "flex items-center gap-2 mb-1", children: [_jsx("span", { className: "text-xs font-bold text-primary uppercase tracking-wider", children: agentLabels[msg.agent] }), _jsx("span", { className: "text-xs text-muted-foreground", children: msg.timestamp.toLocaleTimeString() })] }), _jsx("p", { className: "text-sm text-foreground/90", children: msg.message })] }, msg.id)))) }));
}
