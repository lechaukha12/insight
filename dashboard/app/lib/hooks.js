'use client';

import { useState, useEffect, useCallback } from 'react';

/**
 * Custom hook for fetching data with auto-refresh
 */
export function useData(fetchFn, deps = [], refreshInterval = null) {
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    const refresh = useCallback(async () => {
        try {
            setError(null);
            const result = await fetchFn();
            setData(result);
        } catch (err) {
            setError(err.message);
            console.error('Data fetch error:', err);
        } finally {
            setLoading(false);
        }
    }, deps);

    useEffect(() => {
        refresh();
        if (refreshInterval) {
            const interval = setInterval(refresh, refreshInterval);
            return () => clearInterval(interval);
        }
    }, [refresh, refreshInterval]);

    return { data, loading, error, refresh };
}

/**
 * Format relative time
 */
export function timeAgo(dateStr) {
    if (!dateStr) return '';
    const date = new Date(dateStr);
    const now = new Date();
    const seconds = Math.floor((now - date) / 1000);

    if (seconds < 60) return 'just now';
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
    if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
    return `${Math.floor(seconds / 86400)}d ago`;
}

/**
 * Format datetime
 */
export function formatDate(dateStr) {
    if (!dateStr) return '';
    const date = new Date(dateStr);
    return date.toLocaleString('vi-VN', {
        year: 'numeric', month: '2-digit', day: '2-digit',
        hour: '2-digit', minute: '2-digit', second: '2-digit',
    });
}
