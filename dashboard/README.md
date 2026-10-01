# Aristotle Dashboard

Live read-only view of your Capital Flywheel reconciliation, powered by the
`snapshots` table in Supabase. **Pull-based:** it shows the latest snapshot you
pushed with `python reconcile.py --push`. Nothing runs on its own — no polling,
no LLM, no background jobs.

## Architecture

```
python reconcile.py --push   (local, reads Schwab, zero LLM tokens)
        │  inserts a row
        ▼
Supabase  snapshots table  (RLS on; service-role only)
        │  server-side read
        ▼
Vercel  Next.js dashboard   (this app — read-only view)
```

## One-time setup

1. **Supabase:** run `../supabase_schema.sql` in the Supabase SQL editor.
2. **Local push:** copy `../supabase_config.example.json` → `../supabase_config.json`,
   fill in `url` + `service_role_key`. Test:
   ```
   python reconcile.py --push
   ```
3. **Dashboard env:** copy `.env.local.example` → `.env.local`, set `SUPABASE_URL`
   and `SUPABASE_SERVICE_ROLE_KEY`.
4. **Run locally:**
   ```
   npm install
   npm run dev        # http://localhost:3000
   ```

## Deploy to Vercel

```
npm i -g vercel
vercel                       # first deploy (set root dir = this folder)
vercel env add SUPABASE_URL
vercel env add SUPABASE_SERVICE_ROLE_KEY
vercel --prod
```

## Security (do before real use)

- The service role key is full-access. It is only used **server-side** (env var),
  never shipped to the browser. Do not add a public Supabase read policy.
- Turn on **Vercel Deployment Protection** (password / SSO) so your financial data
  isn't on a public URL.
- Later: this Vercel domain also becomes your stable Schwab OAuth callback
  (`https://<app>.vercel.app/callback`), retiring the ngrok tunnel.

## Refreshing

Run `python reconcile.py --push` whenever you want fresh numbers (after a fill,
before a session, etc.), then reload the page. That's the whole loop.
