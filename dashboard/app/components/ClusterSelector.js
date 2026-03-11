'use client';

import { useState, useEffect, useCallback } from 'react';
import { getClusters } from '../lib/api';

/**
 * Cluster selector dropdown.
 * Persists selected cluster in localStorage.
 */
export default function ClusterSelector({ onClusterChange }) {
    const [clusters, setClusters] = useState([]);
    const [selected, setSelected] = useState('');

    useEffect(() => {
        const saved = localStorage.getItem('insight_cluster');
        if (saved) setSelected(saved);
    }, []);

    const fetchClusters = useCallback(async () => {
        try {
            const d = await getClusters();
            setClusters(d.clusters || []);
        } catch (e) { console.error(e); }
    }, []);

    useEffect(() => { fetchClusters(); }, [fetchClusters]);

    const handleChange = (e) => {
        const val = e.target.value;
        setSelected(val);
        localStorage.setItem('insight_cluster', val);
        onClusterChange?.(val || null);
    };

    if (clusters.length === 0) return null;

    return (
        <select className="cluster-selector" value={selected} onChange={handleChange}>
            <option value="">All Clusters</option>
            {clusters.map(c => (
                <option key={c.id} value={c.id}>{c.name}</option>
            ))}
        </select>
    );
}
