'use client';

import { useState, useEffect, useCallback } from 'react';
import { useParams } from 'next/navigation';
import { getAgent, getMetrics, getEvents, getLogs } from '../../lib/api';
import { timeAgo } from '../../lib/hooks';
import { MetricsLineChart } from '../../components/Charts';

export default function AgentDetailPage() {
    const params = useParams();
    const agentId = params.id;
    const [agent, setAgent] = useState(null);
    const [events, setEvents] = useState([]);
    const [logs, setLogs] = useState([]);
    const [loading, setLoading] = useState(true);
    const [tab, setTab] = useState('metrics');

    const fetchData = useCallback(async () => {
        try {
            const [agentData, eventsData, logsData] = await Promise.all([
                getAgent(agentId),
                getEvents({ agent_id: agentId, last_hours: 48, limit: 50 }),
                getLogs({ agent_id: agentId, last_hours: 48, limit: 50 }),
            ]);
            setAgent(agentData);
            setEvents(eventsData?.events || []);
            setLogs(logsData?.logs || []);
        } catch (err) {
            console.error('Error loading agent:', err);
        } finally {
            setLoading(false);
        }
    }, [agentId]);

    useEffect(() => { fetchData(); }, [fetchData]);

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
                    <div className="stat-card"><div className="stat-icon agents">ID</div><div className="stat-info"><div className="stat-label">Agent ID</div><div style={{ fontSize: 13, wordBreak: 'break-all' }}>{agent.id}</div></div></div>
                    <div className="stat-card"><div className="stat-icon active">T</div><div className="stat-info"><div className="stat-value">{agent.agent_type}</div><div className="stat-label">Type</div></div></div>
                    <div className="stat-card"><div className="stat-icon warnings">H</div><div className="stat-info"><div className="stat-value">{agent.hostname || '-'}</div><div className="stat-label">Hostname</div></div></div>
                    <div className="stat-card"><div className="stat-icon critical">L</div><div className="stat-info"><div className="stat-value">{timeAgo(agent.last_heartbeat)}</div><div className="stat-label">Last Heartbeat</div></div></div>
                </div>

                {/* Tabs */}
                <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
                    {['metrics', 'events', 'logs'].map(t => (
                        <button key={t} className={`btn ${tab === t ? 'btn-primary' : 'btn-secondary'}`} onClick={() => setTab(t)}>
                            {t.charAt(0).toUpperCase() + t.slice(1)}
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

                {/* Logs Tab */}
                {tab === 'logs' && (
                    <div className="card">
                        <div className="card-header"><div><div className="card-title">Error Logs ({logs.length})</div></div></div>
                        {logs.length === 0 ? (
                            <div className="empty-state"><div className="empty-state-icon">OK</div><div className="empty-state-text">No error logs</div></div>
                        ) : (
                            <table className="data-table">
                                <thead><tr><th>Namespace</th><th>Pod</th><th>Message</th><th>Time</th></tr></thead>
                                <tbody>{logs.map((l, i) => (
                                    <tr key={l.id || i}>
                                        <td><span className="badge info">{l.namespace || '-'}</span></td>
                                        <td style={{ fontWeight: 500 }}>{l.pod_name || '-'}</td>
                                        <td style={{ maxWidth: 400, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{l.message}</td>
                                        <td>{timeAgo(l.timestamp)}</td>
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
