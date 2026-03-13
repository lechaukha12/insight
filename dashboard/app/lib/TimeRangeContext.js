'use client';

import { createContext, useContext, useState, useCallback, useMemo } from 'react';

const TimeRangeContext = createContext(null);

// Preset options
const PRESETS = [
    { label: '5m', value: 5 * 60 * 1000, key: '5m' },
    { label: '15m', value: 15 * 60 * 1000, key: '15m' },
    { label: '1h', value: 60 * 60 * 1000, key: '1h' },
    { label: '6h', value: 6 * 60 * 60 * 1000, key: '6h' },
    { label: '24h', value: 24 * 60 * 60 * 1000, key: '24h' },
    { label: '7d', value: 7 * 24 * 60 * 60 * 1000, key: '7d' },
];

export { PRESETS };

export function TimeRangeProvider({ children }) {
    const [preset, setPreset] = useState('1h');
    const [isLive, setIsLive] = useState(true);
    const [customFrom, setCustomFrom] = useState(null);
    const [customTo, setCustomTo] = useState(null);

    // Compute from/to based on preset or custom
    const timeRange = useMemo(() => {
        if (customFrom && customTo) {
            return {
                from: customFrom,
                to: customTo,
                preset: 'custom',
                isLive: false,
            };
        }
        const presetObj = PRESETS.find(p => p.key === preset);
        const now = new Date();
        const from = new Date(now.getTime() - (presetObj?.value || 3600000));
        return {
            from: from.toISOString(),
            to: now.toISOString(),
            preset,
            isLive,
        };
    }, [preset, isLive, customFrom, customTo]);

    // API query params
    const queryParams = useMemo(() => {
        if (isLive && !customFrom) {
            // In live mode with preset, use from_time only (to = now)
            const presetObj = PRESETS.find(p => p.key === preset);
            const from = new Date(Date.now() - (presetObj?.value || 3600000));
            return { from_time: from.toISOString().replace('T', ' ').substring(0, 19) };
        }
        return {
            from_time: timeRange.from.replace('T', ' ').substring(0, 19),
            to_time: timeRange.to.replace('T', ' ').substring(0, 19),
        };
    }, [timeRange, preset, isLive, customFrom]);

    const selectPreset = useCallback((key) => {
        setPreset(key);
        setCustomFrom(null);
        setCustomTo(null);
        setIsLive(true);
    }, []);

    const setCustomRange = useCallback((from, to) => {
        setCustomFrom(from);
        setCustomTo(to);
        setIsLive(false);
    }, []);

    const toggleLive = useCallback(() => {
        if (!isLive) {
            setCustomFrom(null);
            setCustomTo(null);
            setIsLive(true);
        } else {
            setIsLive(false);
        }
    }, [isLive]);

    const value = {
        ...timeRange,
        queryParams,
        preset,
        isLive,
        PRESETS,
        selectPreset,
        setCustomRange,
        toggleLive,
    };

    return (
        <TimeRangeContext.Provider value={value}>
            {children}
        </TimeRangeContext.Provider>
    );
}

export function useTimeRange() {
    const ctx = useContext(TimeRangeContext);
    if (!ctx) throw new Error('useTimeRange must be used within TimeRangeProvider');
    return ctx;
}
