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

## Optional autostart

Install `deploy/loogikabot.service` as `/etc/systemd/system/loogikabot.service`,
then enable it:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now loogikabot.service
```

Do this only after the first manual deployment has passed verification.
