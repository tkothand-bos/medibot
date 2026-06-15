/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "export",   // static export for Amplify hosting
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000",
  },
};

export default nextConfig;
