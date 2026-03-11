'use client';

import { useState, useEffect, useCallback } from 'react';
import { getAgents, getClusters } from '../lib/api';
import { timeAgo } from '../lib/hooks';

export default function AgentsPage() {
    const [data, setData] = useState(null);
    const [clusters, setClusters] = useState([]);
    const [loading, setLoading] = useState(true);
    const [search, setSearch] = useState('');
    const [filterCluster, setFilterCluster] = useState('');
    const [filterStatus, setFilterStatus] = useState('');
    const [viewMode, setViewMode] = useState('table'); // 'table' or 'grid'

    const fetchData = useCallback(async () => {
        try {
            const [agentResult, clusterResult] = await Promise.all([getAgents(), getClusters()]);
            setData(agentResult);
            setClusters(clusterResult?.clusters || []);
        } catch (err) { console.error(err); }
        finally { setLoading(false); }
    }, []);

    useEffect(() => {
        fetchData();
        const interval = setInterval(fetchData, 15000);
        return () => clearInterval(interval);
    }, [fetchData]);

    const allAgents = data?.agents || [];

    // Apply filters
    const filteredAgents = allAgents.filter(a => {
        if (search && !a.name?.toLowerCase().includes(search.toLowerCase()) && !a.hostname?.toLowerCase().includes(search.toLowerCase())) return false;
        if (filterCluster && a.cluster_id !== filterCluster) return false;
        if (filterStatus && a.status !== filterStatus) return false;
        return true;
    });

    // Group by cluster
    const grouped = {};
    filteredAgents.forEach(a => {
        const cid = a.cluster_id || 'default';
        if (!grouped[cid]) grouped[cid] = [];
        grouped[cid].push(a);
    });

    const clusterName = (id) => clusters.find(c => c.id === id)?.name || id || 'Default Cluster';

    return (
        <>
            <div className="main-header">
                <h2>Agents</h2>
                <div className="header-actions">
                    <button className={`btn ${viewMode === 'table' ? 'btn-primary' : 'btn-secondary'} btn-sm`} onClick={() => setViewMode('table')}>Table</button>
                    <button className={`btn ${viewMode === 'grid' ? 'btn-primary' : 'btn-secondary'} btn-sm`} onClick={() => setViewMode('grid')}>Grid</button>
                    <button className="btn btn-secondary btn-sm" onClick={fetchData}>Refresh</button>
                </div>
            </div>
            <div className="main-body">
                {/* Filters */}
                <div style={{ display: 'flex', gap: 12, marginBottom: 20, flexWrap: 'wrap' }}>
                    <input className="form-input" style={{ maxWidth: 260 }} placeholder="Search by name or hostname..." value={search} onChange={e => setSearch(e.target.value)} />
                    <select className="form-input" style={{ maxWidth: 180 }} value={filterCluster} onChange={e => setFilterCluster(e.target.value)}>
                        <option value="">All Clusters</option>
                        {clusters.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
                    </select>
                    <select className="form-input" style={{ maxWidth: 140 }} value={filterStatus} onChange={e => setFilterStatus(e.target.value)}>
                        <option value="">All Status</option>
                        <option value="active">Active</option>
                        <option value="inactive">Inactive</option>
                    </select>
                    <div style={{ marginLeft: 'auto', fontSize: 13, color: 'var(--text-muted)', alignSelf: 'center' }}>{filteredAgents.length} agent(s)</div>
                </div>

                {loading ? (
                    <div className="loading-overlay"><div className="loading-spinner" /><span>Loading agents...</span></div>
                ) : filteredAgents.length === 0 ? (
                    <div className="card"><div className="empty-state"><div className="empty-state-icon">--</div><div className="empty-state-text">No agents found</div><div className="empty-state-hint">Deploy agents or adjust your filters</div></div></div>
                ) : (
                    Object.entries(grouped).map(([clusterId, agents]) => (
                        <div key={clusterId} className="cluster-group">
                            <div className="cluster-group-header">
                                <div className="cluster-group-title">{clusterName(clusterId)}</div>
                                <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                                    <span className="badge active"><span className="badge-dot" />{agents.filter(a => a.status === 'active').length} active</span>
                                    {agents.filter(a => a.status !== 'active').length > 0 && (
                                        <span className="badge error"><span className="badge-dot" />{agents.filter(a => a.status !== 'active').length} down</span>
                                    )}
                                    <span className="badge info">{agents.length} total</span>
                                </div>
                            </div>

                            {viewMode === 'grid' ? (
                                <div className="agent-grid">
                                    {agents.map(agent => (
                                        <a key={agent.id} href={`/agents/${agent.id}`} className="agent-card">
                                            <div className="agent-card-header">
                                                <div className="agent-card-name">{agent.name}</div>
                                                <span className={`badge ${agent.status === 'active' ? 'active' : 'error'}`}><span className="badge-dot" />{agent.status}</span>
                                            </div>
                                            <div className="agent-card-info">
                                                <div><span className="agent-card-label">Type</span><span className="badge info">{agent.agent_type}</span></div>
                                                <div><span className="agent-card-label">Host</span><span style={{ fontFamily: 'monospace', fontSize: 12 }}>{agent.hostname || '-'}</span></div>
                                                <div><span className="agent-card-label">Heartbeat</span><span>{timeAgo(agent.last_heartbeat)}</span></div>
                                            </div>
                                        </a>
                                    ))}
                                </div>
                            ) : (
                                <div className="card" style={{ marginBottom: 0 }}>
                                    <table className="data-table">
                                        <thead><tr><th>Name</th><th>Type</th><th>Hostname</th><th>Status</th><th>Last Heartbeat</th><th>Created</th></tr></thead>
                                        <tbody>{agents.map(agent => (
                                            <tr key={agent.id} onClick={() => window.location.href = `/agents/${agent.id}`} style={{ cursor: 'pointer' }}>
                                                <td style={{ fontWeight: 600 }}>{agent.name}<div style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'monospace' }}>{agent.id?.slice(0, 12)}...</div></td>
                                                <td><span className="badge info">{agent.agent_type}</span></td>
                                                <td style={{ fontFamily: 'monospace', fontSize: 13 }}>{agent.hostname || '-'}</td>
                                                <td><span className={`badge ${agent.status === 'active' ? 'active' : 'error'}`}><span className="badge-dot" />{agent.status}</span></td>
                                                <td>{timeAgo(agent.last_heartbeat)}</td>
                                                <td style={{ fontSize: 13 }}>{agent.created_at?.slice(0, 10)}</td>
                                            </tr>
                                        ))}</tbody>
                                    </table>
                                </div>
                            )}
                        </div>
                    ))
                )}
            </div>
        </>
    );
}
