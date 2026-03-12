'use client';

import { useState, useEffect, useCallback } from 'react';
import { getAlertConfigs, createAlertConfig, deleteAlertConfig, getSettings, updateSettings } from '../lib/api';

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

    useEffect(() => { fetchData(); fetchWebhooks(); }, [fetchData, fetchWebhooks]);

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
                    <button className={`btn ${tab === 'webhooks' ? 'btn-primary' : 'btn-secondary'}`} onClick={() => setTab('webhooks')}>
                        Webhooks
                    </button>
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

                {/* ─── Webhooks Tab ─── */}
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
            </div>
        </>
    );
}
