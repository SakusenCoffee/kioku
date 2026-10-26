# Self-hosted server (Docker)

> **Applies to:** web

Run Kioku on your own server or NAS and open it from any browser. Unlike
the [web version](web.md), your collection stays **on the server**: the
browser only shows it, so phones and computers all use the same copy,
with nothing to sync between them. Experimental, like the web version:
back up first.

## Start it

With Docker Compose (`compose.yaml`):

```yaml
services:
  kioku:
    image: ghcr.io/krmanik/kioku-server:latest
    restart: unless-stopped
    ports:
      - "127.0.0.1:8080:8080"
    environment:
      KIOKU_PASSWORD: change-me
    volumes:
      - ./kioku-data:/data
```

```sh
docker compose up -d
```

Everything is kept in `kioku-data/`: profiles, collections, media,
backups (each profile's `backups` folder) and add-ons. Back that folder up.

## HTTPS is required

Browsers run Kioku only on `https://` (or `localhost` on the same
computer), so put it behind a reverse proxy with a certificate. The proxy
must pass WebSockets and large uploads (imports), and leave the
`Cross-Origin-Opener-Policy`/`Cross-Origin-Embedder-Policy` headers alone.

**Caddy**

```
kioku.example.com {
    reverse_proxy 127.0.0.1:8080
}
```

**nginx**

```nginx
server {
    listen 443 ssl;
    server_name kioku.example.com;
    # ssl_certificate ...;
    client_max_body_size 0;
    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $http_host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 1h;
    }
}
```

**Traefik** (labels on the `kioku` service; WebSockets work as is)

```yaml
    labels:
      - traefik.http.routers.kioku.rule=Host(`kioku.example.com`)
      - traefik.http.routers.kioku.tls.certresolver=letsencrypt
      - traefik.http.services.kioku.loadbalancer.server.port=8080
```

## Settings

| Variable | Default | |
| --- | --- | --- |
| `KIOKU_PASSWORD` | | the login password (or `KIOKU_PASSWORD_FILE`, e.g. a Docker secret) |
| `KIOKU_AUTH` | `password` | `none` when your proxy already asks for a login (Authelia, basic auth). Never expose it without either. |
| `KIOKU_PORT` | `8080` | port inside the container |
| `KIOKU_RELAY_ALLOW` | | extra `host:port` add-ons may connect to besides port 443 |
| `KIOKU_IDLE_MINUTES` | `10` | close the collection after this long unused (it opens again on the next action) |
| `KIOKU_LEASE_SECONDS` | `60` | how long a device keeps the collection without using it |

## One device at a time

The collection is used by one device at a time. Opening Kioku on a second
device while the first was used in the last minute asks **Use it here
instead?**; the first device then shows "Kioku is open on another device"
with a button to take it back. Closing the tab frees it at once; opening
Kioku again in the same browser never asks.

Profiles work as in Anki: one per person.

## Syncing

You don't need to sync between your browsers. **Sync** in Kioku runs on
the server, with AnkiWeb or [a sync server](../features/sync-server.md),
for example to also use AnkiDroid or the Kioku apps.

## Add-ons

Add-ons run in the browser, as in the web version; their files are kept on
the server, so every browser gets the ones you installed. Add-ons that
reach other websites need `KIOKU_RELAY_ALLOW` for ports other than 443.
