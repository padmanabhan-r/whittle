# Deploying Whittle on a domain with HTTPS

For Sethuraman, who owns the AWS side. The app takes a model API key in a form,
so it must be served over HTTPS. Browsers flag a password field on plain HTTP as
"not secure", and they are right: the key would cross the internet in cleartext.
Certificates are issued to hostnames, not IP addresses, so the deployment needs a
domain. The domain is **whittleai.site**, bought on GoDaddy for one year with no
auto-renew. Everything below takes about an hour, most of it waiting on DNS.

The repository is checked out at `/home/ubuntu/whittle-main`.

## 1. Buy the domain on GoDaddy

The domain is in the GoDaddy account. Keep GoDaddy's nameservers; do not use
domain forwarding.

## 2. Give the instance an address that does not change

1. EC2 console, **Network & Security, Elastic IPs**, **Allocate Elastic IP
   address**, then **Actions, Associate** it with the Whittle instance. Without
   one, the public IP (today `3.239.203.8`) changes on every stop and start,
   and the DNS record would go stale. An Elastic IP is free while it is attached
   to a running instance.
2. **Security group** of the instance, inbound rules: allow TCP **80** and
   **443** from `0.0.0.0/0`. Ports 5173 and 8787 can be removed from the group
   once Caddy is in front; the sandbox reaches the proxy through
   `host.docker.internal`, not the public address.

## 3. Point the domain at the instance

In GoDaddy: **My Products**, the domain, **DNS**, **Manage DNS**.

1. Delete the default `A` record whose value is `Parked`.
2. **Add new record**: Type `A`, Name `@`, Value `35.171.208.95`, TTL `600 seconds`.
3. **Add new record**: Type `A`, Name `www`, Value `35.171.208.95`, TTL `600 seconds`.
   (If a `CNAME www` record exists, delete it first; GoDaddy will not let both exist.)
4. Remove any stale `AAAA` records for `@` or `www` unless IPv6 is deliberately
   configured for this instance. An incorrect IPv6 record can make some
   visitors reach the wrong host.
5. Do **not** use GoDaddy's "Forwarding" feature. Forwarding is an HTTP redirect
   through GoDaddy's servers and breaks the certificate.
6. Wait, then check from any machine:

   ```bash
   dig +short whittleai.site        # must print the Elastic IP
   dig +short www.whittleai.site    # same
   ```

   Usually under ten minutes. Nothing below works until this does.

## 4. Install Caddy on the instance

Caddy is a web server that requests and renews the Let's Encrypt certificate by
itself, as soon as the DNS record points at it.

```bash
# Ubuntu / Debian. For Amazon Linux see https://caddyserver.com/docs/install
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update && sudo apt install -y caddy
```

## 5. Build the UI for one origin

The UI reads the API address at build time. Built with `VITE_API_URL` empty, it
calls `/api` on whatever host served it, so the UI and the API share one
origin and one certificate.

```bash
cd /home/ubuntu/whittle-main
cd web && VITE_API_URL="" npm ci && npm run build
sudo install -d -o root -g root -m 755 /var/www/whittle
sudo cp -a dist/. /var/www/whittle/
```

## 6. Configure Caddy and start it

```bash
cd /home/ubuntu/whittle-main
sudo install -D -o root -g root -m 644 deploy/Caddyfile /etc/caddy/Caddyfile
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl enable --now caddy
sudo systemctl reload caddy
sudo journalctl -u caddy -n 30 --no-pager
```

`deploy/Caddyfile` routes `/api`, `/proxy` and `/health` to the backend on port
8787 before falling back to the static UI. API and proxy routes use separate
`handle` blocks so the SPA's `try_files` rewrite cannot swallow API requests.
The public `/health` route is rewritten to the backend's `/proxy/health`
endpoint. API responses are unbuffered for event streams. Caddy redirects
`www.` to the bare domain.

## 7. Run the backend behind Caddy

The Vite dev server on 5173 is no longer needed; Caddy serves the static UI.
Whittle's system service runs the API on port 8787. Keep it listening on
`0.0.0.0` so the Docker sandbox's proxy relay can reach it. Restrict the API
port at the security group; only ports 80 and 443 should be public.

```bash
sudo systemctl status whittle.service --no-pager
```

Keep `.env.local` and the Docker setup exactly as they are. If the port is not
8787, `WHITTLE_API_PORT` must match it, because the sandbox reaches the proxy at
`host.docker.internal:<port>`.

## 8. Check

- `https://whittleai.site/health` answers `{"status":"ok"}`.
- `https://whittleai.site` loads the UI and its API calls use the same HTTPS origin.
- The browser shows the padlock on `https://whittleai.site` and no "not secure" text.
- `http://whittleai.site` and `https://www.whittleai.site` both land on the HTTPS bare domain.
- Start a scan of a public repository: the events stream in as they happen.

If Caddy logs a certificate error, DNS is not pointing at the instance yet or
port 80 is closed; Caddy needs both to prove it owns the name.
