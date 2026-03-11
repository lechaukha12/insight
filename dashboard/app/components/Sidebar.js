'use client';

import { usePathname } from 'next/navigation';
import { useAuth } from './AuthProvider';

const navItems = [
    {
        label: 'OVERVIEW', items: [
            { name: 'Dashboard', href: '/' },
        ]
    },
    {
        label: 'MONITORING', items: [
            { name: 'Agents', href: '/agents' },
            { name: 'Events & Alerts', href: '/events' },
            { name: 'Error Logs', href: '/logs' },
        ]
    },
    {
        label: 'RULES & ALERTS', items: [
            { name: 'Notification Rules', href: '/rules' },
        ]
    },
    {
        label: 'ACTIONS', items: [
            { name: 'Reports', href: '/reports' },
            { name: 'Settings', href: '/settings' },
        ]
    },
    {
        label: 'SYSTEM', items: [
            { name: 'Audit Log', href: '/audit' },
        ]
    },
];

export default function Sidebar() {
    const pathname = usePathname();
    const { user, logout } = useAuth();

    return (
        <aside className="sidebar">
            <div className="sidebar-brand">
                <img
                    src="https://ops.namabank.com.vn/assets/images/logo-OPS.78237a4d.png"
                    alt="Insight Logo"
                    className="sidebar-logo"
                />
                <span className="sidebar-title">INSIGHT</span>
            </div>

            <nav className="sidebar-nav">
                {navItems.map(group => (
                    <div key={group.label} className="nav-section">
                        <div className="nav-section-label">{group.label}</div>
                        {group.items.map(item => (
                            <a
                                key={item.href}
                                href={item.href}
                                className={`nav-item ${pathname === item.href ? 'active' : ''}`}
                            >
                                {item.name}
                            </a>
                        ))}
                    </div>
                ))}
            </nav>

            <div className="sidebar-footer">
                {user && (
                    <div className="sidebar-user">
                        <div className="sidebar-user-info">
                            <span className="sidebar-user-name">{user.username}</span>
                            <span className="sidebar-user-role">{user.role}</span>
                        </div>
                        <button className="btn btn-sm btn-secondary" onClick={logout}>
                            Logout
                        </button>
                    </div>
                )}
                <div className="sidebar-version">v4.0.0</div>
            </div>
        </aside>
    );
}
