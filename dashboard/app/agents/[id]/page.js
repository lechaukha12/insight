'use client';

import { useState, useEffect, useCallback } from 'react';
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

    const fetchData = useCallback(async () => {
        try {
            const [agentData, eventsData, logsData, procData, tracesData] = await Promise.all([
                getAgent(agentId),
                getEvents({ agent_id: agentId, last_hours: 48, limit: 50 }),
                getLogs({ agent_id: agentId, last_hours: 48, limit: 50 }),
                getProcesses(agentId).catch(() => ({ processes: [], timestamp: null })),
                getTraces({ agent_id: agentId, last_hours: 24, limit: 100 }).catch(() => ({ traces: [] })),
            ]);
            setAgent(agentData);
            setEvents(eventsData?.events || []);
            setLogs(logsData?.logs || []);
            setProcesses(procData?.processes || []);
            setProcessTimestamp(procData?.timestamp);
            setTraces(tracesData?.traces || []);
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
        ? logs.filter(l => l.level === logFilter)
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
                        {traces.length === 0 ? (
                            <div className="empty-state"><div className="empty-state-icon">--</div><div className="empty-state-text">No traces</div><div className="empty-state-hint">Send OTLP data to this agent's OTLP endpoint</div></div>
                        ) : (
                            <table className="data-table">
                                <thead><tr><th>Service</th><th>Span</th><th>Status</th><th>Duration</th><th>Trace ID</th><th>Time</th></tr></thead>
                                <tbody>{traces.map((t, i) => (
                                    <tr key={t.id || i}>
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
                                        <td><span className={`badge ${l.level === 'critical' ? 'error' : l.level === 'error' ? 'error' : l.level === 'warning' ? 'warning' : 'info'}`}>{l.level}</span></td>
                                        <td><span className="badge info">{l.source || l.namespace || '-'}</span></td>
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
