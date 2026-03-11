'use client';

import { useState, useEffect, useCallback } from 'react';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8080';

async function api(endpoint, opts = {}) {
    const token = typeof window !== 'undefined' ? localStorage.getItem('insight_token') : null;
    const headers = { 'Content-Type': 'application/json', ...opts.headers };
    if (token) headers['Authorization'] = `Bearer ${token}`;
    const res = await fetch(`${API_BASE}${endpoint}`, { headers, ...opts });
    if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || 'Error'); }
    return res.json();
}

export default function WebhooksPage() {
    const [webhooks, setWebhooks] = useState([]);
    const [loading, setLoading] = useState(true);
    const [showForm, setShowForm] = useState(false);
    const [form, setForm] = useState({ name: '', url: '', type: 'slack', events: ['critical', 'error'] });
    const [testResult, setTestResult] = useState({});

    const fetchWebhooks = useCallback(async () => {
        try { const d = await api('/api/v1/webhooks'); setWebhooks(d.webhooks || []); }
        catch (err) { console.error(err); }
        finally { setLoading(false); }
    }, []);

    useEffect(() => { fetchWebhooks(); }, [fetchWebhooks]);

    const handleCreate = async (e) => {
        e.preventDefault();
        try {
            await api('/api/v1/webhooks', { method: 'POST', body: JSON.stringify(form) });
            setShowForm(false);
            setForm({ name: '', url: '', type: 'slack', events: ['critical', 'error'] });
            fetchWebhooks();
        } catch (err) { alert('Failed: ' + err.message); }
    };

    const handleDelete = async (id) => {
        if (!confirm('Delete this webhook?')) return;
        await api(`/api/v1/webhooks/${id}`, { method: 'DELETE' });
        fetchWebhooks();
    };

    const handleToggle = async (id, enabled) => {
        await api(`/api/v1/webhooks/${id}/toggle`, { method: 'PUT', body: JSON.stringify({ enabled: !enabled }) });
        fetchWebhooks();
    };

    const handleTest = async (id) => {
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

    const typeIcons = { slack: 'S', discord: 'D', custom: 'W' };

    return (
        <>
            <div className="main-header">
                <h2>Webhooks</h2>
                <div className="header-actions">
                    <button className="btn btn-primary" onClick={() => setShowForm(!showForm)}>{showForm ? 'Cancel' : '+ New Webhook'}</button>
                </div>
            </div>
            <div className="main-body">
                {showForm && (
                    <div className="card" style={{ marginBottom: 24 }}>
                        <div className="card-header"><div><div className="card-title">Add Webhook</div></div></div>
                        <form onSubmit={handleCreate} style={{ display: 'grid', gridTemplateColumns: '1fr 2fr', gap: 16, padding: '0 16px 16px' }}>
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

                {loading ? <div className="loading-overlay"><div className="loading-spinner" /></div> : webhooks.length === 0 ? (
                    <div className="card"><div className="empty-state"><div className="empty-state-icon">W</div><div className="empty-state-text">No webhooks configured</div><div className="empty-state-hint">Add Slack, Discord, or custom webhooks to receive alerts</div></div></div>
                ) : (
                    <div className="card">
                        <table className="data-table">
                            <thead><tr><th>Name</th><th>Type</th><th>URL</th><th>Events</th><th>Status</th><th>Actions</th></tr></thead>
                            <tbody>{webhooks.map(w => (
                                <tr key={w.id}>
                                    <td style={{ fontWeight: 600 }}>{w.name}</td>
                                    <td><span className="badge info">{typeIcons[w.type] || 'W'} {w.type}</span></td>
                                    <td style={{ maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontFamily: 'monospace', fontSize: 12 }}>{w.url}</td>
                                    <td>{(w.events || []).map(e => <span key={e} className={`badge ${e === 'critical' ? 'critical' : e === 'error' ? 'error' : e === 'warning' ? 'warning' : 'info'}`} style={{ marginRight: 4 }}>{e}</span>)}</td>
                                    <td><span className={`badge ${w.enabled ? 'active' : 'error'}`}><span className="badge-dot" />{w.enabled ? 'Active' : 'Disabled'}</span></td>
                                    <td style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                                        <button className="btn btn-sm btn-secondary" onClick={() => handleToggle(w.id, w.enabled)}>{w.enabled ? 'Disable' : 'Enable'}</button>
                                        <button className="btn btn-sm btn-secondary" onClick={() => handleTest(w.id)}>{testResult[w.id] || 'Test'}</button>
                                        <button className="btn btn-sm btn-secondary" onClick={() => handleDelete(w.id)} style={{ color: 'var(--color-error)' }}>Delete</button>
                                    </td>
                                </tr>
                            ))}</tbody>
                        </table>
                    </div>
                )}
            </div>
        </>
    );
}
