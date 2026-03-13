'use client';

import { useState, useRef, useEffect } from 'react';
import { useTimeRange, PRESETS } from '../lib/TimeRangeContext';

export default function TimeRangePicker() {
    const { preset, isLive, selectPreset, setCustomRange, toggleLive, from, to } = useTimeRange();
    const [showCustom, setShowCustom] = useState(false);
    const [customFromVal, setCustomFromVal] = useState('');
    const [customToVal, setCustomToVal] = useState('');
    const dropRef = useRef(null);

    // Close custom dropdown on outside click
    useEffect(() => {
        const handler = (e) => {
            if (dropRef.current && !dropRef.current.contains(e.target)) setShowCustom(false);
        };
        document.addEventListener('mousedown', handler);
        return () => document.removeEventListener('mousedown', handler);
    }, []);

    const handleCustomApply = () => {
        if (customFromVal && customToVal) {
            setCustomRange(new Date(customFromVal).toISOString(), new Date(customToVal).toISOString());
            setShowCustom(false);
        }
    };

    const formatTime = (iso) => {
        if (!iso) return '--';
        const d = new Date(iso);
        return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false }) +
            ' ' + d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    };

    return (
        <div className="time-range-picker">
            {/* Live toggle */}
            <button
                className={`trp-live ${isLive ? 'active' : ''}`}
                onClick={toggleLive}
                title={isLive ? 'Live mode ON' : 'Live mode OFF'}
            >
                <span className="trp-live-dot" />
                Live
            </button>

            {/* Preset buttons */}
            <div className="trp-presets">
                {PRESETS.map(p => (
                    <button
                        key={p.key}
                        className={`trp-preset ${preset === p.key && !showCustom ? 'active' : ''}`}
                        onClick={() => selectPreset(p.key)}
                    >
                        {p.label}
                    </button>
                ))}
                <button
                    className={`trp-preset ${preset === 'custom' ? 'active' : ''}`}
                    onClick={() => setShowCustom(!showCustom)}
                >
                    Custom
                </button>
            </div>

            {/* Time display */}
            <div className="trp-display">
                <span className="trp-range">{formatTime(from)} → {formatTime(to)}</span>
            </div>

            {/* Custom dropdown */}
            {showCustom && (
                <div className="trp-custom-dropdown" ref={dropRef}>
                    <div className="trp-custom-row">
                        <label>From</label>
                        <input
                            type="datetime-local"
                            value={customFromVal}
                            onChange={e => setCustomFromVal(e.target.value)}
                        />
                    </div>
                    <div className="trp-custom-row">
                        <label>To</label>
                        <input
                            type="datetime-local"
                            value={customToVal}
                            onChange={e => setCustomToVal(e.target.value)}
                        />
                    </div>
                    <button className="trp-apply" onClick={handleCustomApply}>Apply</button>
                </div>
            )}

            <style jsx>{`
                .time-range-picker {
                    display: flex;
                    align-items: center;
                    gap: 8px;
                    padding: 6px 12px;
                    background: var(--card-bg, #1a1a2e);
                    border: 1px solid var(--border-color, rgba(255,255,255,0.08));
                    border-radius: 10px;
                    position: relative;
                    flex-wrap: wrap;
                }
                .trp-live {
                    display: flex;
                    align-items: center;
                    gap: 5px;
                    padding: 5px 12px;
                    border: 1px solid rgba(255,255,255,0.1);
                    border-radius: 6px;
                    background: transparent;
                    color: var(--text-muted, #666);
                    font-size: 12px;
                    font-weight: 600;
                    cursor: pointer;
                    transition: all 0.2s;
                }
                .trp-live.active {
                    background: rgba(16, 185, 129, 0.15);
                    border-color: rgba(16, 185, 129, 0.4);
                    color: #10b981;
                }
                .trp-live-dot {
                    width: 7px;
                    height: 7px;
                    border-radius: 50%;
                    background: currentColor;
                    animation: ${isLive ? 'pulse 1.5s infinite' : 'none'};
                }
                @keyframes pulse {
                    0%, 100% { opacity: 1; }
                    50% { opacity: 0.3; }
                }
                .trp-presets {
                    display: flex;
                    gap: 2px;
                    background: rgba(0,0,0,0.2);
                    border-radius: 6px;
                    padding: 2px;
                }
                .trp-preset {
                    padding: 4px 10px;
                    border: none;
                    border-radius: 5px;
                    background: transparent;
                    color: var(--text-muted, #888);
                    font-size: 11px;
                    font-weight: 600;
                    cursor: pointer;
                    transition: all 0.15s;
                    white-space: nowrap;
                }
                .trp-preset:hover {
                    color: var(--text-primary, #fff);
                    background: rgba(255,255,255,0.05);
                }
                .trp-preset.active {
                    background: var(--color-primary, #d4a843);
                    color: #000;
                }
                .trp-display {
                    margin-left: auto;
                    font-size: 11px;
                    color: var(--text-muted, #888);
                    font-family: 'SF Mono', monospace;
                    white-space: nowrap;
                }
                .trp-custom-dropdown {
                    position: absolute;
                    top: calc(100% + 8px);
                    right: 0;
                    background: var(--card-bg, #1a1a2e);
                    border: 1px solid var(--border-color, rgba(255,255,255,0.1));
                    border-radius: 10px;
                    padding: 16px;
                    z-index: 100;
                    box-shadow: 0 8px 32px rgba(0,0,0,0.4);
                    min-width: 280px;
                }
                .trp-custom-row {
                    display: flex;
                    align-items: center;
                    gap: 10px;
                    margin-bottom: 10px;
                }
                .trp-custom-row label {
                    font-size: 12px;
                    font-weight: 600;
                    color: var(--text-secondary, #aaa);
                    min-width: 36px;
                }
                .trp-custom-row input {
                    flex: 1;
                    padding: 6px 10px;
                    border: 1px solid var(--border-color, rgba(255,255,255,0.1));
                    border-radius: 6px;
                    background: rgba(0,0,0,0.2);
                    color: var(--text-primary, #fff);
                    font-size: 12px;
                    outline: none;
                }
                .trp-custom-row input:focus {
                    border-color: var(--color-primary, #d4a843);
                }
                .trp-apply {
                    width: 100%;
                    padding: 8px;
                    border: none;
                    border-radius: 6px;
                    background: var(--color-primary, #d4a843);
                    color: #000;
                    font-weight: 700;
                    font-size: 13px;
                    cursor: pointer;
                    transition: opacity 0.2s;
                }
                .trp-apply:hover { opacity: 0.85; }
            `}</style>
        </div>
    );
}
