'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';

export default function AgentsRedirect() {
    const router = useRouter();
    useEffect(() => {
        router.replace('/monitoring/system');
    }, [router]);
    return <div className="page-container"><div className="loading-spinner" /></div>;
}
