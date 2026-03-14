'use client';

import { useState, useEffect, useCallback } from 'react';
import { getReports, generateReport } from '../lib/api';
import { formatDate, timeAgo } from '../lib/hooks';

const reportTypes = [
    { id: 'summary', label: 'Summary', desc: 'High-level overview of all agents & events', icon: '📊' },
    { id: 'detailed', label: 'Detailed', desc: 'Full breakdown with metrics, logs, and traces', icon: '📋' },
    { id: 'executive', label: 'Executive', desc: 'Brief management-level status report', icon: '📈' },
];

export default function ReportsPage() {
    const [reports, setReports] = useState([]);
    const [loading, setLoading] = useState(true);
    const [sending, setSending] = useState(false);
    const [sendResult, setSendResult] = useState(null);
    const [selectedChannels, setSelectedChannels] = useState(['telegram']);
    const [selectedType, setSelectedType] = useState('summary');
    const [expandedId, setExpandedId] = useState(null);
    const [previewMode, setPreviewMode] = useState(false);

    const fetchData = useCallback(async () => {
        try {
            const result = await getReports(20);
            setReports(result?.reports || []);
        } catch (err) { console.error(err); }
        finally { setLoading(false); }
    }, []);

    useEffect(() => { fetchData(); }, [fetchData]);

    const handleGenerate = async () => {
        setSending(true);
        setSendResult(null);
        try {
            const result = await generateReport(selectedChannels);
            setSendResult({ success: true, message: `Report generated and sent to: ${result.sent_to?.join(', ') || 'none (no alert configs)'}` });
            fetchData();
        } catch (err) {
            setSendResult({ success: false, message: err.message });
        } finally {
            setSending(false);
        }
    };

    const toggleChannel = (ch) => {
        setSelectedChannels(prev =>
            prev.includes(ch) ? prev.filter(c => c !== ch) : [...prev, ch]
        );
    };

    const channelIcons = { telegram: '📱', email: '✉️', webhook: '🔗' };

    return (
        <>
            <div className="main-header"><h2>Reports</h2></div>
            <div className="main-body">

                {/* ── Generate Report Section ── */}
                <div className="card" style={{ marginBottom: 24 }}>
                    <div className="card-header">
                        <div className="card-title">Generate Report</div>
                    </div>

                    {/* Report Type Selection */}
                    <div style={{ marginBottom: 20 }}>
                        <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: 10 }}>Report Template</div>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 12 }}>
                            {reportTypes.map(t => (
                                <button key={t.id}
                                    onClick={() => setSelectedType(t.id)}
                                    style={{
                                        padding: '14px 16px', borderRadius: 12, cursor: 'pointer',
                                        border: selectedType === t.id ? '2px solid var(--text-primary)' : '2px solid var(--border-color)',
                                        background: selectedType === t.id ? 'var(--bg-secondary, rgba(0,0,0,0.03))' : 'transparent',
                                        textAlign: 'left', transition: 'all 0.2s',
                                    }}
                                >
                                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                                        <span style={{ fontSize: 18 }}>{t.icon}</span>
                                        <span style={{ fontWeight: 700, fontSize: 14 }}>{t.label}</span>
                                    </div>
                                    <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>{t.desc}</div>
                                </button>
                            ))}
                        </div>
                    </div>

                    {/* Channel Selection */}
                    <div style={{ marginBottom: 20 }}>
                        <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: 10 }}>Delivery Channels</div>
                        <div style={{ display: 'flex', gap: 12 }}>
                            {['telegram', 'email', 'webhook'].map(ch => (
                                <label key={ch} style={{
                                    display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer',
                                    padding: '8px 16px', borderRadius: 10,
                                    border: selectedChannels.includes(ch) ? '2px solid var(--text-primary)' : '2px solid var(--border-color)',
                                    background: selectedChannels.includes(ch) ? 'var(--bg-secondary, rgba(0,0,0,0.03))' : 'transparent',
                                    transition: 'all 0.2s',
                                }}>
                                    <input
                                        type="checkbox"
                                        checked={selectedChannels.includes(ch)}
                                        onChange={() => toggleChannel(ch)}
                                        style={{ accentColor: 'var(--text-primary)', cursor: 'pointer' }}
                                    />
                                    <span style={{ fontSize: 16 }}>{channelIcons[ch]}</span>
                                    <span style={{ fontSize: 14, textTransform: 'capitalize', fontWeight: 600 }}>{ch}</span>
                                </label>
                            ))}
                        </div>
                    </div>

                    {/* Actions */}
                    <div style={{ display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
                        <button className="btn btn-primary" onClick={handleGenerate} disabled={sending || selectedChannels.length === 0}>
                            {sending ? <><div className="loading-spinner" /> Generating...</> : 'Generate & Send Report'}
                        </button>
                        {sendResult && (
                            <span style={{
                                fontSize: 13, padding: '6px 14px', borderRadius: 8,
                                background: sendResult.success ? '#15803d12' : '#dc262612',
                                color: sendResult.success ? '#15803d' : '#dc2626',
                                fontWeight: 600,
                            }}>
                                {sendResult.success ? '✓ ' : '✕ '}{sendResult.message}
                            </span>
                        )}
                    </div>
                </div>

                {/* ── Report History ── */}
                <div className="card">
                    <div className="card-header">
                        <div>
                            <div className="card-title">Report History</div>
                            <div className="card-subtitle">{reports.length} reports generated</div>
                        </div>
                    </div>
                    {loading ? (
                        <div className="loading-overlay"><div className="loading-spinner" /></div>
                    ) : reports.length === 0 ? (
                        <div className="empty-state">
                            <div className="empty-state-icon">—</div>
                            <div className="empty-state-text">No reports generated yet</div>
                        </div>
                    ) : (
                        <div>
                            {reports.map((report, i) => (
                                <div key={report.id || i}>
                                    {/* Report Row */}
                                    <div
                                        className="event-item"
                                        style={{
                                            cursor: 'pointer', transition: 'background 0.15s',
                                            background: expandedId === report.id ? 'var(--bg-secondary, rgba(0,0,0,0.02))' : undefined,
                                        }}
                                        onClick={() => setExpandedId(expandedId === report.id ? null : report.id)}
                                        onMouseEnter={e => e.currentTarget.style.background = 'rgba(0,0,0,0.03)'}
                                        onMouseLeave={e => e.currentTarget.style.background = expandedId === report.id ? 'var(--bg-secondary, rgba(0,0,0,0.02))' : ''}
                                    >
                                        <div style={{
                                            width: 36, height: 36, borderRadius: 10,
                                            background: '#7c3aed15', color: '#7c3aed',
                                            display: 'flex', alignItems: 'center', justifyContent: 'center',
                                            fontWeight: 800, fontSize: 12, flexShrink: 0,
                                        }}>📊</div>
                                        <div style={{ flex: 1, minWidth: 0 }}>
                                            <div style={{ fontWeight: 600, fontSize: 13 }}>
                                                <span className="badge info" style={{ marginRight: 8 }}>{report.report_type}</span>
                                                {formatDate(report.generated_at)}
                                            </div>
                                            <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>
                                                {report.content?.summary ? (
                                                    <>Agents: {report.content.summary.total_agents} | Events: {report.content.summary.total_events} | Critical: {report.content.summary.critical_events}</>
                                                ) : 'No summary'}
                                            </div>
                                        </div>
                                        <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexShrink: 0 }}>
                                            {(report.sent_to || []).map(ch => (
                                                <span key={ch} className="badge success" style={{ fontSize: 10 }}>{channelIcons[ch] || ''} {ch}</span>
                                            ))}
                                            {(!report.sent_to || report.sent_to.length === 0) && <span className="badge" style={{ fontSize: 10, color: 'var(--text-muted)' }}>Not sent</span>}
                                            <span style={{ fontSize: 11, color: 'var(--text-muted)', marginLeft: 4 }}>{timeAgo(report.generated_at)}</span>
                                            <span style={{ fontSize: 14, color: 'var(--text-muted)', marginLeft: 4, transition: 'transform 0.2s', transform: expandedId === report.id ? 'rotate(180deg)' : '' }}>▾</span>
                                        </div>
                                    </div>

                                    {/* Expanded Content */}
                                    {expandedId === report.id && report.content && (
                                        <div style={{
                                            padding: '16px 24px', margin: '0 16px 8px',
                                            background: 'var(--bg-secondary, #f7f5f0)', borderRadius: 10,
                                            animation: 'slideUp 0.2s ease',
                                        }}>
                                            {report.content.summary && (
                                                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))', gap: 12, marginBottom: 16 }}>
                                                    {Object.entries(report.content.summary).map(([key, val]) => (
                                                        <div key={key} style={{ textAlign: 'center', padding: '8px 0' }}>
                                                            <div style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: 4 }}>
                                                                {key.replace(/_/g, ' ')}
                                                            </div>
                                                            <div style={{ fontSize: 18, fontWeight: 700 }}>{val}</div>
                                                        </div>
                                                    ))}
                                                </div>
                                            )}
                                            {report.content.text && (
                                                <pre style={{
                                                    background: '#1a1a2e', color: '#e0e0e0', borderRadius: 10,
                                                    padding: '14px 18px', fontSize: 12,
                                                    fontFamily: "'JetBrains Mono', monospace",
                                                    whiteSpace: 'pre-wrap', wordBreak: 'break-word',
                                                    maxHeight: 300, overflowY: 'auto', margin: 0,
                                                }}>{report.content.text}</pre>
                                            )}
                                        </div>
                                    )}
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            </div>

            <style jsx>{`
                @keyframes slideUp { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
            `}</style>
        </>
    );
}
