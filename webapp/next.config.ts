import type { NextConfig } from "next";

const API = process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8400/api/v1";

const nextConfig: NextConfig = {
  async rewrites() {
    // Browser calls same-origin /api/v1/* — proxied to the read-API (no CORS needed).
    return [{ source: "/api/v1/:path*", destination: `${API}/:path*` }];
  },
};

export default nextConfig;
