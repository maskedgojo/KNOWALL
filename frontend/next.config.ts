
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async headers() {
    return [{
      source: "/invitations/:path*",
      headers: [
        {key: "Referrer-Policy", value: "no-referrer"},
        {key: "Cache-Control", value: "private, no-store"},
        {key: "X-Robots-Tag", value: "noindex, nofollow"},
      ],
    }];
  },
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: "http://127.0.0.1:5000/api/:path*",
      },
    ];
  },
};

export default nextConfig;
