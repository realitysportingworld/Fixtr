# Deploying Fixtr

One small Linux server (1 vCPU / 1–2 GB RAM is plenty to start) runs everything:
Postgres, the API, and Caddy for HTTPS. Caddy gets and renews the certificate
by itself.

## What you need

- A server with Docker: Hetzner, DigitalOcean, Linode or any VPS
- A domain or subdomain, e.g. `fixtr.yourdomain.com`
- An SMTP account for password reset emails: Postmark, Amazon SES, Brevo, Mailgun...

## First deploy

1. **DNS.** Add an `A` record for your domain pointing at the server's IP. Wait
   until `ping fixtr.yourdomain.com` shows that IP.
2. **Firewall.** Open ports 22, 80 and 443 only.
3. **Code and settings** on the server:
   ```
   git clone <your repo> fixtr && cd fixtr
   cp .env.prod.example .env.prod
   nano .env.prod    # DOMAIN, passwords, SECRET_KEY, SMTP; see the comments
   ```
4. **Start it:**
   ```
   docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build
   ```
   Migrations run automatically when the API starts.
5. **Check:** `https://fixtr.yourdomain.com/health` should say
   `{"status":"ok","database":"ok"}`.

## Point the app at it

Build the app with the API address:

```
EXPO_PUBLIC_API_URL=https://fixtr.yourdomain.com/api/v1
```

(in `mobile/.env`, or as an EAS build environment variable). Share links come
out as `https://fixtr.yourdomain.com/c/...` automatically.

## Updating

```
git pull
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build
```

## Backups

The database lives in the `pgdata` Docker volume. Back it up daily, e.g. with a
cron job, and copy the file off the server:

```
docker compose -f docker-compose.prod.yml --env-file .env.prod exec -T db \
  pg_dump -U fixtr -Fc fixtr > backup-$(date +%F).dump
```

Restore with `pg_restore -U fixtr -d fixtr --clean backup.dump`.

## Notes

- Logs: `docker compose -f docker-compose.prod.yml logs -f api`
- Rate limits are stored in Postgres, so they hold across restarts and API workers.
- Changing `SECRET_KEY` signs everyone out.
- Running more than one API server: run `alembic upgrade head` once as a
  separate step instead of on every start.
