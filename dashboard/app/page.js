'use client';

import { useState, useEffect, useCallback } from 'react';
import { getDashboardSummary, generateReport, getTraceSummary } from './lib/api';
import { useWebSocket } from './lib/useWebSocket';
import { useTimeRange } from './lib/TimeRangeContext';
import { timeAgo } from './lib/hooks';
import { MetricsLineChart, EventsBarChart, HealthDonut } from './components/Charts';
import ClusterSelector from './components/ClusterSelector';

const levelIcons = { critical: 'C', error: 'E', warning: 'W', info: 'I' };

export default function DashboardPage() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [clusterId, setClusterId] = useState(null);
  const [sending, setSending] = useState(false);
  const [wsFlash, setWsFlash] = useState(null);
  const [traceSummary, setTraceSummary] = useState(null);
  const { queryParams, isLive } = useTimeRange();

  const WS_URL = typeof window !== 'undefined' ? `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}/ws/dashboard` : '';
  const { lastMessage, isConnected } = useWebSocket(WS_URL);

  const fetchData = useCallback(async () => {
    try {
      const [result, traceData] = await Promise.all([
        getDashboardSummary(clusterId, queryParams),
        getTraceSummary(1).catch(() => null),
      ]);
      setData(result);
      if (traceData) setTraceSummary(traceData);
    } catch (err) { console.error(err); }
    finally { setLoading(false); }
  }, [clusterId, queryParams]);

  // Initial and periodic fetch (only auto-refresh in live mode)
  useEffect(() => {
    fetchData();
    if (isLive) {
      const i = setInterval(fetchData, 15000);
      return () => clearInterval(i);
    }
  }, [fetchData, isLive]);

  // WebSocket-driven refresh
  useEffect(() => {
    if (lastMessage) {
      if (lastMessage.type === 'metrics' || lastMessage.type === 'events') {
        fetchData();
        setWsFlash(lastMessage.type);
        setTimeout(() => setWsFlash(null), 1500);
      }
    }
  }, [lastMessage, fetchData]);

  const handleSendReport = async () => {
    if (sending) return;
    setSending(true);
    try { await generateReport(['telegram']); } catch (e) { console.error(e); }
    finally { setSending(false); }
  };

  const handleClusterChange = (id) => {
    setClusterId(id);
    setLoading(true);
  };

  const summary = data?.summary || {};
  const agents = data?.agents || [];
  const events = data?.recent_events || [];
  const clusters = data?.clusters || [];

  return (
    <>
      <div className="main-header">
        <h2>Dashboard</h2>
      </div>
      <div className="main-body">
        {/* Stats */}
        <div className={`stats-grid ${wsFlash === 'metrics' ? 'ws-flash' : ''}`}>
          <div className="stat-card"><div className="stat-icon agents">AG</div><div className="stat-info"><div className="stat-value">{summary.total_agents || 0}</div><div className="stat-label">Total Agents</div></div></div>
          <div className="stat-card"><div className="stat-icon active">ON</div><div className="stat-info"><div className="stat-value">{summary.active_agents || 0}</div><div className="stat-label">Active Agents</div></div></div>
          <div className="stat-card"><div className="stat-icon warnings">EV</div><div className="stat-info"><div className="stat-value">{summary.total_events_24h || 0}</div><div className="stat-label">Events (24h)</div></div></div>
          <div className="stat-card"><div className="stat-icon critical">AL</div><div className="stat-info"><div className="stat-value">{summary.critical_alerts || 0}</div><div className="stat-label">Critical Alerts</div></div></div>
        </div>

        {/* Cluster Health (if multiple) */}
        {clusters.length > 1 && !clusterId && (
          <div className="card" style={{ marginBottom: 24 }}>
            <div className="card-header"><div><div className="card-title">Cluster Health</div><div className="card-subtitle">{clusters.length} clusters registered</div></div></div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: 12 }}>
              {clusters.map(c => {
                const cAgents = agents.filter(a => a.cluster_id === c.id);
                const active = cAgents.filter(a => a.status === 'active').length;
                return (
                  <div key={c.id} className="stat-card" style={{ cursor: 'pointer' }} onClick={() => handleClusterChange(c.id)}>
                    <div className="stat-info">
                      <div style={{ fontWeight: 600, fontSize: 14 }}>{c.name}</div>
                      <div className="stat-label">{active}/{cAgents.length} agents up</div>
                      <div className="stat-trend up">{active === cAgents.length ? 'Healthy' : 'Degraded'}</div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Charts */}
        <div className="grid-2" style={{ marginBottom: 28 }}>
          <div className={`card ${wsFlash === 'metrics' ? 'ws-flash' : ''}`}>
            <div className="card-header"><div><div className="card-title">System Metrics</div><div className="card-subtitle">Auto-detected from active agents</div></div></div>
            <MetricsLineChart lastHours={6} height={280} />
          </div>
          <div className={`card ${wsFlash === 'events' ? 'ws-flash' : ''}`}>
            <div className="card-header"><div><div className="card-title">Event Timeline</div><div className="card-subtitle">Events by severity (24h)</div></div></div>
            <EventsBarChart lastHours={24} height={200} />
            <div style={{ display: 'flex', justifyContent: 'center', marginTop: 16 }}>
              <HealthDonut total={summary.total_agents || 0} active={summary.active_agents || 0} size={120} />
            </div>
          </div>
        </div>

        {/* Application Monitoring */}
        {traceSummary && traceSummary.total_requests > 0 && (
          <div style={{ marginBottom: 28 }}>
            <div className="card">
              <div className="card-header">
                <div><div className="card-title">Application Monitoring</div><div className="card-subtitle">OTLP trace data from instrumented services (last 1h)</div></div>
                <a href="/agents" className="btn btn-secondary btn-sm">View Agents</a>
              </div>
              {/* APM Stats */}
              <div className="stats-grid" style={{ marginBottom: 16 }}>
                <div className="stat-card">
                  <div className="stat-icon" style={{ background: '#7c3aed22', color: '#7c3aed' }}>RQ</div>
                  <div className="stat-info"><div className="stat-value">{traceSummary.total_requests}</div><div className="stat-label">Total Requests</div></div>
                </div>
                <div className="stat-card">
                  <div className="stat-icon" style={{ background: '#0ea5e922', color: '#0ea5e9' }}>MS</div>
                  <div className="stat-info">
                    <div className="stat-value">{traceSummary.avg_latency_ms?.toFixed(1)}<span style={{ fontSize: 12, fontWeight: 400 }}>ms</span></div>
                    <div className="stat-label">Avg Latency</div>
                  </div>
                </div>
                <div className="stat-card">
                  <div className="stat-icon" style={{ background: traceSummary.error_rate > 5 ? '#ef444422' : '#22c55e22', color: traceSummary.error_rate > 5 ? '#ef4444' : '#22c55e' }}>ER</div>
                  <div className="stat-info">
                    <div className="stat-value" style={{ color: traceSummary.error_rate > 5 ? 'var(--color-error)' : 'var(--color-success)' }}>{traceSummary.error_rate}%</div>
                    <div className="stat-label">Error Rate</div>
                  </div>
                </div>
                <div className="stat-card">
                  <div className="stat-icon" style={{ background: '#f59e0b22', color: '#f59e0b' }}>SV</div>
                  <div className="stat-info"><div className="stat-value">{traceSummary.services?.length || 0}</div><div className="stat-label">Services</div></div>
                </div>
              </div>
              {/* Service Table */}
              {traceSummary.services?.length > 0 && (
                <table className="data-table">
                  <thead><tr>
                    <th>Service</th><th>Requests</th><th>Avg Latency</th><th>P95 Latency</th><th>Max Latency</th><th>Errors</th><th>Error Rate</th>
                  </tr></thead>
                  <tbody>{traceSummary.services.map((s, i) => (
                    <tr key={i}>
                      <td><span className="badge info">{s.name}</span></td>
                      <td style={{ fontWeight: 600 }}>{s.requests}</td>
                      <td style={{ color: s.avg_latency_ms > 500 ? 'var(--color-error)' : s.avg_latency_ms > 100 ? 'var(--color-warning)' : 'var(--color-success)', fontWeight: 600 }}>{s.avg_latency_ms?.toFixed(1)}ms</td>
                      <td style={{ fontWeight: 600 }}>{s.p95_latency_ms?.toFixed(1)}ms</td>
                      <td style={{ fontWeight: 600, color: s.max_latency_ms > 1000 ? 'var(--color-error)' : 'inherit' }}>{s.max_latency_ms?.toFixed(1)}ms</td>
                      <td>{s.error_count > 0 ? <span className="badge error">{s.error_count}</span> : <span style={{ color: 'var(--color-success)' }}>0</span>}</td>
                      <td style={{ color: s.error_rate > 5 ? 'var(--color-error)' : 'var(--color-success)', fontWeight: 600 }}>{s.error_rate}%</td>
                    </tr>
                  ))}</tbody>
                </table>
              )}
              {/* Service Map */}
              {traceSummary.services?.length > 1 && (
                <div style={{ marginTop: 20, padding: 20, background: 'var(--bg-secondary, #faf7f2)', borderRadius: 12 }}>
                  <div style={{ fontSize: 13, fontWeight: 700, color: '#666', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 16 }}>Service Map</div>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 0, flexWrap: 'wrap', padding: '20px 0' }}>
                    {traceSummary.services.map((svc, idx) => (
                      <div key={svc.name} style={{ display: 'flex', alignItems: 'center' }}>
                        {/* Service Node */}
                        <div style={{
                          background: idx === 0 ? 'linear-gradient(135deg, #7c3aed, #a78bfa)' : 'linear-gradient(135deg, #0ea5e9, #67e8f9)',
                          color: '#fff', borderRadius: 16, padding: '16px 24px', textAlign: 'center',
                          boxShadow: '0 4px 16px rgba(0,0,0,0.12)', minWidth: 160,
                          border: '3px solid ' + (idx === 0 ? '#7c3aed55' : '#0ea5e955'),
                        }}>
                          <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 6 }}>{svc.name}</div>
                          <div style={{ fontSize: 11, opacity: 0.9 }}>{svc.requests} req · {svc.avg_latency_ms?.toFixed(0)}ms avg</div>
                          <div style={{ fontSize: 10, opacity: 0.7, marginTop: 2 }}>
                            {svc.error_count > 0 ? `${svc.error_count} errors` : 'healthy'}
                          </div>
                        </div>
                        {/* Arrow between nodes */}
                        {idx < traceSummary.services.length - 1 && (
                          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', margin: '0 8px' }}>
                            <div style={{ fontSize: 10, color: '#888', marginBottom: 4, whiteSpace: 'nowrap' }}>
                              HTTP →
                            </div>
                            <svg width="60" height="20" style={{ display: 'block' }}>
                              <defs>
                                <marker id="arrowhead" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
                                  <polygon points="0 0, 8 3, 0 6" fill="#7c3aed" />
                                </marker>
                              </defs>
                              <line x1="0" y1="10" x2="50" y2="10" stroke="#7c3aed" strokeWidth="2" markerEnd="url(#arrowhead)" />
                            </svg>
                            <div style={{ fontSize: 10, color: '#888', marginTop: 4, whiteSpace: 'nowrap' }}>
                              {traceSummary.services[idx + 1]?.requests || 0} req
                            </div>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Agents + Events */}
        <div className="grid-2">
          <div className="card">
            <div className="card-header">
              <div><div className="card-title">Agents</div><div className="card-subtitle">{agents.length} registered</div></div>
              <a href="/agents" className="btn btn-secondary btn-sm">View All</a>
            </div>
            {agents.length === 0 ? (
              <div className="empty-state"><div className="empty-state-text">No agents</div></div>
            ) : (
              <table className="data-table"><tbody>{agents.slice(0, 5).map(a => (
                <tr key={a.id} onClick={() => window.location.href = `/agents/${a.id}`} style={{ cursor: 'pointer' }}>
                  <td style={{ fontWeight: 600 }}>{a.name}</td>
                  <td><span className="badge info">{a.agent_type}</span></td>
                  <td><span className={`badge ${a.status === 'active' ? 'active' : 'error'}`}><span className="badge-dot" />{a.status}</span></td>
                </tr>
              ))}</tbody></table>
            )}
          </div>
          <div className="card">
            <div className="card-header">
              <div><div className="card-title">Recent Events</div><div className="card-subtitle">Last 24 hours</div></div>
              <a href="/events" className="btn btn-secondary btn-sm">View All</a>
            </div>
            {events.length === 0 ? (
              <div className="empty-state"><div className="empty-state-text">No events in the last 24h</div></div>
            ) : (
              <div>{events.slice(0, 5).map((e, i) => (
                <div key={e.id || i} className="event-item">
                  <div className={`event-icon ${e.level}`}>{levelIcons[e.level] || 'I'}</div>
                  <div className="event-content"><div className="event-title">{e.title}</div><div className="event-message">{e.message}</div></div>
                  <div className="event-time">{timeAgo(e.created_at)}</div>
                </div>
              ))}</div>
            )}
          </div>
        </div>
      </div>
    </>
  );
}
