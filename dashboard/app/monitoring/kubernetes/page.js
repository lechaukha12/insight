'use client';

import { useState, useEffect, useCallback } from 'react';
import { getAgents, getClusters, getEvents } from '../../lib/api';
import { timeAgo } from '../../lib/hooks';

export default function KubernetesMonitoringPage() {
    const [agents, setAgents] = useState([]);
    const [clusters, setClusters] = useState([]);
    const [events, setEvents] = useState([]);
    const [loading, setLoading] = useState(true);
    const [selectedCluster, setSelectedCluster] = useState('');

    const fetchData = useCallback(async () => {
        try {
            const [agentResult, clusterResult, eventResult] = await Promise.all([
                getAgents(),
                getClusters(),
                getEvents({ last_hours: 24, limit: 50 }),
            ]);
            const k8sAgents = (agentResult?.agents || []).filter(a => {
                const cat = a.agent_category || (a.agent_type === 'kubernetes' ? 'kubernetes' : null);
                return cat === 'kubernetes' || a.agent_type === 'kubernetes';
            });
            setAgents(k8sAgents);
            setClusters(clusterResult?.clusters || []);
            setEvents(eventResult?.events || []);
        } catch (err) { console.error(err); }
        finally { setLoading(false); }
    }, []);

    useEffect(() => {
        fetchData();
        const interval = setInterval(fetchData, 30000);
        return () => clearInterval(interval);
    }, [fetchData]);

    const filteredAgents = selectedCluster ? agents.filter(a => a.cluster_id === selectedCluster) : agents;
    const filteredEvents = events.filter(e => {
        const isK8sEvent = agents.some(a => a.id === e.agent_id);
        if (!isK8sEvent) return false;
        if (selectedCluster) {
            const agent = agents.find(a => a.id === e.agent_id);
            return agent && agent.cluster_id === selectedCluster;
        }
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

    let totalNodes = 0, totalNamespaces = 0, totalPods = 0, totalServices = 0, totalWarnings = 0;
    filteredAgents.forEach(a => {
        totalNodes += getMetricValue(a, 'k8s_node_count') || 0;
        totalNamespaces += getMetricValue(a, 'k8s_namespace_count') || 0;
        totalPods += getMetricValue(a, 'k8s_pod_count') || 0;
        totalServices += getMetricValue(a, 'k8s_service_count') || 0;
        totalWarnings += getMetricValue(a, 'k8s_warning_event_count') || 0;
    });

    const onlineAgents = filteredAgents.filter(a => getStatus(a) === 'online').length;
    const warningEvents = filteredEvents.filter(e => e.level === 'warning' || e.level === 'error' || e.level === 'critical');

    if (loading) return (
        <>
            <div className="main-header"><h2>Kubernetes Monitoring</h2></div>
            <div className="main-body"><div className="loading-overlay"><div className="loading-spinner" /><span>Loading K8s clusters...</span></div></div>
        </>
    );

    return (
        <>
            {/* Header */}
            <div className="main-header">
                <h2>Kubernetes Monitoring</h2>
                <div className="header-actions">
                    {clusters.length > 0 && (
                        <select className="form-input" value={selectedCluster} onChange={e => setSelectedCluster(e.target.value)}
                            style={{ width: 240, padding: '8px 14px', fontSize: 13 }}>
                            <option value="">All Clusters ({agents.length} agents)</option>
                            {clusters.map(c => (
                                <option key={c.id} value={c.id}>{c.name} ({agents.filter(a => a.cluster_id === c.id).length})</option>
                            ))}
                        </select>
                    )}
                </div>
            </div>

            {/* Body */}
            <div className="main-body">
                {filteredAgents.length === 0 ? (
                    <div className="card">
                        <div className="empty-state">
                            <div className="empty-state-icon">K8S</div>
                            <div className="empty-state-text">No Kubernetes agents found</div>
                            <p style={{ color: 'var(--text-muted)', fontSize: 13, marginTop: 8 }}>Deploy a K8s Agent in your cluster to start monitoring.</p>
                        </div>
                    </div>
                ) : (
                    <>
                        {/* Cluster Overview Stats */}
                        <div className="stats-grid" style={{ gridTemplateColumns: 'repeat(5, 1fr)' }}>
                            {[
                                { label: 'Nodes', value: totalNodes, icon: 'NO', color: '#0ea5e9' },
                                { label: 'Namespaces', value: totalNamespaces, icon: 'NS', color: '#7c3aed' },
                                { label: 'Pods', value: totalPods, icon: 'PO', color: '#22c55e' },
                                { label: 'Services', value: totalServices, icon: 'SV', color: '#f59e0b' },
                                { label: 'Warnings', value: totalWarnings, icon: 'WA', color: totalWarnings > 0 ? '#ef4444' : '#22c55e' },
                            ].map(s => (
                                <div key={s.label} className="stat-card">
                                    <div className="stat-icon" style={{ background: s.color + '18', color: s.color }}>{s.icon}</div>
                                    <div className="stat-info">
                                        <div className="stat-value">{s.value}</div>
                                        <div className="stat-label">{s.label}</div>
                                    </div>
                                </div>
                            ))}
                        </div>

                        {/* Agents Table */}
                        <div className="card" style={{ marginBottom: 24 }}>
                            <div className="card-header">
                                <div>
                                    <div className="card-title">K8s Agents ({filteredAgents.length})</div>
                                    <div className="card-subtitle">{onlineAgents} online, {filteredAgents.length - onlineAgents} offline</div>
                                </div>
                            </div>
                            <table className="data-table">
                                <thead><tr>
                                    <th>Agent Name</th>
                                    <th>Cluster</th>
                                    <th style={{ textAlign: 'center' }}>Nodes</th>
                                    <th style={{ textAlign: 'center' }}>Pods</th>
                                    <th>Status</th>
                                    <th>Last Heartbeat</th>
                                </tr></thead>
                                <tbody>
                                    {filteredAgents.map(a => (
                                        <tr key={a.id}>
                                            <td>
                                                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                                                    <div style={{
                                                        width: 36, height: 36, borderRadius: 'var(--radius-sm)',
                                                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                                                        background: 'rgba(1,101,167,0.1)', color: 'var(--blue)', fontWeight: 800, fontSize: 12
                                                    }}>K8S</div>
                                                    <span style={{ fontWeight: 600 }}>{a.name}</span>
                                                </div>
                                            </td>
                                            <td><span className="badge info">{clusters.find(c => c.id === a.cluster_id)?.name || a.cluster_id}</span></td>
                                            <td style={{ textAlign: 'center', fontWeight: 600 }}>{getMetricValue(a, 'k8s_node_count') || 0}</td>
                                            <td style={{ textAlign: 'center', fontWeight: 600 }}>{getMetricValue(a, 'k8s_pod_count') || 0}</td>
                                            <td>
                                                <span className={`badge ${getStatus(a) === 'online' ? 'active' : 'inactive'}`}>
                                                    <span className="badge-dot" />{getStatus(a)}
                                                </span>
                                            </td>
                                            <td style={{ fontSize: 12, color: 'var(--text-muted)' }}>{a.last_heartbeat ? timeAgo(a.last_heartbeat) : 'never'}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>

                        {/* Recent K8s Events */}
                        <div className="card">
                            <div className="card-header">
                                <div>
                                    <div className="card-title">Recent Cluster Events</div>
                                    <div className="card-subtitle">{warningEvents.length} warnings / errors in last 24h</div>
                                </div>
                            </div>
                            {warningEvents.length > 0 ? (
                                <div style={{ maxHeight: 400, overflow: 'auto' }}>
                                    {warningEvents.slice(0, 20).map((e, i) => (
                                        <div key={i} className="event-item">
                                            <div className={`event-icon ${e.level}`}>
                                                {e.level === 'critical' ? 'C' : e.level === 'error' ? 'E' : 'W'}
                                            </div>
                                            <div className="event-content">
                                                <div className="event-title">{e.title}</div>
                                                <div className="event-message">
                                                    {e.namespace && <span className="badge info" style={{ marginRight: 6, fontSize: 10, padding: '2px 8px' }}>{e.namespace}</span>}
                                                    {e.message || e.resource || '--'}
                                                </div>
                                            </div>
                                            <div className="event-time">{timeAgo(e.created_at)}</div>
                                        </div>
                                    ))}
                                </div>
                            ) : (
                                <div className="empty-state" style={{ padding: 40 }}>
                                    <div className="empty-state-text" style={{ color: 'var(--color-success)' }}>No warnings or errors in the last 24 hours</div>
                                </div>
                            )}
                        </div>
                    </>
                )}
            </div>
        </>
    );
}
