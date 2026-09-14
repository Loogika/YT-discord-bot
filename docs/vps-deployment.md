# VPS Deployment

The production checkout is expected at `/opt/loogikabot`.

## Before deployment

Run the read-only environment report:

```bash
bash scripts/vps-audit.sh
```

Confirm that Docker Engine and the Docker Compose plugin are available. Stop
the old bot job immediately before starting LoogikaBot to avoid two bots using
the same Discord token.

## First deployment

Clone the repository into `/opt/loogikabot`, then create `.env` from
`.env.example`. The real `.env` must stay only on the VPS.

Deploy or update the Compose stack:

```bash
bash scripts/vps-deploy.sh
```

The script validates the environment, builds the bot image, starts all Compose
services, and prints their state.

## Verification

```bash
docker compose logs --tail=100 bot
docker compose ps
```

Expected bot events:

```text
bot.commands.synced
bot.ready
```

Grafana listens only on `127.0.0.1:3000`. Access it from a workstation with an
SSH tunnel:

```bash
ssh -L 3000:127.0.0.1:3000 user@server
```

## Expose Grafana on loogika.ru

Keep the Grafana container bound to `127.0.0.1:3000` and expose it through
Nginx on the VPS. This makes Grafana available at `https://loogika.ru/` without
publishing port `3000` to the internet.

First, make sure DNS `A` records for `loogika.ru` and `www.loogika.ru` point to
the VPS public IP. Then install Nginx and Certbot:

```bash
sudo apt update
sudo apt install -y nginx certbot python3-certbot-nginx
```

Create the first certificate. Stop Nginx temporarily so Certbot can bind port
`80` for the domain check:

```bash
sudo systemctl stop nginx
sudo certbot certonly --standalone -d loogika.ru -d www.loogika.ru
sudo systemctl start nginx
```

Install the project Nginx config and reload Nginx:

```bash
sudo cp /opt/loogikabot/deploy/nginx-loogika-grafana.conf /etc/nginx/sites-available/loogika.ru
sudo ln -sf /etc/nginx/sites-available/loogika.ru /etc/nginx/sites-enabled/loogika.ru
sudo nginx -t
sudo systemctl reload nginx
```

Deploy the Compose stack so Grafana uses the public root URL from
`compose.yaml`:

```bash
cd /opt/loogikabot
docker compose up -d --build
```

Open `https://loogika.ru/` and sign in as `admin` with the
`GRAFANA_ADMIN_PASSWORD` value from `.env`.

## Optional autostart

Install `deploy/loogikabot.service` as `/etc/systemd/system/loogikabot.service`,
then enable it:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now loogikabot.service
```

Do this only after the first manual deployment has passed verification.
