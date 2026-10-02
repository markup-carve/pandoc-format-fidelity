import { defineConfig } from '@playwright/test'
export default defineConfig({
  testDir: './tests/browser',
  fullyParallel: true,
  reporter: 'list',
  use: { baseURL: 'http://127.0.0.1:4174', trace: 'retain-on-failure' },
  webServer: { command: 'python3 -m http.server 4174 --bind 127.0.0.1 --directory dist', url: 'http://127.0.0.1:4174', reuseExistingServer: !process.env.CI },
  projects: [ { name:'desktop', use: { viewport: { width:1440, height:1000 } } }, { name:'mobile', use: { viewport: { width:390, height:844 }, isMobile:true, hasTouch:true } } ],
})
