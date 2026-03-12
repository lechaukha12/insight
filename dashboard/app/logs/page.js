'use client';

import { useState, useEffect, useCallback } from 'react';
import { getLogs } from '../lib/api';
import { timeAgo } from '../lib/hooks';

export default function LogsPage() {
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [selected, setSelected] = useState(null);

    const fetchData = useCallback(async () => {
        try {
            const result = await getLogs({ last_hours: 24, limit: 200 });
            setData(result);
        } catch (err) {
            console.error(err);
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        fetchData();
        const interval = setInterval(fetchData, 15000);
        return () => clearInterval(interval);
    }, [fetchData]);

    const logs = data?.logs || [];

    const levelColor = (l) =>
        l === 'critical' ? '#dc2626' : l === 'error' ? '#ef4444' : l === 'warning' ? '#f59e0b' : '#3b82f6';

    return (
        <>
            <div className="main-header">
                <h2>Error Logs</h2>
                <div className="header-actions">
                    <button className="btn btn-secondary" onClick={fetchData}>Refresh</button>
                </div>
            </div>
            <div className="main-body">
                {loading ? (
                    <div className="loading-overlay"><div className="loading-spinner" /><span>Loading logs...</span></div>
                ) : logs.length === 0 ? (
                    <div className="empty-state">
                        <div className="empty-state-icon">OK</div>
                        <div className="empty-state-text">No error logs</div>
                        <p style={{ color: 'var(--text-muted)', fontSize: '13px' }}>All pods are running without errors</p>
                    </div>
                ) : (
                    <div className="card">
                        <div className="card-header">
                            <div className="card-title">{logs.length} error log entries</div>
                        </div>
                        <table className="data-table">
                            <thead>
                                <tr>
                                    <th>Namespace</th><th>Pod</th><th>Container</th>
                                    <th>Level</th><th>Message</th><th>Time</th>
                                </tr>
                            </thead>
                            <tbody>
                                {logs.map((log, i) => (
                                    <tr key={log.id || i}
                                        onClick={() => setSelected(log)}
                                        style={{ cursor: 'pointer', transition: 'background 0.15s' }}
                                        onMouseEnter={e => e.currentTarget.style.background = 'rgba(0,0,0,0.04)'}
                                        onMouseLeave={e => e.currentTarget.style.background = ''}
                                    >
                                        <td><span className="badge info">{log.namespace || '—'}</span></td>
                                        <td style={{ fontFamily: 'monospace', fontSize: '13px' }}>{log.pod_name || '—'}</td>
                                        <td style={{ fontSize: '13px' }}>{log.container || '—'}</td>
                                        <td><span className="badge error">{log.log_level}</span></td>
                                        <td>
                                            <div style={{ maxWidth: '400px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontSize: '13px', fontFamily: 'monospace' }}>
                                                {log.message?.slice(0, 200) || '—'}
                                            </div>
                                        </td>
                                        <td style={{ fontSize: '13px', whiteSpace: 'nowrap' }}>{timeAgo(log.timestamp)}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </div>

            {/* ─── Log Detail Modal ─── */}
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
                            border: `2px solid ${levelColor(selected.log_level)}22`
                        }}
                    >
                        {/* Header */}
                        <div style={{
                            padding: '20px 24px', display: 'flex', alignItems: 'center', gap: 12,
                            borderBottom: '1px solid var(--border-color, #e5e7eb)',
                            background: `${levelColor(selected.log_level)}08`,
                        }}>
                            <div style={{
                                width: 40, height: 40, borderRadius: 10,
                                background: `${levelColor(selected.log_level)}18`,
                                color: levelColor(selected.log_level),
                                display: 'flex', alignItems: 'center', justifyContent: 'center',
                                fontWeight: 800, fontSize: 16,
                            }}>
                                {selected.log_level === 'critical' ? '!!' : selected.log_level === 'error' ? 'E' : 'W'}
                            </div>
                            <div style={{ flex: 1 }}>
                                <div style={{ fontWeight: 700, fontSize: 16 }}>Log Detail</div>
                                <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>
                                    {selected.pod_name} / {selected.container}
                                </div>
                            </div>
                            <span className="badge" style={{
                                background: `${levelColor(selected.log_level)}18`,
                                color: levelColor(selected.log_level),
                                fontWeight: 700, fontSize: 13,
                            }}>
                                {selected.log_level?.toUpperCase()}
                            </span>
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
                                    <div style={{ color: 'var(--text-muted)', fontSize: 11, fontWeight: 600, textTransform: 'uppercase', marginBottom: 4 }}>Pod</div>
                                    <span style={{ fontFamily: 'monospace', fontWeight: 600 }}>{selected.pod_name || '—'}</span>
                                </div>
                                <div>
                                    <div style={{ color: 'var(--text-muted)', fontSize: 11, fontWeight: 600, textTransform: 'uppercase', marginBottom: 4 }}>Container</div>
                                    <span style={{ fontFamily: 'monospace' }}>{selected.container || '—'}</span>
                                </div>
                                <div>
                                    <div style={{ color: 'var(--text-muted)', fontSize: 11, fontWeight: 600, textTransform: 'uppercase', marginBottom: 4 }}>Timestamp</div>
                                    <span>{selected.timestamp ? new Date(selected.timestamp).toLocaleString('vi-VN') : '—'}</span>
                                    <span style={{ color: 'var(--text-muted)', marginLeft: 8, fontSize: 12 }}>({timeAgo(selected.timestamp)})</span>
                                </div>
                                {selected.agent_id && (
                                    <div style={{ gridColumn: 'span 2' }}>
                                        <div style={{ color: 'var(--text-muted)', fontSize: 11, fontWeight: 600, textTransform: 'uppercase', marginBottom: 4 }}>Agent ID</div>
                                        <span style={{ fontFamily: 'monospace', fontSize: 12 }}>{selected.agent_id}</span>
                                    </div>
                                )}
                            </div>

                            {/* Full Message */}
                            <div>
                                <div style={{ color: 'var(--text-muted)', fontSize: 11, fontWeight: 600, textTransform: 'uppercase', marginBottom: 8 }}>Full Message</div>
                                <pre style={{
                                    background: '#1a1a2e', color: '#e0e0e0', borderRadius: 10,
                                    padding: '16px 20px', fontSize: 13, fontFamily: "'JetBrains Mono', 'Fira Code', 'Consolas', monospace",
                                    whiteSpace: 'pre-wrap', wordBreak: 'break-word',
                                    lineHeight: 1.6, maxHeight: 300, overflowY: 'auto',
                                    border: '1px solid #2a2a4a',
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
                            <button className="btn btn-secondary btn-sm" onClick={() => {
                                navigator.clipboard.writeText(selected.message || '');
                            }}>
                                Copy Message
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
