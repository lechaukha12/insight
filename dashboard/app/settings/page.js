'use client';

import { useState, useEffect, useCallback } from 'react';
import { getAlertConfigs, createAlertConfig, deleteAlertConfig, getSettings, updateSettings, getStorageStats, applyRetention, purgeAllData, getAgentTokens, createAgentToken, revokeAgentToken, getGeminiSettings, updateGeminiSettings, testGeminiConnection } from '../lib/api';
import { useAuth } from '../components/AuthProvider';

const API_BASE = '';

async function api(endpoint, opts = {}) {
    const token = typeof window !== 'undefined' ? localStorage.getItem('insight_token') : null;
    const headers = { 'Content-Type': 'application/json', ...opts.headers };
    if (token) headers['Authorization'] = `Bearer ${token}`;
    const res = await fetch(`${API_BASE}${endpoint}`, { headers, ...opts });
    if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || 'Error'); }
    return res.json();
}

export default function SettingsPage() {
    const [tab, setTab] = useState('general');
    const [configs, setConfigs] = useState([]);
    const [settings, setSettings] = useState({});
    const [loading, setLoading] = useState(true);
    const [newConfig, setNewConfig] = useState({ channel: 'telegram', bot_token: '', chat_id: '' });
    const [saving, setSaving] = useState(false);
    const [message, setMessage] = useState(null);

    // Webhooks state
    const [webhooks, setWebhooks] = useState([]);
    const [webhookLoading, setWebhookLoading] = useState(true);
    const [showForm, setShowForm] = useState(false);
    const [form, setForm] = useState({ name: '', url: '', type: 'slack', events: ['critical', 'error'] });
    const [testResult, setTestResult] = useState({});

    // Retention state
    const [storageStats, setStorageStats] = useState(null);
    const [retention, setRetention] = useState({
        retention_traces_days: 7, retention_logs_days: 14,
        retention_metrics_days: 30, retention_events_days: 30,
        retention_processes_days: 3, retention_audit_days: 90
    });
    const [retentionSaving, setRetentionSaving] = useState(false);
    const [retentionMsg, setRetentionMsg] = useState(null);
    const [confirmPurge, setConfirmPurge] = useState(false);

    // Tokens state
    const [tokens, setTokens] = useState([]);
    const [tokensLoading, setTokensLoading] = useState(true);
    const [showTokenForm, setShowTokenForm] = useState(false);
    const [tokenForm, setTokenForm] = useState({ name: '', agent_type: 'any', cluster_id: 'default' });
    const [newCreatedToken, setNewCreatedToken] = useState(null);
    const [tokenCopied, setTokenCopied] = useState(false);

    // AI Assistant state
    const [geminiKey, setGeminiKey] = useState('');
    const [geminiEnabled, setGeminiEnabled] = useState(false);
    const [geminiHasKey, setGeminiHasKey] = useState(false);
    const [geminiSaving, setGeminiSaving] = useState(false);
    const [geminiMsg, setGeminiMsg] = useState(null);
    const [geminiTesting, setGeminiTesting] = useState(false);

    const { user } = useAuth();

    const fetchData = useCallback(async () => {
        try {
            const [alertData, settingsData] = await Promise.all([getAlertConfigs(), getSettings()]);
            setConfigs(alertData?.configs || []);
            setSettings(settingsData || {});
        } catch (err) { console.error(err); }
        finally { setLoading(false); }
    }, []);

    const fetchWebhooks = useCallback(async () => {
        try { const d = await api('/api/v1/webhooks'); setWebhooks(d.webhooks || []); }
        catch (err) { console.error(err); }
        finally { setWebhookLoading(false); }
    }, []);

    const fetchGemini = useCallback(async () => {
        try {
            const d = await getGeminiSettings();
            setGeminiKey(d.api_key || '');
            setGeminiEnabled(d.enabled || false);
            setGeminiHasKey(d.has_key || false);
        } catch (err) { console.error(err); }
    }, []);

    useEffect(() => { fetchData(); fetchWebhooks(); fetchTokens(); if (user?.role === 'admin') fetchGemini(); }, [fetchData, fetchWebhooks, fetchGemini, user]);

    const fetchTokens = async () => {
        try { const d = await getAgentTokens(); setTokens(d.tokens || []); }
        catch (err) { console.error(err); }
        finally { setTokensLoading(false); }
    };

    // Fetch storage stats when retention tab is selected
    useEffect(() => {
        if (tab === 'retention') {
            getStorageStats().then(d => setStorageStats(d)).catch(console.error);
        }
    }, [tab]);

    // Sync retention settings from loaded settings
    useEffect(() => {
        if (settings) {
            setRetention(prev => ({
                retention_traces_days: settings.retention_traces_days || prev.retention_traces_days,
                retention_logs_days: settings.retention_logs_days || prev.retention_logs_days,
                retention_metrics_days: settings.retention_metrics_days || prev.retention_metrics_days,
                retention_events_days: settings.retention_events_days || prev.retention_events_days,
                retention_processes_days: settings.retention_processes_days || prev.retention_processes_days,
                retention_audit_days: settings.retention_audit_days || prev.retention_audit_days,
            }));
        }
    }, [settings]);

    // Settings handlers
    const handleAddTelegram = async () => {
        setSaving(true);
        try {
            await createAlertConfig({
                channel: 'telegram',
                config: { bot_token: newConfig.bot_token, chat_id: newConfig.chat_id },
                enabled: true, alert_levels: ['critical', 'error'],
            });
            setNewConfig({ channel: 'telegram', bot_token: '', chat_id: '' });
            setMessage({ type: 'success', text: 'Telegram config added!' });
            fetchData();
        } catch (err) { setMessage({ type: 'error', text: err.message }); }
        finally { setSaving(false); }
    };

    const handleDeleteConfig = async (id) => {
        try { await deleteAlertConfig(id); fetchData(); } catch (err) { console.error(err); }
    };

    const handleAutoReportToggle = async () => {
        const current = settings.auto_report || {};
        const updated = { ...current, enabled: !current.enabled };
        try {
            await updateSettings({ auto_report: updated });
            setSettings(prev => ({ ...prev, auto_report: updated }));
        } catch (err) { console.error(err); }
    };

    // Webhook handlers
    const handleCreateWebhook = async (e) => {
        e.preventDefault();
        try {
            await api('/api/v1/webhooks', { method: 'POST', body: JSON.stringify(form) });
            setShowForm(false);
            setForm({ name: '', url: '', type: 'slack', events: ['critical', 'error'] });
            fetchWebhooks();
        } catch (err) { alert('Failed: ' + err.message); }
    };

    const handleDeleteWebhook = async (id) => {
        if (!confirm('Delete this webhook?')) return;
        await api(`/api/v1/webhooks/${id}`, { method: 'DELETE' });
        fetchWebhooks();
    };

    const handleToggleWebhook = async (id, enabled) => {
        await api(`/api/v1/webhooks/${id}/toggle`, { method: 'PUT', body: JSON.stringify({ enabled: !enabled }) });
        fetchWebhooks();
    };

    const handleTestWebhook = async (id) => {
        setTestResult({ ...testResult, [id]: 'sending...' });
        try {
            const r = await api(`/api/v1/webhooks/${id}/test`, { method: 'POST' });
            setTestResult({ ...testResult, [id]: r.ok ? 'Sent!' : 'Failed' });
        } catch { setTestResult({ ...testResult, [id]: 'Error' }); }
    };

    const toggleEvent = (evt) => {
        setForm(f => ({
            ...f,
            events: f.events.includes(evt) ? f.events.filter(e => e !== evt) : [...f.events, evt]
        }));
    };

    if (loading) return (
        <>
            <div className="main-header"><h2>Settings</h2></div>
            <div className="main-body"><div className="loading-overlay"><div className="loading-spinner" /></div></div>
        </>
    );

    return (
        <>
            <div className="main-header"><h2>Settings</h2></div>
            <div className="main-body">
                {/* Tabs */}
                <div style={{ display: 'flex', gap: 8, marginBottom: 20 }}>
                    <button className={`btn ${tab === 'general' ? 'btn-primary' : 'btn-secondary'}`} onClick={() => setTab('general')}>
                        General
                    </button>
                    <button className={`btn ${tab === 'tokens' ? 'btn-primary' : 'btn-secondary'}`} onClick={() => setTab('tokens')}>
                        Agent Tokens
                    </button>
                    <button className={`btn ${tab === 'webhooks' ? 'btn-primary' : 'btn-secondary'}`} onClick={() => setTab('webhooks')}>
                        Webhooks
                    </button>
                    <button className={`btn ${tab === 'retention' ? 'btn-primary' : 'btn-secondary'}`} onClick={() => setTab('retention')}>
                        Data Retention
                    </button>
                    {user?.role === 'admin' && (
                        <button className={`btn ${tab === 'ai' ? 'btn-primary' : 'btn-secondary'}`} onClick={() => setTab('ai')}>
                            AI Assistant
                        </button>
                    )}
                </div>

                {/* ─── General Tab ─── */}
                {tab === 'general' && (
                    <>
                        {message && (
                            <div style={{
                                background: message.type === 'success' ? 'var(--color-success-bg)' : 'var(--color-error-bg)',
                                border: `1px solid ${message.type === 'success' ? 'rgba(34,197,94,0.3)' : 'rgba(239,68,68,0.3)'}`,
                                borderRadius: 'var(--radius-sm)', padding: '10px 16px', marginBottom: '16px',
                                color: message.type === 'success' ? 'var(--color-success)' : 'var(--color-error)', fontSize: '13px',
                            }}>
                                {message.text}
                            </div>
                        )}

                        <div className="grid-2">
                            <div className="card">
                                <div className="card-header"><div className="card-title">Alert Channels</div></div>
                                {configs.length > 0 && (
                                    <div style={{ marginBottom: '20px' }}>
                                        {configs.map(cfg => (
                                            <div key={cfg.id} style={{
                                                display: 'flex', alignItems: 'center', gap: '12px', padding: '12px',
                                                background: 'var(--bg-input)', borderRadius: 'var(--radius-sm)', marginBottom: '8px',
                                            }}>
                                                <div style={{ flex: 1 }}>
                                                    <div style={{ fontWeight: 600, textTransform: 'capitalize' }}>{cfg.channel}</div>
                                                    <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>Levels: {cfg.alert_levels?.join(', ')}</div>
                                                </div>
                                                <span className={`badge ${cfg.enabled ? 'active' : 'inactive'}`}>{cfg.enabled ? 'Active' : 'Off'}</span>
                                                <button className="btn btn-sm btn-danger" onClick={() => handleDeleteConfig(cfg.id)}>Delete</button>
                                            </div>
                                        ))}
                                    </div>
                                )}
                                <div style={{ borderTop: '1px solid var(--border-color)', paddingTop: '16px' }}>
                                    <h4 style={{ fontSize: '14px', marginBottom: '12px' }}>Add Telegram</h4>
                                    <div className="form-group">
                                        <label className="form-label">Bot Token</label>
                                        <input className="form-input" placeholder="123456:ABC-DEF..."
                                            value={newConfig.bot_token}
                                            onChange={e => setNewConfig(p => ({ ...p, bot_token: e.target.value }))} />
                                    </div>
                                    <div className="form-group">
                                        <label className="form-label">Chat ID</label>
                                        <input className="form-input" placeholder="-100123456789"
                                            value={newConfig.chat_id}
                                            onChange={e => setNewConfig(p => ({ ...p, chat_id: e.target.value }))} />
                                    </div>
                                    <button className="btn btn-primary btn-sm" onClick={handleAddTelegram} disabled={saving || !newConfig.bot_token || !newConfig.chat_id}>
                                        {saving ? 'Saving...' : '+ Add Telegram'}
                                    </button>
                                </div>
                            </div>

                            <div className="card">
                                <div className="card-header"><div className="card-title">Auto Reports</div></div>
                                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '20px' }}>
                                    <div>
                                        <div style={{ fontWeight: 600 }}>Auto Daily Report</div>
                                        <div style={{ fontSize: '13px', color: 'var(--text-muted)' }}>Send automatic report daily at 7:45 AM</div>
                                    </div>
                                    <label className="toggle">
                                        <input type="checkbox" checked={settings.auto_report?.enabled || false} onChange={handleAutoReportToggle} />
                                        <span className="toggle-slider" />
                                    </label>
                                </div>
                                <div className="form-group">
                                    <label className="form-label">Schedule (Cron)</label>
                                    <input className="form-input" value={settings.auto_report?.schedule || '45 0 * * *'} readOnly style={{ fontFamily: 'monospace' }} />
                                    <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '4px' }}>7:45 AM UTC+7 daily</div>
                                </div>
                                <div className="form-group">
                                    <label className="form-label">Alert Dedup (minutes)</label>
                                    <input className="form-input" type="number" value={settings.alert_dedup_minutes || 5} readOnly />
                                    <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '4px' }}>Suppress duplicate alerts within this window</div>
                                </div>
                                <div className="form-group">
                                    <label className="form-label">Metric Retention (days)</label>
                                    <input className="form-input" type="number" value={settings.metric_retention_days || 30} readOnly />
                                </div>
                            </div>
                        </div>
                    </>
                )}

                {/* --- Agent Tokens Tab --- */}
                {tab === 'tokens' && (
                    <>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
                            <div>
                                <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-secondary)' }}>Manage tokens used by agents to authenticate with Insight Core.</div>
                            </div>
                            <button className="btn btn-primary" onClick={() => { setShowTokenForm(!showTokenForm); setNewCreatedToken(null); }}>
                                {showTokenForm ? 'Cancel' : '+ Create Token'}
                            </button>
                        </div>

                        {/* New token just created */}
                        {newCreatedToken && (
                            <div className="card" style={{ marginBottom: 20, border: '2px solid var(--color-success)' }}>
                                <div className="card-header">
                                    <div className="card-title" style={{ color: 'var(--color-success)' }}>Token Created</div>
                                </div>
                                <div style={{ padding: '0 16px 16px' }}>
                                    <p style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 8 }}>Copy this token now. It will not be shown again.</p>
                                    <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                                        <code style={{
                                            flex: 1, padding: '10px 14px', background: '#1e293b', color: '#e2e8f0',
                                            borderRadius: 'var(--radius-sm)', fontSize: 13, wordBreak: 'break-all', fontFamily: 'monospace',
                                        }}>{newCreatedToken}</code>
                                        <button className="btn btn-sm btn-primary" onClick={() => {
                                            navigator.clipboard.writeText(newCreatedToken);
                                            setTokenCopied(true); setTimeout(() => setTokenCopied(false), 2000);
                                        }}>{tokenCopied ? 'Copied!' : 'Copy'}</button>
                                    </div>
                                </div>
                            </div>
                        )}

                        {/* Create form */}
                        {showTokenForm && !newCreatedToken && (
                            <div className="card" style={{ marginBottom: 20 }}>
                                <div className="card-header"><div className="card-title">Create Agent Token</div></div>
                                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 16, padding: '0 16px 16px' }}>
                                    <div className="form-group">
                                        <label className="form-label">Token Name</label>
                                        <input className="form-input" placeholder="e.g. Production Servers"
                                            value={tokenForm.name} onChange={e => setTokenForm({ ...tokenForm, name: e.target.value })} />
                                    </div>
                                    <div className="form-group">
                                        <label className="form-label">Agent Type</label>
                                        <select className="form-input" value={tokenForm.agent_type}
                                            onChange={e => setTokenForm({ ...tokenForm, agent_type: e.target.value })}>
                                            <option value="any">Any Type</option>
                                            <option value="system">System Only</option>
                                            <option value="kubernetes">Kubernetes Only</option>
                                            <option value="application">Application Only</option>
                                        </select>
                                    </div>
                                    <div className="form-group">
                                        <label className="form-label">Cluster</label>
                                        <input className="form-input" value={tokenForm.cluster_id}
                                            onChange={e => setTokenForm({ ...tokenForm, cluster_id: e.target.value })} />
                                    </div>
                                </div>
                                <div style={{ padding: '0 16px 16px' }}>
                                    <button className="btn btn-primary" disabled={!tokenForm.name} onClick={async () => {
                                        try {
                                            const result = await createAgentToken(tokenForm);
                                            setNewCreatedToken(result.token?.token || '');
                                            setTokenForm({ name: '', agent_type: 'any', cluster_id: 'default' });
                                            fetchTokens();
                                        } catch (err) { alert('Failed: ' + err.message); }
                                    }}>Generate Token</button>
                                </div>
                            </div>
                        )}

                        {/* Token List */}
                        {tokensLoading ? <div className="loading-overlay"><div className="loading-spinner" /></div> : tokens.length === 0 ? (
                            <div className="card"><div className="empty-state"><div className="empty-state-icon">TK</div><div className="empty-state-text">No agent tokens</div><div className="empty-state-hint">Create a token to allow agents to authenticate with Insight Core</div></div></div>
                        ) : (
                            <div className="card">
                                <div className="table-container">
                                    <table className="data-table">
                                        <thead><tr>
                                            <th>NAME</th><th>TOKEN</th><th>TYPE</th><th>CLUSTER</th><th>AGENTS</th><th>LAST USED</th><th>STATUS</th><th>ACTIONS</th>
                                        </tr></thead>
                                        <tbody>{tokens.map(t => (
                                            <tr key={t.id}>
                                                <td style={{ fontWeight: 600 }}>{t.name}</td>
                                                <td><code style={{ fontSize: 12, color: 'var(--text-muted)' }}>{t.token_preview}</code></td>
                                                <td><span className="badge info">{t.agent_type}</span></td>
                                                <td>{t.cluster_id}</td>
                                                <td style={{ fontWeight: 600 }}>{t.agent_count || 0}</td>
                                                <td style={{ fontSize: 12, color: 'var(--text-muted)' }}>{t.last_used || 'Never'}</td>
                                                <td><span className={`badge ${t.is_active ? 'active' : 'error'}`}><span className="badge-dot" />{t.is_active ? 'Active' : 'Revoked'}</span></td>
                                                <td>
                                                    {t.is_active ? (
                                                        <button className="btn btn-sm btn-secondary" style={{ color: 'var(--color-error)' }}
                                                            onClick={async () => {
                                                                if (!confirm(`Revoke token "${t.name}"? Agents using this token will be disconnected.`)) return;
                                                                try {
                                                                    await revokeAgentToken(t.id);
                                                                    fetchTokens();
                                                                } catch (err) {
                                                                    alert('Failed to revoke token: ' + err.message);
                                                                    fetchTokens();
                                                                }
                                                            }}>Revoke</button>
                                                    ) : <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>Revoked</span>}
                                                </td>
                                            </tr>
                                        ))}</tbody>
                                    </table>
                                </div>
                            </div>
                        )}
                    </>
                )}

                {/* --- Webhooks Tab --- */}
                {tab === 'webhooks' && (
                    <>
                        <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 16 }}>
                            <button className="btn btn-primary" onClick={() => setShowForm(!showForm)}>{showForm ? 'Cancel' : '+ New Webhook'}</button>
                        </div>

                        {showForm && (
                            <div className="card" style={{ marginBottom: 24 }}>
                                <div className="card-header"><div><div className="card-title">Add Webhook</div></div></div>
                                <form onSubmit={handleCreateWebhook} style={{ display: 'grid', gridTemplateColumns: '1fr 2fr', gap: 16, padding: '0 16px 16px' }}>
                                    <div className="form-group"><label className="form-label">Name</label>
                                        <input className="form-input" value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} placeholder="Slack Alerts" required /></div>
                                    <div className="form-group"><label className="form-label">URL</label>
                                        <input className="form-input" value={form.url} onChange={e => setForm({ ...form, url: e.target.value })} placeholder="https://hooks.slack.com/..." required /></div>
                                    <div className="form-group"><label className="form-label">Type</label>
                                        <select className="form-input" value={form.type} onChange={e => setForm({ ...form, type: e.target.value })}>
                                            <option value="slack">Slack</option><option value="discord">Discord</option><option value="custom">Custom (JSON POST)</option>
                                        </select></div>
                                    <div className="form-group"><label className="form-label">Events</label>
                                        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                                            {['critical', 'error', 'warning', 'info'].map(evt => (
                                                <label key={evt} style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 13, cursor: 'pointer' }}>
                                                    <input type="checkbox" checked={form.events.includes(evt)} onChange={() => toggleEvent(evt)} /> {evt}
                                                </label>
                                            ))}
                                        </div></div>
                                    <div style={{ gridColumn: 'span 2' }}><button type="submit" className="btn btn-primary">Add Webhook</button></div>
                                </form>
                            </div>
                        )}

                        {webhookLoading ? <div className="loading-overlay"><div className="loading-spinner" /></div> : webhooks.length === 0 ? (
                            <div className="card"><div className="empty-state"><div className="empty-state-icon">W</div><div className="empty-state-text">No webhooks configured</div><div className="empty-state-hint">Add Slack, Discord, or custom webhooks to receive alerts</div></div></div>
                        ) : (
                            <div className="card">
                                <table className="data-table">
                                    <thead><tr><th>Name</th><th>Type</th><th>URL</th><th>Events</th><th>Status</th><th>Actions</th></tr></thead>
                                    <tbody>{webhooks.map(w => (
                                        <tr key={w.id}>
                                            <td style={{ fontWeight: 600 }}>{w.name}</td>
                                            <td><span className="badge info">{w.type}</span></td>
                                            <td style={{ maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontFamily: 'monospace', fontSize: 12 }}>{w.url}</td>
                                            <td>{(w.events || []).map(e => <span key={e} className={`badge ${e}`} style={{ marginRight: 4 }}>{e}</span>)}</td>
                                            <td><span className={`badge ${w.enabled ? 'active' : 'error'}`}><span className="badge-dot" />{w.enabled ? 'Active' : 'Disabled'}</span></td>
                                            <td style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                                                <button className="btn btn-sm btn-secondary" onClick={() => handleToggleWebhook(w.id, w.enabled)}>{w.enabled ? 'Disable' : 'Enable'}</button>
                                                <button className="btn btn-sm btn-secondary" onClick={() => handleTestWebhook(w.id)}>{testResult[w.id] || 'Test'}</button>
                                                <button className="btn btn-sm btn-secondary" onClick={() => handleDeleteWebhook(w.id)} style={{ color: 'var(--color-error)' }}>Delete</button>
                                            </td>
                                        </tr>
                                    ))}</tbody>
                                </table>
                            </div>
                        )}
                    </>
                )}

                {/* ─── Data Retention Tab ─── */}
                {tab === 'retention' && (
                    <>
                        {retentionMsg && (
                            <div style={{
                                background: retentionMsg.type === 'success' ? 'var(--color-success-bg)' : 'var(--color-error-bg)',
                                border: `1px solid ${retentionMsg.type === 'success' ? 'rgba(34,197,94,0.3)' : 'rgba(239,68,68,0.3)'}`,
                                borderRadius: 'var(--radius-sm)', padding: '10px 16px', marginBottom: '16px',
                                color: retentionMsg.type === 'success' ? 'var(--color-success)' : 'var(--color-error)', fontSize: '13px',
                            }}>
                                {retentionMsg.text}
                            </div>
                        )}

                        <div className="grid-2">
                            {/* Retention Policies */}
                            <div className="card">
                                <div className="card-header"><div className="card-title">Retention Policies</div></div>
                                <p style={{ fontSize: 13, color: 'var(--color-text-muted)', margin: '0 0 16px' }}>Set how long data is kept before automatic cleanup.</p>
                                <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                                    {[
                                        { key: 'retention_traces_days', label: 'Traces', icon: '', min: 1, max: 90 },
                                        { key: 'retention_logs_days', label: 'Logs', icon: '', min: 1, max: 90 },
                                        { key: 'retention_metrics_days', label: 'Metrics', icon: '', min: 1, max: 365 },
                                        { key: 'retention_events_days', label: 'Events', icon: '', min: 1, max: 90 },
                                        { key: 'retention_processes_days', label: 'Processes', icon: '', min: 1, max: 30 },
                                        { key: 'retention_audit_days', label: 'Audit Logs', icon: '', min: 1, max: 365 },
                                    ].map(item => (
                                        <div key={item.key} style={{
                                            display: 'flex', alignItems: 'center', gap: 12,
                                            padding: '10px 14px', background: 'var(--color-bg)', borderRadius: 'var(--radius-sm)',
                                            border: '1px solid var(--color-border)'
                                        }}>
                                            <span style={{ fontSize: 20 }}>{item.icon}</span>
                                            <span style={{ flex: 1, fontWeight: 600, fontSize: 13 }}>{item.label}</span>
                                            <input type="number" min={item.min} max={item.max}
                                                value={retention[item.key]} onChange={e => setRetention(p => ({ ...p, [item.key]: parseInt(e.target.value) || item.min }))}
                                                style={{
                                                    width: 70, padding: '6px 8px', borderRadius: 'var(--radius-sm)',
                                                    border: '1px solid var(--color-border)', background: 'var(--color-bg-card)',
                                                    color: 'var(--color-text)', fontSize: 13, textAlign: 'center'
                                                }} />
                                            <span style={{ fontSize: 12, color: 'var(--color-text-muted)', minWidth: 30 }}>days</span>
                                        </div>
                                    ))}
                                </div>
                                <div style={{ display: 'flex', gap: 8, marginTop: 16 }}>
                                    <button className="btn btn-primary" disabled={retentionSaving} onClick={async () => {
                                        setRetentionSaving(true); setRetentionMsg(null);
                                        try {
                                            await updateSettings(retention);
                                            const result = await applyRetention();
                                            setRetentionMsg({ type: 'success', text: `Retention policies applied! ${JSON.stringify(result.retention || {})}` });
                                            getStorageStats().then(d => setStorageStats(d));
                                        } catch (err) {
                                            setRetentionMsg({ type: 'error', text: 'Failed to apply: ' + err.message });
                                        } finally { setRetentionSaving(false); }
                                    }}>
                                        {retentionSaving ? 'Applying...' : 'Save & Apply'}
                                    </button>
                                </div>
                            </div>

                            {/* Storage Stats */}
                            <div className="card">
                                <div className="card-header"><div className="card-title">Storage Statistics</div></div>
                                {storageStats?.engine === 'clickhouse' ? (
                                    storageStats.tables?.length > 0 ? (
                                        <div className="table-container">
                                            <table className="data-table">
                                                <thead><tr>
                                                    <th>TABLE</th><th>SIZE</th><th>ROWS</th><th>TTL (days)</th><th>DATA RANGE</th>
                                                </tr></thead>
                                                <tbody>
                                                    {storageStats.tables.map(t => (
                                                        <tr key={t.name}>
                                                            <td style={{ fontWeight: 600 }}>{t.name}</td>
                                                            <td><span className="badge badge-info">{t.size}</span></td>
                                                            <td>{Number(t.rows).toLocaleString()}</td>
                                                            <td>{t.retention_days ? `${t.retention_days}d` : '-'}</td>
                                                            <td style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>
                                                                {t.oldest && t.newest ? `${t.oldest} → ${t.newest}` : '-'}
                                                            </td>
                                                        </tr>
                                                    ))}
                                                </tbody>
                                            </table>
                                        </div>
                                    ) : (
                                        <p style={{ color: 'var(--color-text-muted)', fontSize: 13 }}>No data stored yet. Data will appear after ClickHouse receives writes.</p>
                                    )
                                ) : (
                                    <div style={{ padding: 16, background: 'var(--color-bg)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--color-border)' }}>
                                        <p style={{ fontWeight: 600, marginBottom: 8 }}>ClickHouse not configured</p>
                                        <p style={{ fontSize: 13, color: 'var(--color-text-muted)' }}>
                                            Set <code>CLICKHOUSE_URL</code> env var on insight-api to enable storage statistics and retention management.
                                        </p>
                                    </div>
                                )}
                                <button className="btn btn-secondary" style={{ marginTop: 12 }}
                                    onClick={() => getStorageStats().then(d => setStorageStats(d))}>
                                    Refresh Stats
                                </button>
                            </div>
                        </div>

                        {/* Admin-only Purge Section */}
                        {user?.role === 'admin' && (
                            <div className="card" style={{ marginTop: 20, border: '1px solid rgba(239,68,68,0.3)' }}>
                                <div className="card-header">
                                    <div className="card-title" style={{ color: 'var(--color-error)' }}>Danger Zone</div>
                                </div>
                                <p style={{ fontSize: 13, color: 'var(--color-text-muted)', margin: '0 0 12px' }}>
                                    Permanently delete all monitoring data (metrics, logs, traces, events). This action cannot be undone.
                                </p>
                                {!confirmPurge ? (
                                    <button className="btn" style={{
                                        background: 'rgba(239,68,68,0.1)', color: 'var(--color-error)',
                                        border: '1px solid rgba(239,68,68,0.3)', fontWeight: 600,
                                    }} onClick={() => setConfirmPurge(true)}>
                                        Purge All Data
                                    </button>
                                ) : (
                                    <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                                        <span style={{ fontSize: 13, color: 'var(--color-error)', fontWeight: 600 }}>Are you sure? This will delete ALL data!</span>
                                        <button className="btn" style={{
                                            background: 'var(--color-error)', color: '#fff', fontWeight: 600,
                                        }} onClick={async () => {
                                            try {
                                                const result = await purgeAllData();
                                                setRetentionMsg({ type: 'success', text: `Data purged: ${Object.entries(result.tables || {}).map(([k, v]) => `${k}: ${v}`).join(', ')}` });
                                                setConfirmPurge(false);
                                                getStorageStats().then(d => setStorageStats(d));
                                            } catch (err) {
                                                setRetentionMsg({ type: 'error', text: 'Purge failed: ' + err.message });
                                                setConfirmPurge(false);
                                            }
                                        }}>
                                            Yes, Delete Everything
                                        </button>
                                        <button className="btn btn-secondary" onClick={() => setConfirmPurge(false)}>Cancel</button>
                                    </div>
                                )}
                            </div>
                        )}
                    </>
                )}

                {/* ─── AI Assistant Tab ─── */}
                {tab === 'ai' && user?.role === 'admin' && (
                    <>
                        {geminiMsg && (
                            <div style={{
                                background: geminiMsg.type === 'success' ? 'var(--color-success-bg)' : 'var(--color-error-bg)',
                                border: `1px solid ${geminiMsg.type === 'success' ? 'rgba(34,197,94,0.3)' : 'rgba(239,68,68,0.3)'}`,
                                borderRadius: 'var(--radius-sm)', padding: '10px 16px', marginBottom: '16px',
                                color: geminiMsg.type === 'success' ? 'var(--color-success)' : 'var(--color-error)', fontSize: '13px',
                            }}>
                                {geminiMsg.text}
                            </div>
                        )}

                        <div className="grid-2">
                            <div className="card">
                                <div className="card-header">
                                    <div className="card-title">Gemini AI Configuration</div>
                                </div>
                                <p style={{ fontSize: 13, color: 'var(--text-muted)', margin: '0 0 16px' }}>
                                    Configure Google Gemini API for the AI monitoring assistant. The assistant can analyze system health, traces, logs, and metrics.
                                </p>

                                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '20px', padding: '12px', background: 'var(--bg-input)', borderRadius: 'var(--radius-sm)' }}>
                                    <div>
                                        <div style={{ fontWeight: 600 }}>Enable AI Assistant</div>
                                        <div style={{ fontSize: '13px', color: 'var(--text-muted)' }}>Show floating chatbot for admin users</div>
                                    </div>
                                    <label className="toggle">
                                        <input type="checkbox" checked={geminiEnabled} onChange={async (e) => {
                                            const val = e.target.checked;
                                            setGeminiEnabled(val);
                                            try {
                                                await updateGeminiSettings({ enabled: val });
                                                setGeminiMsg({ type: 'success', text: val ? 'AI Assistant enabled' : 'AI Assistant disabled' });
                                            } catch (err) { setGeminiMsg({ type: 'error', text: err.message }); }
                                        }} />
                                        <span className="toggle-slider" />
                                    </label>
                                </div>

                                <div className="form-group">
                                    <label className="form-label">Gemini API Key</label>
                                    <div style={{ display: 'flex', gap: 8 }}>
                                        <input
                                            className="form-input"
                                            type="password"
                                            placeholder={geminiHasKey ? '••••••••••••••••' : 'Enter your Gemini API key'}
                                            value={geminiKey.startsWith('*') ? '' : geminiKey}
                                            onChange={e => setGeminiKey(e.target.value)}
                                            style={{ flex: 1 }}
                                        />
                                        <button
                                            className="btn btn-primary"
                                            disabled={geminiSaving || (!geminiKey || geminiKey.startsWith('*'))}
                                            onClick={async () => {
                                                setGeminiSaving(true); setGeminiMsg(null);
                                                try {
                                                    await updateGeminiSettings({ api_key: geminiKey });
                                                    setGeminiMsg({ type: 'success', text: 'API key saved!' });
                                                    setGeminiKey('');
                                                    fetchGemini();
                                                } catch (err) { setGeminiMsg({ type: 'error', text: err.message }); }
                                                finally { setGeminiSaving(false); }
                                            }}
                                        >
                                            {geminiSaving ? 'Saving...' : 'Save Key'}
                                        </button>
                                    </div>
                                    <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '6px' }}>
                                        Get your API key from <a href="https://aistudio.google.com/apikey" target="_blank" rel="noreferrer" style={{ color: 'var(--color-primary)' }}>Google AI Studio</a>
                                    </div>
                                </div>
                            </div>

                            <div className="card">
                                <div className="card-header">
                                    <div className="card-title">Connection Status</div>
                                </div>
                                <div style={{ padding: '12px', background: 'var(--bg-input)', borderRadius: 'var(--radius-sm)', marginBottom: '16px' }}>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                                        <span className={`badge ${geminiHasKey ? 'active' : 'error'}`}>
                                            <span className="badge-dot" />{geminiHasKey ? 'Key Configured' : 'No Key'}
                                        </span>
                                        <span className={`badge ${geminiEnabled ? 'active' : 'inactive'}`}>
                                            {geminiEnabled ? 'Enabled' : 'Disabled'}
                                        </span>
                                    </div>
                                    <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>Model: Gemini 2.0 Flash</div>
                                </div>

                                <button
                                    className="btn btn-secondary"
                                    disabled={geminiTesting || !geminiHasKey}
                                    onClick={async () => {
                                        setGeminiTesting(true); setGeminiMsg(null);
                                        try {
                                            const res = await testGeminiConnection();
                                            setGeminiMsg({ type: 'success', text: `Connection successful! Response: ${res.response}` });
                                        } catch (err) { setGeminiMsg({ type: 'error', text: err.message }); }
                                        finally { setGeminiTesting(false); }
                                    }}
                                >
                                    {geminiTesting ? 'Testing...' : 'Test Connection'}
                                </button>

                                <div style={{ marginTop: 20, padding: '12px', background: 'var(--bg-input)', borderRadius: 'var(--radius-sm)' }}>
                                    <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 8 }}>Features</div>
                                    <ul style={{ fontSize: 12, color: 'var(--text-muted)', margin: 0, paddingLeft: 16, lineHeight: 1.8 }}>
                                        <li>Query system health & agent status</li>
                                        <li>Analyze traces, logs, and metrics</li>
                                        <li>Identify performance issues</li>
                                        <li>Get actionable recommendations</li>
                                        <li>Natural language monitoring queries</li>
                                    </ul>
                                </div>
                            </div>
                        </div>
                    </>
                )}
            </div>
        </>
    );
}
