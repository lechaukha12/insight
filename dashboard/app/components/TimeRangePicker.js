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
                    gap: 6px;
                    padding: 4px 10px;
                    background: var(--bg-card, rgba(255, 250, 220, 0.85));
                    border: 1px solid var(--border-color, rgba(201, 177, 0, 0.25));
                    border-radius: 8px;
                    position: relative;
                }
                .trp-live {
                    display: flex;
                    align-items: center;
                    gap: 4px;
                    padding: 3px 10px;
                    border: 1px solid var(--border-color, rgba(201, 177, 0, 0.25));
                    border-radius: 5px;
                    background: transparent;
                    color: var(--text-muted, #7a7050);
                    font-size: 11px;
                    font-weight: 600;
                    cursor: pointer;
                    transition: all 0.2s;
                }
                .trp-live.active {
                    background: rgba(21, 128, 61, 0.12);
                    border-color: rgba(21, 128, 61, 0.4);
                    color: #15803d;
                }
                .trp-live-dot {
                    width: 6px;
                    height: 6px;
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
                    gap: 1px;
                    background: rgba(201, 177, 0, 0.12);
                    border-radius: 5px;
                    padding: 2px;
                }
                .trp-preset {
                    padding: 3px 8px;
                    border: none;
                    border-radius: 4px;
                    background: transparent;
                    color: var(--text-muted, #7a7050);
                    font-size: 11px;
                    font-weight: 600;
                    cursor: pointer;
                    transition: all 0.15s;
                    white-space: nowrap;
                }
                .trp-preset:hover {
                    color: var(--text-primary, #1a1a1a);
                    background: rgba(255, 243, 180, 0.6);
                }
                .trp-preset.active {
                    background: var(--blue, #0165a7);
                    color: #fff;
                }
                .trp-display {
                    margin-left: auto;
                    font-size: 10px;
                    color: var(--text-muted, #7a7050);
                    font-family: 'SF Mono', 'Consolas', monospace;
                    white-space: nowrap;
                }
                .trp-custom-dropdown {
                    position: absolute;
                    top: calc(100% + 6px);
                    right: 0;
                    background: var(--bg-card, rgba(255, 250, 220, 0.98));
                    border: 1px solid var(--border-color, rgba(201, 177, 0, 0.3));
                    border-radius: 8px;
                    padding: 12px;
                    z-index: 1000;
                    box-shadow: 0 6px 24px rgba(0,0,0,0.15);
                    min-width: 260px;
                    backdrop-filter: blur(8px);
                }
                .trp-custom-row {
                    display: flex;
                    align-items: center;
                    gap: 8px;
                    margin-bottom: 8px;
                }
                .trp-custom-row label {
                    font-size: 11px;
                    font-weight: 600;
                    color: var(--text-secondary, #3a3a3a);
                    min-width: 32px;
                }
                .trp-custom-row input {
                    flex: 1;
                    padding: 5px 8px;
                    border: 1px solid var(--border-color, rgba(201, 177, 0, 0.3));
                    border-radius: 5px;
                    background: var(--bg-input, rgba(255, 248, 200, 0.8));
                    color: var(--text-primary, #1a1a1a);
                    font-size: 12px;
                    outline: none;
                }
                .trp-custom-row input:focus {
                    border-color: var(--blue, #0165a7);
                    box-shadow: 0 0 0 2px rgba(1, 101, 167, 0.15);
                }
                .trp-apply {
                    width: 100%;
                    padding: 6px;
                    border: none;
                    border-radius: 5px;
                    background: var(--blue, #0165a7);
                    color: #fff;
                    font-weight: 700;
                    font-size: 12px;
                    cursor: pointer;
                    transition: opacity 0.2s;
                }
                .trp-apply:hover { opacity: 0.85; }
            `}</style>
        </div>
    );
}
