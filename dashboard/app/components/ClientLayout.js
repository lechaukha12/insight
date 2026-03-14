'use client';

import { useState } from 'react';
import { usePathname } from 'next/navigation';
import { AuthProvider, useAuth } from './AuthProvider';
import { TimeRangeProvider } from '../lib/TimeRangeContext';
import Sidebar from './Sidebar';
import TimeRangePicker from './TimeRangePicker';
import AIChatbot from './AIChatbot';

function AppShell({ children }) {
    const pathname = usePathname();
    const { isAuthenticated, loading } = useAuth();
    const isLoginPage = pathname === '/login';
    const [sidebarOpen, setSidebarOpen] = useState(false);

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

    // Authenticated: show sidebar + content with time picker overlay in header
    return (
        <div className="app-layout">
            {/* Mobile hamburger button */}
            <button
                className="mobile-menu-btn"
                onClick={() => setSidebarOpen(true)}
                aria-label="Menu"
            >
                <span /><span /><span />
            </button>

            {/* Backdrop overlay for mobile sidebar */}
            {sidebarOpen && (
                <div
                    className="sidebar-backdrop"
                    onClick={() => setSidebarOpen(false)}
                />
            )}

            <Sidebar isOpen={sidebarOpen} onClose={() => setSidebarOpen(false)} />
            <main className="main-content">
                <div className="trp-overlay">
                    <TimeRangePicker />
                </div>
                {children}
            </main>
            <AIChatbot />
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
