'use client';

import { useState, useRef, useEffect } from 'react';
import { useTimeRange, PRESETS } from '../lib/TimeRangeContext';

export default function TimeRangePicker() {
    const { preset, isLive, selectPreset, setCustomRange, toggleLive, from, to } = useTimeRange();
    const [showDropdown, setShowDropdown] = useState(false);
    const [customFromVal, setCustomFromVal] = useState('');
    const [customToVal, setCustomToVal] = useState('');
    const dropRef = useRef(null);

    useEffect(() => {
        const handler = (e) => {
            if (dropRef.current && !dropRef.current.contains(e.target)) setShowDropdown(false);
        };
        document.addEventListener('mousedown', handler);
        return () => document.removeEventListener('mousedown', handler);
    }, []);

    const handleCustomApply = () => {
        if (customFromVal && customToVal) {
            setCustomRange(new Date(customFromVal).toISOString(), new Date(customToVal).toISOString());
            setShowDropdown(false);
        }
    };

    const formatTime = (iso) => {
        if (!iso) return '--:--';
        const d = new Date(iso);
        return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false }) +
            ' ' + d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    };

    const activeLabel = preset === 'custom' ? 'Custom' : PRESETS.find(p => p.key === preset)?.label || '1h';

    return (
        <div className="trp" ref={dropRef}>
            {/* Live indicator */}
            <button
                className={`trp-live ${isLive ? 'on' : ''}`}
                onClick={toggleLive}
                title={isLive ? 'Live: auto-refresh' : 'Click to enable live'}
            >
                <span className="trp-dot" />
            </button>

            {/* Main selector button */}
            <button className="trp-selector" onClick={() => setShowDropdown(!showDropdown)}>
                <span className="trp-label">{activeLabel}</span>
                <svg width="10" height="6" viewBox="0 0 10 6" fill="none">
                    <path d="M1 1L5 5L9 1" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
            </button>

            {/* Time range display */}
            <span className="trp-time">{formatTime(from)} → {formatTime(to)}</span>

            {/* Dropdown */}
            {showDropdown && (
                <div className="trp-drop">
                    <div className="trp-drop-section">
                        <div className="trp-drop-title">Quick Select</div>
                        <div className="trp-grid">
                            {PRESETS.map(p => (
                                <button
                                    key={p.key}
                                    className={`trp-opt ${preset === p.key ? 'active' : ''}`}
                                    onClick={() => { selectPreset(p.key); setShowDropdown(false); }}
                                >
                                    {p.label}
                                </button>
                            ))}
                        </div>
                    </div>
                    <div className="trp-divider" />
                    <div className="trp-drop-section">
                        <div className="trp-drop-title">Custom Range</div>
                        <div className="trp-field">
                            <label>From</label>
                            <input type="datetime-local" value={customFromVal} onChange={e => setCustomFromVal(e.target.value)} />
                        </div>
                        <div className="trp-field">
                            <label>To</label>
                            <input type="datetime-local" value={customToVal} onChange={e => setCustomToVal(e.target.value)} />
                        </div>
                        <button className="trp-apply" onClick={handleCustomApply}>Apply Range</button>
                    </div>
                </div>
            )}

            <style jsx>{`
                .trp {
                    display: inline-flex;
                    align-items: center;
                    gap: 6px;
                    position: relative;
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                }
                /* Live dot */
                .trp-live {
                    width: 24px;
                    height: 24px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    border: 1.5px solid var(--border-color, rgba(180,160,50,0.25));
                    border-radius: 6px;
                    background: transparent;
                    cursor: pointer;
                    transition: all 0.2s;
                    padding: 0;
                }
                .trp-live:hover {
                    border-color: rgba(21,128,61,0.5);
                }
                .trp-dot {
                    width: 7px;
                    height: 7px;
                    border-radius: 50%;
                    background: var(--text-muted, #999);
                    transition: background 0.2s;
                }
                .trp-live.on {
                    border-color: rgba(21,128,61,0.5);
                    background: rgba(21,128,61,0.08);
                }
                .trp-live.on .trp-dot {
                    background: #16a34a;
                    box-shadow: 0 0 6px rgba(22,163,74,0.5);
                    animation: blink 1.5s infinite;
                }
                @keyframes blink {
                    0%, 100% { opacity: 1; }
                    50% { opacity: 0.3; }
                }
                /* Selector button */
                .trp-selector {
                    display: flex;
                    align-items: center;
                    gap: 5px;
                    padding: 4px 10px;
                    border: 1.5px solid var(--border-color, rgba(180,160,50,0.25));
                    border-radius: 6px;
                    background: rgba(255,250,230,0.6);
                    color: var(--text-primary, #1a1a1a);
                    font-size: 12px;
                    font-weight: 700;
                    cursor: pointer;
                    transition: all 0.15s;
                    height: 24px;
                }
                .trp-selector:hover {
                    border-color: var(--blue, #0165a7);
                    background: rgba(255,250,230,0.9);
                }
                .trp-selector svg {
                    opacity: 0.5;
                    transition: transform 0.2s;
                }
                /* Time display */
                .trp-time {
                    font-size: 10px;
                    color: var(--text-muted, #7a7050);
                    font-family: 'SF Mono', 'Consolas', 'Monaco', monospace;
                    letter-spacing: 0.2px;
                    white-space: nowrap;
                }
                /* Dropdown */
                .trp-drop {
                    position: absolute;
                    top: calc(100% + 8px);
                    right: 0;
                    background: var(--bg-card, rgba(255,252,240,0.98));
                    border: 1px solid var(--border-color, rgba(180,160,50,0.2));
                    border-radius: 10px;
                    padding: 10px;
                    z-index: 1000;
                    box-shadow: 0 8px 32px rgba(0,0,0,0.12), 0 2px 8px rgba(0,0,0,0.06);
                    min-width: 240px;
                    backdrop-filter: blur(12px);
                }
                .trp-drop-section {}
                .trp-drop-title {
                    font-size: 9px;
                    font-weight: 700;
                    text-transform: uppercase;
                    letter-spacing: 0.8px;
                    color: var(--text-muted, #999);
                    margin-bottom: 6px;
                }
                .trp-divider {
                    height: 1px;
                    background: var(--border-color, rgba(180,160,50,0.15));
                    margin: 8px -10px;
                }
                /* Quick select grid */
                .trp-grid {
                    display: grid;
                    grid-template-columns: repeat(4, 1fr);
                    gap: 4px;
                }
                .trp-opt {
                    padding: 5px 0;
                    border: 1px solid var(--border-color, rgba(180,160,50,0.15));
                    border-radius: 5px;
                    background: transparent;
                    color: var(--text-secondary, #555);
                    font-size: 11px;
                    font-weight: 600;
                    cursor: pointer;
                    transition: all 0.12s;
                    text-align: center;
                }
                .trp-opt:hover {
                    background: rgba(1,101,167,0.06);
                    border-color: rgba(1,101,167,0.2);
                    color: var(--blue, #0165a7);
                }
                .trp-opt.active {
                    background: var(--blue, #0165a7);
                    border-color: var(--blue, #0165a7);
                    color: #fff;
                }
                /* Custom range fields */
                .trp-field {
                    display: flex;
                    align-items: center;
                    gap: 8px;
                    margin-bottom: 6px;
                }
                .trp-field label {
                    font-size: 10px;
                    font-weight: 700;
                    color: var(--text-muted, #888);
                    min-width: 28px;
                    text-transform: uppercase;
                    letter-spacing: 0.5px;
                }
                .trp-field input {
                    flex: 1;
                    padding: 5px 8px;
                    border: 1px solid var(--border-color, rgba(180,160,50,0.2));
                    border-radius: 5px;
                    background: var(--bg-input, rgba(255,248,200,0.6));
                    color: var(--text-primary, #1a1a1a);
                    font-size: 11px;
                    outline: none;
                    transition: border-color 0.15s;
                }
                .trp-field input:focus {
                    border-color: var(--blue, #0165a7);
                    box-shadow: 0 0 0 2px rgba(1,101,167,0.1);
                }
                .trp-apply {
                    width: 100%;
                    padding: 6px;
                    border: none;
                    border-radius: 5px;
                    background: var(--blue, #0165a7);
                    color: #fff;
                    font-weight: 700;
                    font-size: 11px;
                    cursor: pointer;
                    transition: all 0.15s;
                    margin-top: 2px;
                }
                .trp-apply:hover {
                    background: #014f85;
                    transform: translateY(-1px);
                    box-shadow: 0 2px 8px rgba(1,101,167,0.25);
                }
            `}</style>
        </div>
    );
}
