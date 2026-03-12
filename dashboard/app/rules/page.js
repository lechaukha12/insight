'use client';

import { useState, useEffect, useCallback } from 'react';

const API_BASE = '';

async function fetchRulesAPI(endpoint, options = {}) {
    const token = typeof window !== 'undefined' ? localStorage.getItem('insight_token') : null;
    const headers = { 'Content-Type': 'application/json', ...options.headers };
    if (token) headers['Authorization'] = `Bearer ${token}`;
    const res = await fetch(`${API_BASE}${endpoint}`, { headers, ...options });
    if (!res.ok) throw new Error(`API error: ${res.status}`);
    return res.json();
}

export default function RulesPage() {
    const [rules, setRules] = useState([]);
    const [loading, setLoading] = useState(true);
    const [showForm, setShowForm] = useState(false);
    const [form, setForm] = useState({
        name: '', metric_name: 'cpu_percent', operator: '>', threshold: 90, duration_minutes: 5, channels: ['telegram']
    });

    const fetchRules = useCallback(async () => {
        try {
            const data = await fetchRulesAPI('/api/v1/rules');
            setRules(data?.rules || []);
        } catch (err) { console.error(err); }
        finally { setLoading(false); }
    }, []);

    useEffect(() => { fetchRules(); }, [fetchRules]);

    const handleCreate = async (e) => {
        e.preventDefault();
        try {
            await fetchRulesAPI('/api/v1/rules', { method: 'POST', body: JSON.stringify(form) });
            setShowForm(false);
            setForm({ name: '', metric_name: 'cpu_percent', operator: '>', threshold: 90, duration_minutes: 5, channels: ['telegram'] });
            fetchRules();
        } catch (err) { alert('Failed: ' + err.message); }
    };

    const handleDelete = async (id) => {
        if (!confirm('Delete this rule?')) return;
        await fetchRulesAPI(`/api/v1/rules/${id}`, { method: 'DELETE' });
        fetchRules();
    };

    const handleToggle = async (id, enabled) => {
        await fetchRulesAPI(`/api/v1/rules/${id}/toggle`, { method: 'PUT', body: JSON.stringify({ enabled: !enabled }) });
        fetchRules();
    };

    return (
        <>
            <div className="main-header">
                <h2>Notification Rules</h2>
                <div className="header-actions">
                    <button className="btn btn-primary" onClick={() => setShowForm(!showForm)}>
                        {showForm ? 'Cancel' : '+ New Rule'}
                    </button>
                </div>
            </div>
            <div className="main-body">
                {showForm && (
                    <div className="card" style={{ marginBottom: 24 }}>
                        <div className="card-header"><div><div className="card-title">Create Rule</div></div></div>
                        <form onSubmit={handleCreate} style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, padding: '0 16px 16px' }}>
                            <div className="form-group"><label className="form-label">Rule Name</label>
                                <input className="form-input" value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} placeholder="High CPU Alert" required /></div>
                            <div className="form-group"><label className="form-label">Metric</label>
                                <select className="form-input" value={form.metric_name} onChange={e => setForm({ ...form, metric_name: e.target.value })}>
                                    <option value="cpu_percent">CPU %</option><option value="memory_percent">Memory %</option><option value="disk_percent">Disk %</option>
                                </select></div>
                            <div className="form-group"><label className="form-label">Operator</label>
                                <select className="form-input" value={form.operator} onChange={e => setForm({ ...form, operator: e.target.value })}>
                                    <option value=">">{">"} Greater than</option><option value=">=">{"≥"} Greater or equal</option>
                                    <option value="<">{"<"} Less than</option><option value="<=">{"≤"} Less or equal</option>
                                </select></div>
                            <div className="form-group"><label className="form-label">Threshold (%)</label>
                                <input type="number" className="form-input" value={form.threshold} onChange={e => setForm({ ...form, threshold: Number(e.target.value) })} /></div>
                            <div className="form-group"><label className="form-label">Duration (minutes)</label>
                                <input type="number" className="form-input" value={form.duration_minutes} onChange={e => setForm({ ...form, duration_minutes: Number(e.target.value) })} /></div>
                            <div className="form-group" style={{ display: 'flex', alignItems: 'flex-end' }}>
                                <button type="submit" className="btn btn-primary" style={{ width: '100%' }}>Create Rule</button></div>
                        </form>
                    </div>
                )}

                {loading ? (
                    <div className="loading-overlay"><div className="loading-spinner" /></div>
                ) : rules.length === 0 ? (
                    <div className="card"><div className="empty-state"><div className="empty-state-icon">R</div><div className="empty-state-text">No notification rules configured</div><div className="empty-state-hint">Create rules to get alerts when metrics exceed thresholds</div></div></div>
                ) : (
                    <div className="card">
                        <table className="data-table">
                            <thead><tr><th>Name</th><th>Metric</th><th>Condition</th><th>Duration</th><th>Status</th><th>Actions</th></tr></thead>
                            <tbody>{rules.map(r => (
                                <tr key={r.id}>
                                    <td style={{ fontWeight: 600 }}>{r.name}</td>
                                    <td><span className="badge info">{r.metric_name}</span></td>
                                    <td>{r.operator} {r.threshold}%</td>
                                    <td>{r.duration_minutes}m</td>
                                    <td><span className={`badge ${r.enabled ? 'active' : 'error'}`}><span className="badge-dot" />{r.enabled ? 'Active' : 'Disabled'}</span></td>
                                    <td style={{ display: 'flex', gap: 6 }}>
                                        <button className="btn btn-sm btn-secondary" onClick={() => handleToggle(r.id, r.enabled)}>{r.enabled ? 'Disable' : 'Enable'}</button>
                                        <button className="btn btn-sm btn-secondary" onClick={() => handleDelete(r.id)} style={{ color: 'var(--color-error)' }}>Delete</button>
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
