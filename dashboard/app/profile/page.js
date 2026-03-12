'use client';

import { useState, useEffect, useCallback } from 'react';
import { useAuth } from '../components/AuthProvider';
import { timeAgo } from '../lib/hooks';

const API_BASE = '';

export default function ProfilePage() {
    const { user } = useAuth();
    const [tab, setTab] = useState('account');
    const [form, setForm] = useState({ current_password: '', new_password: '', confirm_password: '' });
    const [message, setMessage] = useState('');
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(false);

    // Audit state
    const [auditLogs, setAuditLogs] = useState([]);
    const [auditLoading, setAuditLoading] = useState(true);

    const fetchAudit = useCallback(async () => {
        try {
            const token = localStorage.getItem('insight_token');
            const headers = { 'Content-Type': 'application/json' };
            if (token) headers['Authorization'] = `Bearer ${token}`;
            const res = await fetch(`${API_BASE}/api/v1/audit?last_hours=168&limit=100`, { headers });
            const data = await res.json();
            setAuditLogs(data?.logs || []);
        } catch (err) { console.error(err); }
        finally { setAuditLoading(false); }
    }, []);

    useEffect(() => { fetchAudit(); }, [fetchAudit]);

    const handleSubmit = async (e) => {
        e.preventDefault();
        setError(''); setMessage('');
        if (form.new_password !== form.confirm_password) { setError('New passwords do not match'); return; }
        if (form.new_password.length < 6) { setError('Password must be at least 6 characters'); return; }
        setLoading(true);
        try {
            const token = localStorage.getItem('insight_token');
            const res = await fetch(`${API_BASE}/api/v1/auth/password`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
                body: JSON.stringify({ current_password: form.current_password, new_password: form.new_password }),
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Failed');
            setMessage('Password changed successfully');
            setForm({ current_password: '', new_password: '', confirm_password: '' });
        } catch (err) { setError(err.message); }
        finally { setLoading(false); }
    };

    const actionColors = {
        login: '#15803d',
        create_cluster: '#0165a7',
        update_settings: '#b45309',
        create_alert: '#7c3aed',
        delete_rule: '#dc2626',
    };

    return (
        <>
            <div className="main-header"><h2>Profile</h2></div>
            <div className="main-body">
                {/* Tabs */}
                <div style={{ display: 'flex', gap: 8, marginBottom: 20 }}>
                    <button className={`btn ${tab === 'account' ? 'btn-primary' : 'btn-secondary'}`} onClick={() => setTab('account')}>
                        Account
                    </button>
                    <button className={`btn ${tab === 'audit' ? 'btn-primary' : 'btn-secondary'}`} onClick={() => setTab('audit')}>
                        Audit Log
                    </button>
                </div>

                {/* ─── Account Tab ─── */}
                {tab === 'account' && (
                    <div className="grid-2">
                        <div className="card">
                            <div className="card-header"><div><div className="card-title">Account Info</div></div></div>
                            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                                <div><span style={{ fontSize: 13, color: 'var(--text-muted)' }}>Username</span><div style={{ fontWeight: 600, fontSize: 18 }}>{user?.username || '-'}</div></div>
                                <div><span style={{ fontSize: 13, color: 'var(--text-muted)' }}>Role</span><div><span className="badge info">{user?.role || 'viewer'}</span></div></div>
                            </div>
                        </div>

                        <div className="card">
                            <div className="card-header"><div><div className="card-title">Change Password</div></div></div>
                            {message && <div style={{ background: 'var(--color-success-bg)', borderRadius: 8, padding: '10px 14px', color: 'var(--color-success)', fontSize: 13, marginBottom: 16 }}>{message}</div>}
                            {error && <div className="login-error" style={{ marginBottom: 16 }}>{error}</div>}
                            <form onSubmit={handleSubmit}>
                                <div className="form-group"><label className="form-label">Current Password</label>
                                    <input type="password" className="form-input" value={form.current_password} onChange={e => setForm({ ...form, current_password: e.target.value })} required /></div>
                                <div className="form-group"><label className="form-label">New Password</label>
                                    <input type="password" className="form-input" value={form.new_password} onChange={e => setForm({ ...form, new_password: e.target.value })} required /></div>
                                <div className="form-group"><label className="form-label">Confirm New Password</label>
                                    <input type="password" className="form-input" value={form.confirm_password} onChange={e => setForm({ ...form, confirm_password: e.target.value })} required /></div>
                                <button className="btn btn-primary" type="submit" disabled={loading}>{loading ? 'Changing...' : 'Change Password'}</button>
                            </form>
                        </div>
                    </div>
                )}

                {/* ─── Audit Log Tab ─── */}
                {tab === 'audit' && (
                    <>
                        <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 16 }}>
                            <button className="btn btn-secondary" onClick={() => { setAuditLoading(true); fetchAudit(); }}>Refresh</button>
                        </div>
                        {auditLoading ? (
                            <div className="loading-overlay"><div className="loading-spinner" /></div>
                        ) : auditLogs.length === 0 ? (
                            <div className="card"><div className="empty-state"><div className="empty-state-icon">A</div><div className="empty-state-text">No audit entries</div></div></div>
                        ) : (
                            <div className="card">
                                <table className="data-table">
                                    <thead><tr><th>Time</th><th>User</th><th>Action</th><th>Resource</th><th>IP</th></tr></thead>
                                    <tbody>{auditLogs.map((l, i) => (
                                        <tr key={l.id || i}>
                                            <td style={{ whiteSpace: 'nowrap' }}>{timeAgo(l.timestamp)}</td>
                                            <td style={{ fontWeight: 600 }}>{l.username || 'system'}</td>
                                            <td><span className="badge" style={{ background: (actionColors[l.action] || '#666') + '22', color: actionColors[l.action] || '#666' }}>{l.action}</span></td>
                                            <td style={{ maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis' }}>{l.resource || '-'}</td>
                                            <td style={{ fontFamily: 'monospace', fontSize: 12 }}>{l.ip || '-'}</td>
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
