"""
K8s Resources — Direct Kubernetes API queries for dashboard resource browsing.
Provides real-time cluster data: nodes, namespaces, pods, deployments, etc.
Includes 30s TTL cache to avoid hitting K8s API on every request.
"""

import logging
import time as _time
from functools import lru_cache

logger = logging.getLogger("insight.k8s_resources")

# ─── TTL Cache ───

_cache: dict[str, tuple] = {}  # {key: (data, expire_time)}
K8S_CACHE_TTL = 30  # seconds


def _cached(key: str, fn, ttl: int = K8S_CACHE_TTL):
    """Return cached result if fresh, otherwise call fn and cache."""
    now = _time.time()
    if key in _cache and _cache[key][1] > now:
        return _cache[key][0]
    result = fn()
    _cache[key] = (result, now + ttl)
    return result


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
    def _fetch():
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
    return _cached("k8s:nodes", _fetch)


# ─── Namespaces ───

def get_k8s_namespaces() -> list[dict]:
    _ensure_k8s()
    def _fetch():
        nss = _v1.list_namespace()
        return [{"name": ns.metadata.name, "status": ns.status.phase, "age": _age(ns.metadata.creation_timestamp)} for ns in nss.items]
    return _cached("k8s:namespaces", _fetch)


# ─── Pods ───

def get_k8s_pods(namespace: str = None) -> list[dict]:
    _ensure_k8s()
    def _fetch():
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
    return _cached(f"k8s:pods:{namespace}", _fetch)


# ─── Deployments ───

def get_k8s_deployments(namespace: str = None) -> list[dict]:
    _ensure_k8s()
    def _fetch():
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
    return _cached(f"k8s:deployments:{namespace}", _fetch)


# ─── StatefulSets ───

def get_k8s_statefulsets(namespace: str = None) -> list[dict]:
    _ensure_k8s()
    def _fetch():
        sts_list = _apps_v1.list_namespaced_stateful_set(namespace) if namespace else _apps_v1.list_stateful_set_for_all_namespaces()
        return [{
            "name": s.metadata.name,
            "namespace": s.metadata.namespace,
            "replicas": s.spec.replicas or 0,
            "ready": s.status.ready_replicas or 0,
            "age": _age(s.metadata.creation_timestamp),
            "images": list(set(c.image for c in s.spec.template.spec.containers)),
        } for s in sts_list.items]
    return _cached(f"k8s:statefulsets:{namespace}", _fetch)


# ─── DaemonSets ───

def get_k8s_daemonsets(namespace: str = None) -> list[dict]:
    _ensure_k8s()
    def _fetch():
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
    return _cached(f"k8s:daemonsets:{namespace}", _fetch)


# ─── Services ───

def get_k8s_services(namespace: str = None) -> list[dict]:
    _ensure_k8s()
    def _fetch():
        svcs = _v1.list_namespaced_service(namespace) if namespace else _v1.list_service_for_all_namespaces()
        return [{
            "name": s.metadata.name,
            "namespace": s.metadata.namespace,
            "type": s.spec.type,
            "cluster_ip": s.spec.cluster_ip or "",
            "ports": [{"port": p.port, "target": p.target_port, "protocol": p.protocol} for p in (s.spec.ports or [])],
            "age": _age(s.metadata.creation_timestamp),
        } for s in svcs.items]
    return _cached(f"k8s:services:{namespace}", _fetch)


# ─── ConfigMaps ───

def get_k8s_configmaps(namespace: str = None) -> list[dict]:
    _ensure_k8s()
    def _fetch():
        cms = _v1.list_namespaced_config_map(namespace) if namespace else _v1.list_config_map_for_all_namespaces()
        return [{"name": c.metadata.name, "namespace": c.metadata.namespace,
                 "data_keys": list((c.data or {}).keys()), "age": _age(c.metadata.creation_timestamp)} for c in cms.items]
    return _cached(f"k8s:configmaps:{namespace}", _fetch)


# ─── Secrets ───

def get_k8s_secrets(namespace: str = None) -> list[dict]:
    _ensure_k8s()
    def _fetch():
        secs = _v1.list_namespaced_secret(namespace) if namespace else _v1.list_secret_for_all_namespaces()
        return [{"name": s.metadata.name, "namespace": s.metadata.namespace,
                 "type": s.type, "data_keys": list((s.data or {}).keys()),
                 "age": _age(s.metadata.creation_timestamp)} for s in secs.items]
    return _cached(f"k8s:secrets:{namespace}", _fetch)


# ─── PVCs ───

def get_k8s_pvcs(namespace: str = None) -> list[dict]:
    _ensure_k8s()
    def _fetch():
        pvcs = _v1.list_namespaced_persistent_volume_claim(namespace) if namespace else _v1.list_persistent_volume_claim_for_all_namespaces()
        return [{
            "name": p.metadata.name, "namespace": p.metadata.namespace,
            "status": p.status.phase or "", "volume": p.spec.volume_name or "",
            "capacity": p.status.capacity.get("storage", "") if p.status.capacity else "",
            "access_modes": p.spec.access_modes or [],
            "storage_class": p.spec.storage_class_name or "",
            "age": _age(p.metadata.creation_timestamp),
        } for p in pvcs.items]
    return _cached(f"k8s:pvcs:{namespace}", _fetch)


# ─── PVs ───

def get_k8s_pvs() -> list[dict]:
    _ensure_k8s()
    def _fetch():
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
    return _cached("k8s:pvs", _fetch)


# ─── StorageClasses ───

def get_k8s_storageclasses() -> list[dict]:
    _ensure_k8s()
    def _fetch():
        scs = _storage_v1.list_storage_class()
        return [{
            "name": sc.metadata.name, "provisioner": sc.provisioner or "",
            "reclaim_policy": sc.reclaim_policy or "",
            "volume_binding_mode": sc.volume_binding_mode or "",
            "allow_expansion": sc.allow_volume_expansion or False,
            "is_default": any(v == "true" for k, v in (sc.metadata.annotations or {}).items() if "is-default" in k),
            "age": _age(sc.metadata.creation_timestamp),
        } for sc in scs.items]
    return _cached("k8s:storageclasses", _fetch)


# ─── Ingresses ───

def get_k8s_ingresses(namespace: str = None) -> list[dict]:
    _ensure_k8s()
    def _fetch():
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
                "name": ing.metadata.name, "namespace": ing.metadata.namespace,
                "class": ing.spec.ingress_class_name or "", "hosts": hosts, "paths": paths,
                "address": ", ".join([lb.ip or lb.hostname or "" for lb in (ing.status.load_balancer.ingress or [])]) if ing.status and ing.status.load_balancer else "",
                "age": _age(ing.metadata.creation_timestamp),
            })
        return result
    return _cached(f"k8s:ingresses:{namespace}", _fetch)


# ─── Events ───

def get_k8s_events(namespace: str = None) -> list[dict]:
    _ensure_k8s()
    def _fetch():
        evts = _v1.list_namespaced_event(namespace) if namespace else _v1.list_event_for_all_namespaces()
        result = []
        for e in evts.items:
            result.append({
                "type": e.type or "Normal", "reason": e.reason or "",
                "message": e.message or "", "namespace": e.metadata.namespace or "",
                "object": f"{e.involved_object.kind}/{e.involved_object.name}" if e.involved_object else "",
                "count": e.count or 1, "first_seen": _age(e.first_timestamp),
                "last_seen": _age(e.last_timestamp),
                "source": e.source.component if e.source else "",
            })
        result.sort(key=lambda x: (0 if x["type"] == "Warning" else 1, -(x["count"] or 0)))
        return result
    return _cached(f"k8s:events:{namespace}", _fetch, ttl=15)  # shorter TTL for events


# ─── Pod Detail ───

def get_k8s_pod_detail(namespace: str, pod_name: str) -> dict:
    """Get detailed pod information including spec, status, containers, conditions, and events."""
    _ensure_k8s()
    try:
        pod = _v1.read_namespaced_pod(pod_name, namespace)
        containers = []
        for c in (pod.spec.containers or []):
            cs = None
            for s in (pod.status.container_statuses or []):
                if s.name == c.name:
                    cs = s
                    break
            state = "unknown"
            if cs:
                if cs.state.running:
                    state = "running"
                elif cs.state.waiting:
                    state = f"waiting: {cs.state.waiting.reason or ''}"
                elif cs.state.terminated:
                    state = f"terminated: {cs.state.terminated.reason or ''}"
            containers.append({
                "name": c.name,
                "image": c.image,
                "ports": [{"port": p.container_port, "protocol": p.protocol or "TCP"} for p in (c.ports or [])],
                "state": state,
                "ready": cs.ready if cs else False,
                "restart_count": cs.restart_count if cs else 0,
                "resources": {
                    "requests": {k: str(v) for k, v in (c.resources.requests or {}).items()} if c.resources and c.resources.requests else {},
                    "limits": {k: str(v) for k, v in (c.resources.limits or {}).items()} if c.resources and c.resources.limits else {},
                },
            })
        conditions = []
        for cond in (pod.status.conditions or []):
            conditions.append({
                "type": cond.type, "status": cond.status,
                "reason": cond.reason or "", "message": cond.message or "",
                "last_transition": str(cond.last_transition_time or ""),
            })
        # Get pod events
        events = []
        try:
            evts = _v1.list_namespaced_event(namespace, field_selector=f"involvedObject.name={pod_name}")
            for e in evts.items:
                events.append({
                    "type": e.type or "Normal", "reason": e.reason or "",
                    "message": e.message or "", "count": e.count or 1,
                    "last_seen": _age(e.last_timestamp),
                })
        except Exception:
            pass
        return {
            "name": pod.metadata.name,
            "namespace": pod.metadata.namespace,
            "node": pod.spec.node_name or "",
            "phase": pod.status.phase or "",
            "pod_ip": pod.status.pod_ip or "",
            "host_ip": pod.status.host_ip or "",
            "start_time": str(pod.status.start_time or ""),
            "labels": dict(pod.metadata.labels or {}),
            "annotations": {k: v[:200] for k, v in (pod.metadata.annotations or {}).items()},
            "service_account": pod.spec.service_account_name or "",
            "containers": containers,
            "conditions": conditions,
            "events": events,
            "age": _age(pod.metadata.creation_timestamp),
        }
    except Exception as e:
        logger.error(f"Failed to get pod detail {namespace}/{pod_name}: {e}")
        return {"error": str(e)}


# ─── Pod Logs ───

def get_k8s_pod_logs(namespace: str, pod_name: str, container: str = None, tail_lines: int = 100) -> dict:
    """Get pod container logs."""
    _ensure_k8s()
    try:
        kwargs = {"name": pod_name, "namespace": namespace, "tail_lines": tail_lines}
        if container:
            kwargs["container"] = container
        logs = _v1.read_namespaced_pod_log(**kwargs)
        lines = logs.split("\n") if logs else []
        return {
            "pod": pod_name,
            "namespace": namespace,
            "container": container or "default",
            "lines": lines,
            "total_lines": len(lines),
        }
    except Exception as e:
        logger.error(f"Failed to get pod logs {namespace}/{pod_name}: {e}")
        return {"error": str(e)}


# ─── ConfigMap Detail ───

def get_k8s_configmap_detail(namespace: str, cm_name: str) -> dict:
    """Get ConfigMap data."""
    _ensure_k8s()
    try:
        cm = _v1.read_namespaced_config_map(cm_name, namespace)
        return {
            "name": cm.metadata.name,
            "namespace": cm.metadata.namespace,
            "data": dict(cm.data or {}),
            "labels": dict(cm.metadata.labels or {}),
            "age": _age(cm.metadata.creation_timestamp),
        }
    except Exception as e:
        logger.error(f"Failed to get configmap {namespace}/{cm_name}: {e}")
        return {"error": str(e)}
