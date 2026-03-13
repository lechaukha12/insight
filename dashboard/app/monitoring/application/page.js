'use client';

import { useState, useEffect, useCallback } from 'react';
import { getServices, getServiceTraces, getServiceMetrics, getTraceSummary } from '../../lib/api';
import { timeAgo } from '../../lib/hooks';

export default function ApplicationMonitoringPage() {
    const [services, setServices] = useState([]);
    const [summary, setSummary] = useState(null);
    const [loading, setLoading] = useState(true);
    const [selectedService, setSelectedService] = useState(null);
    const [serviceTraces, setServiceTraces] = useState([]);
    const [serviceMetrics, setServiceMetrics] = useState([]);
    const [detailTab, setDetailTab] = useState('traces');
    const [detailLoading, setDetailLoading] = useState(false);
    const [lastHours, setLastHours] = useState(24);

    const fetchData = useCallback(async () => {
        try {
            const [svcResult, summaryResult] = await Promise.all([
                getServices(lastHours),
                getTraceSummary(lastHours)
            ]);
            setServices(svcResult?.services || []);
            setSummary(summaryResult);
        } catch (err) { console.error(err); }
        finally { setLoading(false); }
    }, [lastHours]);

    useEffect(() => {
        fetchData();
        const interval = setInterval(fetchData, 30000);
        return () => clearInterval(interval);
    }, [fetchData]);

    const openService = async (name) => {
        setSelectedService(name);
        setDetailTab('traces');
        setDetailLoading(true);
        try {
            const [t, m] = await Promise.all([
                getServiceTraces(name, lastHours, 50),
                getServiceMetrics(name, lastHours),
            ]);
            setServiceTraces(t?.traces || []);
            setServiceMetrics(m?.metrics || []);
        } catch (err) { console.error(err); }
        finally { setDetailLoading(false); }
    };

    const statusColor = (val, warn, error) => val > error ? 'var(--color-error)' : val > warn ? 'var(--color-warning)' : 'var(--color-success)';

    if (loading) return (
        <>
            <div className="main-header"><h2>Application Monitoring</h2></div>
            <div className="main-body"><div className="loading-overlay"><div className="loading-spinner" /><span>Loading services...</span></div></div>
        </>
    );

    return (
        <>
            {/* Header */}
            <div className="main-header">
                <h2>Application Monitoring</h2>
            </div>

            {/* Body */}
            <div className="main-body">
                {/* Overview Stats */}
                {summary && summary.total_requests > 0 && (
                    <div className="stats-grid">
                        <div className="stat-card">
                            <div className="stat-icon agents">REQ</div>
                            <div className="stat-info">
                                <div className="stat-value">{summary.total_requests?.toLocaleString()}</div>
                                <div className="stat-label">Total Requests</div>
                            </div>
                        </div>
                        <div className="stat-card">
                            <div className="stat-icon" style={{ background: 'rgba(14,165,233,0.12)', color: '#0ea5e9' }}>LAT</div>
                            <div className="stat-info">
                                <div className="stat-value">{summary.avg_latency_ms?.toFixed(0)}<span style={{ fontSize: 14, fontWeight: 500, marginLeft: 2 }}>ms</span></div>
                                <div className="stat-label">Avg Latency</div>
                            </div>
                        </div>
                        <div className="stat-card">
                            <div className="stat-icon" style={{ background: summary.error_rate > 5 ? 'var(--color-error-bg)' : 'var(--color-success-bg)', color: summary.error_rate > 5 ? 'var(--color-error)' : 'var(--color-success)' }}>ERR</div>
                            <div className="stat-info">
                                <div className="stat-value" style={{ color: summary.error_rate > 5 ? 'var(--color-error)' : 'var(--color-success)' }}>{summary.error_rate}%</div>
                                <div className="stat-label">Error Rate</div>
                            </div>
                        </div>
                        <div className="stat-card">
                            <div className="stat-icon" style={{ background: 'rgba(124,58,237,0.12)', color: '#7c3aed' }}>SVC</div>
                            <div className="stat-info">
                                <div className="stat-value">{services.length}</div>
                                <div className="stat-label">Active Services</div>
                            </div>
                        </div>
                    </div>
                )}

                {/* Service List */}
                {services.length === 0 ? (
                    <div className="card">
                        <div className="empty-state">
                            <div className="empty-state-icon">APP</div>
                            <div className="empty-state-text">No application services detected</div>
                            <p style={{ color: 'var(--text-muted)', fontSize: 13, marginTop: 8 }}>Configure your Java/Python/Node.js apps with an OTLP exporter pointing to the Insight Collector.</p>
                        </div>
                    </div>
                ) : (
                    <div className="card">
                        <div className="card-header">
                            <div className="card-title">Services ({services.length})</div>
                        </div>
                        <table className="data-table">
                            <thead><tr>
                                <th>Service Name</th>
                                <th style={{ textAlign: 'right' }}>Requests</th>
                                <th style={{ textAlign: 'right' }}>Avg Latency</th>
                                <th style={{ textAlign: 'right' }}>Errors</th>
                                <th style={{ textAlign: 'right' }}>Error Rate</th>
                                <th>Status</th>
                                <th>Last Seen</th>
                            </tr></thead>
                            <tbody>
                                {services.map(svc => {
                                    const errorRate = svc.req_count > 0 ? ((svc.error_count / svc.req_count) * 100) : 0;
                                    return (
                                        <tr key={svc.service_name} style={{ cursor: 'pointer' }} onClick={() => openService(svc.service_name)}>
                                            <td>
                                                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                                                    <div style={{
                                                        width: 36, height: 36, borderRadius: 'var(--radius-sm)', display: 'flex', alignItems: 'center', justifyContent: 'center',
                                                        background: 'rgba(1,101,167,0.1)', color: 'var(--blue)', fontWeight: 800, fontSize: 13
                                                    }}>
                                                        {svc.service_name.substring(0, 2).toUpperCase()}
                                                    </div>
                                                    <span style={{ fontWeight: 700, color: 'var(--blue)' }}>{svc.service_name}</span>
                                                </div>
                                            </td>
                                            <td style={{ textAlign: 'right', fontWeight: 700, fontSize: 15 }}>{svc.req_count?.toLocaleString()}</td>
                                            <td style={{ textAlign: 'right', fontWeight: 600, color: statusColor(svc.avg_latency || 0, 300, 1000) }}>
                                                {svc.avg_latency?.toFixed(0) || 0} ms
                                            </td>
                                            <td style={{ textAlign: 'right', fontWeight: 600, color: svc.error_count > 0 ? 'var(--color-error)' : 'var(--text-muted)' }}>
                                                {svc.error_count || 0}
                                            </td>
                                            <td style={{ textAlign: 'right' }}>
                                                <span style={{
                                                    fontWeight: 600,
                                                    color: errorRate > 5 ? 'var(--color-error)' : errorRate > 1 ? 'var(--color-warning)' : 'var(--color-success)'
                                                }}>{errorRate.toFixed(1)}%</span>
                                            </td>
                                            <td><span className={`badge ${errorRate > 5 ? 'error' : 'active'}`}><span className="badge-dot" />{errorRate > 5 ? 'degraded' : 'healthy'}</span></td>
                                            <td style={{ fontSize: 12, color: 'var(--text-muted)' }}>{svc.last_seen ? timeAgo(svc.last_seen) : '--'}</td>
                                        </tr>
                                    );
                                })}
                            </tbody>
                        </table>
                    </div>
                )}
            </div>

            {/* Service Detail Modal */}
            {selectedService && (
                <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.45)', backdropFilter: 'blur(4px)', zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24 }}
                    onClick={() => setSelectedService(null)}>
                    <div className="card" style={{ maxWidth: 1000, width: '100%', maxHeight: '85vh', overflow: 'auto', boxShadow: 'var(--shadow-lg)' }}
                        onClick={e => e.stopPropagation()}>
                        <div className="card-header">
                            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                                <div style={{
                                    width: 42, height: 42, borderRadius: 'var(--radius-sm)', display: 'flex', alignItems: 'center', justifyContent: 'center',
                                    background: 'rgba(1,101,167,0.1)', color: 'var(--blue)', fontWeight: 800, fontSize: 15
                                }}>
                                    {selectedService.substring(0, 2).toUpperCase()}
                                </div>
                                <div>
                                    <div className="card-title" style={{ fontSize: 18 }}>{selectedService}</div>
                                    <div className="card-subtitle">Service Detail — Last {lastHours}h</div>
                                </div>
                            </div>
                            <button className="btn btn-secondary btn-sm" onClick={() => setSelectedService(null)}>Close</button>
                        </div>

                        {/* Tabs */}
                        <div style={{ display: 'flex', gap: 8, marginBottom: 20 }}>
                            {[
                                { key: 'traces', label: `Traces (${serviceTraces.length})` },
                                { key: 'metrics', label: `Metrics (${serviceMetrics.length})` },
                            ].map(tab => (
                                <button key={tab.key}
                                    className={`btn ${detailTab === tab.key ? 'btn-primary' : 'btn-secondary'} btn-sm`}
                                    onClick={() => setDetailTab(tab.key)}>
                                    {tab.label}
                                </button>
                            ))}
                        </div>

                        {detailLoading ? (
                            <div className="loading-overlay"><div className="loading-spinner" /><span>Loading...</span></div>
                        ) : detailTab === 'traces' ? (
                            serviceTraces.length > 0 ? (
                                <table className="data-table">
                                    <thead><tr>
                                        <th>Span Name</th><th>Trace ID</th><th>Duration</th><th>Status</th><th>Time</th>
                                    </tr></thead>
                                    <tbody>
                                        {serviceTraces.map((t, i) => (
                                            <tr key={i}>
                                                <td style={{ fontWeight: 600, maxWidth: 280, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{t.span_name}</td>
                                                <td style={{ fontFamily: 'monospace', fontSize: 11, color: 'var(--text-muted)' }}>{t.trace_id?.substring(0, 16)}...</td>
                                                <td><span style={{ fontWeight: 700, color: statusColor(t.duration_ms || 0, 100, 500) }}>{t.duration_ms?.toFixed(1)} ms</span></td>
                                                <td><span className={`badge ${t.status === 'error' ? 'error' : 'success'}`}>{t.status}</span></td>
                                                <td style={{ fontSize: 12, color: 'var(--text-muted)' }}>{timeAgo(t.timestamp)}</td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            ) : <div className="empty-state" style={{ padding: 40 }}><div className="empty-state-text">No traces found</div></div>
                        ) : (
                            serviceMetrics.length > 0 ? (
                                <table className="data-table">
                                    <thead><tr>
                                        <th>Metric Name</th><th style={{ textAlign: 'right' }}>Value</th><th>Time</th>
                                    </tr></thead>
                                    <tbody>
                                        {serviceMetrics.slice(0, 50).map((m, i) => (
                                            <tr key={i}>
                                                <td style={{ fontWeight: 600 }}>{m.metric_name}</td>
                                                <td style={{ textAlign: 'right', fontFamily: 'monospace', fontWeight: 600 }}>{typeof m.metric_value === 'number' ? m.metric_value.toFixed(2) : m.metric_value}</td>
                                                <td style={{ fontSize: 12, color: 'var(--text-muted)' }}>{timeAgo(m.timestamp)}</td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            ) : <div className="empty-state" style={{ padding: 40 }}><div className="empty-state-text">No metrics found</div></div>
                        )}
                    </div>
                </div>
            )}
        </>
    );
}
