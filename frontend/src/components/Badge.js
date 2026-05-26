import { jsx as _jsx } from "react/jsx-runtime";
import clsx from 'clsx';
const variants = {
    default: 'bg-primary text-primary-foreground',
    secondary: 'bg-secondary text-secondary-foreground',
    destructive: 'bg-destructive text-destructive-foreground',
    success: 'bg-success text-success-foreground',
    warning: 'bg-yellow-900/30 text-yellow-200',
};
export function Badge({ variant = 'default', children, className, }) {
    return (_jsx("span", { className: clsx('inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold transition-colors', variants[variant], className), children: children }));
}
