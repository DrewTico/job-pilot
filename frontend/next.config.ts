import type { NextConfig } from 'next';

const config: NextConfig = {
  output: 'export',
  basePath: '/ui',
  trailingSlash: true,
  poweredByHeader: false,
  productionBrowserSourceMaps: false,
  // Stable identifier makes identical source builds comparable.
  generateBuildId: async () => 'run5b',
};
export default config;
