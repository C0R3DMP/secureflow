import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useEffect, useRef } from 'react';
import clsx from 'clsx';
const levelColors = {
    info: 'text-blue-400 bg-blue-500/10',
    warning: 'text-yellow-400 bg-yellow-500/10',
    error: 'text-red-400 bg-red-500/10',
    success: 'text-green-400 bg-green-500/10',
};
export function LogViewer({ logs }) {
    const scrollRef = useRef(null);
    useEffect(() => {
        if (scrollRef.current) {
            scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
        }
    }, [logs]);
    return (_jsx("div", { ref: scrollRef, className: "flex-1 overflow-y-auto p-3 bg-card/50 rounded-lg border border-border font-mono text-xs", children: logs.length === 0 ? (_jsx("div", { className: "text-muted-foreground text-center py-8", children: "No logs yet" })) : (_jsx("div", { className: "space-y-1", children: logs.map((log) => (_jsxs("div", { className: clsx('px-2 py-1 rounded flex gap-3 items-start', levelColors[log.level]), children: [_jsxs("span", { className: "text-muted-foreground shrink-0", children: ["[", log.timestamp.toLocaleTimeString(), "]"] }), _jsx("span", { className: "font-bold shrink-0 w-10", children: log.level.toUpperCase() }), _jsx("span", { className: "flex-1 break-words", children: log.message })] }, log.id))) })) }));
}
