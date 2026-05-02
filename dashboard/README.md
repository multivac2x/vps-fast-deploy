# Hosting Dashboard

A lightweight Flask dashboard for viewing site versions and triggering promotions
across environments. Sits inside `hosting/dashboard/` and reads `sites/*.yaml` and
`promotion.log` from the parent `hosting/` directory.

---

## Prerequisites

### Python 3.10+

```bash
python3 --version
# If missing:
sudo apt update && sudo apt install -y python3 python3-pip
```

### Caddy

Caddy is the web server that handles reverse proxying, SSL, and basic auth. It isn't
in the default apt repositories, so you add the official Caddy repo first:

```bash
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https curl

curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
  | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg

curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
  | sudo tee /etc/apt/sources.list.d/caddy-stable.list

sudo apt update && sudo apt install -y caddy

caddy version   # confirm
```

Then **disable the systemd service** — the hosting system runs Caddy under PM2, and
having both active at the same time will cause a port conflict:

```bash
sudo systemctl stop caddy
sudo systemctl disable caddy
```

### PM2

PM2 is a process manager that keeps Caddy and all site processes alive, restarts them
on crash, and provides unified logging. PM2 is a Node.js tool, so Node is required
to install it — but Node is not used by the dashboard, by Flask sites, or by static
sites. It is purely an implementation detail of PM2.

```bash
# Add the NodeSource repo for Node 20 LTS
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
sudo apt install -y nodejs

node --version   # v22.x.x
npm --version    # 10.x.x

# Install PM2 globally
sudo npm install -g pm2

pm2 --version   # confirm
```

Configure PM2 to start automatically on boot:

```bash
pm2 startup
# This prints a command — copy and run it, e.g.:
# sudo env PATH=$PATH:/usr/bin pm2 startup systemd -u alice --hp /home/alice
```

You'll run `pm2 save` later, after starting all your processes for the first time,
to persist the list across reboots.

---

## Directory layout (expected)

```
hosting/
├── sites/                 ← one YAML per site
├── auth/                  ← bcrypt credential files
├── promote.py
├── generate-config.py
├── ecosystem.config.js    ← auto-generated
├── Caddyfile              ← auto-generated
├── promotion.log
└── dashboard/
    ├── app.py
    ├── requirements.txt
    ├── README.md
    └── templates/
        └── index.html
```

---

## Install dashboard dependencies

```bash
cd hosting/dashboard
pip install -r requirements.txt
```

This installs `flask` and `pyyaml`. Nothing else is needed.

---

## Running the dashboard

### Option A — directly with Python (quick test)

```bash
cd hosting/dashboard
DASHBOARD_PORT=9000 python3 app.py
# → http://localhost:9000
```

Press Ctrl+C to stop. Fine for local testing but the process dies when you close the terminal.

### Option B — under PM2 (recommended for servers)

Since PM2 is already managing Caddy and all site processes, the dashboard can be
added to the same `ecosystem.config.js` so it is supervised and restarted on crash
alongside everything else.

**Step 1 — verify it works manually first:**

```bash
cd hosting/dashboard
DASHBOARD_PORT=9000 python3 app.py
# Check http://localhost:9000, then Ctrl+C
```

**Step 2 — add the dashboard to `ecosystem.config.js`:**

Open `hosting/ecosystem.config.js` and add the dashboard entry to the `apps` array:

```js
module.exports = {
  apps: [
    // ... existing entries (caddy, site processes) ...

    {
      name: "dashboard",
      cwd: "/absolute/path/to/hosting/dashboard",   // ← update this
      script: "python3",
      args: "app.py",
      interpreter: "none",
      autorestart: true,
      watch: false,
      env: {
        DASHBOARD_PORT: "9000"
      }
    }
  ]
}
```

> Replace `/absolute/path/to/hosting/dashboard` with the real path on your server,
> e.g. `/home/alice/hosting/dashboard` or `/var/hosting/dashboard`.

**Step 3 — load it into PM2:**

```bash
cd hosting
pm2 start ecosystem.config.js --only dashboard

# Verify it's running
pm2 status
pm2 logs dashboard
```

**Step 4 — save the process list:**

```bash
pm2 save
```

This persists the updated process list so the dashboard is included in any
future `pm2 resurrect` or system reboot recovery (assuming `pm2 startup` was
already configured for the hosting system).

---

## Exposing the dashboard via Caddy

By default the dashboard is only reachable on `localhost:9000`. To expose it on a
domain or subdomain, add a site YAML for it so it flows through the same pipeline
as every other site.

**Step 1 — create `sites/dashboard.yaml`:**

```yaml
id: dashboard
name: Hosting Dashboard
type: flask
environments:
  production:
    path: /absolute/path/to/hosting/dashboard
    port: 9000
    pm2_name: dashboard
    auth: dev-team    # ← protect with basic auth; omit to leave open
```

> The `port` must match `DASHBOARD_PORT` in the PM2 config above.

**Step 2 — regenerate configs and reload:**

```bash
cd hosting
python3 generate-config.py
pm2 reload caddy
pm2 reload ecosystem.config.js
```

Caddy now reverse-proxies the dashboard. If you're using a domain name
(e.g. `dashboard.example.com`), Caddy provisions the SSL certificate automatically.

---

## Environment variables

| Variable         | Default | Description               |
|------------------|---------|---------------------------|
| `DASHBOARD_PORT` | `9000`  | Port Flask listens on     |

---

## Auth model

The dashboard has **no built-in login**. Access control is delegated to Caddy —
add an `auth:` key to `sites/dashboard.yaml` referencing a credentials file in
`auth/`, exactly like any other protected environment. Omit it to leave the
dashboard open to anyone who can reach the port.

When triggering a promotion, a **username field** appears in the confirm modal.
You enter your name there — it is passed directly to `promote.py` as the
`promoted-by` field and written to `promotion.log`. This is an audit trail,
not authentication.

---

## What it does

**Version matrix** — one row per site, columns for dev / test / preprod / production.
A `→` arrow appears between adjacent environments when their versions differ.
An `=` means they are already in sync.

**Promote button** — appears on any cell where a promotion is pending. Clicking
opens a confirmation modal where you enter your username, then the dashboard
runs in sequence:

```
promote.py <site> <from> <to> <username>
generate-config.py
pm2 reload caddy
pm2 reload ecosystem.config.js
```

The page reloads automatically once done.

**Promotion history** — the full `promotion.log` rendered as a table, filterable
by site name and environment.

---

## Troubleshooting

**Dashboard shows "No site YAML files found"**
The app resolves `sites/` relative to `hosting/`. Confirm the path is correct:
```bash
python3 -c "from pathlib import Path; print(Path('app.py').resolve().parent.parent / 'sites')"
```

**Promotion fails with `promote.py not found`**
Verify `hosting/promote.py` exists and is executable:
```bash
ls -la ../promote.py
chmod +x ../promote.py
```

**`pm2 reload` fails during a promotion**
PM2 must be on the `PATH` of the user running the dashboard. Check with `which pm2`.
If it returns nothing, find where PM2 is installed and add it to PATH:
```bash
which pm2 || npm root -g
export PATH="$PATH:$(npm root -g)/../.bin"
```
Add that line to `~/.bashrc` or `~/.profile` to make it permanent, then `source ~/.bashrc`.

**Port 9000 already in use**
```bash
lsof -i :9000                        # see what's occupying it
DASHBOARD_PORT=9001 python3 app.py   # pick a different port
```
