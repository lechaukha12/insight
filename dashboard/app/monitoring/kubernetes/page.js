'use client';

import { useState, useEffect, useCallback } from 'react';
import { getAgents } from '../../lib/api';
import { useTimeRange } from '../../lib/TimeRangeContext';
import { timeAgo } from '../../lib/hooks';
import { useRouter } from 'next/navigation';

export default function KubernetesMonitoringPage() {
    const [agents, setAgents] = useState([]);
    const [loading, setLoading] = useState(true);
    const [viewMode, setViewMode] = useState('grid');
    const { queryParams, isLive } = useTimeRange();
    const router = useRouter();

    const fetchData = useCallback(async () => {
        try {
            const result = await getAgents(queryParams);
            const k8sAgents = (result?.agents || []).filter(a => {
                const cat = a.agent_category || (a.agent_type === 'kubernetes' ? 'kubernetes' : null);
                return cat === 'kubernetes' || a.agent_type === 'kubernetes';
            });
            setAgents(k8sAgents);
        } catch (err) { console.error(err); }
        finally { setLoading(false); }
    }, [queryParams]);

    useEffect(() => {
        fetchData();
        if (isLive) {
            const interval = setInterval(fetchData, 30000);
            return () => clearInterval(interval);
        }
    }, [fetchData, isLive]);

    const getStatus = (a) => {
        if (!a.last_heartbeat) return 'offline';
        const diff = (Date.now() - new Date(a.last_heartbeat + 'Z').getTime()) / 1000;
        return diff < 120 ? 'online' : 'offline';
    };

    const getMetricValue = (a, name) => {
        const m = a.latest_metrics?.find(m => m.metric_name === name);
        return m ? m.metric_value : 0;
    };

    if (loading) return (
        <>
            <div className="main-header"><h2>Kubernetes Monitoring</h2></div>
            <div className="main-body"><div className="loading-overlay"><div className="loading-spinner" /><span>Loading K8s agents...</span></div></div>
        </>
    );

    return (
        <>
            <div className="main-header">
                <h2>Kubernetes Monitoring</h2>
                <div className="header-actions">
                    <div style={{ display: 'flex', gap: 4, background: 'var(--bg-input)', borderRadius: 6, padding: 2 }}>
                        {['grid', 'list'].map(m => (
                            <button key={m} onClick={() => setViewMode(m)}
                                style={{
                                    padding: '5px 12px', border: 'none', borderRadius: 4, cursor: 'pointer',
                                    fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: 0.5,
                                    background: viewMode === m ? 'var(--blue)' : 'transparent',
                                    color: viewMode === m ? '#fff' : 'var(--text-muted)',
                                    transition: 'all 0.15s',
                                }}>
                                {m === 'grid' ? '⊞ Grid' : '☰ List'}
                            </button>
                        ))}
                    </div>
                </div>
            </div>

            <div className="main-body">
                {agents.length === 0 ? (
                    <div className="card">
                        <div className="empty-state">
                            <div className="empty-state-icon">K8S</div>
                            <div className="empty-state-text">No Kubernetes agents found</div>
                            <p style={{ color: 'var(--text-muted)', fontSize: 13, marginTop: 8 }}>Deploy a K8s Agent in your cluster to start monitoring.</p>
                        </div>
                    </div>
                ) : viewMode === 'grid' ? (
                    /* GRID VIEW */
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 16 }}>
                        {agents.map(a => {
                            const status = getStatus(a);
                            const nodes = getMetricValue(a, 'k8s_node_count');
                            const pods = getMetricValue(a, 'k8s_pod_count');
                            const nss = getMetricValue(a, 'k8s_namespace_count');
                            const warnings = getMetricValue(a, 'k8s_warning_event_count');
                            return (
                                <div key={a.id} className="card" onClick={() => router.push(`/monitoring/kubernetes/${a.id}`)}
                                    style={{ cursor: 'pointer', transition: 'transform 0.15s, box-shadow 0.15s' }}
                                    onMouseEnter={e => { e.currentTarget.style.transform = 'translateY(-2px)'; e.currentTarget.style.boxShadow = 'var(--shadow-lg)'; }}
                                    onMouseLeave={e => { e.currentTarget.style.transform = ''; e.currentTarget.style.boxShadow = ''; }}
                                >
                                    <div style={{ padding: '20px 24px' }}>
                                        {/* Header */}
                                        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
                                            <div style={{
                                                width: 48, height: 48, borderRadius: 10,
                                                background: 'linear-gradient(135deg, rgba(1,101,167,0.15), rgba(14,165,233,0.1))',
                                                display: 'flex', alignItems: 'center', justifyContent: 'center',
                                                fontSize: 16, fontWeight: 900, color: 'var(--blue)', letterSpacing: -0.5,
                                            }}>K8S</div>
                                            <div style={{ flex: 1 }}>
                                                <div style={{ fontWeight: 700, fontSize: 15, color: 'var(--text-primary)' }}>{a.name}</div>
                                                <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>
                                                    {a.cluster_id || 'default'} • {a.version || ''}
                                                </div>
                                            </div>
                                            <span className={`badge ${status === 'online' ? 'active' : 'inactive'}`}>
                                                <span className="badge-dot" />{status}
                                            </span>
                                        </div>

                                        {/* Stats */}
                                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 8 }}>
                                            {[
                                                { label: 'Nodes', value: nodes, color: '#0ea5e9' },
                                                { label: 'Pods', value: pods, color: '#22c55e' },
                                                { label: 'NS', value: nss, color: '#7c3aed' },
                                                { label: 'Warns', value: warnings, color: warnings > 0 ? '#ef4444' : '#22c55e' },
                                            ].map(s => (
                                                <div key={s.label} style={{
                                                    textAlign: 'center', padding: '8px 4px', borderRadius: 6,
                                                    background: s.color + '10',
                                                }}>
                                                    <div style={{ fontSize: 18, fontWeight: 800, color: s.color }}>{s.value}</div>
                                                    <div style={{ fontSize: 9, fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: 0.5 }}>{s.label}</div>
                                                </div>
                                            ))}
                                        </div>

                                        {/* Footer */}
                                        <div style={{ marginTop: 12, fontSize: 11, color: 'var(--text-muted)', display: 'flex', justifyContent: 'space-between' }}>
                                            <span>Last heartbeat: {a.last_heartbeat ? timeAgo(a.last_heartbeat) : 'never'}</span>
                                            <span style={{ color: 'var(--blue)', fontWeight: 600 }}>View →</span>
                                        </div>
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                ) : (
                    /* LIST VIEW */
                    <div className="card">
                        <table className="data-table">
                            <thead><tr>
                                <th>Agent Name</th>
                                <th>Cluster</th>
                                <th style={{ textAlign: 'center' }}>Nodes</th>
                                <th style={{ textAlign: 'center' }}>Pods</th>
                                <th style={{ textAlign: 'center' }}>Warnings</th>
                                <th>Status</th>
                                <th>Last Heartbeat</th>
                            </tr></thead>
                            <tbody>
                                {agents.map(a => (
                                    <tr key={a.id} style={{ cursor: 'pointer' }} onClick={() => router.push(`/monitoring/kubernetes/${a.id}`)}>
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
                                        <td><span className="badge info">{a.cluster_id || 'default'}</span></td>
                                        <td style={{ textAlign: 'center', fontWeight: 600 }}>{getMetricValue(a, 'k8s_node_count')}</td>
                                        <td style={{ textAlign: 'center', fontWeight: 600 }}>{getMetricValue(a, 'k8s_pod_count')}</td>
                                        <td style={{ textAlign: 'center', fontWeight: 600, color: getMetricValue(a, 'k8s_warning_event_count') > 0 ? 'var(--color-error)' : 'var(--text-muted)' }}>
                                            {getMetricValue(a, 'k8s_warning_event_count')}
                                        </td>
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
                )}
            </div>
        </>
    );
}
