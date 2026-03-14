'use client';

import { useState, useEffect, useCallback } from 'react';
import { getEvents, acknowledgeEvent } from '../lib/api';
import { useTimeRange } from '../lib/TimeRangeContext';
import { timeAgo } from '../lib/hooks';

const levelIcons = { critical: 'C', error: 'E', warning: 'W', info: 'I' };
const levelColor = (l) =>
    l === 'critical' ? '#dc2626' : l === 'error' ? '#ef4444' : l === 'warning' ? '#f59e0b' : '#3b82f6';

export default function EventsPage() {
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [filter, setFilter] = useState('all');
    const [search, setSearch] = useState('');
    const [selected, setSelected] = useState(null);
    const [selectedIds, setSelectedIds] = useState(new Set());
    const [bulkAcking, setBulkAcking] = useState(false);
    const { queryParams, isLive } = useTimeRange();

    const fetchData = useCallback(async () => {
        try {
            const params = { ...queryParams, limit: 200 };
            if (filter !== 'all') params.level = filter;
            const result = await getEvents(params);
            setData(result);
        } catch (err) { console.error(err); }
        finally { setLoading(false); }
    }, [filter, queryParams]);

    useEffect(() => {
        fetchData();
        if (isLive) {
            const interval = setInterval(fetchData, 10000);
            return () => clearInterval(interval);
        }
    }, [fetchData, isLive]);

    const handleAcknowledge = async (eventId) => {
        try {
            await acknowledgeEvent(eventId);
            fetchData();
            if (selected?.id === eventId) setSelected(prev => ({ ...prev, acknowledged: true }));
        } catch (err) { console.error(err); }
    };

    const handleBulkAck = async () => {
        if (selectedIds.size === 0) return;
        setBulkAcking(true);
        try {
            await Promise.all([...selectedIds].map(id => acknowledgeEvent(id)));
            setSelectedIds(new Set());
            fetchData();
        } catch (err) { console.error(err); }
        finally { setBulkAcking(false); }
    };

    const toggleSelect = (id) => {
        setSelectedIds(prev => {
            const next = new Set(prev);
            if (next.has(id)) next.delete(id); else next.add(id);
            return next;
        });
    };

    const selectAll = () => {
        const filteredEvents = getFilteredEvents();
        const unacked = filteredEvents.filter(e => !e.acknowledged);
        setSelectedIds(new Set(unacked.map(e => e.id)));
    };

    const events = data?.events || [];

    const getFilteredEvents = () => {
        if (!search.trim()) return events;
        const q = search.toLowerCase();
        return events.filter(e =>
            (e.title || '').toLowerCase().includes(q) ||
            (e.message || '').toLowerCase().includes(q) ||
            (e.source || '').toLowerCase().includes(q) ||
            (e.namespace || '').toLowerCase().includes(q) ||
            (e.agent_id || '').toLowerCase().includes(q)
        );
    };
    const filteredEvents = getFilteredEvents();

    // Count by level
    const counts = { critical: 0, error: 0, warning: 0, info: 0 };
    events.forEach(e => { if (counts[e.level] !== undefined) counts[e.level]++; });

    return (
        <>
            <div className="main-header">
                <h2>Events & Alerts</h2>
                <div className="header-actions" style={{ gap: 8 }}>
                    {isLive && <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 11, color: '#15803d', marginRight: 8 }}>
                        <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#15803d', display: 'inline-block', animation: 'pulse 2s infinite' }} />Live
                    </span>}
                    {['all', 'critical', 'error', 'warning', 'info'].map(level => (
                        <button key={level}
                            className={`btn btn-sm ${filter === level ? 'btn-primary' : 'btn-secondary'}`}
                            onClick={() => { setFilter(level); setLoading(true); }}
                            style={{ position: 'relative' }}
                        >
                            {level === 'all' ? 'All' : level}
                            {level !== 'all' && counts[level] > 0 && (
                                <span style={{
                                    position: 'absolute', top: -6, right: -6,
                                    background: levelColor(level), color: '#fff',
                                    borderRadius: 10, fontSize: 9, fontWeight: 700,
                                    padding: '1px 5px', minWidth: 16, textAlign: 'center',
                                }}>{counts[level]}</span>
                            )}
                        </button>
                    ))}
                </div>
            </div>
            <div className="main-body">

                {/* ── Alert Summary Bar ── */}
                <div className="stats-grid" style={{ marginBottom: 20, gridTemplateColumns: 'repeat(4, 1fr)' }}>
                    {['critical', 'error', 'warning', 'info'].map(level => (
                        <div key={level} className="stat-card" style={{
                            cursor: 'pointer', borderLeft: `3px solid ${levelColor(level)}`,
                            background: filter === level ? `${levelColor(level)}08` : undefined,
                        }} onClick={() => { setFilter(level); setLoading(true); }}>
                            <div className={`stat-icon ${level}`} style={{ width: 32, height: 32, fontSize: 13 }}>
                                {levelIcons[level]}
                            </div>
                            <div className="stat-info">
                                <div className="stat-value" style={{ fontSize: 22 }}>{counts[level]}</div>
                                <div className="stat-label" style={{ textTransform: 'capitalize' }}>{level}</div>
                            </div>
                        </div>
                    ))}
                </div>

                {/* ── Search + Bulk Actions ── */}
                <div style={{ display: 'flex', gap: 12, marginBottom: 16, alignItems: 'center' }}>
                    <div style={{ flex: 1, position: 'relative' }}>
                        <input
                            type="text" placeholder="Search events by title, message, source, namespace..."
                            value={search} onChange={e => setSearch(e.target.value)}
                            style={{
                                width: '100%', padding: '10px 16px 10px 36px',
                                border: '1px solid var(--border-color)', borderRadius: 10,
                                fontSize: 13, background: 'var(--card-bg)',
                                outline: 'none',
                            }}
                        />
                        <span style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)', fontSize: 14, color: 'var(--text-muted)' }}>🔍</span>
                    </div>
                    {selectedIds.size > 0 && (
                        <button className="btn btn-primary btn-sm" onClick={handleBulkAck} disabled={bulkAcking}>
                            {bulkAcking ? 'Acknowledging...' : `Ack Selected (${selectedIds.size})`}
                        </button>
                    )}
                    <button className="btn btn-secondary btn-sm" onClick={selectAll} title="Select all unacknowledged">
                        Select All
                    </button>
                </div>

                {loading ? (
                    <div className="loading-overlay"><div className="loading-spinner" /><span>Loading events...</span></div>
                ) : filteredEvents.length === 0 ? (
                    <div className="empty-state">
                        <div className="empty-state-icon" style={{ color: '#15803d' }}>✓</div>
                        <div className="empty-state-text">{search ? 'No events match your search' : 'No events found'}</div>
                    </div>
                ) : (
                    <div className="card">
                        <div className="card-header">
                            <div className="card-title">{filteredEvents.length} events</div>
                        </div>
                        {filteredEvents.map((event, i) => (
                            <div
                                key={event.id || i}
                                className="event-item"
                                style={{
                                    cursor: 'pointer', transition: 'background 0.15s',
                                    background: selectedIds.has(event.id) ? `${levelColor(event.level)}08` : undefined,
                                }}
                                onMouseEnter={e => { if (!selectedIds.has(event.id)) e.currentTarget.style.background = 'rgba(0,0,0,0.03)'; }}
                                onMouseLeave={e => { if (!selectedIds.has(event.id)) e.currentTarget.style.background = ''; }}
                            >
                                {/* Checkbox for bulk select */}
                                <input type="checkbox"
                                    checked={selectedIds.has(event.id)}
                                    onChange={() => toggleSelect(event.id)}
                                    onClick={e => e.stopPropagation()}
                                    style={{ marginRight: 8, accentColor: levelColor(event.level), cursor: 'pointer' }}
                                />
                                <div className={`event-icon ${event.level}`} onClick={() => setSelected(event)}>
                                    {levelIcons[event.level] || 'I'}
                                </div>
                                <div className="event-content" onClick={() => setSelected(event)} style={{ flex: 1, minWidth: 0 }}>
                                    <div className="event-title">
                                        <span className={`badge ${event.level}`} style={{ marginRight: '8px', fontSize: '11px' }}>{event.level}</span>
                                        {event.title}
                                    </div>
                                    <div className="event-message">{event.message}</div>
                                    {(event.namespace || event.source) && (
                                        <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '4px' }}>
                                            {event.namespace && <span className="badge info" style={{ fontSize: 10, marginRight: 4 }}>{event.namespace}</span>}
                                            {event.resource && <span style={{ marginRight: 8 }}>{event.resource}</span>}
                                            {event.source && <span style={{ color: 'var(--text-muted)' }}>Source: {event.source}</span>}
                                        </div>
                                    )}
                                </div>
                                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '6px', flexShrink: 0 }}>
                                    <div className="event-time">{timeAgo(event.created_at)}</div>
                                    {event.acknowledged ? (
                                        <span style={{ fontSize: 10, color: '#15803d', fontWeight: 600 }}>✓ ACK</span>
                                    ) : (
                                        <button className="btn btn-sm btn-secondary" style={{ fontSize: 10, padding: '2px 8px' }} onClick={(e) => {
                                            e.stopPropagation();
                                            handleAcknowledge(event.id);
                                        }}>Ack</button>
                                    )}
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </div>

            {/* ─── Event Detail Modal ─── */}
            {selected && (
                <div onClick={() => setSelected(null)}
                    style={{
                        position: 'fixed', inset: 0, zIndex: 9999,
                        background: 'rgba(0,0,0,0.5)', backdropFilter: 'blur(4px)',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        animation: 'fadeIn 0.2s ease',
                    }}
                >
                    <div onClick={e => e.stopPropagation()}
                        style={{
                            background: 'var(--card-bg, #fff)', borderRadius: 16,
                            boxShadow: '0 25px 60px rgba(0,0,0,0.3)',
                            width: '90%', maxWidth: 720, maxHeight: '85vh',
                            overflow: 'hidden', display: 'flex', flexDirection: 'column',
                            animation: 'slideUp 0.25s ease',
                            border: `2px solid ${levelColor(selected.level)}22`
                        }}
                    >
                        {/* Modal Header */}
                        <div style={{
                            padding: '20px 24px', display: 'flex', alignItems: 'center', gap: 12,
                            borderBottom: '1px solid var(--border-color, #e5e7eb)',
                            background: `${levelColor(selected.level)}08`,
                        }}>
                            <div style={{
                                width: 40, height: 40, borderRadius: 10,
                                background: `${levelColor(selected.level)}18`,
                                color: levelColor(selected.level),
                                display: 'flex', alignItems: 'center', justifyContent: 'center',
                                fontWeight: 800, fontSize: 18,
                            }}>{levelIcons[selected.level] || 'I'}</div>
                            <div style={{ flex: 1, minWidth: 0 }}>
                                <div style={{ fontWeight: 700, fontSize: 16, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                    {selected.title || 'Event Detail'}
                                </div>
                                <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>{selected.source || 'Unknown source'}</div>
                            </div>
                            <span className="badge" style={{
                                background: `${levelColor(selected.level)}18`, color: levelColor(selected.level),
                                fontWeight: 700, fontSize: 13, flexShrink: 0,
                            }}>{selected.level?.toUpperCase()}</span>
                            {selected.acknowledged && (
                                <span style={{ background: '#15803d18', color: '#15803d', padding: '3px 10px', borderRadius: 6, fontSize: 11, fontWeight: 700 }}>✓ ACK</span>
                            )}
                            <button onClick={() => setSelected(null)} style={{
                                background: 'none', border: 'none', fontSize: 22, cursor: 'pointer',
                                color: 'var(--text-muted)', padding: '0 4px', lineHeight: 1,
                            }}>✕</button>
                        </div>

                        {/* Modal Body */}
                        <div style={{ padding: '20px 24px', overflowY: 'auto', flex: 1 }}>
                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px 24px', marginBottom: 20, fontSize: 13 }}>
                                {[
                                    { label: 'Namespace', value: selected.namespace, badge: true },
                                    { label: 'Resource', value: selected.resource, mono: true },
                                    { label: 'Source', value: selected.source },
                                    { label: 'Timestamp', value: selected.created_at ? `${new Date(selected.created_at).toLocaleString('vi-VN')} (${timeAgo(selected.created_at)})` : null },
                                    { label: 'Agent ID', value: selected.agent_id, mono: true },
                                    { label: 'Status', value: selected.acknowledged ? '✓ Acknowledged' : '⏳ Pending', color: selected.acknowledged ? '#15803d' : '#f59e0b' },
                                ].filter(f => f.value).map(f => (
                                    <div key={f.label}>
                                        <div style={{ color: 'var(--text-muted)', fontSize: 11, fontWeight: 600, textTransform: 'uppercase', marginBottom: 4 }}>{f.label}</div>
                                        {f.badge ? <span className="badge info">{f.value}</span> :
                                         f.mono ? <span style={{ fontFamily: 'monospace', fontSize: 12 }}>{f.value}</span> :
                                         f.color ? <span style={{ color: f.color, fontWeight: 600 }}>{f.value}</span> :
                                         <span>{f.value}</span>}
                                    </div>
                                ))}
                            </div>
                            <div>
                                <div style={{ color: 'var(--text-muted)', fontSize: 11, fontWeight: 600, textTransform: 'uppercase', marginBottom: 8 }}>Full Message</div>
                                <pre style={{
                                    background: '#1a1a2e', color: '#e0e0e0', borderRadius: 10,
                                    padding: '16px 20px', fontSize: 13, fontFamily: "'JetBrains Mono', 'Consolas', monospace",
                                    whiteSpace: 'pre-wrap', wordBreak: 'break-word',
                                    lineHeight: 1.6, maxHeight: 300, overflowY: 'auto',
                                    border: '1px solid #2a2a4a', margin: 0,
                                }}>{selected.message || '—'}</pre>
                            </div>
                        </div>

                        {/* Modal Footer */}
                        <div style={{ padding: '14px 24px', borderTop: '1px solid var(--border-color, #e5e7eb)', display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
                            {!selected.acknowledged && (
                                <button className="btn btn-secondary btn-sm" onClick={() => handleAcknowledge(selected.id)}>Acknowledge</button>
                            )}
                            <button className="btn btn-secondary btn-sm" onClick={() => {
                                navigator.clipboard.writeText(`[${selected.level}] ${selected.title}\n${selected.message}\nNamespace: ${selected.namespace || '—'}\nResource: ${selected.resource || '—'}\nSource: ${selected.source || '—'}`);
                            }}>Copy Details</button>
                            <button className="btn btn-primary btn-sm" onClick={() => setSelected(null)}>Close</button>
                        </div>
                    </div>
                </div>
            )}

            <style jsx>{`
                @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
                @keyframes slideUp { from { opacity: 0; transform: translateY(20px); } to { opacity: 1; transform: translateY(0); } }
                @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }
            `}</style>
        </>
    );
}
