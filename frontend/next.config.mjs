/** @type {import('next').NextConfig} */
const backendPort = process.env.LINEFORGE_BACKEND_PORT ?? "8000";
const backendBase = `http://localhost:${backendPort}`;

const nextConfig = {
  reactStrictMode: true,
  // Backend lives on a different port during dev; rewrite /api and /ws.
  // The port follows the CLI's port-conflict fallback via the
  // LINEFORGE_BACKEND_PORT env var set by `lineforge gui`.
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${backendBase}/api/:path*` },
      { source: "/ws/:path*", destination: `${backendBase}/ws/:path*` },
    ];
  },
};

export default nextConfig;
