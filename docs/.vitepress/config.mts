import { defineConfig } from 'vitepress'

export default defineConfig({
  title: 'LXC AutoScale ML',
  description: 'ML-powered autoscaling for Proxmox LXC containers',

  head: [
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
      message: 'Released under the MIT License.',
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
