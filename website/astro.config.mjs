import { defineConfig } from 'astro/config';

export default defineConfig({
  site: 'https://zerooperators.com',
  output: 'static',
  build: {
    assets: '_assets'
  }
});
