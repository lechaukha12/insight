"""
K8s Resources — Direct Kubernetes API queries for dashboard resource browsing.
Provides real-time cluster data: nodes, namespaces, pods, deployments, etc.
"""

import logging
from functools import lru_cache

logger = logging.getLogger("insight.k8s_resources")

# ─── K8s Client Init ───

_v1 = None
_apps_v1 = None
_storage_v1 = None
_networking_v1 = None
_initialized = False


def _init_k8s():
    """Lazy-init K8s client. Called on first use."""
    global _v1, _apps_v1, _storage_v1, _networking_v1, _initialized
    if _initialized:
        return _initialized
    try:
        from kubernetes import client, config
        try:
            config.load_incluster_config()
            logger.info("K8s: loaded in-cluster config")
        except config.ConfigException:
            config.load_kube_config()
            logger.info("K8s: loaded local kubeconfig")
        _v1 = client.CoreV1Api()
        _apps_v1 = client.AppsV1Api()
        _storage_v1 = client.StorageV1Api()
        _networking_v1 = client.NetworkingV1Api()
        _initialized = True
    except Exception as e:
        logger.warning(f"K8s client init failed (resource browsing disabled): {e}")
        _initialized = False
    return _initialized


def _ensure_k8s():
    if not _init_k8s():
        raise RuntimeError("Kubernetes API not available")


# ─── Helpers ───

def _parse_cpu(val: str) -> float:
    if not val:
        return 0
    if val.endswith("n"):
        return float(val[:-1]) / 1e9
    if val.endswith("m"):
        return float(val[:-1]) / 1000
    return float(val)


def _parse_mem(val: str) -> int:
    if not val:
        return 0
    units = {"Ki": 1024, "Mi": 1024**2, "Gi": 1024**3, "Ti": 1024**4}
    for suffix, mult in units.items():
        if val.endswith(suffix):
            return int(float(val[:-len(suffix)]) * mult)
    return int(val)


def _age(ts) -> str:
    if not ts:
        return "--"
    from datetime import datetime, timezone
    if hasattr(ts, 'timestamp'):
        diff = (datetime.now(timezone.utc) - ts.replace(tzinfo=timezone.utc)).total_seconds()
    else:
        return str(ts)
    if diff < 60:
        return f"{int(diff)}s"
    if diff < 3600:
        return f"{int(diff/60)}m"
    if diff < 86400:
        return f"{int(diff/3600)}h"
    return f"{int(diff/86400)}d"


# ─── Nodes ───

def get_k8s_nodes() -> list[dict]:
    _ensure_k8s()
    nodes = _v1.list_node()
    # Try to get usage from metrics-server
    usage_map = {}
    try:
        from kubernetes import client
        api = client.CustomObjectsApi()
        metrics = api.list_cluster_custom_object("metrics.k8s.io", "v1beta1", "nodes")
        for item in metrics.get("items", []):
            name = item["metadata"]["name"]
            usage_map[name] = {
                "cpu_used": _parse_cpu(item.get("usage", {}).get("cpu", "0")),
                "mem_used": _parse_mem(item.get("usage", {}).get("memory", "0")),
            }
    except Exception as e:
        logger.debug(f"Metrics server not available: {e}")

    result = []
    for n in nodes.items:
        name = n.metadata.name
        cap = n.status.capacity or {}
        alloc = n.status.allocatable or {}
        ready = "Unknown"
        for c in (n.status.conditions or []):
            if c.type == "Ready":
                ready = "Ready" if c.status == "True" else "NotReady"
        usage = usage_map.get(name, {})
        result.append({
            "name": name,
            "status": ready,
            "roles": ",".join([k.replace("node-role.kubernetes.io/", "") for k in (n.metadata.labels or {}) if k.startswith("node-role.kubernetes.io/")]) or "worker",
            "cpu_capacity": _parse_cpu(cap.get("cpu", "0")),
            "cpu_allocatable": _parse_cpu(alloc.get("cpu", "0")),
            "cpu_used": usage.get("cpu_used"),
            "mem_capacity": _parse_mem(cap.get("memory", "0")),
            "mem_allocatable": _parse_mem(alloc.get("memory", "0")),
            "mem_used": usage.get("mem_used"),
            "os_image": n.status.node_info.os_image if n.status.node_info else "",
            "kubelet_version": n.status.node_info.kubelet_version if n.status.node_info else "",
            "age": _age(n.metadata.creation_timestamp),
        })
    return result


# ─── Namespaces ───

def get_k8s_namespaces() -> list[dict]:
    _ensure_k8s()
    nss = _v1.list_namespace()
    return [{"name": ns.metadata.name, "status": ns.status.phase, "age": _age(ns.metadata.creation_timestamp)} for ns in nss.items]


# ─── Pods ───

def get_k8s_pods(namespace: str = None) -> list[dict]:
    _ensure_k8s()
    pods = _v1.list_namespaced_pod(namespace) if namespace else _v1.list_pod_for_all_namespaces()
    result = []
    for p in pods.items:
        containers = []
        restarts = 0
        for cs in (p.status.container_statuses or []):
            restarts += cs.restart_count or 0
            state = "running" if cs.state and cs.state.running else "waiting" if cs.state and cs.state.waiting else "terminated" if cs.state and cs.state.terminated else "unknown"
            containers.append({"name": cs.name, "ready": cs.ready, "state": state, "restarts": cs.restart_count or 0})
        ready_count = sum(1 for c in containers if c["ready"])
        total_count = len(containers)
        result.append({
            "name": p.metadata.name,
            "namespace": p.metadata.namespace,
            "status": p.status.phase or "Unknown",
            "ready": f"{ready_count}/{total_count}",
            "restarts": restarts,
            "node": p.spec.node_name or "",
            "ip": p.status.pod_ip or "",
            "age": _age(p.metadata.creation_timestamp),
        })
    return result


# ─── Deployments ───

def get_k8s_deployments(namespace: str = None) -> list[dict]:
    _ensure_k8s()
    deps = _apps_v1.list_namespaced_deployment(namespace) if namespace else _apps_v1.list_deployment_for_all_namespaces()
    return [{
        "name": d.metadata.name,
        "namespace": d.metadata.namespace,
        "replicas": d.spec.replicas or 0,
        "ready": d.status.ready_replicas or 0,
        "available": d.status.available_replicas or 0,
        "updated": d.status.updated_replicas or 0,
        "age": _age(d.metadata.creation_timestamp),
        "images": list(set(c.image for c in d.spec.template.spec.containers)),
    } for d in deps.items]


# ─── StatefulSets ───

def get_k8s_statefulsets(namespace: str = None) -> list[dict]:
    _ensure_k8s()
    sts_list = _apps_v1.list_namespaced_stateful_set(namespace) if namespace else _apps_v1.list_stateful_set_for_all_namespaces()
    return [{
        "name": s.metadata.name,
        "namespace": s.metadata.namespace,
        "replicas": s.spec.replicas or 0,
        "ready": s.status.ready_replicas or 0,
        "age": _age(s.metadata.creation_timestamp),
        "images": list(set(c.image for c in s.spec.template.spec.containers)),
    } for s in sts_list.items]


# ─── DaemonSets ───

def get_k8s_daemonsets(namespace: str = None) -> list[dict]:
    _ensure_k8s()
    ds_list = _apps_v1.list_namespaced_daemon_set(namespace) if namespace else _apps_v1.list_daemon_set_for_all_namespaces()
    return [{
        "name": d.metadata.name,
        "namespace": d.metadata.namespace,
        "desired": d.status.desired_number_scheduled or 0,
        "current": d.status.current_number_scheduled or 0,
        "ready": d.status.number_ready or 0,
        "age": _age(d.metadata.creation_timestamp),
        "images": list(set(c.image for c in d.spec.template.spec.containers)),
    } for d in ds_list.items]


# ─── Services ───

def get_k8s_services(namespace: str = None) -> list[dict]:
    _ensure_k8s()
    svcs = _v1.list_namespaced_service(namespace) if namespace else _v1.list_service_for_all_namespaces()
    return [{
        "name": s.metadata.name,
        "namespace": s.metadata.namespace,
        "type": s.spec.type,
        "cluster_ip": s.spec.cluster_ip or "",
        "ports": [{"port": p.port, "target": p.target_port, "protocol": p.protocol} for p in (s.spec.ports or [])],
        "age": _age(s.metadata.creation_timestamp),
    } for s in svcs.items]


# ─── ConfigMaps ───

def get_k8s_configmaps(namespace: str = None) -> list[dict]:
    _ensure_k8s()
    cms = _v1.list_namespaced_config_map(namespace) if namespace else _v1.list_config_map_for_all_namespaces()
    return [{
        "name": c.metadata.name,
        "namespace": c.metadata.namespace,
        "data_keys": list((c.data or {}).keys()),
        "age": _age(c.metadata.creation_timestamp),
    } for c in cms.items]


# ─── Secrets ───

def get_k8s_secrets(namespace: str = None) -> list[dict]:
    _ensure_k8s()
    secs = _v1.list_namespaced_secret(namespace) if namespace else _v1.list_secret_for_all_namespaces()
    return [{
        "name": s.metadata.name,
        "namespace": s.metadata.namespace,
        "type": s.type,
        "data_keys": list((s.data or {}).keys()),
        "age": _age(s.metadata.creation_timestamp),
    } for s in secs.items]


# ─── PVCs ───

def get_k8s_pvcs(namespace: str = None) -> list[dict]:
    _ensure_k8s()
    pvcs = _v1.list_namespaced_persistent_volume_claim(namespace) if namespace else _v1.list_persistent_volume_claim_for_all_namespaces()
    return [{
        "name": p.metadata.name,
        "namespace": p.metadata.namespace,
        "status": p.status.phase or "",
        "volume": p.spec.volume_name or "",
        "capacity": p.status.capacity.get("storage", "") if p.status.capacity else "",
        "access_modes": p.spec.access_modes or [],
        "storage_class": p.spec.storage_class_name or "",
        "age": _age(p.metadata.creation_timestamp),
    } for p in pvcs.items]


# ─── PVs ───

def get_k8s_pvs() -> list[dict]:
    _ensure_k8s()
    pvs = _v1.list_persistent_volume()
    return [{
        "name": p.metadata.name,
        "capacity": p.spec.capacity.get("storage", "") if p.spec.capacity else "",
        "access_modes": p.spec.access_modes or [],
        "reclaim_policy": p.spec.persistent_volume_reclaim_policy or "",
        "status": p.status.phase or "",
        "claim": f"{p.spec.claim_ref.namespace}/{p.spec.claim_ref.name}" if p.spec.claim_ref else "",
        "storage_class": p.spec.storage_class_name or "",
        "age": _age(p.metadata.creation_timestamp),
    } for p in pvs.items]


# ─── StorageClasses ───

def get_k8s_storageclasses() -> list[dict]:
    _ensure_k8s()
    scs = _storage_v1.list_storage_class()
    return [{
        "name": sc.metadata.name,
        "provisioner": sc.provisioner or "",
        "reclaim_policy": sc.reclaim_policy or "",
        "volume_binding_mode": sc.volume_binding_mode or "",
        "allow_expansion": sc.allow_volume_expansion or False,
        "is_default": any(v == "true" for k, v in (sc.metadata.annotations or {}).items() if "is-default" in k),
        "age": _age(sc.metadata.creation_timestamp),
    } for sc in scs.items]


# ─── Ingresses ───

def get_k8s_ingresses(namespace: str = None) -> list[dict]:
    _ensure_k8s()
    ings = _networking_v1.list_namespaced_ingress(namespace) if namespace else _networking_v1.list_ingress_for_all_namespaces()
    result = []
    for ing in ings.items:
        hosts = []
        paths = []
        for rule in (ing.spec.rules or []):
            h = rule.host or "*"
            hosts.append(h)
            for p in (rule.http.paths if rule.http else []):
                paths.append(f"{h}{p.path or '/'}")
        result.append({
            "name": ing.metadata.name,
            "namespace": ing.metadata.namespace,
            "class": ing.spec.ingress_class_name or "",
            "hosts": hosts,
            "paths": paths,
            "address": ", ".join([lb.ip or lb.hostname or "" for lb in (ing.status.load_balancer.ingress or [])]) if ing.status and ing.status.load_balancer else "",
            "age": _age(ing.metadata.creation_timestamp),
        })
    return result


# ─── Events ───

def get_k8s_events(namespace: str = None) -> list[dict]:
    _ensure_k8s()
    evts = _v1.list_namespaced_event(namespace) if namespace else _v1.list_event_for_all_namespaces()
    result = []
    for e in evts.items:
        result.append({
            "type": e.type or "Normal",
            "reason": e.reason or "",
            "message": e.message or "",
            "namespace": e.metadata.namespace or "",
            "object": f"{e.involved_object.kind}/{e.involved_object.name}" if e.involved_object else "",
            "count": e.count or 1,
            "first_seen": _age(e.first_timestamp),
            "last_seen": _age(e.last_timestamp),
            "source": e.source.component if e.source else "",
        })
    # Sort by type (Warning first), then by count
    result.sort(key=lambda x: (0 if x["type"] == "Warning" else 1, -(x["count"] or 0)))
    return result
