'use client';

import { useState, useEffect, useCallback } from 'react';
import { useAuth } from '../components/AuthProvider';

const API_BASE = '';

async function api(endpoint, opts = {}) {
    const token = typeof window !== 'undefined' ? localStorage.getItem('insight_token') : null;
    const headers = { 'Content-Type': 'application/json', ...opts.headers };
    if (token) headers['Authorization'] = `Bearer ${token}`;
    const res = await fetch(`${API_BASE}${endpoint}`, { headers, ...opts });
    if (res.status === 403) throw new Error('Not authorized');
    if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || 'Error'); }
    return res.json();
}

export default function UsersPage() {
    const { user: currentUser } = useAuth();
    const [users, setUsers] = useState([]);
    const [loading, setLoading] = useState(true);
    const [showForm, setShowForm] = useState(false);
    const [form, setForm] = useState({ username: '', password: '', role: 'viewer' });
    const [error, setError] = useState('');

    const fetchUsers = useCallback(async () => {
        try { const d = await api('/api/v1/users'); setUsers(d.users || []); }
        catch (err) { setError(err.message); }
        finally { setLoading(false); }
    }, []);

    useEffect(() => { fetchUsers(); }, [fetchUsers]);

    const handleCreate = async (e) => {
        e.preventDefault();
        setError('');
        try {
            await api('/api/v1/users', { method: 'POST', body: JSON.stringify(form) });
            setShowForm(false);
            setForm({ username: '', password: '', role: 'viewer' });
            fetchUsers();
        } catch (err) { setError(err.message); }
    };

    const handleDelete = async (id, username) => {
        if (!confirm(`Delete user "${username}"?`)) return;
        try { await api(`/api/v1/users/${id}`, { method: 'DELETE' }); fetchUsers(); }
        catch (err) { setError(err.message); }
    };

    const roleColors = { admin: 'var(--color-error)', operator: 'var(--blue)', viewer: 'var(--color-success)' };

    if (currentUser?.role !== 'admin') {
        return (
            <>
                <div className="main-header"><h2>Users</h2></div>
                <div className="main-body"><div className="card"><div className="empty-state"><div className="empty-state-icon">X</div><div className="empty-state-text">Admin access required</div></div></div></div>
            </>
        );
    }

    return (
        <>
            <div className="main-header">
                <h2>User Management</h2>
                <div className="header-actions">
                    <button className="btn btn-primary" onClick={() => setShowForm(!showForm)}>{showForm ? 'Cancel' : '+ New User'}</button>
                </div>
            </div>
            <div className="main-body">
                {error && <div className="login-error" style={{ marginBottom: 16 }}>{error}</div>}

                {showForm && (
                    <div className="card" style={{ marginBottom: 24 }}>
                        <div className="card-header"><div><div className="card-title">Create User</div></div></div>
                        <form onSubmit={handleCreate} style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr auto', gap: 16, padding: '0 16px 16px', alignItems: 'end' }}>
                            <div className="form-group"><label className="form-label">Username</label>
                                <input className="form-input" value={form.username} onChange={e => setForm({ ...form, username: e.target.value })} required /></div>
                            <div className="form-group"><label className="form-label">Password</label>
                                <input type="password" className="form-input" value={form.password} onChange={e => setForm({ ...form, password: e.target.value })} required /></div>
                            <div className="form-group"><label className="form-label">Role</label>
                                <select className="form-input" value={form.role} onChange={e => setForm({ ...form, role: e.target.value })}>
                                    <option value="admin">Admin</option><option value="operator">Operator</option><option value="viewer">Viewer</option>
                                </select></div>
                            <button type="submit" className="btn btn-primary">Create</button>
                        </form>
                    </div>
                )}

                {loading ? <div className="loading-overlay"><div className="loading-spinner" /></div> : (
                    <div className="card">
                        <table className="data-table">
                            <thead><tr><th>Username</th><th>Role</th><th>Created</th><th>Actions</th></tr></thead>
                            <tbody>{users.map(u => (
                                <tr key={u.id}>
                                    <td style={{ fontWeight: 600 }}>{u.username}</td>
                                    <td><span className="badge" style={{ background: (roleColors[u.role] || '#666') + '18', color: roleColors[u.role] || '#666' }}>{u.role}</span></td>
                                    <td>{u.created_at?.slice(0, 10)}</td>
                                    <td>{u.id !== currentUser?.id && (
                                        <button className="btn btn-sm btn-secondary" onClick={() => handleDelete(u.id, u.username)} style={{ color: 'var(--color-error)' }}>Delete</button>
                                    )}</td>
                                </tr>
                            ))}</tbody>
                        </table>
                    </div>
                )}
            </div>
        </>
    );
}
