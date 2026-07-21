import { defineConfig } from 'vitepress'

export default defineConfig({
  title: 'LXC AutoScale ML',
  description: 'ML-powered autoscaling for Proxmox LXC containers',
  base: '/proxmox-lxc-autoscale-ml/',

  head: [
    // Everything this site loads is first-party. 'unsafe-inline' is required
    // because VitePress emits an inline appearance script and inline styles.
    // Applied to the built site only: `vitepress dev` serves HMR over a
    // websocket, which a strict connect-src would block as soon as the dev
    // server is not same-origin (--host, or a custom server.hmr.port).
    ...(process.env.NODE_ENV === 'production'
      ? [
          [
            'meta',
            {
              'http-equiv': 'Content-Security-Policy',
              content:
                "default-src 'self'; script-src 'self' 'unsafe-inline'; " +
                "style-src 'self' 'unsafe-inline'; img-src 'self' data:; " +
                "font-src 'self'; connect-src 'self'; base-uri 'self'; form-action 'self'",
            },
          ] as [string, Record<string, string>],
        ]
      : []),
    ['link', { rel: 'icon', type: 'image/png', href: '/favicon.png' }],
    ['meta', { name: 'theme-color', content: '#3eaf7c' }],
    ['meta', { name: 'og:type', content: 'website' }],
    ['meta', { name: 'og:title', content: 'LXC AutoScale ML Documentation' }],
    ['meta', { name: 'og:description', content: 'ML-powered autoscaling for Proxmox LXC containers' }],
  ],

  lastUpdated: true,
  cleanUrls: true,

  themeConfig: {
    logo: '/logo.png',

    nav: [
      { text: 'Guide', link: '/guide/getting-started' },
      { text: 'Components', items: [
        { text: 'API', link: '/components/api' },
        { text: 'Model', link: '/components/model' },
        { text: 'Monitor', link: '/components/monitor' },
      ]},
      { text: 'Reference', items: [
        { text: 'Configuration', link: '/reference/configuration' },
        { text: 'API Endpoints', link: '/reference/api-endpoints' },
        { text: 'Metrics', link: '/reference/metrics' },
      ]},
    ],

    sidebar: {
      '/guide/': [
        {
          text: 'Introduction',
          items: [
            { text: 'What is LXC AutoScale ML?', link: '/guide/introduction' },
            { text: 'Getting Started', link: '/guide/getting-started' },
            { text: 'Architecture', link: '/guide/architecture' },
          ]
        },
        {
          text: 'Installation',
          items: [
            { text: 'Requirements', link: '/guide/requirements' },
            { text: 'Installation', link: '/guide/installation' },
            { text: 'Upgrading', link: '/guide/upgrading' },
            { text: 'Uninstallation', link: '/guide/uninstallation' },
          ]
        },
        {
          text: 'Usage',
          items: [
            { text: 'Basic Usage', link: '/guide/usage' },
            { text: 'Examples', link: '/guide/examples' },
          ]
        },
        {
          text: 'Support',
          items: [
            { text: 'Troubleshooting', link: '/guide/troubleshooting' },
            { text: 'FAQ', link: '/guide/faq' },
          ]
        },
      ],
      '/components/': [
        {
          text: 'Components',
          items: [
            { text: 'Overview', link: '/components/' },
            { text: 'API', link: '/components/api' },
            { text: 'Model', link: '/components/model' },
            { text: 'Monitor', link: '/components/monitor' },
          ]
        },
      ],
      '/reference/': [
        {
          text: 'Reference',
          items: [
            { text: 'Configuration', link: '/reference/configuration' },
            { text: 'API Endpoints', link: '/reference/api-endpoints' },
            { text: 'Metrics', link: '/reference/metrics' },
            { text: 'Environment Variables', link: '/reference/environment' },
          ]
        },
      ],
    },

    socialLinks: [
      { icon: 'github', link: 'https://github.com/fabriziosalmi/proxmox-lxc-autoscale-ml' }
    ],

    footer: {
      message: 
        'Released under the MIT License. · <a href="https://fabriziosalmi.github.io/privacy">Privacy &amp; legal</a>',
      copyright: 'Copyright 2024 Fabrizio Salmi'
    },

    editLink: {
      pattern: 'https://github.com/fabriziosalmi/proxmox-lxc-autoscale-ml/edit/main/docs/:path',
      text: 'Edit this page on GitHub'
    },

    search: {
      provider: 'local'
    },

    outline: {
      level: [2, 3]
    }
  }
})
