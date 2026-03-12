'use client';

import { useState, useEffect, useCallback } from 'react';
import { getEvents, acknowledgeEvent } from '../lib/api';
import { timeAgo } from '../lib/hooks';

const levelIcons = { critical: 'C', error: 'E', warning: 'W', info: 'I' };
const levelColor = (l) =>
    l === 'critical' ? '#dc2626' : l === 'error' ? '#ef4444' : l === 'warning' ? '#f59e0b' : '#3b82f6';

export default function EventsPage() {
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [filter, setFilter] = useState('all');
    const [selected, setSelected] = useState(null);

    const fetchData = useCallback(async () => {
        try {
            const params = { last_hours: 24, limit: 100 };
            if (filter !== 'all') params.level = filter;
            const result = await getEvents(params);
            setData(result);
        } catch (err) {
            console.error(err);
        } finally {
            setLoading(false);
        }
    }, [filter]);

    useEffect(() => {
        fetchData();
        const interval = setInterval(fetchData, 10000);
        return () => clearInterval(interval);
    }, [fetchData]);

    const handleAcknowledge = async (eventId) => {
        try {
            await acknowledgeEvent(eventId);
            fetchData();
            if (selected?.id === eventId) setSelected(prev => ({ ...prev, acknowledged: true }));
        } catch (err) {
            console.error(err);
        }
    };

    const events = data?.events || [];

    return (
        <>
            <div className="main-header">
                <h2>Events & Alerts</h2>
                <div className="header-actions">
                    {['all', 'critical', 'error', 'warning', 'info'].map(level => (
                        <button
                            key={level}
                            className={`btn btn-sm ${filter === level ? 'btn-primary' : 'btn-secondary'}`}
                            onClick={() => { setFilter(level); setLoading(true); }}
                        >
                            {level === 'all' ? 'All' : level}
                        </button>
                    ))}
                </div>
            </div>
            <div className="main-body">
                {loading ? (
                    <div className="loading-overlay"><div className="loading-spinner" /><span>Loading events...</span></div>
                ) : events.length === 0 ? (
                    <div className="empty-state">
                        <div className="empty-state-icon">OK</div>
                        <div className="empty-state-text">No events found</div>
                    </div>
                ) : (
                    <div className="card">
                        <div className="card-header">
                            <div className="card-title">{events.length} events</div>
                        </div>
                        {events.map((event, i) => (
                            <div
                                key={event.id || i}
                                className="event-item"
                                onClick={() => setSelected(event)}
                                style={{ cursor: 'pointer', transition: 'background 0.15s' }}
                                onMouseEnter={e => e.currentTarget.style.background = 'rgba(0,0,0,0.03)'}
                                onMouseLeave={e => e.currentTarget.style.background = ''}
                            >
                                <div className={`event-icon ${event.level}`}>
                                    {levelIcons[event.level] || 'I'}
                                </div>
                                <div className="event-content">
                                    <div className="event-title">
                                        <span className={`badge ${event.level}`} style={{ marginRight: '8px', fontSize: '11px' }}>{event.level}</span>
                                        {event.title}
                                    </div>
                                    <div className="event-message">{event.message}</div>
                                    {event.namespace && (
                                        <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '4px' }}>
                                            {event.namespace} / {event.resource || '—'} | Source: {event.source || '—'}
                                        </div>
                                    )}
                                </div>
                                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '6px' }}>
                                    <div className="event-time">{timeAgo(event.created_at)}</div>
                                    {!event.acknowledged && (
                                        <button className="btn btn-sm btn-secondary" onClick={(e) => {
                                            e.stopPropagation();
                                            handleAcknowledge(event.id);
                                        }}>
                                            Ack
                                        </button>
                                    )}
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </div>

            {/* ─── Event Detail Modal ─── */}
            {selected && (
                <div
                    onClick={() => setSelected(null)}
                    style={{
                        position: 'fixed', inset: 0, zIndex: 9999,
                        background: 'rgba(0,0,0,0.5)', backdropFilter: 'blur(4px)',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        animation: 'fadeIn 0.2s ease',
                    }}
                >
                    <div
                        onClick={e => e.stopPropagation()}
                        style={{
                            background: 'var(--card-bg, #fff)', borderRadius: 16,
                            boxShadow: '0 25px 60px rgba(0,0,0,0.3)',
                            width: '90%', maxWidth: 720, maxHeight: '85vh',
                            overflow: 'hidden', display: 'flex', flexDirection: 'column',
                            animation: 'slideUp 0.25s ease',
                            border: `2px solid ${levelColor(selected.level)}22`
                        }}
                    >
                        {/* Header */}
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
                            }}>
                                {levelIcons[selected.level] || 'I'}
                            </div>
                            <div style={{ flex: 1, minWidth: 0 }}>
                                <div style={{ fontWeight: 700, fontSize: 16, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                    {selected.title || 'Event Detail'}
                                </div>
                                <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>
                                    {selected.source || 'Unknown source'}
                                </div>
                            </div>
                            <span className="badge" style={{
                                background: `${levelColor(selected.level)}18`,
                                color: levelColor(selected.level),
                                fontWeight: 700, fontSize: 13, flexShrink: 0,
                            }}>
                                {selected.level?.toUpperCase()}
                            </span>
                            {selected.acknowledged && (
                                <span style={{
                                    background: '#15803d18', color: '#15803d',
                                    padding: '3px 10px', borderRadius: 6, fontSize: 11, fontWeight: 700,
                                }}>✓ ACK</span>
                            )}
                            <button onClick={() => setSelected(null)} style={{
                                background: 'none', border: 'none', fontSize: 22, cursor: 'pointer',
                                color: 'var(--text-muted)', padding: '0 4px', lineHeight: 1,
                            }}>✕</button>
                        </div>

                        {/* Body */}
                        <div style={{ padding: '20px 24px', overflowY: 'auto', flex: 1 }}>
                            {/* Meta Info Grid */}
                            <div style={{
                                display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px 24px',
                                marginBottom: 20, fontSize: 13,
                            }}>
                                <div>
                                    <div style={{ color: 'var(--text-muted)', fontSize: 11, fontWeight: 600, textTransform: 'uppercase', marginBottom: 4 }}>Namespace</div>
                                    <span className="badge info">{selected.namespace || '—'}</span>
                                </div>
                                <div>
                                    <div style={{ color: 'var(--text-muted)', fontSize: 11, fontWeight: 600, textTransform: 'uppercase', marginBottom: 4 }}>Resource</div>
                                    <span style={{ fontFamily: 'monospace', fontWeight: 600 }}>{selected.resource || '—'}</span>
                                </div>
                                <div>
                                    <div style={{ color: 'var(--text-muted)', fontSize: 11, fontWeight: 600, textTransform: 'uppercase', marginBottom: 4 }}>Source</div>
                                    <span>{selected.source || '—'}</span>
                                </div>
                                <div>
                                    <div style={{ color: 'var(--text-muted)', fontSize: 11, fontWeight: 600, textTransform: 'uppercase', marginBottom: 4 }}>Timestamp</div>
                                    <span>{selected.created_at ? new Date(selected.created_at).toLocaleString('vi-VN') : '—'}</span>
                                    <span style={{ color: 'var(--text-muted)', marginLeft: 8, fontSize: 12 }}>({timeAgo(selected.created_at)})</span>
                                </div>
                                {selected.agent_id && (
                                    <div>
                                        <div style={{ color: 'var(--text-muted)', fontSize: 11, fontWeight: 600, textTransform: 'uppercase', marginBottom: 4 }}>Agent ID</div>
                                        <span style={{ fontFamily: 'monospace', fontSize: 12 }}>{selected.agent_id}</span>
                                    </div>
                                )}
                                {selected.cluster_id && (
                                    <div>
                                        <div style={{ color: 'var(--text-muted)', fontSize: 11, fontWeight: 600, textTransform: 'uppercase', marginBottom: 4 }}>Cluster</div>
                                        <span>{selected.cluster_id}</span>
                                    </div>
                                )}
                                <div>
                                    <div style={{ color: 'var(--text-muted)', fontSize: 11, fontWeight: 600, textTransform: 'uppercase', marginBottom: 4 }}>Status</div>
                                    {selected.acknowledged ? (
                                        <span style={{ color: '#15803d', fontWeight: 600 }}>✓ Acknowledged</span>
                                    ) : (
                                        <span style={{ color: '#f59e0b', fontWeight: 600 }}>⏳ Pending</span>
                                    )}
                                </div>
                                {selected.id && (
                                    <div>
                                        <div style={{ color: 'var(--text-muted)', fontSize: 11, fontWeight: 600, textTransform: 'uppercase', marginBottom: 4 }}>Event ID</div>
                                        <span style={{ fontFamily: 'monospace', fontSize: 12 }}>{selected.id}</span>
                                    </div>
                                )}
                            </div>

                            {/* Title */}
                            {selected.title && (
                                <div style={{ marginBottom: 16 }}>
                                    <div style={{ color: 'var(--text-muted)', fontSize: 11, fontWeight: 600, textTransform: 'uppercase', marginBottom: 8 }}>Title</div>
                                    <div style={{
                                        background: 'rgba(0,0,0,0.04)', borderRadius: 8,
                                        padding: '10px 14px', fontSize: 14, fontWeight: 600,
                                    }}>
                                        {selected.title}
                                    </div>
                                </div>
                            )}

                            {/* Full Message */}
                            <div>
                                <div style={{ color: 'var(--text-muted)', fontSize: 11, fontWeight: 600, textTransform: 'uppercase', marginBottom: 8 }}>Full Message</div>
                                <pre style={{
                                    background: '#1a1a2e', color: '#e0e0e0', borderRadius: 10,
                                    padding: '16px 20px', fontSize: 13, fontFamily: "'JetBrains Mono', 'Fira Code', 'Consolas', monospace",
                                    whiteSpace: 'pre-wrap', wordBreak: 'break-word',
                                    lineHeight: 1.6, maxHeight: 300, overflowY: 'auto',
                                    border: '1px solid #2a2a4a', margin: 0,
                                }}>
                                    {selected.message || '—'}
                                </pre>
                            </div>
                        </div>

                        {/* Footer */}
                        <div style={{
                            padding: '14px 24px', borderTop: '1px solid var(--border-color, #e5e7eb)',
                            display: 'flex', justifyContent: 'flex-end', gap: 8,
                        }}>
                            {!selected.acknowledged && (
                                <button className="btn btn-secondary btn-sm" onClick={() => {
                                    handleAcknowledge(selected.id);
                                }}>
                                    Acknowledge
                                </button>
                            )}
                            <button className="btn btn-secondary btn-sm" onClick={() => {
                                navigator.clipboard.writeText(
                                    `[${selected.level}] ${selected.title}\n${selected.message}\nNamespace: ${selected.namespace || '—'}\nResource: ${selected.resource || '—'}\nSource: ${selected.source || '—'}`
                                );
                            }}>
                                Copy Details
                            </button>
                            <button className="btn btn-primary btn-sm" onClick={() => setSelected(null)}>
                                Close
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* Animations */}
            <style jsx>{`
                @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
                @keyframes slideUp { from { opacity: 0; transform: translateY(20px); } to { opacity: 1; transform: translateY(0); } }
            `}</style>
        </>
    );
}
