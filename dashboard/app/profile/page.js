'use client';

import { useState } from 'react';
import { useAuth } from '../components/AuthProvider';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8080';

export default function ProfilePage() {
    const { user } = useAuth();
    const [form, setForm] = useState({ current_password: '', new_password: '', confirm_password: '' });
    const [message, setMessage] = useState('');
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(false);

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

    return (
        <>
            <div className="main-header"><h2>Profile</h2></div>
            <div className="main-body">
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
            </div>
        </>
    );
}
