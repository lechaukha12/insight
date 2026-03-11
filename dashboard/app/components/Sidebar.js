'use client';

import Image from 'next/image';
import Link from 'next/link';
import { usePathname } from 'next/navigation';

const navItems = [
    {
        section: 'Overview', items: [
            { href: '/', icon: '📊', label: 'Dashboard' },
        ]
    },
    {
        section: 'Monitoring', items: [
            { href: '/agents', icon: '🤖', label: 'Agents' },
            { href: '/events', icon: '⚡', label: 'Events & Alerts' },
            { href: '/logs', icon: '📝', label: 'Error Logs' },
        ]
    },
    {
        section: 'Actions', items: [
            { href: '/reports', icon: '📋', label: 'Reports' },
            { href: '/settings', icon: '⚙️', label: 'Settings' },
        ]
    },
];

export default function Sidebar() {
    const pathname = usePathname();

    return (
        <aside className="sidebar">
            <div className="sidebar-brand">
                <Image
                    src="/images/logo.png"
                    alt="Insight Logo"
                    width={42}
                    height={42}
                    className="sidebar-brand-logo"
                    priority
                />
                <h1>INSIGHT</h1>
            </div>
            <nav className="sidebar-nav">
                {navItems.map(section => (
                    <div key={section.section} className="sidebar-nav-section">
                        <div className="sidebar-nav-section-title">{section.section}</div>
                        {section.items.map(item => (
                            <Link key={item.href} href={item.href}>
                                <div className={`sidebar-nav-item ${pathname === item.href ? 'active' : ''}`}>
                                    <span className="sidebar-nav-icon">{item.icon}</span>
                                    <span>{item.label}</span>
                                </div>
                            </Link>
                        ))}
                    </div>
                ))}
            </nav>
            <div style={{
                padding: '16px 24px',
                borderTop: '1px solid var(--border-color)',
                fontSize: '11px',
                color: 'var(--text-muted)',
                letterSpacing: '0.5px',
            }}>
                Insight v2.0.0
            </div>
        </aside>
    );
}
