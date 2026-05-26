import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { CheckCircle2, Circle, Loader2 } from 'lucide-react';
import clsx from 'clsx';
export function ProgressPhases({ phases }) {
    return (_jsx("div", { className: "space-y-3", children: phases.map((phase) => (_jsxs("div", { className: clsx('flex items-center gap-3 p-4 rounded-lg border transition-all duration-300', phase.status === 'completed'
                ? 'border-success/50 bg-success/5'
                : phase.status === 'running'
                    ? 'border-primary/50 bg-primary/5 shadow-lg shadow-primary/20'
                    : 'border-border bg-card/50'), children: [_jsxs("div", { className: "relative w-10 h-10 flex-shrink-0", children: [phase.status === 'completed' && (_jsx(CheckCircle2, { className: "w-10 h-10 text-success" })), phase.status === 'running' && (_jsx(Loader2, { className: "w-10 h-10 text-primary animate-spin" })), phase.status === 'pending' && (_jsx(Circle, { className: "w-10 h-10 text-muted-foreground" }))] }), _jsxs("div", { className: "flex-1", children: [_jsx("h3", { className: "text-sm font-semibold text-foreground capitalize", children: phase.name.replace('_', ' ') }), _jsxs("p", { className: "text-xs text-muted-foreground", children: [phase.status === 'pending' && 'Waiting...', phase.status === 'running' && 'In Progress', phase.status === 'completed' && 'Completed ✓'] })] }), phase.startTime && (_jsx(Timer, { startTime: phase.startTime, isRunning: phase.status === 'running' }))] }, phase.name))) }));
}
function Timer({ startTime, isRunning }) {
    const [time, setTime] = React.useState(0);
    React.useEffect(() => {
        if (!isRunning)
            return;
        const interval = setInterval(() => {
            setTime(Math.floor((Date.now() - startTime.getTime()) / 1000));
        }, 1000);
        return () => clearInterval(interval);
    }, [isRunning, startTime]);
    const mins = Math.floor(time / 60);
    const secs = time % 60;
    return (_jsxs("div", { className: "text-sm font-mono text-primary font-semibold", children: [mins.toString().padStart(2, '0'), ":", secs.toString().padStart(2, '0')] }));
}
import React from 'react';
