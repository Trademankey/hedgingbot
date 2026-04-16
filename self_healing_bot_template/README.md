# Self-Healing Trading Bot Template

This template gives you the recovery plumbing that most customer bot fleets are missing:

- supervisor-friendly exits
- health endpoint
- internal watchdog
- strict timeouts
- reconnect with backoff
- state reconciliation
- safe mode on mismatch
- Telegram alerts
- `systemd` unit
- Dockerfile and Compose file

It is intentionally exchange-agnostic. You plug your exchange-specific adapter and your strategy into the provided framework.

## What this template does

The bot runs several concurrent loops:

1. **Market data loop** updates the market-data heartbeat.
2. **Ping loop** proves exchange connectivity.
3. **Reconciliation loop** compares expected local state vs exchange state.
4. **Watchdog loop** forces a restart if the bot is alive but stale.
5. **HTTP health server** exposes `/health` and `/live`.
6. **Alerting** pushes important state changes to Telegram.

If the process becomes unhealthy, the watchdog exits with a non-zero code so your supervisor can restart it.

## Files

- `main.py` – app entry point
- `healthcheck.py` – local health probe used by Docker/system checks
- `self_healing_bot/config.py` – env-based config
- `self_healing_bot/models.py` – normalized data models
- `self_healing_bot/health.py` – health state and thresholds
- `self_healing_bot/notify.py` – systemd watchdog notifications without extra deps
- `self_healing_bot/alerting.py` – Telegram alert sender
- `self_healing_bot/exchange.py` – exchange adapter interface + demo adapter
- `self_healing_bot/reconcile.py` – state reconciliation logic
- `self_healing_bot/httpserver.py` – tiny async health server
- `self_healing_bot/runtime.py` – orchestrates loops and self-healing behavior
- `systemd/self-healing-bot.service` – recommended Ubuntu service
- `Dockerfile` / `docker-compose.yml` – optional container deployment

## Quick start

### 1) Copy files to your VPS

Example:

```bash
mkdir -p /opt/self-healing-bot
cp -r . /opt/self-healing-bot/
cd /opt/self-healing-bot
cp .env.example .env
```

### 2) Edit `.env`

Set at least:

```env
BOT_NAME=customer-bot-001
SYMBOLS=BTCUSDT,ETHUSDT
HEALTH_PORT=8080
HEARTBEAT_TIMEOUT_SECONDS=25
MARKET_DATA_TIMEOUT_SECONDS=30
EXCHANGE_TIMEOUT_SECONDS=30
RECONCILIATION_TIMEOUT_SECONDS=90
API_TIMEOUT_SECONDS=10
RECONNECT_MAX_ATTEMPTS=5
TELEGRAM_BOT_TOKEN=123456:ABCDEF...
TELEGRAM_CHAT_ID=123456789
```

### 3) Replace the demo exchange adapter

Open `main.py` and replace `DemoExchangeAdapter` with your real adapter implementation.

At minimum your adapter should implement:

- `ping()`
- `poll_market_snapshot(symbols)`
- `fetch_open_orders()`
- `fetch_positions()`
- `fetch_balances()`
- `reconnect(reason)`

### 4) Run directly

```bash
python3 main.py
```

### 5) Test health

```bash
curl http://127.0.0.1:8080/health
HEALTH_HOST=127.0.0.1 HEALTH_PORT=8080 python3 healthcheck.py
```

## How to wire your live strategy

The framework is separate from your alpha logic. Your strategy should:

- update the **expected orders** after submitting/canceling an order
- update the **expected positions** after fills
- optionally enable **safe mode** if it detects abnormal fills or drift

Useful pattern:

```python
runtime.reconciler.set_expected_orders([...])
runtime.reconciler.set_expected_positions([...])
```

Then the reconciliation loop will compare expected state with exchange state.

## Safe mode behavior

When reconciliation finds unexpected orders or positions, the template:

- enters `SAFE_MODE`
- stops being healthy
- sends an alert
- keeps running long enough for you to inspect
- exits if health remains bad and the watchdog threshold is exceeded

You can change this to auto-cancel orders or flatten positions, but that is strategy-specific and intentionally not automatic in the template.

## `systemd` deployment

1. Copy the service file:

```bash
sudo cp systemd/self-healing-bot.service /etc/systemd/system/self-healing-bot.service
```

2. Edit the `WorkingDirectory`, `ExecStart`, and `EnvironmentFile` paths if needed.

3. Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now self-healing-bot.service
sudo systemctl status self-healing-bot.service
```

4. Follow logs:

```bash
journalctl -u self-healing-bot.service -f
```

## Docker deployment

```bash
docker compose up -d --build
```

Health check:

```bash
docker compose ps
docker inspect --format='{{json .State.Health}}' self-healing-bot
```

## Production notes

- For Docker Compose alone, `HEALTHCHECK` marks the container unhealthy, but the bot's own watchdog still needs to exit when stuck so the restart policy can do its job.
- `systemd` is often the simplest production supervisor for one-bot-per-service on Ubuntu.
- Put **one customer bot per service** to isolate failures.
- Use separate API keys and config per customer.
- Keep exchange-specific code isolated in the adapter.

## Next customization I recommend

After you drop this in, the next step is to add:

- your real exchange adapter
- order journal integration with your strategy
- per-customer Telegram channels or topics
- optional auto-cancel/flatten procedures per strategy rules
