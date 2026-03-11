import './globals.css';
import ClientLayout from './components/ClientLayout';

export const metadata = {
  title: 'Insight - Monitoring System',
  description: 'Central monitoring platform for infrastructure and Kubernetes clusters',
};

export default function RootLayout({ children }) {
  return (
    <html lang="vi">
      <body>
        <ClientLayout>{children}</ClientLayout>
      </body>
    </html>
  );
}
