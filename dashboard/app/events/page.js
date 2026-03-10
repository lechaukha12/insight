'use client';

import { useState, useEffect, useCallback } from 'react';
import { getEvents, acknowledgeEvent } from '../lib/api';
import { timeAgo } from '../lib/hooks';

export default function EventsPage() {
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [filter, setFilter] = useState('all');

    const fetchData = useCallback(async () => {
        try {
            const params = { last_hours: 24, limit: 100 };
            if (filter !== 'all') params.level = filter;
            const result = await getEvents(params);
            setData(result);
        } catch (err) {
            console.error(err);
        } finally {
            setLoading(false);
        }
    }, [filter]);

    useEffect(() => {
        fetchData();
        const interval = setInterval(fetchData, 10000);
        return () => clearInterval(interval);
    }, [fetchData]);

    const handleAcknowledge = async (eventId) => {
        try {
            await acknowledgeEvent(eventId);
            fetchData();
        } catch (err) {
            console.error(err);
        }
    };

    const events = data?.events || [];
    const levelIcon = { critical: '🔴', error: '❌', warning: '⚠️', info: 'ℹ️' };

    return (
        <>
            <div className="main-header">
                <h2>Events & Alerts</h2>
                <div className="header-actions">
                    {['all', 'critical', 'error', 'warning', 'info'].map(level => (
                        <button
                            key={level}
                            className={`btn btn-sm ${filter === level ? 'btn-primary' : 'btn-secondary'}`}
                            onClick={() => { setFilter(level); setLoading(true); }}
                        >
                            {level === 'all' ? 'All' : `${levelIcon[level]} ${level}`}
                        </button>
                    ))}
                </div>
            </div>
            <div className="main-body">
                {loading ? (
                    <div className="loading-overlay"><div className="loading-spinner" /><span>Loading events...</span></div>
                ) : events.length === 0 ? (
                    <div className="empty-state">
                        <div className="empty-state-icon">✅</div>
                        <div className="empty-state-text">No events found</div>
                    </div>
                ) : (
                    <div className="card">
                        <div className="card-header">
                            <div className="card-title">{events.length} events</div>
                        </div>
                        {events.map((event, i) => (
                            <div key={event.id || i} className="event-item">
                                <div className={`event-icon ${event.level}`}>
                                    {levelIcon[event.level] || '📋'}
                                </div>
                                <div className="event-content">
                                    <div className="event-title">
                                        <span className={`badge ${event.level}`} style={{ marginRight: '8px', fontSize: '11px' }}>{event.level}</span>
                                        {event.title}
                                    </div>
                                    <div className="event-message">{event.message}</div>
                                    {event.namespace && (
                                        <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '4px' }}>
                                            📍 {event.namespace} / {event.resource || '—'} &nbsp;|&nbsp; Source: {event.source || '—'}
                                        </div>
                                    )}
                                </div>
                                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '6px' }}>
                                    <div className="event-time">{timeAgo(event.created_at)}</div>
                                    {!event.acknowledged && (
                                        <button className="btn btn-sm btn-secondary" onClick={() => handleAcknowledge(event.id)}>
                                            ✓ Ack
                                        </button>
                                    )}
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </div>
        </>
    );
}
