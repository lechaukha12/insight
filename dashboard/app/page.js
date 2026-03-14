'use client';

import { useState, useEffect, useCallback } from 'react';
import { getDashboardV2Summary, acknowledgeEvent } from './lib/api';
import { useWebSocket } from './lib/useWebSocket';
import { useTimeRange } from './lib/TimeRangeContext';
import { timeAgo } from './lib/hooks';
import { MetricsLineChart, EventsBarChart, HealthDonut } from './components/Charts';

const levelIcons = { critical: 'C', error: 'E', warning: 'W', info: 'I' };
const levelColors = { critical: '#dc2626', error: '#ef4444', warning: '#f59e0b', info: '#3b82f6' };
const catIcons = { system: '🖥', kubernetes: '☸', application: '⚡', other: '📦' };
const catColors = { system: '#0165a7', kubernetes: '#326ce5', application: '#7c3aed', other: '#6b7280' };
const catLinks = { system: '/monitoring/system', kubernetes: '/monitoring/kubernetes', application: '/monitoring/application' };

export default function DashboardPage() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [clusterId, setClusterId] = useState(null);
  const [wsFlash, setWsFlash] = useState(null);
  const { queryParams, isLive } = useTimeRange();

  const WS_URL = typeof window !== 'undefined' ? `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}/ws/dashboard` : '';
  const { lastMessage, isConnected } = useWebSocket(WS_URL);

  const fetchData = useCallback(async () => {
    try {
      const result = await getDashboardV2Summary(clusterId, queryParams);
      setData(result);
    } catch (err) { console.error(err); }
    finally { setLoading(false); }
  }, [clusterId, queryParams]);

  useEffect(() => {
    fetchData();
    if (isLive) {
      const i = setInterval(fetchData, 15000);
      return () => clearInterval(i);
    }
  }, [fetchData, isLive]);

  useEffect(() => {
    if (lastMessage && (lastMessage.type === 'metrics' || lastMessage.type === 'events')) {
      fetchData();
      setWsFlash(lastMessage.type);
      setTimeout(() => setWsFlash(null), 1500);
    }
  }, [lastMessage, fetchData]);

  const handleAck = async (eventId) => {
    try { await acknowledgeEvent(eventId); fetchData(); } catch (e) { console.error(e); }
  };

  const s = data?.summary || {};
  const cats = data?.categories || {};
  const alerts = data?.active_alerts || [];
  const events = data?.recent_events || [];
  const clusters = data?.clusters || [];

  return (
    <>
      <div className="main-header"><h2>Dashboard</h2></div>
      <div className="main-body">

        {/* ═══ Section 1: Summary Stats Bar ═══ */}
        <div className={`stats-grid ${wsFlash === 'metrics' ? 'ws-flash' : ''}`} style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))' }}>
          {[
            { icon: 'AG', label: 'Total Agents', value: s.total_agents || 0, cls: 'agents' },
            { icon: 'ON', label: 'Active', value: s.active_agents || 0, cls: 'active' },
            { icon: 'EV', label: 'Events (24h)', value: s.total_events_24h || 0, cls: 'warnings' },
            { icon: 'AL', label: 'Critical', value: s.critical_alerts || 0, cls: 'critical' },
            { icon: 'SV', label: 'Services', value: s.total_services || 0, cls: 'info' },
            { icon: 'CL', label: 'Clusters', value: s.total_clusters || 0, cls: 'info' },
          ].map((st, i) => (
            <div key={i} className="stat-card">
              <div className={`stat-icon ${st.cls}`}>{st.icon}</div>
              <div className="stat-info"><div className="stat-value">{st.value}</div><div className="stat-label">{st.label}</div></div>
            </div>
          ))}
        </div>

        {/* ═══ Section 2: Agent Category Cards ═══ */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 20, margin: '24px 0' }}>
          {Object.entries(cats).map(([cat, info]) => (
            <a key={cat} href={catLinks[cat] || '/agents'} style={{ textDecoration: 'none', color: 'inherit' }}>
              <div className="card" style={{
                borderLeft: `4px solid ${catColors[cat] || '#6b7280'}`,
                transition: 'transform 0.2s, box-shadow 0.2s', cursor: 'pointer',
              }}
                onMouseEnter={e => { e.currentTarget.style.transform = 'translateY(-2px)'; e.currentTarget.style.boxShadow = '0 8px 24px rgba(0,0,0,0.12)'; }}
                onMouseLeave={e => { e.currentTarget.style.transform = ''; e.currentTarget.style.boxShadow = ''; }}
              >
                {/* Card Header */}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <span style={{ fontSize: 22 }}>{catIcons[cat] || '📦'}</span>
                    <div>
                      <div style={{ fontWeight: 700, fontSize: 15, textTransform: 'capitalize' }}>{cat} Agents</div>
                      <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>{info.active}/{info.count} active</div>
                    </div>
                  </div>
                  <div style={{
                    background: info.active === info.count ? '#15803d18' : '#f59e0b18',
                    color: info.active === info.count ? '#15803d' : '#f59e0b',
                    padding: '3px 10px', borderRadius: 6, fontSize: 11, fontWeight: 700,
                  }}>
                    {info.active === info.count ? 'Healthy' : 'Degraded'}
                  </div>
                </div>

                {/* Card Content — Category-specific */}
                {cat === 'system' && (
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12 }}>
                    {/* CPU with progress bar */}
                    <div style={{ textAlign: 'center' }}>
                      <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 }}>CPU</div>
                      <div style={{ fontSize: 18, fontWeight: 700, color: (info.avg_cpu || 0) > 80 ? '#dc2626' : '#0165a7' }}>
                        {info.avg_cpu != null ? `${info.avg_cpu}%` : '—'}
                      </div>
                      {info.avg_cpu != null && (
                        <div style={{ height: 4, borderRadius: 2, background: '#e5e7eb', marginTop: 6 }}>
                          <div style={{
                            height: '100%', borderRadius: 2, width: `${Math.min(info.avg_cpu, 100)}%`,
                            background: info.avg_cpu > 80 ? '#dc2626' : info.avg_cpu > 60 ? '#f59e0b' : '#0165a7',
                            transition: 'width 0.5s ease',
                          }} />
                        </div>
                      )}
                    </div>
                    {/* Memory in GB */}
                    <div style={{ textAlign: 'center' }}>
                      <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 }}>Memory</div>
                      <div style={{ fontSize: 18, fontWeight: 700, color: '#e6a800' }}>
                        {info.avg_memory_gb != null ? `${info.avg_memory_gb} GB` : '—'}
                      </div>
                    </div>
                    {/* Disk in GB */}
                    <div style={{ textAlign: 'center' }}>
                      <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 }}>Disk</div>
                      <div style={{ fontSize: 18, fontWeight: 700, color: '#d4380d' }}>
                        {info.avg_disk_gb != null ? `${info.avg_disk_gb} GB` : '—'}
                      </div>
                    </div>
                  </div>
                )}

                {cat === 'kubernetes' && (
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12, textAlign: 'center' }}>
                    <div>
                      <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>Nodes</div>
                      <div style={{ fontSize: 20, fontWeight: 700, color: '#326ce5' }}>{info.nodes || 0}</div>
                    </div>
                    <div>
                      <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>Pods</div>
                      <div style={{ fontSize: 20, fontWeight: 700, color: '#326ce5' }}>{info.pods || 0}</div>
                    </div>
                    <div>
                      <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>Warnings</div>
                      <div style={{ fontSize: 20, fontWeight: 700, color: (info.warnings || 0) > 0 ? '#f59e0b' : '#15803d' }}>
                        {info.warnings || 0}
                      </div>
                    </div>
                  </div>
                )}

                {cat === 'application' && (
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12, textAlign: 'center' }}>
                    <div>
                      <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>Services</div>
                      <div style={{ fontSize: 20, fontWeight: 700, color: '#7c3aed' }}>{info.services || 0}</div>
                    </div>
                    <div>
                      <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>Latency</div>
                      <div style={{ fontSize: 18, fontWeight: 700, color: (info.avg_latency || 0) > 500 ? '#dc2626' : '#7c3aed' }}>
                        {info.avg_latency != null ? `${info.avg_latency.toFixed(0)}ms` : '—'}
                      </div>
                    </div>
                    <div>
                      <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>Error Rate</div>
                      <div style={{ fontSize: 18, fontWeight: 700, color: (info.error_rate || 0) > 5 ? '#dc2626' : '#15803d' }}>
                        {info.error_rate != null ? `${info.error_rate}%` : '—'}
                      </div>
                    </div>
                  </div>
                )}

                {cat !== 'system' && cat !== 'kubernetes' && cat !== 'application' && (
                  <div style={{ fontSize: 13, color: 'var(--text-muted)' }}>
                    {info.count} agent(s) registered
                  </div>
                )}

                {/* Agent list pills */}
                <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 14 }}>
                  {(info.agent_names || []).slice(0, 4).map(a => (
                    <span key={a.id} className={`badge ${a.status === 'active' ? 'active' : 'error'}`} style={{ fontSize: 11 }}>
                      <span className="badge-dot" />{a.name}
                    </span>
                  ))}
                  {(info.agent_names || []).length > 4 && (
                    <span className="badge info" style={{ fontSize: 11 }}>+{info.agent_names.length - 4} more</span>
                  )}
                </div>
              </div>
            </a>
          ))}
        </div>

        {/* ═══ Section 3: Charts ═══ */}
        <div className="grid-2" style={{ marginBottom: 24 }}>
          <div className={`card ${wsFlash === 'metrics' ? 'ws-flash' : ''}`}>
            <div className="card-header"><div><div className="card-title">Infrastructure Health</div><div className="card-subtitle">Auto-detected from active agents</div></div></div>
            <MetricsLineChart lastHours={6} height={260} />
          </div>
          <div className={`card ${wsFlash === 'events' ? 'ws-flash' : ''}`}>
            <div className="card-header"><div><div className="card-title">Alert Timeline</div><div className="card-subtitle">Events by severity (24h)</div></div></div>
            <EventsBarChart lastHours={24} height={220} />
            <div style={{ display: 'flex', justifyContent: 'center', marginTop: 12 }}>
              <HealthDonut agents={events.length > 0 ? Object.values(cats).flatMap(c => c.agent_names || []) : []} size={100} />
            </div>
          </div>
        </div>

        {/* ═══ Section 4: Active Alerts + Recent Activity ═══ */}
        <div className="grid-2">
          {/* Active Alerts */}
          <div className="card">
            <div className="card-header">
              <div>
                <div className="card-title">Active Alerts</div>
                <div className="card-subtitle">{alerts.length} unacknowledged</div>
              </div>
              <a href="/events" className="btn btn-secondary btn-sm">View All</a>
            </div>
            {alerts.length === 0 ? (
              <div className="empty-state" style={{ padding: '30px 0' }}>
                <div className="empty-state-icon" style={{ color: '#15803d', fontSize: 28 }}>✓</div>
                <div className="empty-state-text" style={{ color: '#15803d' }}>All clear — no active alerts</div>
              </div>
            ) : (
              <div>
                {alerts.slice(0, 8).map((a, i) => (
                  <div key={a.id || i} className="event-item" style={{ alignItems: 'center' }}>
                    <div className={`event-icon ${a.level}`}>{levelIcons[a.level] || 'I'}</div>
                    <div className="event-content" style={{ flex: 1, minWidth: 0 }}>
                      <div className="event-title" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        <span className={`badge ${a.level}`} style={{ fontSize: 10, flexShrink: 0 }}>{a.level}</span>
                        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{a.title}</span>
                      </div>
                      <div className="event-message">{a.message?.slice(0, 80)}{a.message?.length > 80 ? '...' : ''}</div>
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 4, flexShrink: 0 }}>
                      <div className="event-time">{timeAgo(a.created_at)}</div>
                      <button className="btn btn-sm btn-secondary" style={{ fontSize: 10, padding: '2px 8px' }}
                        onClick={(e) => { e.preventDefault(); handleAck(a.id); }}>Ack</button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Recent Activity */}
          <div className="card">
            <div className="card-header">
              <div>
                <div className="card-title">Recent Activity</div>
                <div className="card-subtitle">Last 24 hours</div>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                {isConnected && <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 11, color: '#15803d' }}><span style={{ width: 6, height: 6, borderRadius: '50%', background: '#15803d', display: 'inline-block', animation: 'pulse 2s infinite' }} />Live</span>}
                <a href="/events" className="btn btn-secondary btn-sm">View All</a>
              </div>
            </div>
            {events.length === 0 ? (
              <div className="empty-state"><div className="empty-state-text">No events in the last 24h</div></div>
            ) : (
              <div>
                {events.slice(0, 8).map((e, i) => (
                  <div key={e.id || i} className="event-item">
                    <div className={`event-icon ${e.level}`} style={{ width: 28, height: 28, fontSize: 11 }}>{levelIcons[e.level] || 'I'}</div>
                    <div className="event-content">
                      <div className="event-title" style={{ fontSize: 13 }}>{e.title}</div>
                      <div className="event-message" style={{ fontSize: 11 }}>
                        {e.source && <span className="badge info" style={{ fontSize: 10, marginRight: 4 }}>{e.source}</span>}
                        {e.namespace && <span style={{ color: 'var(--text-muted)' }}>{e.namespace}</span>}
                      </div>
                    </div>
                    <div className="event-time" style={{ fontSize: 11 }}>{timeAgo(e.created_at)}</div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

      </div>

      <style jsx>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.4; }
        }
      `}</style>
    </>
  );
}
