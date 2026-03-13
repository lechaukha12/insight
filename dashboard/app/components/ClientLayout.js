'use client';

import { usePathname } from 'next/navigation';
import { AuthProvider, useAuth } from './AuthProvider';
import { TimeRangeProvider } from '../lib/TimeRangeContext';
import Sidebar from './Sidebar';
import TimeRangePicker from './TimeRangePicker';

function AppShell({ children }) {
    const pathname = usePathname();
    const { isAuthenticated, loading } = useAuth();
    const isLoginPage = pathname === '/login';

    // Show loading while checking auth
    if (loading) {
        return <div className="login-page"><div className="loading-spinner" /></div>;
    }

    // If not authenticated and not on login page, redirect
    if (!isAuthenticated && !isLoginPage) {
        if (typeof window !== 'undefined') {
            window.location.href = '/login';
        }
        return <div className="login-page"><div className="loading-spinner" /></div>;
    }

    // Login page: no sidebar
    if (isLoginPage) {
        return <>{children}</>;
    }

    // Authenticated: show sidebar + time picker + content
    return (
        <div className="app-layout">
            <Sidebar />
            <main className="main-content">
                <div className="time-picker-bar">
                    <TimeRangePicker />
                </div>
                {children}
            </main>
        </div>
    );
}

export default function ClientLayout({ children }) {
    return (
        <AuthProvider>
            <TimeRangeProvider>
                <AppShell>{children}</AppShell>
            </TimeRangeProvider>
        </AuthProvider>
    );
}
