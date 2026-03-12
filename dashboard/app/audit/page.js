'use client';

import { useState, useEffect, useCallback } from 'react';
import { timeAgo } from '../lib/hooks';

const API_BASE = '';

export default function AuditPage() {
    const [logs, setLogs] = useState([]);
    const [loading, setLoading] = useState(true);

    const fetchLogs = useCallback(async () => {
        try {
            const token = localStorage.getItem('insight_token');
            const headers = { 'Content-Type': 'application/json' };
            if (token) headers['Authorization'] = `Bearer ${token}`;
            const res = await fetch(`${API_BASE}/api/v1/audit?last_hours=168&limit=100`, { headers });
            const data = await res.json();
            setLogs(data?.logs || []);
        } catch (err) { console.error(err); }
        finally { setLoading(false); }
    }, []);

    useEffect(() => { fetchLogs(); }, [fetchLogs]);

    const actionColors = {
        login: '#15803d',
        create_cluster: '#0165a7',
        update_settings: '#b45309',
        create_alert: '#7c3aed',
        delete_rule: '#dc2626',
    };

    return (
        <>
            <div className="main-header">
                <h2>Audit Log</h2>
                <div className="header-actions">
                    <button className="btn btn-secondary" onClick={() => { setLoading(true); fetchLogs(); }}>Refresh</button>
                </div>
            </div>
            <div className="main-body">
                {loading ? (
                    <div className="loading-overlay"><div className="loading-spinner" /></div>
                ) : logs.length === 0 ? (
                    <div className="card"><div className="empty-state"><div className="empty-state-icon">A</div><div className="empty-state-text">No audit entries</div></div></div>
                ) : (
                    <div className="card">
                        <table className="data-table">
                            <thead><tr><th>Time</th><th>User</th><th>Action</th><th>Resource</th><th>IP</th></tr></thead>
                            <tbody>{logs.map((l, i) => (
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
            </div>
        </>
    );
}
