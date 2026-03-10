'use client';

import { useState, useEffect, useCallback } from 'react';
import { getReports, generateReport } from '../lib/api';
import { formatDate } from '../lib/hooks';

export default function ReportsPage() {
    const [reports, setReports] = useState([]);
    const [loading, setLoading] = useState(true);
    const [sending, setSending] = useState(false);
    const [sendResult, setSendResult] = useState(null);
    const [selectedChannels, setSelectedChannels] = useState(['telegram']);

    const fetchData = useCallback(async () => {
        try {
            const result = await getReports(20);
            setReports(result?.reports || []);
        } catch (err) {
            console.error(err);
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => { fetchData(); }, [fetchData]);

    const handleGenerate = async () => {
        setSending(true);
        setSendResult(null);
        try {
            const result = await generateReport(selectedChannels);
            setSendResult({ success: true, message: `Report generated and sent to: ${result.sent_to?.join(', ') || 'none (no alert configs)'}` });
            fetchData();
        } catch (err) {
            setSendResult({ success: false, message: err.message });
        } finally {
            setSending(false);
        }
    };

    const toggleChannel = (ch) => {
        setSelectedChannels(prev =>
            prev.includes(ch) ? prev.filter(c => c !== ch) : [...prev, ch]
        );
    };

    return (
        <>
            <div className="main-header">
                <h2>Reports</h2>
            </div>
            <div className="main-body">
                {/* Generate Report */}
                <div className="card" style={{ marginBottom: '24px' }}>
                    <div className="card-header">
                        <div className="card-title">📤 Gửi Báo cáo</div>
                    </div>
                    <p style={{ color: 'var(--text-secondary)', fontSize: '14px', marginBottom: '16px' }}>
                        Tạo báo cáo tổng hợp từ tất cả dữ liệu hiện có và gửi qua các kênh đã chọn.
                    </p>

                    <div style={{ display: 'flex', gap: '12px', marginBottom: '16px' }}>
                        {['telegram', 'email', 'webhook'].map(ch => (
                            <label key={ch} style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer' }}>
                                <input
                                    type="checkbox"
                                    checked={selectedChannels.includes(ch)}
                                    onChange={() => toggleChannel(ch)}
                                    style={{ accentColor: 'var(--accent-primary)' }}
                                />
                                <span style={{ fontSize: '14px', textTransform: 'capitalize' }}>
                                    {ch === 'telegram' ? '📱 Telegram' : ch === 'email' ? '📧 Email' : '🔗 Webhook'}
                                </span>
                            </label>
                        ))}
                    </div>

                    <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
                        <button className="btn btn-primary" onClick={handleGenerate} disabled={sending || selectedChannels.length === 0}>
                            {sending ? <><div className="loading-spinner" /> Generating...</> : '📊 Generate & Send Report'}
                        </button>
                        {sendResult && (
                            <span style={{ fontSize: '13px', color: sendResult.success ? 'var(--color-success)' : 'var(--color-error)' }}>
                                {sendResult.message}
                            </span>
                        )}
                    </div>
                </div>

                {/* Report History */}
                <div className="card">
                    <div className="card-header">
                        <div className="card-title">Report History</div>
                    </div>
                    {loading ? (
                        <div className="loading-overlay"><div className="loading-spinner" /></div>
                    ) : reports.length === 0 ? (
                        <div className="empty-state">
                            <div className="empty-state-icon">📋</div>
                            <div className="empty-state-text">No reports generated yet</div>
                        </div>
                    ) : (
                        <table className="data-table">
                            <thead>
                                <tr>
                                    <th>Type</th>
                                    <th>Generated</th>
                                    <th>Sent To</th>
                                    <th>Summary</th>
                                </tr>
                            </thead>
                            <tbody>
                                {reports.map((report, i) => (
                                    <tr key={report.id || i}>
                                        <td><span className="badge info">{report.report_type}</span></td>
                                        <td style={{ fontSize: '13px' }}>{formatDate(report.generated_at)}</td>
                                        <td>
                                            {(report.sent_to || []).map(ch => (
                                                <span key={ch} className="badge success" style={{ marginRight: '4px' }}>{ch}</span>
                                            ))}
                                            {(!report.sent_to || report.sent_to.length === 0) && <span style={{ color: 'var(--text-muted)' }}>—</span>}
                                        </td>
                                        <td style={{ fontSize: '13px' }}>
                                            {report.content?.summary ? (
                                                <>
                                                    Agents: {report.content.summary.total_agents} |
                                                    Events: {report.content.summary.total_events} |
                                                    Critical: {report.content.summary.critical_events}
                                                </>
                                            ) : '—'}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    )}
                </div>
            </div>
        </>
    );
}
