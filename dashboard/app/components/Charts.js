'use client';

import { useState, useEffect, useCallback } from 'react';
import {
    LineChart, Line, AreaChart, Area, BarChart, Bar,
    XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Legend,
    PieChart, Pie, Cell
} from 'recharts';
import { getChartMetrics, getChartEvents } from '../lib/api';

const COLORS = {
    cpu: '#0165a7',
    memory: '#e6a800',
    disk: '#d4380d',
    critical: '#991b1b',
    error: '#dc2626',
    warning: '#b45309',
    info: '#0165a7',
};

const chartTooltipStyle = {
    backgroundColor: 'rgba(255,250,220,0.95)',
    border: '1px solid rgba(201,177,0,0.3)',
    borderRadius: '8px',
    fontSize: '12px',
    color: '#1a1a1a',
};

// ─── Metrics Line Chart ───
export function MetricsLineChart({ agentId = null, lastHours = 6, height = 280 }) {
    const [data, setData] = useState([]);
    const [loading, setLoading] = useState(true);

    const fetchData = useCallback(async () => {
        try {
            const params = { last_hours: lastHours, metric_names: 'cpu_percent,memory_percent,disk_percent' };
            if (agentId) params.agent_id = agentId;
            const result = await getChartMetrics(params);
            setData(result?.timeseries || []);
        } catch (err) {
            console.error('Chart data error:', err);
        } finally {
            setLoading(false);
        }
    }, [agentId, lastHours]);

    useEffect(() => {
        fetchData();
        const interval = setInterval(fetchData, 30000);
        return () => clearInterval(interval);
    }, [fetchData]);

    if (loading) {
        return <div style={{ height, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)' }}>
            <div className="loading-spinner" style={{ marginRight: 8 }} /> Loading chart...
        </div>;
    }

    if (data.length === 0) {
        return <div style={{ height, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)', fontSize: 14 }}>
            No metrics data available. Deploy agents to start collecting metrics.
        </div>;
    }

    const formatTime = (t) => {
        if (!t) return '';
        const parts = t.split('T');
        return parts.length > 1 ? parts[1] : t.slice(11);
    };

    return (
        <ResponsiveContainer width="100%" height={height}>
            <AreaChart data={data} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
                <defs>
                    <linearGradient id="gradCpu" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor={COLORS.cpu} stopOpacity={0.15} />
                        <stop offset="95%" stopColor={COLORS.cpu} stopOpacity={0} />
                    </linearGradient>
                    <linearGradient id="gradMem" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor={COLORS.memory} stopOpacity={0.15} />
                        <stop offset="95%" stopColor={COLORS.memory} stopOpacity={0} />
                    </linearGradient>
                    <linearGradient id="gradDisk" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor={COLORS.disk} stopOpacity={0.15} />
                        <stop offset="95%" stopColor={COLORS.disk} stopOpacity={0} />
                    </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(201,177,0,0.15)" />
                <XAxis dataKey="time" tickFormatter={formatTime} tick={{ fontSize: 11, fill: '#7a7050' }} />
                <YAxis domain={[0, 100]} tick={{ fontSize: 11, fill: '#7a7050' }} tickFormatter={(v) => `${v}%`} />
                <Tooltip
                    contentStyle={chartTooltipStyle}
                    formatter={(value, name) => [`${value}%`, name.replace('_', ' ').replace('percent', '').trim()]}
                    labelFormatter={formatTime}
                />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Area type="monotone" dataKey="cpu_percent" name="CPU" stroke={COLORS.cpu} fill="url(#gradCpu)" strokeWidth={2} dot={false} />
                <Area type="monotone" dataKey="memory_percent" name="Memory" stroke={COLORS.memory} fill="url(#gradMem)" strokeWidth={2} dot={false} />
                <Area type="monotone" dataKey="disk_percent" name="Disk" stroke={COLORS.disk} fill="url(#gradDisk)" strokeWidth={2} dot={false} />
            </AreaChart>
        </ResponsiveContainer>
    );
}

// ─── Events Bar Chart ───
export function EventsBarChart({ lastHours = 24, height = 220 }) {
    const [data, setData] = useState([]);
    const [loading, setLoading] = useState(true);

    const fetchData = useCallback(async () => {
        try {
            const result = await getChartEvents({ last_hours: lastHours });
            setData(result?.timeseries || []);
        } catch (err) {
            console.error('Event chart error:', err);
        } finally {
            setLoading(false);
        }
    }, [lastHours]);

    useEffect(() => {
        fetchData();
        const interval = setInterval(fetchData, 60000);
        return () => clearInterval(interval);
    }, [fetchData]);

    if (loading) {
        return <div style={{ height, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)' }}>
            <div className="loading-spinner" style={{ marginRight: 8 }} /> Loading...
        </div>;
    }

    if (data.length === 0) {
        return <div style={{ height, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)', fontSize: 14 }}>
            No events in the last {lastHours}h
        </div>;
    }

    const formatHour = (h) => h ? h.slice(11, 16) : '';

    return (
        <ResponsiveContainer width="100%" height={height}>
            <BarChart data={data} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(201,177,0,0.15)" />
                <XAxis dataKey="hour" tickFormatter={formatHour} tick={{ fontSize: 11, fill: '#7a7050' }} />
                <YAxis tick={{ fontSize: 11, fill: '#7a7050' }} allowDecimals={false} />
                <Tooltip contentStyle={chartTooltipStyle} labelFormatter={formatHour} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Bar dataKey="critical" name="Critical" fill={COLORS.critical} radius={[3, 3, 0, 0]} />
                <Bar dataKey="error" name="Error" fill={COLORS.error} radius={[3, 3, 0, 0]} />
                <Bar dataKey="warning" name="Warning" fill={COLORS.warning} radius={[3, 3, 0, 0]} />
                <Bar dataKey="info" name="Info" fill={COLORS.info} radius={[3, 3, 0, 0]} />
            </BarChart>
        </ResponsiveContainer>
    );
}

// ─── System Health Donut ───
export function HealthDonut({ agents = [], size = 160 }) {
    const active = agents.filter(a => a.status === 'active').length;
    const inactive = agents.length - active;

    const data = [
        { name: 'Active', value: active || 0 },
        { name: 'Inactive', value: inactive || 0 },
    ];

    const colors = ['#15803d', '#dc2626'];

    if (agents.length === 0) {
        return <div style={{ width: size, height: size, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)', fontSize: 13 }}>
            No agents
        </div>;
    }

    return (
        <div style={{ position: 'relative', width: size, height: size }}>
            <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                    <Pie
                        data={data}
                        cx="50%" cy="50%"
                        innerRadius={size * 0.32}
                        outerRadius={size * 0.45}
                        paddingAngle={2}
                        dataKey="value"
                        stroke="none"
                    >
                        {data.map((entry, i) => (
                            <Cell key={entry.name} fill={colors[i]} />
                        ))}
                    </Pie>
                    <Tooltip contentStyle={chartTooltipStyle} />
                </PieChart>
            </ResponsiveContainer>
            <div style={{
                position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%, -50%)',
                textAlign: 'center', lineHeight: 1.3,
            }}>
                <div style={{ fontSize: 24, fontWeight: 800, color: 'var(--text-primary)' }}>{active}</div>
                <div style={{ fontSize: 10, color: 'var(--text-muted)', fontWeight: 600 }}>ACTIVE</div>
            </div>
        </div>
    );
}
