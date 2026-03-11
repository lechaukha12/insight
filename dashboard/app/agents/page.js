'use client';

import { useState, useEffect, useCallback } from 'react';
import { getAgents } from '../lib/api';
import { timeAgo } from '../lib/hooks';

export default function AgentsPage() {
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(true);

    const fetchData = useCallback(async () => {
        try {
            const result = await getAgents();
            setData(result);
        } catch (err) {
            console.error(err);
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        fetchData();
        const interval = setInterval(fetchData, 10000);
        return () => clearInterval(interval);
    }, [fetchData]);

    const agents = data?.agents || [];

    return (
        <>
            <div className="main-header">
                <h2>Agents</h2>
                <div className="header-actions">
                    <button className="btn btn-secondary" onClick={fetchData}>Refresh</button>
                </div>
            </div>
            <div className="main-body">
                {loading ? (
                    <div className="loading-overlay"><div className="loading-spinner" /><span>Loading agents...</span></div>
                ) : agents.length === 0 ? (
                    <div className="empty-state">
                        <div className="empty-state-icon">--</div>
                        <div className="empty-state-text">No agents registered yet</div>
                        <p style={{ color: 'var(--text-muted)', fontSize: '14px', maxWidth: '400px', margin: '8px auto' }}>
                            Deploy an Insight agent on your K8s cluster, Linux server, or Windows machine to start monitoring.
                        </p>
                    </div>
                ) : (
                    <div className="card">
                        <table className="data-table">
                            <thead>
                                <tr>
                                    <th>Name</th><th>Type</th><th>Hostname</th>
                                    <th>Status</th><th>Last Heartbeat</th><th>Created</th>
                                </tr>
                            </thead>
                            <tbody>
                                {agents.map(agent => (
                                    <tr key={agent.id}>
                                        <td style={{ color: 'var(--text-primary)', fontWeight: 600 }}>
                                            {agent.name}
                                            <div style={{ fontSize: '11px', color: 'var(--text-muted)', fontFamily: 'monospace' }}>{agent.id?.slice(0, 8)}...</div>
                                        </td>
                                        <td><span className="badge info">{agent.agent_type}</span></td>
                                        <td style={{ fontFamily: 'monospace', fontSize: '13px' }}>{agent.hostname || '—'}</td>
                                        <td>
                                            <span className={`badge ${agent.status === 'active' ? 'active' : 'error'}`}>
                                                <span className="badge-dot" />
                                                {agent.status}
                                            </span>
                                        </td>
                                        <td>{timeAgo(agent.last_heartbeat)}</td>
                                        <td style={{ fontSize: '13px' }}>{agent.created_at?.slice(0, 10)}</td>
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
