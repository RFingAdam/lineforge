/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Backend lives on a different port during dev; rewrite /api and /ws.
  async rewrites() {
    return [
      { source: '/api/:path*', destination: 'http://localhost:8000/api/:path*' },
      { source: '/ws/:path*', destination: 'http://localhost:8000/ws/:path*' },
    ];
  },
};

export default nextConfig;
