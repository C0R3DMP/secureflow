import { useState, useCallback } from 'react';
export function useAPI(url, options) {
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);
    const fetch_ = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const response = await fetch(url, options);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            const json = (await response.json());
            setData(json);
            return json;
        }
        catch (e) {
            const err = e instanceof Error ? e : new Error(String(e));
            setError(err);
            throw err;
        }
        finally {
            setLoading(false);
        }
    }, [url, options]);
    return { data, loading, error, fetch: fetch_ };
}
