/**
 * Insight Dashboard - API Client
 * Handles all communication with the Insight Core API
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8080';

async function fetchAPI(endpoint, options = {}) {
    const url = `${API_BASE}${endpoint}`;
    const res = await fetch(url, {
        headers: { 'Content-Type': 'application/json', ...options.headers },
        ...options,
    });
    if (!res.ok) {
        throw new Error(`API error: ${res.status} ${res.statusText}`);
    }
    return res.json();
}

// ─── Dashboard ───

export async function getDashboardSummary() {
    return fetchAPI('/api/v1/dashboard/summary');
}

// ─── Agents ───

export async function getAgents() {
    return fetchAPI('/api/v1/agents');
}

export async function getAgent(agentId) {
    return fetchAPI(`/api/v1/agents/${agentId}`);
}

export async function registerAgent(data) {
    return fetchAPI('/api/v1/agents/register', {
        method: 'POST',
        body: JSON.stringify(data),
    });
}

// ─── Metrics ───

export async function getMetrics(params = {}) {
    const query = new URLSearchParams(params).toString();
    return fetchAPI(`/api/v1/metrics?${query}`);
}

export async function getChartMetrics(params = {}) {
    const query = new URLSearchParams(params).toString();
    return fetchAPI(`/api/v1/charts/metrics?${query}`);
}

export async function getChartEvents(params = {}) {
    const query = new URLSearchParams(params).toString();
    return fetchAPI(`/api/v1/charts/events?${query}`);
}


export async function getEvents(params = {}) {
    const query = new URLSearchParams(params).toString();
    return fetchAPI(`/api/v1/events?${query}`);
}

export async function acknowledgeEvent(eventId) {
    return fetchAPI(`/api/v1/events/${eventId}/acknowledge`, { method: 'POST' });
}

// ─── Logs ───

export async function getLogs(params = {}) {
    const query = new URLSearchParams(params).toString();
    return fetchAPI(`/api/v1/logs?${query}`);
}

// ─── Reports ───

export async function generateReport(channels = ['telegram']) {
    return fetchAPI('/api/v1/reports/generate', {
        method: 'POST',
        body: JSON.stringify({ channels }),
    });
}

export async function getReports(limit = 20) {
    return fetchAPI(`/api/v1/reports?limit=${limit}`);
}

// ─── Alert Configs ───

export async function getAlertConfigs() {
    return fetchAPI('/api/v1/settings/alerts');
}

export async function createAlertConfig(data) {
    return fetchAPI('/api/v1/settings/alerts', {
        method: 'POST',
        body: JSON.stringify(data),
    });
}

export async function deleteAlertConfig(configId) {
    return fetchAPI(`/api/v1/settings/alerts/${configId}`, { method: 'DELETE' });
}

// ─── Settings ───

export async function getSettings() {
    return fetchAPI('/api/v1/settings');
}

export async function updateSettings(data) {
    return fetchAPI('/api/v1/settings', {
        method: 'PUT',
        body: JSON.stringify(data),
    });
}
