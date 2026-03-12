/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  // Generate unique build ID to bust browser cache on each deploy
  generateBuildId: async () => {
    return `build-${Date.now()}`;
  },
  // Disable static page caching
  headers: async () => [
    {
      source: '/:path*',
      headers: [
        { key: 'Cache-Control', value: 'no-cache, no-store, must-revalidate' },
        { key: 'Pragma', value: 'no-cache' },
      ],
    },
  ],
};

export default nextConfig;
