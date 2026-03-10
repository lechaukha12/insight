'use client';

import { useState, useEffect, useCallback } from 'react';
import { getAlertConfigs, createAlertConfig, deleteAlertConfig, getSettings, updateSettings } from '../lib/api';

export default function SettingsPage() {
    const [configs, setConfigs] = useState([]);
    const [settings, setSettings] = useState({});
    const [loading, setLoading] = useState(true);
    const [newConfig, setNewConfig] = useState({ channel: 'telegram', bot_token: '', chat_id: '' });
    const [saving, setSaving] = useState(false);
    const [message, setMessage] = useState(null);

    const fetchData = useCallback(async () => {
        try {
            const [alertData, settingsData] = await Promise.all([getAlertConfigs(), getSettings()]);
            setConfigs(alertData?.configs || []);
            setSettings(settingsData || {});
        } catch (err) {
            console.error(err);
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => { fetchData(); }, [fetchData]);

    const handleAddTelegram = async () => {
        setSaving(true);
        try {
            await createAlertConfig({
                channel: 'telegram',
                config: { bot_token: newConfig.bot_token, chat_id: newConfig.chat_id },
                enabled: true,
                alert_levels: ['critical', 'error'],
            });
            setNewConfig({ channel: 'telegram', bot_token: '', chat_id: '' });
            setMessage({ type: 'success', text: 'Telegram config added!' });
            fetchData();
        } catch (err) {
            setMessage({ type: 'error', text: err.message });
        } finally {
            setSaving(false);
        }
    };

    const handleAddEmail = async () => {
        setSaving(true);
        try {
            await createAlertConfig({
                channel: 'email',
                config: {
                    smtp_host: newConfig.smtp_host || '',
                    smtp_port: parseInt(newConfig.smtp_port || '587'),
                    username: newConfig.email_user || '',
                    password: newConfig.email_pass || '',
                    from_addr: newConfig.from_addr || '',
                    to_addrs: (newConfig.to_addrs || '').split(',').map(s => s.trim()),
                },
                enabled: true,
                alert_levels: ['critical', 'error'],
            });
            setMessage({ type: 'success', text: 'Email config added!' });
            fetchData();
        } catch (err) {
            setMessage({ type: 'error', text: err.message });
        } finally {
            setSaving(false);
        }
    };

    const handleDelete = async (id) => {
        try {
            await deleteAlertConfig(id);
            fetchData();
        } catch (err) {
            console.error(err);
        }
    };

    const handleAutoReportToggle = async () => {
        const current = settings.auto_report || {};
        const updated = { ...current, enabled: !current.enabled };
        try {
            await updateSettings({ auto_report: updated });
            setSettings(prev => ({ ...prev, auto_report: updated }));
        } catch (err) {
            console.error(err);
        }
    };

    if (loading) return (
        <>
            <div className="main-header"><h2>Settings</h2></div>
            <div className="main-body"><div className="loading-overlay"><div className="loading-spinner" /></div></div>
        </>
    );

    return (
        <>
            <div className="main-header">
                <h2>Settings</h2>
            </div>
            <div className="main-body">
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
                    {/* Alert Channels */}
                    <div className="card">
                        <div className="card-header">
                            <div className="card-title">🔔 Kênh Cảnh báo</div>
                        </div>

                        {configs.length > 0 && (
                            <div style={{ marginBottom: '20px' }}>
                                {configs.map(cfg => (
                                    <div key={cfg.id} style={{
                                        display: 'flex', alignItems: 'center', gap: '12px', padding: '12px',
                                        background: 'var(--bg-input)', borderRadius: 'var(--radius-sm)', marginBottom: '8px',
                                    }}>
                                        <span style={{ fontSize: '20px' }}>
                                            {cfg.channel === 'telegram' ? '📱' : cfg.channel === 'email' ? '📧' : '🔗'}
                                        </span>
                                        <div style={{ flex: 1 }}>
                                            <div style={{ fontWeight: 600, textTransform: 'capitalize' }}>{cfg.channel}</div>
                                            <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                                                Levels: {cfg.alert_levels?.join(', ')}
                                            </div>
                                        </div>
                                        <span className={`badge ${cfg.enabled ? 'active' : 'inactive'}`}>{cfg.enabled ? 'Active' : 'Off'}</span>
                                        <button className="btn btn-sm btn-danger" onClick={() => handleDelete(cfg.id)}>🗑</button>
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
                                    onChange={e => setNewConfig(p => ({ ...p, bot_token: e.target.value }))}
                                />
                            </div>
                            <div className="form-group">
                                <label className="form-label">Chat ID</label>
                                <input className="form-input" placeholder="-100123456789"
                                    value={newConfig.chat_id}
                                    onChange={e => setNewConfig(p => ({ ...p, chat_id: e.target.value }))}
                                />
                            </div>
                            <button className="btn btn-primary btn-sm" onClick={handleAddTelegram} disabled={saving || !newConfig.bot_token || !newConfig.chat_id}>
                                {saving ? 'Saving...' : '+ Add Telegram'}
                            </button>
                        </div>
                    </div>

                    {/* Auto Report Settings */}
                    <div className="card">
                        <div className="card-header">
                            <div className="card-title">📊 Báo cáo Tự động</div>
                        </div>

                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '20px' }}>
                            <div>
                                <div style={{ fontWeight: 600 }}>Auto Daily Report</div>
                                <div style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
                                    Gửi báo cáo tự động mỗi ngày lúc 7:45 AM
                                </div>
                            </div>
                            <label className="toggle">
                                <input type="checkbox"
                                    checked={settings.auto_report?.enabled || false}
                                    onChange={handleAutoReportToggle}
                                />
                                <span className="toggle-slider" />
                            </label>
                        </div>

                        <div className="form-group">
                            <label className="form-label">Schedule (Cron)</label>
                            <input className="form-input" value={settings.auto_report?.schedule || '45 0 * * *'} readOnly
                                style={{ fontFamily: 'monospace' }}
                            />
                            <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '4px' }}>
                                7:45 AM UTC+7 hàng ngày
                            </div>
                        </div>

                        <div className="form-group">
                            <label className="form-label">Alert Dedup (minutes)</label>
                            <input className="form-input" type="number" value={settings.alert_dedup_minutes || 5} readOnly />
                            <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '4px' }}>
                                Không gửi cùng alert trong khoảng thời gian này
                            </div>
                        </div>

                        <div className="form-group">
                            <label className="form-label">Metric Retention (days)</label>
                            <input className="form-input" type="number" value={settings.metric_retention_days || 30} readOnly />
                        </div>
                    </div>
                </div>
            </div>
        </>
    );
}
