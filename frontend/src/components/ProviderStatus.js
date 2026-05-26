import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { CheckCircle2, AlertCircle, XCircle, RefreshCw } from 'lucide-react';
import { Badge } from './Badge';
import clsx from 'clsx';
import { useState } from 'react';
const providerEmojis = {
    claude: '🤖',
    gemini: '✨',
    ollama: '🦙',
};
export function ProviderStatus({ providers, onTest }) {
    const [testing, setTesting] = useState(null);
    const handleTest = async (name) => {
        setTesting(name);
        onTest?.(name);
        setTimeout(() => setTesting(null), 2000);
    };
    return (_jsx("div", { className: "space-y-2", children: providers.map((provider) => (_jsxs("div", { className: clsx('flex items-center justify-between p-3 rounded-lg border transition-colors', provider.status === 'available'
                ? 'border-success/30 bg-success/5'
                : provider.status === 'limited'
                    ? 'border-yellow-500/30 bg-yellow-500/5'
                    : 'border-destructive/30 bg-destructive/5'), children: [_jsxs("div", { className: "flex items-center gap-3", children: [_jsx("span", { className: "text-lg", children: providerEmojis[provider.name] }), _jsxs("div", { children: [_jsx("p", { className: "text-sm font-semibold capitalize text-foreground", children: provider.name }), _jsxs("p", { className: "text-xs text-muted-foreground", children: ["Priority: #", provider.priority] })] })] }), _jsxs("div", { className: "flex items-center gap-2", children: [provider.status === 'available' && (_jsx(CheckCircle2, { className: "h-5 w-5 text-success" })), provider.status === 'limited' && (_jsx(AlertCircle, { className: "h-5 w-5 text-yellow-500" })), provider.status === 'unavailable' && (_jsx(XCircle, { className: "h-5 w-5 text-destructive" })), _jsx(Badge, { variant: provider.status === 'available'
                                ? 'success'
                                : provider.status === 'limited'
                                    ? 'warning'
                                    : 'destructive', children: provider.status }), _jsx("button", { onClick: () => handleTest(provider.name), disabled: testing === provider.name, className: clsx('p-1 rounded hover:bg-primary/20 transition-colors disabled:opacity-50', testing === provider.name && 'animate-spin'), title: "Test connection", children: _jsx(RefreshCw, { className: "h-4 w-4" }) })] })] }, provider.name))) }));
}
