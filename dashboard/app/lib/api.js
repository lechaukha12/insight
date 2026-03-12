/**
 * Insight Dashboard - API Client v4.0.0
 * Handles all communication with the Insight Core API
 * Includes JWT auth header injection
 */

const API_BASE = '';

async function fetchAPI(endpoint, options = {}) {
    const url = `${API_BASE}${endpoint}`;
    const token = typeof window !== 'undefined' ? localStorage.getItem('insight_token') : null;
    const headers = { 'Content-Type': 'application/json', ...options.headers };
    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }
    const res = await fetch(url, { headers, ...options });
    if (res.status === 401) {
        // Token expired or invalid - redirect to login
        if (typeof window !== 'undefined') {
            localStorage.removeItem('insight_token');
            localStorage.removeItem('insight_user');
            window.location.href = '/login';
        }
        throw new Error('Authentication required');
    }
    if (!res.ok) {
        throw new Error(`API error: ${res.status} ${res.statusText}`);
    }
    return res.json();
}

// ─── Auth ───

export async function login(username, password) {
    const res = await fetch(`${API_BASE}/api/v1/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
    });
    if (!res.ok) throw new Error('Invalid credentials');
    return res.json();
}

export async function getMe() {
    return fetchAPI('/api/v1/auth/me');
}

// ─── Dashboard ───

export async function getDashboardSummary(clusterId) {
    const q = clusterId ? `?cluster_id=${clusterId}` : '';
    return fetchAPI(`/api/v1/dashboard/summary${q}`);
}

// ─── Clusters ───

export async function getClusters() {
    return fetchAPI('/api/v1/clusters');
}

export async function createCluster(data) {
    return fetchAPI('/api/v1/clusters', { method: 'POST', body: JSON.stringify(data) });
}

// ─── Agents ───

export async function getAgents(params = {}) {
    const query = new URLSearchParams(params).toString();
    return fetchAPI(`/api/v1/agents?${query}`);
}

export async function getAgent(agentId) {
    return fetchAPI(`/api/v1/agents/${agentId}`);
}

export async function registerAgent(data) {
    return fetchAPI('/api/v1/agents/register', { method: 'POST', body: JSON.stringify(data) });
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

// ─── Events ───

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
    return fetchAPI('/api/v1/reports/generate', { method: 'POST', body: JSON.stringify({ channels }) });
}

export async function getReports(limit = 20) {
    return fetchAPI(`/api/v1/reports?limit=${limit}`);
}

// ─── Alert Configs ───

export async function getAlertConfigs() {
    return fetchAPI('/api/v1/settings/alerts');
}

export async function createAlertConfig(data) {
    return fetchAPI('/api/v1/settings/alerts', { method: 'POST', body: JSON.stringify(data) });
}

export async function deleteAlertConfig(configId) {
    return fetchAPI(`/api/v1/settings/alerts/${configId}`, { method: 'DELETE' });
}

// ─── Rules ───

export async function getRules() {
    return fetchAPI('/api/v1/rules');
}

export async function createRule(data) {
    return fetchAPI('/api/v1/rules', { method: 'POST', body: JSON.stringify(data) });
}

export async function deleteRule(ruleId) {
    return fetchAPI(`/api/v1/rules/${ruleId}`, { method: 'DELETE' });
}

// ─── Settings ───

export async function getSettings() {
    return fetchAPI('/api/v1/settings');
}

export async function updateSettings(data) {
    return fetchAPI('/api/v1/settings', { method: 'PUT', body: JSON.stringify(data) });
}

export async function getStorageStats() {
    return fetchAPI('/api/v1/storage/stats');
}

export async function applyRetention() {
    return fetchAPI('/api/v1/retention/apply', { method: 'POST' });
}

export async function purgeAllData() {
    return fetchAPI('/api/v1/storage/purge', { method: 'POST' });
}

// ─── Audit ───

export async function getAuditLogs(params = {}) {
    const query = new URLSearchParams(params).toString();
    return fetchAPI(`/api/v1/audit?${query}`);
}

// ─── Processes ───

export async function getProcesses(agentId) {
    return fetchAPI(`/api/v1/processes?agent_id=${agentId}`);
}

// ─── Traces ───

export async function getTraces(params = {}) {
    const query = new URLSearchParams(params).toString();
    return fetchAPI(`/api/v1/traces?${query}`);
}

export async function getTraceSummary(lastHours = 1) {
    return fetchAPI(`/api/v1/traces/summary?last_hours=${lastHours}`);
}

// ─── Services (v5.0.2) ───

export async function getServices(lastHours = 24) {
    return fetchAPI(`/api/v1/services?last_hours=${lastHours}`);
}

export async function getServiceTraces(serviceName, lastHours = 24, limit = 100) {
    return fetchAPI(`/api/v1/services/${encodeURIComponent(serviceName)}/traces?last_hours=${lastHours}&limit=${limit}`);
}

export async function getServiceMetrics(serviceName, lastHours = 24) {
    return fetchAPI(`/api/v1/services/${encodeURIComponent(serviceName)}/metrics?last_hours=${lastHours}`);
}
