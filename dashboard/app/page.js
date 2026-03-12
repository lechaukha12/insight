'use client';

import { useState, useEffect, useCallback } from 'react';
import { getDashboardSummary, generateReport } from './lib/api';
import { useWebSocket } from './lib/useWebSocket';
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

  const WS_URL = typeof window !== 'undefined' ? `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}/ws/dashboard` : '';
  const { lastMessage, isConnected } = useWebSocket(WS_URL);

  const fetchData = useCallback(async () => {
    try {
      const result = await getDashboardSummary(clusterId);
      setData(result);
    } catch (err) { console.error(err); }
    finally { setLoading(false); }
  }, [clusterId]);

  // Initial and periodic fetch as fallback
  useEffect(() => { fetchData(); const i = setInterval(fetchData, 30000); return () => clearInterval(i); }, [fetchData]);

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
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <h2>Dashboard Overview</h2>
          <span className={`ws-indicator ${isConnected ? 'connected' : 'disconnected'}`}>{isConnected ? 'Live' : 'Offline'}</span>
        </div>
        <div className="header-actions">
          <ClusterSelector onClusterChange={handleClusterChange} />
          <button className="btn btn-primary" onClick={handleSendReport} disabled={sending}>{sending ? 'Sending...' : 'Send Report'}</button>
        </div>
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
            <div className="card-header"><div><div className="card-title">System Metrics</div><div className="card-subtitle">CPU / Memory / Disk usage</div></div></div>
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
