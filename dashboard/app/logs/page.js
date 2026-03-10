'use client';

import { useState, useEffect, useCallback } from 'react';
import { getLogs } from '../lib/api';
import { timeAgo } from '../lib/hooks';

export default function LogsPage() {
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(true);

    const fetchData = useCallback(async () => {
        try {
            const result = await getLogs({ last_hours: 24, limit: 200 });
            setData(result);
        } catch (err) {
            console.error(err);
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        fetchData();
        const interval = setInterval(fetchData, 15000);
        return () => clearInterval(interval);
    }, [fetchData]);

    const logs = data?.logs || [];

    return (
        <>
            <div className="main-header">
                <h2>Error Logs</h2>
                <div className="header-actions">
                    <button className="btn btn-secondary" onClick={fetchData}>🔄 Refresh</button>
                </div>
            </div>
            <div className="main-body">
                {loading ? (
                    <div className="loading-overlay"><div className="loading-spinner" /><span>Loading logs...</span></div>
                ) : logs.length === 0 ? (
                    <div className="empty-state">
                        <div className="empty-state-icon">✅</div>
                        <div className="empty-state-text">No error logs</div>
                        <p style={{ color: 'var(--text-muted)', fontSize: '13px' }}>All pods are running without errors</p>
                    </div>
                ) : (
                    <div className="card">
                        <div className="card-header">
                            <div className="card-title">{logs.length} error log entries</div>
                        </div>
                        <table className="data-table">
                            <thead>
                                <tr>
                                    <th>Namespace</th>
                                    <th>Pod</th>
                                    <th>Container</th>
                                    <th>Level</th>
                                    <th>Message</th>
                                    <th>Time</th>
                                </tr>
                            </thead>
                            <tbody>
                                {logs.map((log, i) => (
                                    <tr key={log.id || i}>
                                        <td><span className="badge info">{log.namespace || '—'}</span></td>
                                        <td style={{ fontFamily: 'monospace', fontSize: '13px' }}>{log.pod_name || '—'}</td>
                                        <td style={{ fontSize: '13px' }}>{log.container || '—'}</td>
                                        <td><span className="badge error">{log.log_level}</span></td>
                                        <td>
                                            <div style={{ maxWidth: '400px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontSize: '13px', fontFamily: 'monospace' }}>
                                                {log.message?.slice(0, 200) || '—'}
                                            </div>
                                        </td>
                                        <td style={{ fontSize: '13px', whiteSpace: 'nowrap' }}>{timeAgo(log.timestamp)}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </div>
        </>
    );
}
