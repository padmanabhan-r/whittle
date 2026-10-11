# Deploying Whittle on a domain with HTTPS

For Sethuraman, who owns the AWS side. The app takes a model API key in a form,
so it must be served over HTTPS. Browsers flag a password field on plain HTTP as
"not secure", and they are right: the key would cross the internet in cleartext.
Certificates are issued to hostnames, not IP addresses, so the deployment needs a
domain. The domain is **whittleai.site**, bought on GoDaddy for one year with no
auto-renew. Everything below takes about an hour, most of it waiting on DNS.

Where the repository is checked out on the instance is written as
`/opt/whittle` below; use the real path.

## 1. Buy the domain on GoDaddy

1. Buy `whittleai.site` at https://www.godaddy.com/en-in. The ₹129 price is the
   first year only; renewal is far higher, which does not matter for the hackathon.
2. At checkout, set the term to **1 year**, remove every add-on GoDaddy
   pre-selects (domain protection, email, the website builder) and turn
   **auto-renew off**. This is a throwaway domain for the hackathon and must not
   renew. If checkout offers no switch, turn it off straight after buying:
   My Products, the domain, Renewal settings.
3. Keep GoDaddy's own nameservers. There is nothing to change there.

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
2. **Add new record**: Type `A`, Name `@`, Value the Elastic IP, TTL `600 seconds`.
3. **Add new record**: Type `A`, Name `www`, Value the Elastic IP, TTL `600 seconds`.
   (If a `CNAME www` record exists, delete it first; GoDaddy will not let both exist.)
4. Do **not** use GoDaddy's "Forwarding" feature. Forwarding is an HTTP redirect
   through GoDaddy's servers and breaks the certificate.
5. Wait, then check from any machine:

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
cd /opt/whittle && git pull
cd web && VITE_API_URL="" npm ci && npm run build      # writes web/dist
```

## 6. Configure Caddy and start it

```bash
cd /opt/whittle
sudo cp deploy/Caddyfile /etc/caddy/Caddyfile
sudo sed -i 's#/opt/whittle#'"$PWD"'#' /etc/caddy/Caddyfile        # only if the checkout is elsewhere
sudo systemctl enable --now caddy
sudo systemctl reload caddy
sudo journalctl -u caddy -n 30 --no-pager                            # "certificate obtained successfully"
```

`deploy/Caddyfile` serves `web/dist` as static files, proxies `/api`, `/proxy`
and `/health` to the backend on port 8787, keeps the event stream unbuffered,
and redirects `www.` to the bare domain.

## 7. Run the backend on localhost only

The Vite dev server on 5173 is no longer needed; Caddy serves the build. The API
keeps running as before, but it need not listen on all interfaces any more:

```bash
cd /opt/whittle/api
uv run uvicorn costcutter.server:app --host 127.0.0.1 --port 8787
```

Keep `.env.local` and the Docker setup exactly as they are. If the port is not
8787, `WHITTLE_API_PORT` must match it, because the sandbox reaches the proxy at
`host.docker.internal:<port>`.

## 8. Check

- `https://whittleai.site/health` answers `{"status":"ok"}`.
- The browser shows the padlock on `https://whittleai.site` and no "not secure" text.
- `http://whittleai.site` and `https://www.whittleai.site` both land on the HTTPS bare domain.
- Start a scan of a public repository: the events stream in as they happen.

If the UI loads but every request fails, the web build was made without
`VITE_API_URL=""` and still calls `http://localhost:8787`; rebuild (step 5).
If Caddy logs a certificate error, DNS is not pointing at the instance yet or
port 80 is closed; Caddy needs both to prove it owns the name.
