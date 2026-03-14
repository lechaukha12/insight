'use client';

import { useState, useEffect, useCallback } from 'react';
import { getAgents, getClusters, getProcesses } from '../../lib/api';
import { useTimeRange } from '../../lib/TimeRangeContext';
import { timeAgo } from '../../lib/hooks';

export default function SystemMonitoringPage() {
    const [agents, setAgents] = useState([]);
    const [clusters, setClusters] = useState([]);
    const [loading, setLoading] = useState(true);
    const [search, setSearch] = useState('');
    const [filterCluster, setFilterCluster] = useState('');
    const [selectedAgent, setSelectedAgent] = useState(null);
    const [agentProcesses, setAgentProcesses] = useState(null);
    const [processLoading, setProcessLoading] = useState(false);
    const { queryParams, isLive } = useTimeRange();

    const fetchData = useCallback(async () => {
        try {
            const [agentResult, clusterResult] = await Promise.all([getAgents(queryParams), getClusters()]);
            const systemAgents = (agentResult?.agents || []).filter(a => {
                const cat = a.agent_category || (a.agent_type === 'opentelemetry' || a.agent_type === 'collector' ? 'application' : a.agent_type === 'kubernetes' ? 'kubernetes' : 'system');
                return cat === 'system';
            });
            setAgents(systemAgents);
            setClusters(clusterResult?.clusters || []);
        } catch (err) { console.error(err); }
        finally { setLoading(false); }
    }, [queryParams]);

    useEffect(() => {
        fetchData();
        if (isLive) {
            const interval = setInterval(fetchData, 15000);
            return () => clearInterval(interval);
        }
    }, [fetchData, isLive]);

    const openAgent = async (agent) => {
        setSelectedAgent(agent);
        setProcessLoading(true);
        try {
            const data = await getProcesses(agent.id);
            setAgentProcesses(data);
        } catch { setAgentProcesses(null); }
        finally { setProcessLoading(false); }
    };

    const filtered = agents.filter(a => {
        if (search && !a.name?.toLowerCase().includes(search.toLowerCase()) && !a.hostname?.toLowerCase().includes(search.toLowerCase())) return false;
        if (filterCluster && a.cluster_id !== filterCluster) return false;
        return true;
    });

    const getStatus = (a) => {
        if (!a.last_heartbeat) return 'offline';
        const diff = (Date.now() - new Date(a.last_heartbeat + 'Z').getTime()) / 1000;
        return diff < 120 ? 'online' : 'offline';
    };

    const getMetricValue = (a, name) => {
        const m = a.latest_metrics?.find(m => m.metric_name === name);
        return m ? m.metric_value : null;
    };

    const onlineCount = agents.filter(a => getStatus(a) === 'online').length;
    const offlineCount = agents.length - onlineCount;

    if (loading) return (
        <>
            <div className="main-header"><h2>System Monitoring</h2></div>
            <div className="main-body"><div className="loading-overlay"><div className="loading-spinner" /><span>Loading system agents...</span></div></div>
        </>
    );

    return (
        <>
            {/* Header — same as Dashboard */}
            <div className="main-header">
                <h2>System Monitoring</h2>
                <div className="header-actions">
                    <input className="form-input" placeholder="Search agents..."
                        value={search} onChange={e => setSearch(e.target.value)}
                        style={{ width: 220, padding: '8px 14px', fontSize: 13 }} />
                    {clusters.length > 1 && (
                        <select className="form-input" value={filterCluster} onChange={e => setFilterCluster(e.target.value)} style={{ width: 180, padding: '8px 14px', fontSize: 13 }}>
                            <option value="">All Clusters</option>
                            {clusters.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
                        </select>
                    )}
                </div>
            </div>

            {/* Body — same padding as Dashboard */}
            <div className="main-body">
                {/* Summary Stats */}
                <div className="stats-grid" style={{ gridTemplateColumns: 'repeat(3, 1fr)' }}>
                    <div className="stat-card">
                        <div className="stat-icon agents">SYS</div>
                        <div className="stat-info">
                            <div className="stat-value">{agents.length}</div>
                            <div className="stat-label">Total Agents</div>
                        </div>
                    </div>
                    <div className="stat-card">
                        <div className="stat-icon active">ON</div>
                        <div className="stat-info">
                            <div className="stat-value" style={{ color: 'var(--color-success)' }}>{onlineCount}</div>
                            <div className="stat-label">Online</div>
                        </div>
                    </div>
                    <div className="stat-card">
                        <div className="stat-icon" style={{ background: offlineCount > 0 ? 'var(--color-error-bg)' : 'rgba(100,116,139,0.1)', color: offlineCount > 0 ? 'var(--color-error)' : '#64748b' }}>OFF</div>
                        <div className="stat-info">
                            <div className="stat-value" style={{ color: offlineCount > 0 ? 'var(--color-error)' : 'var(--text-muted)' }}>{offlineCount}</div>
                            <div className="stat-label">Offline</div>
                        </div>
                    </div>
                </div>

                {/* Agent Cards */}
                {filtered.length === 0 ? (
                    <div className="card">
                        <div className="empty-state">
                            <div className="empty-state-icon">SYS</div>
                            <div className="empty-state-text">No system agents found</div>
                            <p style={{ color: 'var(--text-muted)', fontSize: 13, marginTop: 8 }}>Deploy a System Agent on your servers to start monitoring.</p>
                        </div>
                    </div>
                ) : (
                    <div className="grid-2">
                        {filtered.map(agent => {
                            const status = getStatus(agent);
                            const cpu = getMetricValue(agent, 'cpu_percent');
                            const mem = getMetricValue(agent, 'memory_percent');
                            const diskUsed = getMetricValue(agent, 'disk_percent');
                            const netSent = getMetricValue(agent, 'network_bytes_sent');
                            const netRecv = getMetricValue(agent, 'network_bytes_recv');
                            const uptime = getMetricValue(agent, 'uptime_seconds');

                            return (
                                <div key={agent.id} className="card" style={{ cursor: 'pointer' }}
                                    onClick={() => openAgent(agent)}>
                                    <div className="card-header">
                                        <div>
                                            <div className="card-title">{agent.name || agent.hostname}</div>
                                            <div className="card-subtitle">{agent.hostname} · {agent.cluster_id || 'default'}</div>
                                            <div style={{ display: 'flex', gap: 6, marginTop: 6, flexWrap: 'wrap' }}>
                                                {agent.agent_version && <span className="badge info" style={{ fontSize: 10 }}>v{agent.agent_version}</span>}
                                                {agent.os_info && <span className="badge" style={{ fontSize: 10, background: 'rgba(100,116,139,0.1)', color: '#64748b' }}>{agent.os_info}</span>}
                                            </div>
                                        </div>
                                        <span className={`badge ${status === 'online' ? 'active' : 'inactive'}`}>
                                            <span className="badge-dot" />{status}
                                        </span>
                                    </div>

                                    {/* Metric Bars */}
                                    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                                        {[
                                            { label: 'CPU', value: cpu, unit: '%', thresholds: [70, 90] },
                                            { label: 'RAM', value: mem, unit: '%', thresholds: [70, 90] },
                                            { label: 'Disk', value: diskUsed, unit: '%', thresholds: [80, 95] },
                                        ].map(m => (
                                            <div key={m.label}>
                                                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                                                    <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)' }}>{m.label}</span>
                                                    <span style={{
                                                        fontSize: 13, fontWeight: 700,
                                                        color: m.value == null ? 'var(--text-muted)' : m.value > m.thresholds[1] ? 'var(--color-error)' : m.value > m.thresholds[0] ? 'var(--color-warning)' : 'var(--color-success)'
                                                    }}>
                                                        {m.value != null ? `${m.value.toFixed(1)}${m.unit}` : '--'}
                                                    </span>
                                                </div>
                                                <div style={{ height: 6, background: 'rgba(0,0,0,0.06)', borderRadius: 3, overflow: 'hidden' }}>
                                                    <div style={{
                                                        height: '100%', borderRadius: 3, transition: 'width 0.6s ease',
                                                        width: m.value != null ? `${Math.min(m.value, 100)}%` : '0%',
                                                        background: m.value == null ? 'transparent' : m.value > m.thresholds[1] ? 'var(--color-error)' : m.value > m.thresholds[0] ? 'var(--color-warning)' : 'var(--color-success)',
                                                    }} />
                                                </div>
                                            </div>
                                        ))}
                                    </div>

                                    {/* Footer Stats */}
                                    <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 16, paddingTop: 12, borderTop: '1px solid var(--border-color)', fontSize: 12, color: 'var(--text-muted)' }}>
                                        <span>Net: {netSent != null ? `${(netSent / 1e9).toFixed(1)} GB` : '--'} / {netRecv != null ? `${(netRecv / 1e9).toFixed(1)} GB` : '--'}</span>
                                        <span>Uptime: {uptime != null ? `${Math.floor(uptime / 86400)}d ${Math.floor((uptime % 86400) / 3600)}h` : '--'}</span>
                                    </div>
                                    <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 6 }}>
                                        Last seen: {agent.last_heartbeat ? timeAgo(agent.last_heartbeat) : 'never'}
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                )}
            </div>

            {/* Process Detail Modal */}
            {selectedAgent && (
                <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.45)', backdropFilter: 'blur(4px)', zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24 }}
                    onClick={() => setSelectedAgent(null)}>
                    <div className="card" style={{ maxWidth: 900, width: '100%', maxHeight: '80vh', overflow: 'auto', boxShadow: 'var(--shadow-lg)' }}
                        onClick={e => e.stopPropagation()}>
                        <div className="card-header">
                            <div>
                                <div className="card-title">{selectedAgent.name}</div>
                                <div className="card-subtitle">{selectedAgent.hostname} — Process List (Top 30 by CPU)</div>
                            </div>
                            <button className="btn btn-secondary btn-sm" onClick={() => setSelectedAgent(null)}>Close</button>
                        </div>
                        {processLoading ? (
                            <div className="loading-overlay"><div className="loading-spinner" /><span>Loading processes...</span></div>
                        ) : agentProcesses?.processes?.length > 0 ? (
                            <table className="data-table">
                                <thead><tr>
                                    <th>PID</th><th>Process Name</th><th>CPU %</th><th>MEM %</th><th>Memory</th><th>Status</th>
                                </tr></thead>
                                <tbody>
                                    {agentProcesses.processes.sort((a, b) => (b.cpu_percent || 0) - (a.cpu_percent || 0)).slice(0, 30).map((p, i) => (
                                        <tr key={i}>
                                            <td style={{ fontFamily: 'monospace', fontSize: 12, color: 'var(--text-muted)' }}>{p.pid}</td>
                                            <td style={{ fontWeight: 600, maxWidth: 220, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{p.name}</td>
                                            <td><span style={{ fontWeight: 700, color: p.cpu_percent > 50 ? 'var(--color-error)' : p.cpu_percent > 20 ? 'var(--color-warning)' : 'var(--color-success)' }}>{p.cpu_percent?.toFixed(1)}%</span></td>
                                            <td><span style={{ fontWeight: 600, color: p.memory_percent > 50 ? 'var(--color-error)' : 'var(--text-secondary)' }}>{p.memory_percent?.toFixed(1)}%</span></td>
                                            <td style={{ fontSize: 13, color: 'var(--text-muted)' }}>{p.memory_mb ? `${p.memory_mb.toFixed(0)} MB` : '--'}</td>
                                            <td><span className={`badge ${p.status === 'running' || !p.status ? 'active' : 'inactive'}`}>{p.status || 'running'}</span></td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        ) : (
                            <div className="empty-state" style={{ padding: 40 }}>
                                <div className="empty-state-text">No process data available</div>
                            </div>
                        )}
                    </div>
                </div>
            )}
        </>
    );
}
