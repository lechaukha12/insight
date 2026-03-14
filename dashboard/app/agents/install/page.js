'use client';

import { useState, useEffect, useRef } from 'react';
import { createAgentToken, getAgents } from '../../lib/api';

const AGENT_TYPES = [
    {
        key: 'system', label: 'System Agent',
        desc: 'Monitor CPU, RAM, Disk, Network, and Processes on Linux/Windows/macOS servers.',
        icon: 'SYS', color: '#0ea5e9',
        platforms: [
            { key: 'linux', label: 'Linux', icon: 'LNX' },
            { key: 'windows', label: 'Windows', icon: 'WIN' },
            { key: 'macos', label: 'macOS', icon: 'MAC' },
        ]
    },
    {
        key: 'kubernetes', label: 'Kubernetes Agent',
        desc: 'Monitor K8s clusters: nodes, pods, services, events, and resource usage.',
        icon: 'K8S', color: '#7c3aed',
        platforms: [
            { key: 'kubectl', label: 'kubectl / YAML', icon: 'K8S' },
            { key: 'helm', label: 'Helm Chart', icon: 'HLM' },
        ]
    },
    {
        key: 'application', label: 'Application (OTel)',
        desc: 'Collect traces, metrics, and logs from Java, Python, Node.js apps via OpenTelemetry.',
        icon: 'APP', color: '#f59e0b',
        platforms: [
            { key: 'java', label: 'Java / Spring Boot', icon: 'JVA' },
            { key: 'python', label: 'Python / FastAPI', icon: 'PY' },
            { key: 'nodejs', label: 'Node.js', icon: 'NOD' },
            { key: 'docker', label: 'Docker Compose', icon: 'DCK' },
        ]
    },
];

function getInstallCommand(type, platform, token, coreUrl) {
    const base = coreUrl || 'http://<INSIGHT_CORE_IP>:8080';
    if (type === 'system') {
        if (platform === 'linux') return `# Install Insight System Agent on Linux
curl -sSL ${base}/install.sh | bash -s -- \\
  --token="${token}" \\
  --type=system \\
  --core-url=${base}

# Or manually with Docker:
docker run -d --name insight-agent \\
  -e AGENT_TOKEN=${token} \\
  -e INSIGHT_CORE_URL=${base} \\
  -e AGENT_TYPE=system \\
  lechaukha12/insight-system-agent:latest`;
        if (platform === 'windows') return `# Install Insight System Agent on Windows (PowerShell)
# Download agent
Invoke-WebRequest -Uri "${base}/downloads/insight-agent.exe" -OutFile insight-agent.exe

# Run with token
.\\insight-agent.exe --token="${token}" --core-url=${base}`;
        if (platform === 'macos') return `# Install Insight System Agent on macOS
brew tap lechaukha12/insight
brew install insight-agent

# Configure
export AGENT_TOKEN=${token}
export INSIGHT_CORE_URL=${base}
insight-agent start`;
    }
    if (type === 'kubernetes') {
        if (platform === 'kubectl') return `# Deploy Insight K8s Agent via kubectl
cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: Namespace
metadata:
  name: insight-system
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: insight-k8s-agent
  namespace: insight-system
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: insight-k8s-agent
rules:
- apiGroups: [""]
  resources: ["nodes", "pods", "services", "namespaces", "events", "persistentvolumeclaims"]
  verbs: ["get", "list", "watch"]
- apiGroups: ["apps"]
  resources: ["deployments", "statefulsets", "daemonsets", "replicasets"]
  verbs: ["get", "list", "watch"]
- apiGroups: ["batch"]
  resources: ["jobs", "cronjobs"]
  verbs: ["get", "list", "watch"]
- apiGroups: ["metrics.k8s.io"]
  resources: ["nodes", "pods"]
  verbs: ["get", "list"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: insight-k8s-agent
subjects:
- kind: ServiceAccount
  name: insight-k8s-agent
  namespace: insight-system
roleRef:
  kind: ClusterRole
  name: insight-k8s-agent
  apiGroup: rbac.authorization.k8s.io
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: insight-k8s-agent
  namespace: insight-system
spec:
  replicas: 1
  selector:
    matchLabels:
      app: insight-k8s-agent
  template:
    metadata:
      labels:
        app: insight-k8s-agent
    spec:
      serviceAccountName: insight-k8s-agent
      containers:
      - name: agent
        image: lechaukha12/insight-k8s-agent:latest
        env:
        - name: AGENT_TOKEN
          value: "${token}"
        - name: INSIGHT_CORE_URL
          value: "${base}"
        - name: AGENT_TYPE
          value: "kubernetes"
EOF`;
        if (platform === 'helm') return `# Deploy Insight K8s Agent via Helm
helm repo add insight https://lechaukha12.github.io/insight-charts
helm install insight-k8s-agent insight/k8s-agent \\
  --namespace insight-system --create-namespace \\
  --set agentToken="${token}" \\
  --set coreUrl="${base}"`;
    }
    if (type === 'application') {
        if (platform === 'java') return `# Java / Spring Boot — OpenTelemetry Auto-Instrumentation
# Download OTel Java Agent:
# https://github.com/open-telemetry/opentelemetry-java-instrumentation/releases

# Run your app with:
java -javaagent:opentelemetry-javaagent.jar \\
  -Dotel.exporter.otlp.endpoint=${base} \\
  -Dotel.exporter.otlp.protocol=http/json \\
  -Dotel.service.name=your-service-name \\
  -jar your-app.jar`;
        if (platform === 'python') return `# Python — OpenTelemetry Auto-Instrumentation
pip install opentelemetry-distro opentelemetry-exporter-otlp

# Set environment variables:
export OTEL_EXPORTER_OTLP_ENDPOINT=${base}
export OTEL_EXPORTER_OTLP_PROTOCOL=http/json
export OTEL_SERVICE_NAME=your-service-name

# Run your app:
opentelemetry-instrument python your-app.py`;
        if (platform === 'nodejs') return `# Node.js — OpenTelemetry Auto-Instrumentation
npm install @opentelemetry/auto-instrumentations-node \\
  @opentelemetry/sdk-node @opentelemetry/exporter-trace-otlp-http

# Set environment variables:
export OTEL_EXPORTER_OTLP_ENDPOINT=${base}
export OTEL_EXPORTER_OTLP_PROTOCOL=http/json
export OTEL_SERVICE_NAME=your-service-name

# Run your app:
node --require @opentelemetry/auto-instrumentations-node/register your-app.js`;
        if (platform === 'docker') return `# Docker Compose — Add OTel environment to your service
services:
  your-app:
    image: your-app-image
    environment:
      - OTEL_EXPORTER_OTLP_ENDPOINT=${base}
      - OTEL_EXPORTER_OTLP_PROTOCOL=http/json
      - OTEL_SERVICE_NAME=your-service-name

# Note: Your app must have OpenTelemetry SDK installed.
# Traces, metrics, and logs will be sent directly to Insight Core.`;
    }
    return `# Configure OpenTelemetry in your app:\n# OTEL_EXPORTER_OTLP_ENDPOINT=${base}\n# OTEL_SERVICE_NAME=your-service-name`;
}

export default function InstallAgentPage() {
    const [step, setStep] = useState(1);
    const [agentType, setAgentType] = useState(null);
    const [platform, setPlatform] = useState(null);
    const [token, setToken] = useState(null);
    const [tokenName, setTokenName] = useState('');
    const [creating, setCreating] = useState(false);
    const [copied, setCopied] = useState(false);
    const [checking, setChecking] = useState(false);
    const [connected, setConnected] = useState(false);
    const intervalRef = useRef(null);
    const coreUrl = typeof window !== 'undefined' ? window.location.origin : '';

    // Step 4: Poll for agent connection
    useEffect(() => {
        if (step === 4 && !connected) {
            setChecking(true);
            let attempts = 0;
            intervalRef.current = setInterval(async () => {
                attempts++;
                try {
                    const data = await getAgents();
                    const agents = data?.agents || [];
                    // Check if any agent connected with our token in last 2 minutes
                    const recentAgent = agents.find(a => {
                        if (!a.last_heartbeat) return false;
                        const hbTime = new Date(a.last_heartbeat.replace(' ', 'T') + 'Z');
                        return (Date.now() - hbTime.getTime()) < 120000;
                    });
                    if (recentAgent) {
                        setConnected(recentAgent);
                        setChecking(false);
                        clearInterval(intervalRef.current);
                    }
                } catch { }
                if (attempts > 60) { // 5 min timeout
                    setChecking(false);
                    clearInterval(intervalRef.current);
                }
            }, 5000);
            return () => clearInterval(intervalRef.current);
        }
    }, [step, connected]);

    const handleCreateToken = async () => {
        setCreating(true);
        try {
            const name = tokenName || `${agentType}-${Date.now()}`;
            const result = await createAgentToken({
                name,
                agent_type: agentType === 'application' ? 'any' : agentType,
                cluster_id: 'default',
            });
            setToken(result.token?.token || '');
            setStep(3);
        } catch (err) { console.error(err); alert('Failed to create token'); }
        finally { setCreating(false); }
    };

    const copyToClipboard = (text) => {
        navigator.clipboard.writeText(text);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
    };

    const typeInfo = AGENT_TYPES.find(t => t.key === agentType);
    const isOtel = agentType === 'application';
    const installCmd = agentType && platform && (isOtel || token) ? getInstallCommand(agentType, platform, token, coreUrl) : '';

    return (
        <>
            <div className="main-header">
                <h2>Install Agent</h2>
                <div className="header-actions">
                    <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>Step {step} of 4</span>
                </div>
            </div>
            <div className="main-body">
                {/* Progress Bar */}
                <div style={{ display: 'flex', gap: 8, marginBottom: 28 }}>
                    {[1, 2, 3, 4].map(s => (
                        <div key={s} style={{
                            flex: 1, height: 4, borderRadius: 2,
                            background: s <= step ? 'var(--gold)' : 'rgba(0,0,0,0.08)',
                            transition: 'background 0.3s ease',
                        }} />
                    ))}
                </div>

                {/* Step 1: Choose Type */}
                {step === 1 && (
                    <>
                        <div className="card" style={{ marginBottom: 24 }}>
                            <div className="card-header">
                                <div className="card-title">Choose Agent Type</div>
                            </div>
                            <div className="card-subtitle" style={{ marginBottom: 20 }}>Select the type of infrastructure you want to monitor.</div>
                            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16 }}>
                                {AGENT_TYPES.map(t => (
                                    <div key={t.key}
                                        onClick={() => { setAgentType(t.key); setPlatform(null); setStep(2); }}
                                        style={{
                                            padding: 24, borderRadius: 'var(--radius-md)', cursor: 'pointer',
                                            border: `2px solid ${agentType === t.key ? t.color : 'var(--border-color)'}`,
                                            background: agentType === t.key ? t.color + '08' : 'var(--bg-card)',
                                            transition: 'all 0.2s ease',
                                        }}>
                                        <div style={{
                                            width: 48, height: 48, borderRadius: 'var(--radius-sm)',
                                            display: 'flex', alignItems: 'center', justifyContent: 'center',
                                            background: t.color + '18', color: t.color, fontWeight: 800, fontSize: 16, marginBottom: 12,
                                        }}>{t.icon}</div>
                                        <div style={{ fontWeight: 700, fontSize: 16, marginBottom: 6, color: 'var(--text-primary)' }}>{t.label}</div>
                                        <div style={{ fontSize: 13, color: 'var(--text-muted)', lineHeight: 1.5 }}>{t.desc}</div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    </>
                )}

                {/* Step 2: Choose Platform */}
                {step === 2 && typeInfo && (
                    <div className="card" style={{ marginBottom: 24 }}>
                        <div className="card-header">
                            <div>
                                <div className="card-title">Choose Platform</div>
                                <div className="card-subtitle">Select your deployment environment for {typeInfo.label}.</div>
                            </div>
                            <button className="btn btn-secondary btn-sm" onClick={() => { setStep(1); setPlatform(null); }}>Back</button>
                        </div>
                        <div style={{ display: 'grid', gridTemplateColumns: `repeat(${Math.min(typeInfo.platforms.length, 4)}, 1fr)`, gap: 16, marginTop: 16 }}>
                            {typeInfo.platforms.map(p => (
                                <div key={p.key}
                                    onClick={() => { setPlatform(p.key); }}
                                    style={{
                                        padding: 24, borderRadius: 'var(--radius-md)', cursor: 'pointer', textAlign: 'center',
                                        border: `2px solid ${platform === p.key ? typeInfo.color : 'var(--border-color)'}`,
                                        background: platform === p.key ? typeInfo.color + '08' : 'var(--bg-card)',
                                        transition: 'all 0.2s ease',
                                    }}>
                                    <div style={{
                                        width: 48, height: 48, borderRadius: 'var(--radius-sm)', margin: '0 auto 12px',
                                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                                        background: typeInfo.color + '18', color: typeInfo.color, fontWeight: 800, fontSize: 15,
                                    }}>{p.icon}</div>
                                    <div style={{ fontWeight: 700, fontSize: 15 }}>{p.label}</div>
                                </div>
                            ))}
                        </div>
                        {platform && !isOtel && (
                            <div style={{ marginTop: 24 }}>
                                <label style={{ display: 'block', fontWeight: 600, fontSize: 13, marginBottom: 6, color: 'var(--text-secondary)' }}>Token Name (optional)</label>
                                <div style={{ display: 'flex', gap: 12 }}>
                                    <input className="form-input" placeholder={`e.g. Production ${typeInfo.label}`}
                                        value={tokenName} onChange={e => setTokenName(e.target.value)}
                                        style={{ flex: 1, padding: '10px 14px', fontSize: 14 }} />
                                    <button className="btn btn-primary" onClick={handleCreateToken} disabled={creating}>
                                        {creating ? 'Generating...' : 'Generate Token & Continue'}
                                    </button>
                                </div>
                            </div>
                        )}
                        {platform && isOtel && (
                            <div style={{ marginTop: 24, textAlign: 'right' }}>
                                <button className="btn btn-primary" onClick={() => setStep(3)}>
                                    View Setup Instructions
                                </button>
                            </div>
                        )}
                    </div>
                )}

                {/* Step 3: Install Command */}
                {step === 3 && (isOtel || token) && (
                    <div className="card" style={{ marginBottom: 24 }}>
                        <div className="card-header">
                            <div>
                                <div className="card-title">Install Agent</div>
                                <div className="card-subtitle">Copy and run this command on your target machine.</div>
                            </div>
                            <button className="btn btn-secondary btn-sm" onClick={() => setStep(2)}>Back</button>
                        </div>

                        {/* Token display (only for non-OTel agents) */}
                        {token && !isOtel && (
                        <div style={{ padding: 16, background: 'rgba(1,101,167,0.06)', borderRadius: 'var(--radius-sm)', marginBottom: 16 }}>
                            <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-muted)', marginBottom: 4 }}>Your Agent Token (save this — it won't be shown again)</div>
                            <div style={{ fontFamily: 'monospace', fontSize: 13, wordBreak: 'break-all', color: 'var(--blue)', fontWeight: 600 }}>{token}</div>
                        </div>
                        )}
                        {isOtel && (
                        <div style={{ padding: 16, background: 'rgba(16,185,129,0.06)', borderRadius: 'var(--radius-sm)', marginBottom: 16, border: '1px solid rgba(16,185,129,0.15)' }}>
                            <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--color-success)', marginBottom: 4 }}>No token required</div>
                            <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>OpenTelemetry apps send data directly to Insight Core. Just set the environment variables below.</div>
                        </div>
                        )}

                        {/* Install command */}
                        <div style={{ position: 'relative' }}>
                            <pre style={{
                                background: '#1e293b', color: '#e2e8f0', padding: 20, borderRadius: 'var(--radius-sm)',
                                fontSize: 13, lineHeight: 1.6, overflow: 'auto', maxHeight: 400,
                                fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
                            }}>{installCmd}</pre>
                            <button
                                onClick={() => copyToClipboard(installCmd)}
                                style={{
                                    position: 'absolute', top: 12, right: 12, padding: '6px 14px',
                                    background: copied ? 'var(--color-success)' : 'rgba(255,255,255,0.15)',
                                    color: '#fff', border: 'none', borderRadius: 6, cursor: 'pointer',
                                    fontSize: 12, fontWeight: 600, transition: 'all 0.2s',
                                }}>
                                {copied ? 'Copied!' : 'Copy'}
                            </button>
                        </div>

                        <div style={{ marginTop: 20, textAlign: 'right' }}>
                            <button className="btn btn-primary" onClick={() => setStep(4)}>
                                I've installed the agent — Verify Connection
                            </button>
                        </div>
                    </div>
                )}

                {/* Step 4: Verify Connection */}
                {step === 4 && (
                    <div className="card" style={{ textAlign: 'center', padding: '48px 32px' }}>
                        {connected ? (
                            <>
                                <div style={{
                                    width: 80, height: 80, borderRadius: '50%', margin: '0 auto 20px',
                                    background: 'var(--color-success-bg)', display: 'flex', alignItems: 'center', justifyContent: 'center',
                                    fontSize: 36, color: 'var(--color-success)',
                                }}>OK</div>
                                <div style={{ fontSize: 22, fontWeight: 700, color: 'var(--color-success)', marginBottom: 8 }}>Agent Connected!</div>
                                <div style={{ fontSize: 14, color: 'var(--text-muted)', marginBottom: 24 }}>
                                    <strong>{connected.name || connected.hostname}</strong> is now sending data to Insight.
                                </div>
                                <div style={{ display: 'flex', gap: 12, justifyContent: 'center' }}>
                                    <a href="/monitoring/system" className="btn btn-primary">View Monitoring</a>
                                    <button className="btn btn-secondary" onClick={() => { setStep(1); setAgentType(null); setPlatform(null); setToken(null); setConnected(false); }}>Install Another</button>
                                </div>
                            </>
                        ) : (
                            <>
                                <div className="loading-spinner" style={{ margin: '0 auto 20px' }} />
                                <div style={{ fontSize: 18, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 8 }}>Waiting for agent connection...</div>
                                <div style={{ fontSize: 14, color: 'var(--text-muted)', marginBottom: 24 }}>
                                    Make sure you've run the install command. This page will automatically detect when your agent connects.
                                </div>
                                <button className="btn btn-secondary btn-sm" onClick={() => setStep(3)}>Back to Install Command</button>
                            </>
                        )}
                    </div>
                )}
            </div>
        </>
    );
}
