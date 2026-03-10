'use client';

import { useState, useEffect, useCallback } from 'react';
import { getDashboardSummary, generateReport } from './lib/api';
import { timeAgo, formatDate } from './lib/hooks';

export default function DashboardPage() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [sending, setSending] = useState(false);
  const [sendResult, setSendResult] = useState(null);

  const fetchData = useCallback(async () => {
    try {
      const result = await getDashboardSummary();
      setData(result);
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 15000); // refresh every 15s
    return () => clearInterval(interval);
  }, [fetchData]);

  const handleSendReport = async () => {
    setSending(true);
    setSendResult(null);
    try {
      const result = await generateReport(['telegram']);
      setSendResult({ success: true, message: `Report sent to: ${result.sent_to?.join(', ') || 'queued'}` });
    } catch (err) {
      setSendResult({ success: false, message: `Failed: ${err.message}` });
    } finally {
      setSending(false);
    }
  };

  if (loading) {
    return (
      <>
        <div className="main-header">
          <h2>Dashboard</h2>
        </div>
        <div className="main-body">
          <div className="loading-overlay">
            <div className="loading-spinner" />
            <span>Loading dashboard...</span>
          </div>
        </div>
      </>
    );
  }

  const summary = data?.summary || {};
  const agents = data?.agents || [];
  const recentEvents = data?.recent_events || [];

  return (
    <>
      <div className="main-header">
        <h2>Dashboard Overview</h2>
        <div className="header-actions">
          {sendResult && (
            <span style={{ fontSize: '13px', color: sendResult.success ? 'var(--color-success)' : 'var(--color-error)' }}>
              {sendResult.message}
            </span>
          )}
          <button className="btn btn-primary" onClick={handleSendReport} disabled={sending}>
            {sending ? <><div className="loading-spinner" /> Sending...</> : '📤 Gửi Báo cáo'}
          </button>
        </div>
      </div>

      <div className="main-body">
        {error && (
          <div style={{ background: 'var(--color-error-bg)', border: '1px solid rgba(239,68,68,0.3)', borderRadius: 'var(--radius)', padding: '12px 16px', marginBottom: '24px', color: 'var(--color-error)', fontSize: '14px' }}>
            ⚠️ Cannot connect to API: {error}. Data shown may be stale.
          </div>
        )}

        {/* Stats Grid */}
        <div className="stats-grid">
          <div className="stat-card">
            <div className="stat-icon agents">🤖</div>
            <div className="stat-info">
              <div className="stat-value">{summary.total_agents || 0}</div>
              <div className="stat-label">Total Agents</div>
            </div>
          </div>
          <div className="stat-card">
            <div className="stat-icon active">✅</div>
            <div className="stat-info">
              <div className="stat-value">{summary.active_agents || 0}</div>
              <div className="stat-label">Active Agents</div>
            </div>
          </div>
          <div className="stat-card">
            <div className="stat-icon warnings">⚡</div>
            <div className="stat-info">
              <div className="stat-value">{summary.total_events_24h || 0}</div>
              <div className="stat-label">Events (24h)</div>
            </div>
          </div>
          <div className="stat-card">
            <div className="stat-icon critical">🔴</div>
            <div className="stat-info">
              <div className="stat-value">{summary.critical_alerts || 0}</div>
              <div className="stat-label">Critical Alerts</div>
              {summary.error_alerts > 0 && (
                <div className="stat-trend down">+{summary.error_alerts} errors</div>
              )}
            </div>
          </div>
        </div>

        {/* Two columns: Agents + Events */}
        <div className="grid-2">
          {/* Agents */}
          <div className="card">
            <div className="card-header">
              <div>
                <div className="card-title">Agents</div>
                <div className="card-subtitle">{agents.length} registered agents</div>
              </div>
              <a href="/agents" className="btn btn-sm btn-secondary">View All →</a>
            </div>
            {agents.length === 0 ? (
              <div className="empty-state">
                <div className="empty-state-icon">🤖</div>
                <div className="empty-state-text">No agents registered</div>
                <p style={{ color: 'var(--text-muted)', fontSize: '13px' }}>Deploy an agent to start monitoring</p>
              </div>
            ) : (
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Type</th>
                    <th>Status</th>
                    <th>Last Seen</th>
                  </tr>
                </thead>
                <tbody>
                  {agents.slice(0, 5).map(agent => (
                    <tr key={agent.id}>
                      <td style={{ color: 'var(--text-primary)', fontWeight: 500 }}>{agent.name}</td>
                      <td><span className="badge info">{agent.agent_type}</span></td>
                      <td>
                        <span className={`badge ${agent.status === 'active' ? 'active' : 'error'}`}>
                          <span className="badge-dot" />
                          {agent.status}
                        </span>
                      </td>
                      <td>{timeAgo(agent.last_heartbeat)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          {/* Recent Events */}
          <div className="card">
            <div className="card-header">
              <div>
                <div className="card-title">Recent Events</div>
                <div className="card-subtitle">Last 24 hours</div>
              </div>
              <a href="/events" className="btn btn-sm btn-secondary">View All →</a>
            </div>
            {recentEvents.length === 0 ? (
              <div className="empty-state">
                <div className="empty-state-icon">✅</div>
                <div className="empty-state-text">No events</div>
                <p style={{ color: 'var(--text-muted)', fontSize: '13px' }}>All systems operating normally</p>
              </div>
            ) : (
              <div>
                {recentEvents.slice(0, 8).map((event, i) => (
                  <div key={event.id || i} className="event-item">
                    <div className={`event-icon ${event.level}`}>
                      {event.level === 'critical' ? '🔴' : event.level === 'error' ? '❌' : event.level === 'warning' ? '⚠️' : 'ℹ️'}
                    </div>
                    <div className="event-content">
                      <div className="event-title">{event.title}</div>
                      <div className="event-message">{event.message}</div>
                    </div>
                    <div className="event-time">{timeAgo(event.created_at)}</div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </>
  );
}
