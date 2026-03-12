'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { useParams } from 'next/navigation';
import { getAgent, getMetrics, getEvents, getLogs, getProcesses, getTraces } from '../../lib/api';
import { timeAgo } from '../../lib/hooks';
import { MetricsLineChart } from '../../components/Charts';

export default function AgentDetailPage() {
    const params = useParams();
    const agentId = params.id;
    const [agent, setAgent] = useState(null);
    const [events, setEvents] = useState([]);
    const [logs, setLogs] = useState([]);
    const [processes, setProcesses] = useState([]);
    const [processTimestamp, setProcessTimestamp] = useState(null);
    const [traces, setTraces] = useState([]);
    const [loading, setLoading] = useState(true);
    const [tab, setTab] = useState('metrics');
    const [logFilter, setLogFilter] = useState('');
    const [processSort, setProcessSort] = useState('cpu');
    const [expandedTrace, setExpandedTrace] = useState(null);
    const [otelMetrics, setOtelMetrics] = useState([]);

    const fetchData = useCallback(async () => {
        try {
            const [agentData, eventsData, logsData, procData, tracesData] = await Promise.all([
                getAgent(agentId),
                getEvents({ agent_id: agentId, last_hours: 48, limit: 50 }),
                getLogs({ agent_id: agentId, last_hours: 2, limit: 50 }),
                getProcesses(agentId).catch(() => ({ processes: [], timestamp: null })),
                getTraces({ agent_id: agentId, last_hours: 1, limit: 100 }).catch(() => ({ traces: [] })),
            ]);
            setAgent(agentData);
            setEvents(eventsData?.events || []);
            setLogs(logsData?.logs || []);
            setProcesses(procData?.processes || []);
            setProcessTimestamp(procData?.timestamp);
            setTraces(tracesData?.traces || []);
            // Fetch OTel application metrics if agent is opentelemetry type
            if (agentData?.agent_type === 'opentelemetry') {
                try {
                    const metricsData = await getMetrics({ agent_id: agentId, last_hours: 1, limit: 500 });
                    setOtelMetrics(metricsData?.metrics || []);
                } catch (e) { console.error('OTel metrics fetch error:', e); }
            }
        } catch (err) {
            console.error('Error loading agent:', err);
        } finally {
            setLoading(false);
        }
    }, [agentId]);

    useEffect(() => {
        fetchData();
        const interval = setInterval(fetchData, 15000);
        return () => clearInterval(interval);
    }, [fetchData]);

    if (loading) {
        return (
            <>
                <div className="main-header"><h2>Agent Detail</h2></div>
                <div className="main-body"><div className="loading-overlay"><div className="loading-spinner" /><span>Loading...</span></div></div>
            </>
        );
    }

    if (!agent) {
        return (
            <>
                <div className="main-header"><h2>Agent Not Found</h2></div>
                <div className="main-body"><div className="empty-state"><div className="empty-state-icon">?</div><div className="empty-state-text">Agent not found</div></div></div>
            </>
        );
    }

    const levelIcons = { critical: 'C', error: 'E', warning: 'W', info: 'I' };
    const isOtel = agent.agent_type === 'opentelemetry';
    const tabs = isOtel
        ? ['metrics', 'events', 'traces', 'logs']
        : ['metrics', 'events', 'processes', 'logs'];

    // Process sorting
    const sortedProcesses = [...processes].sort((a, b) => {
        if (processSort === 'cpu') return b.cpu_percent - a.cpu_percent;
        if (processSort === 'ram') return b.memory_percent - a.memory_percent;
        if (processSort === 'name') return (a.name || '').localeCompare(b.name || '');
        if (processSort === 'pid') return a.pid - b.pid;
        return 0;
    });

    // Log filtering
    const filteredLogs = logFilter
        ? logs.filter(l => (l.log_level || l.level) === logFilter)
        : logs;

    return (
        <>
            <div className="main-header">
                <h2>{agent.name}</h2>
                <div className="header-actions">
                    <span className={`badge ${agent.status === 'active' ? 'active' : 'error'}`}>
                        <span className="badge-dot" /> {agent.status}
                    </span>
                    <a href="/agents" className="btn btn-secondary">Back</a>
                </div>
            </div>
            <div className="main-body">
                {/* Agent Info */}
                <div className="stats-grid" style={{ marginBottom: 24 }}>
                    <div className="stat-card"><div className="stat-icon agents">ID</div><div className="stat-info"><div className="stat-label">Agent ID</div><div style={{ fontSize: 13, wordBreak: 'break-all', fontFamily: 'monospace' }}>{agent.id}</div></div></div>
                    <div className="stat-card"><div className="stat-icon" style={{ background: (agent.agent_category || (agent.agent_type === 'opentelemetry' ? 'application' : 'system')) === 'application' ? '#7c3aed22' : '#0165a722', color: (agent.agent_category || (agent.agent_type === 'opentelemetry' ? 'application' : 'system')) === 'application' ? '#7c3aed' : '#0165a7' }}>C</div><div className="stat-info"><div className="stat-label">Category</div><div style={{ fontSize: 15, fontWeight: 700 }}>{(agent.agent_category || (agent.agent_type === 'opentelemetry' ? 'Application' : 'System'))}</div></div></div>
                    <div className="stat-card"><div className="stat-icon active">T</div><div className="stat-info"><div className="stat-label">Type</div><div style={{ fontSize: 15, fontWeight: 700 }}>{agent.agent_type}</div></div></div>
                    <div className="stat-card"><div className="stat-icon warnings">H</div><div className="stat-info"><div className="stat-label">Hostname</div><div style={{ fontSize: 15, fontWeight: 700 }}>{agent.hostname || '-'}</div></div></div>
                    <div className="stat-card"><div className="stat-icon critical">L</div><div className="stat-info"><div className="stat-label">Last Heartbeat</div><div style={{ fontSize: 15, fontWeight: 700 }}>{timeAgo(agent.last_heartbeat)}</div></div></div>
                </div>

                {/* Tabs */}
                <div style={{ display: 'flex', gap: 8, marginBottom: 16, flexWrap: 'wrap' }}>
                    {tabs.map(t => (
                        <button key={t} className={`btn ${tab === t ? 'btn-primary' : 'btn-secondary'}`} onClick={() => setTab(t)}>
                            {t.charAt(0).toUpperCase() + t.slice(1)}
                            {t === 'processes' && processes.length > 0 ? ` (${processes.length})` : ''}
                            {t === 'traces' && traces.length > 0 ? ` (${traces.length})` : ''}
                        </button>
                    ))}
                </div>

                {/* Metrics Tab */}
                {tab === 'metrics' && (
                    <div className="card">
                        <div className="card-header"><div><div className="card-title">System Metrics</div><div className="card-subtitle">CPU / Memory / Disk for this agent</div></div></div>
                        <MetricsLineChart agentId={agentId} lastHours={12} height={350} />
                        {/* OTel Application Metrics */}
                        {agent?.agent_type === 'opentelemetry' && (
                            <div style={{ marginTop: 20, borderTop: '1px solid var(--border-color, #e0d8cc)', paddingTop: 20 }}>
                                <div className="card-header"><div><div className="card-title">📊 Application Metrics</div><div className="card-subtitle">OTel metrics from instrumented services ({otelMetrics.length} data points)</div></div></div>
                                {otelMetrics.length === 0 ? (
                                    <div className="empty-state"><div className="empty-state-icon">📈</div><div className="empty-state-text">No OTel metrics in the last hour. Metrics are collected automatically from instrumented services.</div></div>
                                ) : (
                                    <div>
                                        {/* Group metrics by category */}
                                        {(() => {
                                            const groups = {};
                                            otelMetrics.forEach(m => {
                                                const name = m.metric_name || '';
                                                let cat = 'Other';
                                                if (name.startsWith('jvm.')) cat = 'JVM';
                                                else if (name.startsWith('http.')) cat = 'HTTP';
                                                else if (name.startsWith('process.')) cat = 'Process';
                                                else if (name.startsWith('system.')) cat = 'System';
                                                else if (name.startsWith('db.')) cat = 'Database';
                                                if (!groups[cat]) groups[cat] = {};
                                                // Keep latest value per metric name
                                                if (!groups[cat][name] || (m.timestamp > groups[cat][name].timestamp)) {
                                                    groups[cat][name] = m;
                                                }
                                            });
                                            return Object.entries(groups).sort().map(([cat, metricsMap]) => (
                                                <div key={cat} style={{ marginBottom: 16 }}>
                                                    <div style={{ fontSize: 13, fontWeight: 700, color: '#666', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 8, paddingLeft: 8 }}>
                                                        {cat === 'JVM' ? '☕' : cat === 'HTTP' ? '🌐' : cat === 'Process' ? '⚙️' : cat === 'System' ? '💻' : cat === 'Database' ? '🗄️' : '📊'} {cat} Metrics ({Object.keys(metricsMap).length})
                                                    </div>
                                                    <table className="data-table">
                                                        <thead><tr><th>Metric</th><th>Value</th><th>Unit</th><th>Service</th></tr></thead>
                                                        <tbody>
                                                            {Object.values(metricsMap).sort((a, b) => (a.metric_name || '').localeCompare(b.metric_name || '')).map((m, i) => {
                                                                const labels = typeof m.labels === 'string' ? JSON.parse(m.labels || '{}') : (m.labels || {});
                                                                const val = m.metric_value;
                                                                const formatted = val >= 1e9 ? `${(val / 1e9).toFixed(2)} G` : val >= 1e6 ? `${(val / 1e6).toFixed(2)} M` : val >= 1000 ? `${(val / 1000).toFixed(1)} K` : typeof val === 'number' ? val.toFixed(2) : val;
                                                                return (
                                                                    <tr key={`${m.metric_name}-${i}`}>
                                                                        <td style={{ fontFamily: 'monospace', fontSize: 12 }}>{m.metric_name}</td>
                                                                        <td style={{ fontWeight: 600, color: 'var(--color-primary, #1a1a1a)' }}>{formatted}</td>
                                                                        <td><span className="badge" style={{ background: '#f5f5f0', color: '#666' }}>{labels.unit || '-'}</span></td>
                                                                        <td><span className="badge info">{labels.service_name || labels.host_name || '-'}</span></td>
                                                                    </tr>
                                                                );
                                                            })}
                                                        </tbody>
                                                    </table>
                                                </div>
                                            ));
                                        })()}
                                    </div>
                                )}
                            </div>
                        )}
                    </div>
                )}

                {/* Events Tab */}
                {tab === 'events' && (
                    <div className="card">
                        <div className="card-header"><div><div className="card-title">Events ({events.length})</div></div></div>
                        {events.length === 0 ? (
                            <div className="empty-state"><div className="empty-state-icon">OK</div><div className="empty-state-text">No events</div></div>
                        ) : (
                            <div>{events.map((e, i) => (
                                <div key={e.id || i} className="event-item">
                                    <div className={`event-icon ${e.level}`}>{levelIcons[e.level] || 'I'}</div>
                                    <div className="event-content"><div className="event-title">{e.title}</div><div className="event-message">{e.message}</div></div>
                                    <div className="event-time">{timeAgo(e.created_at)}</div>
                                </div>
                            ))}</div>
                        )}
                    </div>
                )}

                {/* Processes Tab (NEW v5.1.0) */}
                {tab === 'processes' && (
                    <div className="card">
                        <div className="card-header">
                            <div>
                                <div className="card-title">Processes ({processes.length})</div>
                                <div className="card-subtitle">
                                    {processTimestamp ? `Last updated: ${timeAgo(processTimestamp)}` : 'No data yet'}
                                </div>
                            </div>
                            <div style={{ display: 'flex', gap: 8 }}>
                                <select className="form-input" style={{ maxWidth: 130 }} value={processSort} onChange={e => setProcessSort(e.target.value)}>
                                    <option value="cpu">Sort: CPU ↓</option>
                                    <option value="ram">Sort: RAM ↓</option>
                                    <option value="name">Sort: Name</option>
                                    <option value="pid">Sort: PID</option>
                                </select>
                                <button className="btn btn-secondary btn-sm" onClick={fetchData}>Refresh</button>
                            </div>
                        </div>
                        {processes.length === 0 ? (
                            <div className="empty-state"><div className="empty-state-icon">--</div><div className="empty-state-text">No process data</div><div className="empty-state-hint">Agent needs v5.1.0+ for process monitoring</div></div>
                        ) : (
                            <table className="data-table">
                                <thead><tr>
                                    <th>PID</th><th>Name</th><th>User</th>
                                    <th style={{ cursor: 'pointer' }} onClick={() => setProcessSort('cpu')}>CPU %</th>
                                    <th style={{ cursor: 'pointer' }} onClick={() => setProcessSort('ram')}>RAM %</th>
                                    <th>RAM (MB)</th><th>Status</th><th>Command</th>
                                </tr></thead>
                                <tbody>{sortedProcesses.map((p, i) => (
                                    <tr key={`${p.pid}-${i}`}>
                                        <td style={{ fontFamily: 'monospace', fontSize: 12 }}>{p.pid}</td>
                                        <td style={{ fontWeight: 600 }}>{p.name}</td>
                                        <td><span className="badge info">{p.username}</span></td>
                                        <td>
                                            <span style={{
                                                fontWeight: 700,
                                                color: p.cpu_percent > 50 ? 'var(--color-error)' : p.cpu_percent > 20 ? 'var(--color-warning)' : 'var(--color-success)'
                                            }}>
                                                {p.cpu_percent?.toFixed(1)}%
                                            </span>
                                        </td>
                                        <td>
                                            <span style={{
                                                fontWeight: 600,
                                                color: p.memory_percent > 50 ? 'var(--color-error)' : p.memory_percent > 20 ? 'var(--color-warning)' : 'var(--color-success)'
                                            }}>
                                                {p.memory_percent?.toFixed(1)}%
                                            </span>
                                        </td>
                                        <td style={{ fontFamily: 'monospace', fontSize: 12 }}>{p.memory_mb}</td>
                                        <td><span className={`badge ${p.status === 'running' ? 'active' : 'info'}`}>{p.status}</span></td>
                                        <td style={{ maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontFamily: 'monospace', fontSize: 11 }}>{p.command}</td>
                                    </tr>
                                ))}</tbody>
                            </table>
                        )}
                    </div>
                )}

                {/* Traces Tab (OpenTelemetry only, NEW v5.1.0) */}
                {tab === 'traces' && (
                    <div className="card">
                        <div className="card-header">
                            <div><div className="card-title">Traces ({traces.length})</div><div className="card-subtitle">OTLP trace spans from instrumented applications</div></div>
                            <button className="btn btn-secondary btn-sm" onClick={fetchData}>Refresh</button>
                        </div>
                        {/* Trace Summary Stats */}
                        {traces.length > 0 && (() => {
                            const avgLatency = traces.reduce((s, t) => s + (t.duration_ms || 0), 0) / traces.length;
                            const maxLatency = Math.max(...traces.map(t => t.duration_ms || 0));
                            const errorCount = traces.filter(t => t.status === 'error').length;
                            const errorRate = (errorCount / traces.length * 100).toFixed(1);
                            return (
                                <div className="stats-grid" style={{ marginBottom: 16 }}>
                                    <div className="stat-card"><div className="stat-icon" style={{ background: '#7c3aed22', color: '#7c3aed' }}>RQ</div><div className="stat-info"><div className="stat-value">{traces.length}</div><div className="stat-label">Total Spans</div></div></div>
                                    <div className="stat-card"><div className="stat-icon" style={{ background: '#0ea5e922', color: '#0ea5e9' }}>MS</div><div className="stat-info"><div className="stat-value">{avgLatency.toFixed(1)}<span style={{ fontSize: 12, fontWeight: 400 }}>ms</span></div><div className="stat-label">Avg Latency</div></div></div>
                                    <div className="stat-card"><div className="stat-icon" style={{ background: errorRate > 5 ? '#ef444422' : '#22c55e22', color: errorRate > 5 ? '#ef4444' : '#22c55e' }}>ER</div><div className="stat-info"><div className="stat-value" style={{ color: errorRate > 5 ? 'var(--color-error)' : 'var(--color-success)' }}>{errorRate}%</div><div className="stat-label">Error Rate</div></div></div>
                                    <div className="stat-card"><div className="stat-icon" style={{ background: '#f59e0b22', color: '#f59e0b' }}>MX</div><div className="stat-info"><div className="stat-value">{maxLatency.toFixed(1)}<span style={{ fontSize: 12, fontWeight: 400 }}>ms</span></div><div className="stat-label">Max Latency</div></div></div>
                                </div>
                            );
                        })()}
                        {traces.length === 0 ? (
                            <div className="empty-state"><div className="empty-state-icon">--</div><div className="empty-state-text">No traces</div><div className="empty-state-hint">Send OTLP data to this agent's OTLP endpoint</div></div>
                        ) : (
                            <table className="data-table">
                                <thead><tr><th>Service</th><th>Span</th><th>Status</th><th>Duration</th><th>Trace ID</th><th>Time</th></tr></thead>
                                <tbody>{traces.map((t, i) => (
                                    <React.Fragment key={t.id || `trace-${i}`}>
                                        <tr onClick={() => setExpandedTrace(expandedTrace === i ? null : i)} style={{ cursor: 'pointer' }}>
                                            <td><span className="badge info">{t.service_name}</span></td>
                                            <td style={{ fontWeight: 600 }}>{t.span_name}</td>
                                            <td><span className={`badge ${t.status === 'error' ? 'error' : 'active'}`}><span className="badge-dot" />{t.status}</span></td>
                                            <td style={{
                                                fontWeight: 600,
                                                color: t.duration_ms > 1000 ? 'var(--color-error)' : t.duration_ms > 200 ? 'var(--color-warning)' : 'var(--color-success)'
                                            }}>
                                                {t.duration_ms?.toFixed(1)}ms
                                            </td>
                                            <td style={{ fontFamily: 'monospace', fontSize: 11 }}>{t.trace_id?.slice(0, 16)}...</td>
                                            <td>{timeAgo(t.timestamp)}</td>
                                        </tr>
                                        {expandedTrace === i && (
                                            <tr>
                                                <td colSpan={6} style={{ padding: '12px 16px', background: 'var(--bg-secondary, #faf7f2)' }}>
                                                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 12 }}>
                                                        <div><strong style={{ fontSize: 11, textTransform: 'uppercase', color: '#888' }}>Trace ID</strong><div style={{ fontFamily: 'monospace', fontSize: 12, wordBreak: 'break-all' }}>{t.trace_id}</div></div>
                                                        <div><strong style={{ fontSize: 11, textTransform: 'uppercase', color: '#888' }}>Span ID</strong><div style={{ fontFamily: 'monospace', fontSize: 12 }}>{t.span_id}</div></div>
                                                        <div><strong style={{ fontSize: 11, textTransform: 'uppercase', color: '#888' }}>Kind</strong><div>{['UNSPECIFIED', 'INTERNAL', 'SERVER', 'CLIENT', 'PRODUCER', 'CONSUMER'][t.kind] || t.kind}</div></div>
                                                        <div><strong style={{ fontSize: 11, textTransform: 'uppercase', color: '#888' }}>Duration</strong><div>{t.duration_ms?.toFixed(2)}ms</div></div>
                                                    </div>
                                                    {t.attributes && Object.keys(t.attributes).length > 0 && (
                                                        <div>
                                                            <strong style={{ fontSize: 11, textTransform: 'uppercase', color: '#888' }}>Attributes</strong>
                                                            <div style={{ marginTop: 4, display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '4px 16px' }}>
                                                                {Object.entries(t.attributes).map(([k, v]) => (
                                                                    <div key={k} style={{ fontSize: 12, padding: '2px 0' }}>
                                                                        <span style={{ color: '#7c3aed', fontFamily: 'monospace' }}>{k}</span>
                                                                        <span style={{ color: '#888', margin: '0 4px' }}>=</span>
                                                                        <span style={{ fontFamily: 'monospace' }}>{String(v)}</span>
                                                                    </div>
                                                                ))}
                                                            </div>
                                                        </div>
                                                    )}
                                                </td>
                                            </tr>
                                        )}
                                    </React.Fragment>
                                ))}</tbody>
                            </table>
                        )}
                    </div>
                )}

                {/* Logs Tab (Enhanced v5.1.0) */}
                {tab === 'logs' && (
                    <div className="card">
                        <div className="card-header">
                            <div><div className="card-title">Logs ({filteredLogs.length})</div><div className="card-subtitle">System logs from server</div></div>
                            <div style={{ display: 'flex', gap: 8 }}>
                                <select className="form-input" style={{ maxWidth: 120 }} value={logFilter} onChange={e => setLogFilter(e.target.value)}>
                                    <option value="">All Levels</option>
                                    <option value="critical">Critical</option>
                                    <option value="error">Error</option>
                                    <option value="warning">Warning</option>
                                    <option value="info">Info</option>
                                </select>
                                <button className="btn btn-secondary btn-sm" onClick={fetchData}>Refresh</button>
                            </div>
                        </div>
                        {filteredLogs.length === 0 ? (
                            <div className="empty-state"><div className="empty-state-icon">OK</div><div className="empty-state-text">No logs</div></div>
                        ) : (
                            <table className="data-table">
                                <thead><tr><th>Level</th><th>Source</th><th>Message</th><th>Time</th></tr></thead>
                                <tbody>{filteredLogs.map((l, i) => (
                                    <tr key={l.id || i}>
                                        <td><span className={`badge ${(l.log_level || l.level) === 'critical' ? 'error' : (l.log_level || l.level) === 'error' ? 'error' : (l.log_level || l.level) === 'warning' ? 'warning' : 'info'}`}>{l.log_level || l.level || '-'}</span></td>
                                        <td><span className="badge info">{l.namespace || l.source || '-'}</span></td>
                                        <td style={{ maxWidth: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{l.message}</td>
                                        <td>{timeAgo(l.timestamp || l.created_at)}</td>
                                    </tr>
                                ))}</tbody>
                            </table>
                        )}
                    </div>
                )}
            </div>
        </>
    );
}
