import { useEffect } from 'react';
export function useSSE(target, onEvent, onError) {
    useEffect(() => {
        if (!target)
            return;
        const eventSource = new EventSource(`/stream/${encodeURIComponent(target)}`);
        const handleMessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                onEvent(data);
            }
            catch (e) {
                onError(new Error(`Failed to parse SSE message: ${e}`));
            }
        };
        const handleError = () => {
            eventSource.close();
            onError(new Error('Connection to server lost'));
        };
        eventSource.addEventListener('message', handleMessage);
        eventSource.addEventListener('error', handleError);
        return () => {
            eventSource.removeEventListener('message', handleMessage);
            eventSource.removeEventListener('error', handleError);
            eventSource.close();
        };
    }, [target, onEvent, onError]);
}
