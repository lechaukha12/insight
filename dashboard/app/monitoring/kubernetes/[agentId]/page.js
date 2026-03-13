'use client';

import { useState, useEffect, useCallback } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { getAgent, getK8sNodes, getK8sNamespaces, getK8sPods, getK8sDeployments, getK8sStatefulSets, getK8sDaemonSets, getK8sServices, getK8sConfigMaps, getK8sSecrets, getK8sEvents, getK8sPVs, getK8sPVCs, getK8sStorageClasses, getK8sIngresses } from '@/app/lib/api';
import { timeAgo } from '@/app/lib/hooks';
import { useTimeRange } from '@/app/lib/TimeRangeContext';

const TABS = [
    { key: 'pods', label: 'Pods', icon: '◉' },
    { key: 'deployments', label: 'Deployments', icon: '⊞' },
    { key: 'statefulsets', label: 'StatefulSets', icon: '▥' },
    { key: 'daemonsets', label: 'DaemonSets', icon: '⬡' },
    { key: 'services', label: 'Services', icon: '⟐' },
    { key: 'ingresses', label: 'Ingresses', icon: '⇄' },
    { key: 'configmaps', label: 'ConfigMaps', icon: '☰' },
    { key: 'secrets', label: 'Secrets', icon: '⚿' },
    { key: 'pvcs', label: 'PVCs', icon: '▤' },
    { key: 'pvs', label: 'PVs', icon: '▣' },
    { key: 'storageclasses', label: 'StorageClasses', icon: '⬢' },
    { key: 'events', label: 'Events', icon: '⚡' },
];

export default function K8sAgentDetailPage() {
    const { agentId } = useParams();
    const router = useRouter();
    const { isLive } = useTimeRange();

    const [agent, setAgent] = useState(null);
    const [loading, setLoading] = useState(true);

    const [nodes, setNodes] = useState([]);
    const [namespaces, setNamespaces] = useState([]);
    const [showNodeModal, setShowNodeModal] = useState(false);

    const [selectedNs, setSelectedNs] = useState('_all');
    const [activeTab, setActiveTab] = useState('pods');
    const [resources, setResources] = useState([]);
    const [resLoading, setResLoading] = useState(false);

    const [totalPods, setTotalPods] = useState(0);
    const [totalEvents, setTotalEvents] = useState(0);
    const [errorCount, setErrorCount] = useState(0);

    const fetchAgent = useCallback(async () => {
        try { setAgent(await getAgent(agentId)); }
        catch (e) { console.error(e); }
        finally { setLoading(false); }
    }, [agentId]);

    const fetchClusterData = useCallback(async () => {
        try {
            const [nr, nsr, pr, er] = await Promise.all([
                getK8sNodes(), getK8sNamespaces(), getK8sPods('_all'), getK8sEvents('_all'),
            ]);
            setNodes(nr?.nodes || []);
            setNamespaces(nsr?.namespaces || []);
            setTotalPods((pr?.pods || []).length);
            const evts = er?.events || [];
            setTotalEvents(evts.length);
            setErrorCount(evts.filter(e => e.type === 'Warning').length);
        } catch (e) { console.error(e); }
    }, []);

    const fetchResources = useCallback(async (tab, ns) => {
        setResLoading(true);
        try {
            const f = {
                pods: () => getK8sPods(ns),
                deployments: () => getK8sDeployments(ns),
                statefulsets: () => getK8sStatefulSets(ns),
                daemonsets: () => getK8sDaemonSets(ns),
                services: () => getK8sServices(ns),
                ingresses: () => getK8sIngresses(ns),
                configmaps: () => getK8sConfigMaps(ns),
                secrets: () => getK8sSecrets(ns),
                pvcs: () => getK8sPVCs(),
                pvs: () => getK8sPVs(),
                storageclasses: () => getK8sStorageClasses(),
                events: () => getK8sEvents(ns),
            };
            const result = await f[tab]();
            setResources(result?.[tab] || Object.values(result || {})[0] || []);
        } catch (e) { console.error(e); setResources([]); }
        finally { setResLoading(false); }
    }, []);

    useEffect(() => { fetchAgent(); fetchClusterData(); }, [fetchAgent, fetchClusterData]);
    useEffect(() => { fetchResources(activeTab, selectedNs); }, [activeTab, selectedNs, fetchResources]);
    useEffect(() => {
        if (isLive) {
            const i = setInterval(() => { fetchClusterData(); fetchResources(activeTab, selectedNs); }, 30000);
            return () => clearInterval(i);
        }
    }, [isLive, activeTab, selectedNs, fetchClusterData, fetchResources]);

    const fmtBytes = (b) => { if (!b) return '--'; if (b > 1024**3) return (b/1024**3).toFixed(1)+' Gi'; if (b > 1024**2) return (b/1024**2).toFixed(0)+' Mi'; return (b/1024).toFixed(0)+' Ki'; };
    const fmtCPU = (c) => { if (c === null || c === undefined) return '--'; return c < 1 ? (c*1000).toFixed(0)+'m' : c.toFixed(1); };
    const pct = (u, t) => (!u || !t) ? null : ((u/t)*100).toFixed(0);

    if (loading) return (<><div className="main-header"><h2>Loading...</h2></div><div className="main-body"><div className="loading-overlay"><div className="loading-spinner" /><span>Loading cluster...</span></div></div></>);
    if (!agent) return (<><div className="main-header"><h2>Agent Not Found</h2></div><div className="main-body"><div className="card"><div className="empty-state"><div className="empty-state-text">Agent {agentId} not found</div></div></div></div></>);

    const clusterName = agent.cluster_id || agent.name || 'Cluster';

    return (
        <>
            {/* ─── Header ─── */}
            <div className="main-header">
                <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                    <button className="btn btn-secondary btn-sm" onClick={() => router.push('/monitoring/kubernetes')}
                        style={{ padding: '6px 10px', fontSize: 14, lineHeight: 1 }}>←</button>
                    <div style={{
                        width: 40, height: 40, borderRadius: 10,
                        background: 'linear-gradient(135deg, #326ce5 0%, #1a3f99 100%)',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        color: '#fff', fontWeight: 900, fontSize: 11, letterSpacing: -0.3,
                    }}>K8S</div>
                    <div>
                        <h2 style={{ margin: 0, fontSize: 17, fontWeight: 800 }}>{clusterName}</h2>
                        <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 1 }}>
                            {agent.name} • {agent.hostname || ''}
                        </div>
                    </div>
                </div>
            </div>

            <div className="main-body">
                {/* ─── Cluster Overview Stats ─── */}
                <div style={{
                    display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
                    gap: 10, marginBottom: 16,
                }}>
                    {[
                        { label: 'Nodes', value: nodes.length, icon: 'NO', color: '#0ea5e9', click: () => setShowNodeModal(true) },
                        { label: 'Namespaces', value: namespaces.length, icon: 'NS', color: '#7c3aed' },
                        { label: 'Pods', value: totalPods, icon: 'PO', color: '#22c55e' },
                        { label: 'Events', value: totalEvents, icon: 'EV', color: '#f59e0b' },
                        { label: 'Warnings', value: errorCount, icon: 'WA', color: errorCount > 0 ? '#ef4444' : '#6b7280' },
                    ].map(s => (
                        <div key={s.label} onClick={s.click}
                            style={{
                                background: 'var(--bg-card)', border: '1px solid var(--border-color)',
                                borderRadius: 10, padding: '14px 16px',
                                display: 'flex', alignItems: 'center', gap: 12,
                                cursor: s.click ? 'pointer' : 'default',
                                transition: 'transform 0.12s, box-shadow 0.12s',
                            }}
                            onMouseEnter={e => { if (s.click) { e.currentTarget.style.transform = 'translateY(-1px)'; e.currentTarget.style.boxShadow = '0 4px 12px rgba(0,0,0,0.08)'; }}}
                            onMouseLeave={e => { e.currentTarget.style.transform = ''; e.currentTarget.style.boxShadow = ''; }}
                        >
                            <div style={{
                                width: 36, height: 36, borderRadius: 8,
                                background: s.color + '14', color: s.color,
                                display: 'flex', alignItems: 'center', justifyContent: 'center',
                                fontWeight: 900, fontSize: 11, flexShrink: 0,
                            }}>{s.icon}</div>
                            <div>
                                <div style={{ fontSize: 22, fontWeight: 800, lineHeight: 1.1, color: 'var(--text-primary)' }}>{s.value}</div>
                                <div style={{ fontSize: 10, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: 0.5, lineHeight: 1.3 }}>{s.label}{s.click ? ' ↗' : ''}</div>
                            </div>
                        </div>
                    ))}
                </div>

                {/* ─── Resource Browser ─── */}
                <div className="card">
                    {/* Tab bar + Namespace filter */}
                    <div style={{
                        padding: '8px 16px', display: 'flex', alignItems: 'center',
                        justifyContent: 'space-between', borderBottom: '1px solid var(--border-color)',
                        gap: 12, flexWrap: 'wrap',
                    }}>
                        <div style={{ display: 'flex', gap: 2, flexWrap: 'wrap', flex: 1 }}>
                            {TABS.map(t => (
                                <button key={t.key} onClick={() => setActiveTab(t.key)}
                                    style={{
                                        padding: '5px 10px', border: 'none', borderRadius: 4, cursor: 'pointer',
                                        fontSize: 11, fontWeight: 600,
                                        background: activeTab === t.key ? 'var(--blue)' : 'transparent',
                                        color: activeTab === t.key ? '#fff' : 'var(--text-muted)',
                                        transition: 'all 0.1s', whiteSpace: 'nowrap',
                                    }}>
                                    <span style={{ marginRight: 3, fontSize: 10 }}>{t.icon}</span>{t.label}
                                </button>
                            ))}
                        </div>
                        {!['pvs', 'storageclasses'].includes(activeTab) && (
                            <select value={selectedNs} onChange={e => setSelectedNs(e.target.value)}
                                className="form-input" style={{ width: 180, padding: '4px 8px', fontSize: 11, flexShrink: 0 }}>
                                <option value="_all">All Namespaces</option>
                                {namespaces.map(n => <option key={n.name} value={n.name}>{n.name}</option>)}
                            </select>
                        )}
                    </div>

                    {/* Resource table */}
                    <div style={{ minHeight: 180 }}>
                        {resLoading ? (
                            <div style={{ display: 'flex', justifyContent: 'center', padding: 40 }}><div className="loading-spinner" /></div>
                        ) : resources.length === 0 ? (
                            <div className="empty-state" style={{ padding: 40 }}><div className="empty-state-text">No {TABS.find(t => t.key === activeTab)?.label || activeTab} found</div></div>
                        ) : (
                            <div style={{ maxHeight: 520, overflow: 'auto' }}>
                                {activeTab === 'pods' && <PodsTable data={resources} />}
                                {activeTab === 'deployments' && <DeploymentsTable data={resources} />}
                                {activeTab === 'statefulsets' && <StatefulSetsTable data={resources} />}
                                {activeTab === 'daemonsets' && <DaemonSetsTable data={resources} />}
                                {activeTab === 'services' && <ServicesTable data={resources} />}
                                {activeTab === 'ingresses' && <IngressesTable data={resources} />}
                                {activeTab === 'configmaps' && <ConfigMapsTable data={resources} />}
                                {activeTab === 'secrets' && <SecretsTable data={resources} />}
                                {activeTab === 'pvcs' && <PVCsTable data={resources} />}
                                {activeTab === 'pvs' && <PVsTable data={resources} />}
                                {activeTab === 'storageclasses' && <StorageClassesTable data={resources} />}
                                {activeTab === 'events' && <EventsTable data={resources} />}
                            </div>
                        )}
                    </div>
                </div>
            </div>

            {/* ─── Node Metrics Modal ─── */}
            {showNodeModal && (
                <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', backdropFilter: 'blur(6px)', zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 20 }}
                    onClick={() => setShowNodeModal(false)}>
                    <div className="card" onClick={e => e.stopPropagation()}
                        style={{ maxWidth: 940, width: '100%', maxHeight: '85vh', overflow: 'auto', boxShadow: '0 20px 60px rgba(0,0,0,0.3)' }}>
                        <div className="card-header">
                            <div className="card-title" style={{ fontSize: 15 }}>Cluster Nodes ({nodes.length})</div>
                            <button className="btn btn-secondary btn-sm" onClick={() => setShowNodeModal(false)}>✕</button>
                        </div>
                        <table className="data-table">
                            <thead><tr>
                                <th>Node</th><th>Status</th><th>Role</th>
                                <th style={{ textAlign: 'right' }}>CPU Used / Cap</th>
                                <th style={{ textAlign: 'right' }}>RAM Used / Cap</th>
                                <th>Version</th><th>Age</th>
                            </tr></thead>
                            <tbody>{nodes.map(n => {
                                const cp = pct(n.cpu_used, n.cpu_capacity), mp = pct(n.mem_used, n.mem_capacity);
                                return (
                                    <tr key={n.name}>
                                        <td style={{ fontWeight: 700 }}>{n.name}</td>
                                        <td><span className={`badge ${n.status === 'Ready' ? 'active' : 'error'}`}><span className="badge-dot" />{n.status}</span></td>
                                        <td><span className="badge info">{n.roles}</span></td>
                                        <td style={{ textAlign: 'right' }}>
                                            <div style={{ display: 'flex', alignItems: 'center', gap: 6, justifyContent: 'flex-end' }}>
                                                {cp && <Bar pct={+cp} />}
                                                <span style={{ fontFamily: 'monospace', fontSize: 11 }}>{fmtCPU(n.cpu_used)}/{fmtCPU(n.cpu_capacity)}{cp && <span style={{ color: 'var(--text-muted)', marginLeft: 3 }}>({cp}%)</span>}</span>
                                            </div>
                                        </td>
                                        <td style={{ textAlign: 'right' }}>
                                            <div style={{ display: 'flex', alignItems: 'center', gap: 6, justifyContent: 'flex-end' }}>
                                                {mp && <Bar pct={+mp} />}
                                                <span style={{ fontFamily: 'monospace', fontSize: 11 }}>{fmtBytes(n.mem_used)}/{fmtBytes(n.mem_capacity)}{mp && <span style={{ color: 'var(--text-muted)', marginLeft: 3 }}>({mp}%)</span>}</span>
                                            </div>
                                        </td>
                                        <td style={{ fontSize: 11, color: 'var(--text-muted)' }}>{n.kubelet_version}</td>
                                        <td style={{ fontSize: 11, color: 'var(--text-muted)' }}>{n.age}</td>
                                    </tr>
                                );
                            })}</tbody>
                        </table>
                    </div>
                </div>
            )}
        </>
    );
}

/* ─── Bar gauge ─── */
function Bar({ pct }) {
    const c = pct > 80 ? '#ef4444' : pct > 60 ? '#f59e0b' : '#22c55e';
    return <div style={{ width: 44, height: 5, background: 'var(--border-color)', borderRadius: 3, overflow: 'hidden', flexShrink: 0 }}><div style={{ width: `${Math.min(pct,100)}%`, height: '100%', background: c, borderRadius: 3 }} /></div>;
}

/* ─── Helpers ─── */
const TH = ({ children, ...p }) => <th {...p}>{children}</th>;
const Ns = ({ v }) => <span className="badge info" style={{ fontSize: 9, padding: '1px 6px' }}>{v}</span>;
const Mono = ({ children }) => <span style={{ fontFamily: 'monospace', fontSize: 11, color: 'var(--text-muted)' }}>{children}</span>;
const Dim = ({ children }) => <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{children}</span>;
const Ellip = ({ children, w = 240 }) => <span style={{ display: 'block', maxWidth: w, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontSize: 11, color: 'var(--text-muted)' }}>{children}</span>;

/* ─── Resource Tables ─── */
function PodsTable({ data }) {
    return (<table className="data-table"><thead><tr><th>Name</th><th>Namespace</th><th>Ready</th><th>Status</th><th>Restarts</th><th>Node</th><th>IP</th><th>Age</th></tr></thead><tbody>
        {data.map((r,i) => <tr key={i}>
            <td style={{ fontWeight: 600, maxWidth: 250, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.name}</td>
            <td><Ns v={r.namespace} /></td>
            <td style={{ fontWeight: 600 }}>{r.ready}</td>
            <td><span className={`badge ${r.status === 'Running' ? 'active' : r.status === 'Succeeded' ? 'info' : r.status === 'Pending' ? 'warning' : 'error'}`}>{r.status}</span></td>
            <td style={{ fontWeight: 600, color: r.restarts > 3 ? '#ef4444' : 'inherit' }}>{r.restarts}</td>
            <td><Dim>{r.node}</Dim></td>
            <td><Mono>{r.ip}</Mono></td>
            <td><Dim>{r.age}</Dim></td>
        </tr>)}
    </tbody></table>);
}

function DeploymentsTable({ data }) {
    return (<table className="data-table"><thead><tr><th>Name</th><th>Namespace</th><th>Ready</th><th>Available</th><th>Images</th><th>Age</th></tr></thead><tbody>
        {data.map((r,i) => <tr key={i}>
            <td style={{ fontWeight: 600 }}>{r.name}</td>
            <td><Ns v={r.namespace} /></td>
            <td style={{ fontWeight: 700 }}>{r.ready}/{r.replicas}</td>
            <td style={{ fontWeight: 600, color: r.available === r.replicas ? '#22c55e' : '#f59e0b' }}>{r.available}</td>
            <td><Ellip>{r.images?.join(', ')}</Ellip></td>
            <td><Dim>{r.age}</Dim></td>
        </tr>)}
    </tbody></table>);
}

function StatefulSetsTable({ data }) {
    return (<table className="data-table"><thead><tr><th>Name</th><th>Namespace</th><th>Ready</th><th>Images</th><th>Age</th></tr></thead><tbody>
        {data.map((r,i) => <tr key={i}>
            <td style={{ fontWeight: 600 }}>{r.name}</td>
            <td><Ns v={r.namespace} /></td>
            <td style={{ fontWeight: 700 }}>{r.ready}/{r.replicas}</td>
            <td><Ellip>{r.images?.join(', ')}</Ellip></td>
            <td><Dim>{r.age}</Dim></td>
        </tr>)}
    </tbody></table>);
}

function DaemonSetsTable({ data }) {
    return (<table className="data-table"><thead><tr><th>Name</th><th>Namespace</th><th>Desired</th><th>Ready</th><th>Images</th><th>Age</th></tr></thead><tbody>
        {data.map((r,i) => <tr key={i}>
            <td style={{ fontWeight: 600 }}>{r.name}</td>
            <td><Ns v={r.namespace} /></td>
            <td style={{ fontWeight: 600 }}>{r.desired}</td>
            <td style={{ fontWeight: 700, color: r.ready === r.desired ? '#22c55e' : '#f59e0b' }}>{r.ready}</td>
            <td><Ellip>{r.images?.join(', ')}</Ellip></td>
            <td><Dim>{r.age}</Dim></td>
        </tr>)}
    </tbody></table>);
}

function ServicesTable({ data }) {
    return (<table className="data-table"><thead><tr><th>Name</th><th>Namespace</th><th>Type</th><th>Cluster IP</th><th>Ports</th><th>Age</th></tr></thead><tbody>
        {data.map((r,i) => <tr key={i}>
            <td style={{ fontWeight: 600 }}>{r.name}</td>
            <td><Ns v={r.namespace} /></td>
            <td><span className="badge" style={{ background: r.type === 'LoadBalancer' ? 'rgba(124,58,237,0.1)' : 'rgba(1,101,167,0.06)', color: r.type === 'LoadBalancer' ? '#7c3aed' : 'var(--blue)', fontSize: 10 }}>{r.type}</span></td>
            <td><Mono>{r.cluster_ip}</Mono></td>
            <td><Dim>{r.ports?.map(p => `${p.port}→${p.target}`).join(', ')}</Dim></td>
            <td><Dim>{r.age}</Dim></td>
        </tr>)}
    </tbody></table>);
}

function IngressesTable({ data }) {
    return (<table className="data-table"><thead><tr><th>Name</th><th>Namespace</th><th>Class</th><th>Hosts</th><th>Paths</th><th>Address</th><th>Age</th></tr></thead><tbody>
        {data.map((r,i) => <tr key={i}>
            <td style={{ fontWeight: 600 }}>{r.name}</td>
            <td><Ns v={r.namespace} /></td>
            <td><span className="badge info" style={{ fontSize: 10 }}>{r.class || '-'}</span></td>
            <td><Ellip w={180}>{r.hosts?.join(', ')}</Ellip></td>
            <td><Ellip w={200}>{r.paths?.join(', ')}</Ellip></td>
            <td><Mono>{r.address || '-'}</Mono></td>
            <td><Dim>{r.age}</Dim></td>
        </tr>)}
    </tbody></table>);
}

function ConfigMapsTable({ data }) {
    return (<table className="data-table"><thead><tr><th>Name</th><th>Namespace</th><th>Keys</th><th>Age</th></tr></thead><tbody>
        {data.map((r,i) => <tr key={i}>
            <td style={{ fontWeight: 600 }}>{r.name}</td>
            <td><Ns v={r.namespace} /></td>
            <td><Dim>{r.data_keys?.length || 0} keys</Dim></td>
            <td><Dim>{r.age}</Dim></td>
        </tr>)}
    </tbody></table>);
}

function SecretsTable({ data }) {
    return (<table className="data-table"><thead><tr><th>Name</th><th>Namespace</th><th>Type</th><th>Keys</th><th>Age</th></tr></thead><tbody>
        {data.map((r,i) => <tr key={i}>
            <td style={{ fontWeight: 600 }}>{r.name}</td>
            <td><Ns v={r.namespace} /></td>
            <td><Ellip w={200}>{r.type}</Ellip></td>
            <td><Dim>{r.data_keys?.length || 0} keys</Dim></td>
            <td><Dim>{r.age}</Dim></td>
        </tr>)}
    </tbody></table>);
}

function PVCsTable({ data }) {
    return (<table className="data-table"><thead><tr><th>Name</th><th>Namespace</th><th>Status</th><th>Volume</th><th>Capacity</th><th>Access Modes</th><th>StorageClass</th><th>Age</th></tr></thead><tbody>
        {data.map((r,i) => <tr key={i}>
            <td style={{ fontWeight: 600 }}>{r.name}</td>
            <td><Ns v={r.namespace} /></td>
            <td><span className={`badge ${r.status === 'Bound' ? 'active' : 'warning'}`}>{r.status}</span></td>
            <td><Ellip w={180}>{r.volume}</Ellip></td>
            <td style={{ fontWeight: 600 }}>{r.capacity}</td>
            <td><Dim>{r.access_modes?.join(', ')}</Dim></td>
            <td><span className="badge info" style={{ fontSize: 10 }}>{r.storage_class || '-'}</span></td>
            <td><Dim>{r.age}</Dim></td>
        </tr>)}
    </tbody></table>);
}

function PVsTable({ data }) {
    return (<table className="data-table"><thead><tr><th>Name</th><th>Capacity</th><th>Access Modes</th><th>Reclaim</th><th>Status</th><th>Claim</th><th>StorageClass</th><th>Age</th></tr></thead><tbody>
        {data.map((r,i) => <tr key={i}>
            <td style={{ fontWeight: 600 }}>{r.name}</td>
            <td style={{ fontWeight: 600 }}>{r.capacity}</td>
            <td><Dim>{r.access_modes?.join(', ')}</Dim></td>
            <td><span className="badge" style={{ fontSize: 10 }}>{r.reclaim_policy}</span></td>
            <td><span className={`badge ${r.status === 'Bound' ? 'active' : r.status === 'Available' ? 'info' : 'warning'}`}>{r.status}</span></td>
            <td><Ellip w={200}>{r.claim || '-'}</Ellip></td>
            <td><span className="badge info" style={{ fontSize: 10 }}>{r.storage_class || '-'}</span></td>
            <td><Dim>{r.age}</Dim></td>
        </tr>)}
    </tbody></table>);
}

function StorageClassesTable({ data }) {
    return (<table className="data-table"><thead><tr><th>Name</th><th>Provisioner</th><th>Reclaim Policy</th><th>Binding Mode</th><th>Expansion</th><th>Default</th><th>Age</th></tr></thead><tbody>
        {data.map((r,i) => <tr key={i}>
            <td style={{ fontWeight: 600 }}>{r.name}</td>
            <td><Ellip w={250}>{r.provisioner}</Ellip></td>
            <td><span className="badge" style={{ fontSize: 10 }}>{r.reclaim_policy}</span></td>
            <td><Dim>{r.volume_binding_mode}</Dim></td>
            <td>{r.allow_expansion ? <span className="badge active" style={{ fontSize: 10 }}>Yes</span> : <Dim>No</Dim>}</td>
            <td>{r.is_default ? <span className="badge active" style={{ fontSize: 10 }}>Default</span> : <Dim>-</Dim>}</td>
            <td><Dim>{r.age}</Dim></td>
        </tr>)}
    </tbody></table>);
}

function EventsTable({ data }) {
    return (<table className="data-table"><thead><tr><th>Type</th><th>Reason</th><th>Object</th><th>Message</th><th>Count</th><th>Last Seen</th></tr></thead><tbody>
        {data.map((r,i) => <tr key={i}>
            <td><span className={`badge ${r.type === 'Warning' ? 'error' : 'active'}`} style={{ fontSize: 10 }}>{r.type}</span></td>
            <td style={{ fontWeight: 600 }}>{r.reason}</td>
            <td><Dim>{r.object}</Dim></td>
            <td><Ellip w={350}>{r.message}</Ellip></td>
            <td style={{ fontWeight: 600, textAlign: 'center' }}>{r.count}</td>
            <td><Dim>{r.last_seen}</Dim></td>
        </tr>)}
    </tbody></table>);
}
