# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 1.3.x   | :white_check_mark: |
| < 1.3   | :x:                |

## Reporting a Vulnerability

Please [open an issue](https://github.com/fabriziosalmi/proxmox-lxc-autoscale-ml/issues)
to report a vulnerability. For anything you would rather not discuss in public,
email fabrizio.salmi@gmail.com.

## Deployment notes

The API executes `pct` commands and therefore runs as root. Two settings in
`/etc/lxc_autoscale_ml/lxc_autoscale_api.yaml` matter:

- `server.host` defaults to `0.0.0.0`, which exposes it on every interface. On
  the standard single-node layout, where the ML service runs beside it, set this
  to `127.0.0.1`.
- `authentication.enabled` defaults to `false`. Turn it on, with keys in
  `authentication.api_keys`, if the API has to be reachable from another host —
  and put TLS in front of it, since the API speaks plain HTTP.

## Accepted advisories

Some Dependabot alerts on this repository are open on purpose. They are all in
the documentation site's build toolchain, not in anything that runs on a Proxmox
node.

| Advisory | Package | Why it stays open |
|----------|---------|-------------------|
| [GHSA-67mh-4wv8-2f99](https://github.com/advisories/GHSA-67mh-4wv8-2f99) | esbuild | Lets any website read from the **dev server**. Only reachable while someone runs `npm run dev` locally. |
| [GHSA-4w7w-66w2-5vf9](https://github.com/advisories/GHSA-4w7w-66w2-5vf9) | vite | Path traversal in the **dev server**'s optimized-deps handling. |
| [GHSA-fx2h-pf6j-xcff](https://github.com/advisories/GHSA-fx2h-pf6j-xcff) | vite | `server.fs.deny` bypass, **dev server on Windows only**. |
| [GHSA-v6wh-96g9-6wx3](https://github.com/advisories/GHSA-v6wh-96g9-6wx3) | vite | NTLMv2 hash disclosure via launch-editor, **dev server on Windows only**. |

All four reach the repository through `vitepress` → `vite` → `esbuild`. The
patched versions live in vite 6.4.3 and esbuild 0.25, which require VitePress 2
— currently published only as `2.0.0-alpha`. The site is pinned to VitePress
1.6.4, the newest stable release, and CI runs `vitepress build` only.

None of this affects the published documentation, which is static HTML, or any
component installed on a Proxmox host. These will be closed by moving to
VitePress 2 once it is stable.
