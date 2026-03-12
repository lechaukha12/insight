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
];

// Admin-only items
const adminItems = [
    {
        label: 'ADMINISTRATION', items: [
            { name: 'Users', href: '/users' },
        ]
    },
];

export default function Sidebar() {
    const pathname = usePathname();
    const { user, logout } = useAuth();
    const isAdmin = user?.role === 'admin';

    const allNav = isAdmin ? [...navItems, ...adminItems] : navItems;

    return (
        <aside className="sidebar">
            <div className="sidebar-brand">
                <img src="https://ops.namabank.com.vn/assets/images/logo-OPS.78237a4d.png" alt="Logo" className="sidebar-logo" />
                <span className="sidebar-title">INSIGHT</span>
            </div>

            <nav className="sidebar-nav">
                {allNav.map(group => (
                    <div key={group.label} className="nav-section">
                        <div className="nav-section-label">{group.label}</div>
                        {group.items.map(item => (
                            <a key={item.href} href={item.href} className={`nav-item ${pathname === item.href ? 'active' : ''}`}>{item.name}</a>
                        ))}
                    </div>
                ))}
            </nav>

            <div className="sidebar-footer">
                {user && (
                    <div className="sidebar-user">
                        <a href="/profile" className="sidebar-user-info">
                            <span className="sidebar-user-name">{user.username}</span>
                            <span className="sidebar-user-role">{user.role}</span>
                        </a>
                        <button className="btn btn-sm btn-secondary" onClick={logout}>Logout</button>
                    </div>
                )}
                <div className="sidebar-version">v5.0.0</div>
            </div>
        </aside>
    );
}
