import './globals.css';
import Sidebar from './components/Sidebar';

export const metadata = {
  title: 'Insight - Monitoring System',
  description: 'Central monitoring platform for infrastructure and Kubernetes clusters',
};

export default function RootLayout({ children }) {
  return (
    <html lang="vi">
      <body>
        <div className="app-layout">
          <Sidebar />
          <main className="main-content">
            {children}
          </main>
        </div>
      </body>
    </html>
  );
}
