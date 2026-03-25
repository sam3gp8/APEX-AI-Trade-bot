#!/usr/bin/env python3
"""
APEX Trading AI — Home Assistant Add-on Server
Handles all API calls server-side: broker balance, market data, Claude AI, persistence.
No CORS issues since this runs inside the HA container.
"""

import asyncio
import json
import logging
import os
import time
import traceback
from datetime import datetime, date
from pathlib import Path
from typing import Any, Dict, Optional

import aiohttp
from aiohttp import web, ClientSession, ClientTimeout

# ─────────────────────────────────────────────────────────────
#  CONFIG & LOGGING
# ─────────────────────────────────────────────────────────────
LOG_LEVEL = os.environ.get("LOG_LEVEL", "info").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("apex")

DATA_DIR = Path(os.environ.get("DATA_DIR", "/data/apex"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

PORT = int(os.environ.get("PORT", 7123))
STATIC_DIR = Path("/opt/apex/static")

# Read config from environment (set by s6 from HA options)
CFG = {
    "anthropic_api_key": os.environ.get("ANTHROPIC_API_KEY", ""),
    "market_data_source": os.environ.get("MARKET_DATA_SOURCE", "yahoo"),
    "market_data_key": os.environ.get("MARKET_DATA_KEY", ""),
    "trading_mode": os.environ.get("TRADING_MODE", "paper"),
    "risk_level": os.environ.get("RISK_LEVEL", "moderate"),
    "tax_bracket": float(os.environ.get("TAX_BRACKET", "0.24")),
    "stop_loss_pct": float(os.environ.get("STOP_LOSS_PCT", "2.0")),
    "take_profit_pct": float(os.environ.get("TAKE_PROFIT_PCT", "6.0")),
    "max_position_pct": float(os.environ.get("MAX_POSITION_PCT", "5.0")),
    "daily_loss_limit": float(os.environ.get("DAILY_LOSS_LIMIT", "500.0")),
    "auto_analysis_interval": int(os.environ.get("AUTO_ANALYSIS_INTERVAL", "600")),
    "broker_platform": os.environ.get("BROKER_PLATFORM", ""),
    "broker_api_url": os.environ.get("BROKER_API_URL", ""),
    "broker_api_key": os.environ.get("BROKER_API_KEY", ""),
    "broker_api_secret": os.environ.get("BROKER_API_SECRET", ""),
}

# ─────────────────────────────────────────────────────────────
#  PERSISTENT STORAGE (JSON files in /data/apex)
# ─────────────────────────────────────────────────────────────
def _load(filename: str, default: Any) -> Any:
    path = DATA_DIR / filename
    try:
        if path.exists() and path.stat().st_size > 0:
            return json.loads(path.read_text())
    except Exception as e:
        log.warning(f"Could not load {filename}: {e}")
    return default

def _save(filename: str, data: Any) -> None:
    path = DATA_DIR / filename
    try:
        path.write_text(json.dumps(data, indent=2))
    except Exception as e:
        log.error(f"Could not save {filename}: {e}")

def default_state() -> Dict:
    return {
        "botActive": False,
        "connected": False,
        "portfolio": 0.0,
        "startPortfolio": 0.0,
        "brokerBalance": None,
        "balanceFetched": False,
        "winCount": 0,
        "lossCount": 0,
        "todayPnl": 0.0,
        "todayDate": date.today().isoformat(),
        "tradesToday": 0,
        "currentSym": "SPY",
        "currentSig": "HOLD",
        "confidence": 0,
        "optCycles": 0,
        "paramAdj": 0,
        "wrDelta": 0.0,
        "lastOpt": None,
        "lastPriceFetch": None,
        "stratWeights": {"momentum": 0.25, "meanRev": 0.20, "breakout": 0.20, "sentiment": 0.20, "mlPat": 0.15},
        "stratWR": {"momentum": 0.0, "meanRev": 0.0, "breakout": 0.0, "sentiment": 0.0, "mlPat": 0.0},
        "stratActive": {"momentum": True, "meanRev": True, "breakout": False, "sentiment": True, "mlPat": True},
        "taxYear": {"stGains": 0.0, "ltGains": 0.0, "losses": 0.0},
        "riskCfg": {"maxPos": "5%", "stopL": "2%", "takeP": "6%"},
        "sentData": {"Fear/Greed": 62.0, "VIX": 16.4, "Put/Call": 0.82, "Breadth": 74.0},
        "prices": {
            "SPY": 482.5, "QQQ": 412.3, "AAPL": 227.8, "TSLA": 248.6,
            "BTC/USD": 68420.0, "ETH/USD": 3241.0, "NVDA": 875.2,
            "MSFT": 415.7, "AMZN": 198.4, "META": 513.6,
        },
        "positions": [],
        "lastScan": None,
        "mktSrc": "yahoo",
        "mktApiKey": "",
    }

# Load persistent data
STATE = _load("state.json", None)
if STATE is None:
    STATE = default_state()
    log.info("Fresh install — initialized default state")

# Reset daily counters if new day
if STATE.get("todayDate") != date.today().isoformat():
    STATE["todayDate"] = date.today().isoformat()
    STATE["todayPnl"] = 0.0
    STATE["tradesToday"] = 0
    log.info("New day — daily counters reset")

TRADES: list = _load("trades.json", [])
OPTLOG: list = _load("optlog.json", [])
ANALYSES: list = _load("analyses.json", [])

def save_state():
    _save("state.json", STATE)

def save_trades():
    _save("trades.json", TRADES[:500])

def save_optlog():
    _save("optlog.json", OPTLOG[-400:])

def save_analyses():
    _save("analyses.json", ANALYSES[:50])

# ─────────────────────────────────────────────────────────────
#  MARKET DATA — runs server-side, no CORS issues
# ─────────────────────────────────────────────────────────────
TICKER_MAP = {
    "SPY": "SPY", "QQQ": "QQQ", "AAPL": "AAPL", "TSLA": "TSLA",
    "NVDA": "NVDA", "MSFT": "MSFT", "AMZN": "AMZN", "META": "META",
    "BTC/USD": "BINANCE:BTCUSDT", "ETH/USD": "BINANCE:ETHUSDT",
}
YAHOO_MAP = {
    "SPY": "SPY", "QQQ": "QQQ", "AAPL": "AAPL", "TSLA": "TSLA",
    "NVDA": "NVDA", "MSFT": "MSFT", "AMZN": "AMZN", "META": "META",
    "BTC/USD": "BTC-USD", "ETH/USD": "ETH-USD",
}
AV_MAP = {
    "SPY": "SPY", "QQQ": "QQQ", "AAPL": "AAPL", "TSLA": "TSLA",
    "NVDA": "NVDA", "MSFT": "MSFT", "AMZN": "AMZN", "META": "META",
    "BTC/USD": "BTC", "ETH/USD": "ETH",
}

async def fetch_yahoo_price(session: ClientSession, sym: str) -> Optional[float]:
    ticker = YAHOO_MAP.get(sym, sym)
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1m&range=1d"
    try:
        async with session.get(url, timeout=ClientTimeout(total=8),
                               headers={"User-Agent": "Mozilla/5.0"}) as r:
            if r.status == 200:
                d = await r.json(content_type=None)
                price = d.get("chart", {}).get("result", [{}])[0].get("meta", {}).get("regularMarketPrice")
                if price and price > 0:
                    return float(price)
    except Exception as e:
        log.debug(f"Yahoo fetch {sym}: {e}")
    return None

async def fetch_finnhub_price(session: ClientSession, sym: str, api_key: str) -> Optional[float]:
    ticker = TICKER_MAP.get(sym, sym)
    url = f"https://finnhub.io/api/v1/quote?symbol={ticker}&token={api_key}"
    try:
        async with session.get(url, timeout=ClientTimeout(total=6)) as r:
            if r.status == 200:
                d = await r.json()
                c = d.get("c", 0)
                if c and c > 0:
                    return float(c)
    except Exception as e:
        log.debug(f"Finnhub fetch {sym}: {e}")
    return None

async def fetch_alphavantage_price(session: ClientSession, sym: str, api_key: str) -> Optional[float]:
    is_crypto = "/" in sym
    ticker = AV_MAP.get(sym, sym)
    try:
        if is_crypto:
            url = (f"https://www.alphavantage.co/query?function=CURRENCY_EXCHANGE_RATE"
                   f"&from_currency={ticker}&to_currency=USD&apikey={api_key}")
            async with session.get(url, timeout=ClientTimeout(total=8)) as r:
                if r.status == 200:
                    d = await r.json()
                    rate = d.get("Realtime Currency Exchange Rate", {}).get("5. Exchange Rate")
                    if rate:
                        return float(rate)
        else:
            url = (f"https://www.alphavantage.co/query?function=GLOBAL_QUOTE"
                   f"&symbol={ticker}&apikey={api_key}")
            async with session.get(url, timeout=ClientTimeout(total=8)) as r:
                if r.status == 200:
                    d = await r.json()
                    price = d.get("Global Quote", {}).get("05. price")
                    if price:
                        return float(price)
    except Exception as e:
        log.debug(f"AlphaVantage fetch {sym}: {e}")
    return None

async def fetch_all_prices() -> Dict[str, Any]:
    source = STATE.get("mktSrc", CFG["market_data_source"])
    api_key = STATE.get("mktApiKey", CFG["market_data_key"])
    symbols = list(STATE["prices"].keys())
    results = {}
    errors = []

    if source == "sim":
        return {"fetched": 0, "failed": 0, "source": "sim", "prices": {}}

    timeout = ClientTimeout(total=30)
    connector = aiohttp.TCPConnector(limit=5, ssl=False)
    async with ClientSession(timeout=timeout, connector=connector) as session:
        for sym in symbols:
            price = None
            try:
                if source == "yahoo":
                    price = await fetch_yahoo_price(session, sym)
                elif source == "finnhub" and api_key:
                    price = await fetch_finnhub_price(session, sym, api_key)
                elif source == "alphavantage" and api_key:
                    price = await fetch_alphavantage_price(session, sym, api_key)
                await asyncio.sleep(0.15)  # gentle rate limit
            except Exception as e:
                log.debug(f"Price fetch error {sym}: {e}")

            if price and price > 0:
                results[sym] = price
            else:
                errors.append(sym)

    if results:
        STATE["prices"].update(results)
        STATE["lastPriceFetch"] = datetime.now().isoformat()
        save_state()
        log.info(f"Prices fetched: {len(results)} OK, {len(errors)} failed via {source}")

    return {
        "fetched": len(results),
        "failed": len(errors),
        "source": source,
        "prices": STATE["prices"],
        "errors": errors,
        "timestamp": STATE["lastPriceFetch"],
    }

# ─────────────────────────────────────────────────────────────
#  BROKER BALANCE — runs server-side, no CORS
# ─────────────────────────────────────────────────────────────
async def fetch_broker_balance() -> Dict[str, Any]:
    platform = STATE.get("brokerPlatform", CFG["broker_platform"])
    url_base = STATE.get("brokerUrl", CFG["broker_api_url"])
    api_key = STATE.get("brokerApiKey", CFG["broker_api_key"])
    api_secret = STATE.get("brokerApiSecret", CFG["broker_api_secret"])

    if not url_base or not api_key:
        return {"ok": False, "error": "No broker URL or API key configured"}

    log.info(f"Fetching broker balance from {platform} at {url_base}")
    balance = None
    positions_raw = []

    try:
        connector = aiohttp.TCPConnector(ssl=False)
        async with ClientSession(connector=connector, timeout=ClientTimeout(total=10)) as session:

            if platform == "alpaca":
                headers = {
                    "APCA-API-KEY-ID": api_key,
                    "APCA-API-SECRET-KEY": api_secret,
                    "Content-Type": "application/json",
                }
                async with session.get(f"{url_base}/account", headers=headers) as r:
                    if r.status == 200:
                        d = await r.json()
                        balance = float(d.get("portfolio_value") or d.get("equity") or 0)
                        log.info(f"Alpaca balance: ${balance:,.2f}")
                # Fetch positions
                async with session.get(f"{url_base}/positions", headers=headers) as r:
                    if r.status == 200:
                        positions_raw = await r.json()

            elif platform == "binance":
                headers = {"X-MBX-APIKEY": api_key}
                async with session.get(f"{url_base}/account", headers=headers) as r:
                    if r.status == 200:
                        d = await r.json()
                        # Sum USDT + BUSD balances
                        balances = d.get("balances", [])
                        stable = sum(float(b["free"]) + float(b["locked"])
                                     for b in balances if b["asset"] in ("USDT", "BUSD", "USDC"))
                        balance = stable or sum(float(b["free"]) + float(b["locked"]) for b in balances[:3])

            elif platform == "coinbase":
                headers = {"CB-ACCESS-KEY": api_key, "Content-Type": "application/json"}
                async with session.get(f"{url_base}/accounts", headers=headers) as r:
                    if r.status == 200:
                        d = await r.json()
                        accounts = d.get("data", [])
                        balance = sum(float(a.get("native_balance", {}).get("amount", 0)) for a in accounts)

            elif platform == "kraken":
                headers = {"API-Key": api_key, "Content-Type": "application/x-www-form-urlencoded"}
                async with session.post(f"{url_base}/private/Balance",
                                        headers=headers, data={"nonce": str(int(time.time() * 1000))}) as r:
                    if r.status == 200:
                        d = await r.json()
                        result = d.get("result", {})
                        zusd = float(result.get("ZUSD", 0))
                        balance = zusd if zusd > 0 else sum(float(v) for v in result.values())

            else:
                # Generic: try common endpoints
                headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
                for endpoint in ["/account", "/portfolio", "/balance", "/user/balance", "/api/v1/account"]:
                    try:
                        async with session.get(f"{url_base}{endpoint}", headers=headers) as r:
                            if r.status == 200:
                                d = await r.json()
                                for key in ("portfolio_value", "equity", "balance", "cash",
                                            "total", "net_liquidation", "totalWalletBalance"):
                                    if key in d and float(d[key]) > 0:
                                        balance = float(d[key])
                                        break
                                if balance:
                                    break
                    except Exception:
                        continue

    except Exception as e:
        log.error(f"Broker fetch error: {e}")
        return {"ok": False, "error": str(e)}

    if balance is not None and balance > 0:
        STATE["portfolio"] = balance
        STATE["startPortfolio"] = balance
        STATE["brokerBalance"] = balance
        STATE["balanceFetched"] = True
        save_state()

        # Parse positions (Alpaca format)
        parsed_positions = []
        for p in positions_raw[:20]:
            try:
                qty = float(p.get("qty", 0))
                entry = float(p.get("avg_entry_price") or p.get("cost_basis", 0))
                if qty != 0 and entry > 0:
                    parsed_positions.append({
                        "sym": p.get("symbol", "?"),
                        "dir": "LONG" if qty > 0 else "SHORT",
                        "entry": entry,
                        "size": abs(qty),
                        "stop": round(entry * 0.98, 2),
                        "target": round(entry * 1.06, 2),
                        "open": int(time.time() * 1000),
                    })
            except Exception:
                continue

        if parsed_positions:
            STATE["positions"] = parsed_positions
            save_state()

        return {
            "ok": True,
            "balance": balance,
            "platform": platform,
            "positions": parsed_positions,
            "positions_count": len(parsed_positions),
        }

    return {"ok": False, "error": "Could not extract balance from API response"}

# ─────────────────────────────────────────────────────────────
#  CLAUDE AI PROXY — forwards requests from frontend to Anthropic
# ─────────────────────────────────────────────────────────────
async def call_claude(user_prompt: str, system_prompt: str, max_tokens: int = 1200) -> Dict[str, Any]:
    api_key = STATE.get("anthropicKey", CFG["anthropic_api_key"])
    if not api_key:
        return {"ok": False, "text": "No Anthropic API key configured. Add it in the add-on configuration or the sidebar."}

    try:
        async with ClientSession() as session:
            payload = {
                "model": "claude-sonnet-4-5",
                "max_tokens": max_tokens,
                "system": system_prompt,
                "messages": [{"role": "user", "content": user_prompt}],
            }
            headers = {
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            }
            async with session.post(
                "https://api.anthropic.com/v1/messages",
                json=payload, headers=headers,
                timeout=ClientTimeout(total=60),
            ) as r:
                d = await r.json()
                if r.status == 200 and d.get("content"):
                    return {"ok": True, "text": d["content"][0]["text"]}
                err = d.get("error", {}).get("message", f"HTTP {r.status}")
                return {"ok": False, "text": f"Claude API error: {err}"}
    except asyncio.TimeoutError:
        return {"ok": False, "text": "Claude request timed out (60s). Try again."}
    except Exception as e:
        return {"ok": False, "text": f"Claude connection error: {e}"}

def build_context() -> str:
    tot = STATE["winCount"] + STATE["lossCount"]
    wr = round(STATE["winCount"] / tot * 100) if tot > 0 else 0
    recent = TRADES[:8]
    positions = STATE.get("positions", [])
    prices = STATE.get("prices", {})

    pos_lines = "\n".join(
        f"  {p['sym']} {p['dir']} | Entry ${p['entry']} | Now ${prices.get(p['sym'], p['entry']):.2f} "
        f"| P&L {'+' if (prices.get(p['sym'], p['entry']) - p['entry']) * p['size'] >= 0 else ''}${(prices.get(p['sym'], p['entry']) - p['entry']) * p['size']:.2f}"
        for p in positions
    ) or "  None"

    return f"""You are APEX, an elite AI trading system running as a Home Assistant add-on with full server-side access to real market data and broker APIs.

PORTFOLIO:
- Value: ${STATE['portfolio']:,.2f} (started ${STATE['startPortfolio']:,.2f})
- Today P&L: {'+' if STATE['todayPnl'] >= 0 else ''}${STATE['todayPnl']:.2f} | Trades today: {STATE['tradesToday']}
- Win Rate: {wr}% ({STATE['winCount']}W/{STATE['lossCount']}L / {tot} total trades)
- Mode: {STATE.get('tradingMode', 'paper').upper()} | Risk: {STATE.get('riskLevel', 'moderate')}

LIVE PRICES (fetched server-side via {STATE.get('mktSrc', 'yahoo')}):
{chr(10).join(f"  {k}: ${v:,.2f}" for k, v in prices.items())}

OPEN POSITIONS ({len(positions)}):
{pos_lines}

SENTIMENT:
  Fear/Greed: {STATE['sentData']['Fear/Greed']:.0f} | VIX: {STATE['sentData']['VIX']:.1f} | Put/Call: {STATE['sentData']['Put/Call']:.2f} | Breadth: {STATE['sentData']['Breadth']:.0f}

STRATEGIES:
{chr(10).join(f"  {s}: {STATE['stratWR'][s]:.1f}% WR | {STATE['stratWeights'][s]*100:.0f}% weight | {'ACTIVE' if STATE['stratActive'][s] else 'OFF'}" for s in STATE['stratWeights'])}

OPTIMIZATION: {STATE['optCycles']} cycles | {STATE['paramAdj']} adjustments | WR delta: +{STATE['wrDelta']:.1f}%

TAX YTD:
  ST gains: ${STATE['taxYear']['stGains']:.2f} | LT gains: ${STATE['taxYear']['ltGains']:.2f} | Losses: ${STATE['taxYear']['losses']:.2f} | Bracket: {STATE['taxBracket']*100:.0f}%

RISK: Stop {STATE['riskCfg']['stopL']} | Target {STATE['riskCfg']['takeP']} | Max pos {STATE['riskCfg']['maxPos']}

RECENT TRADES: {', '.join(f"{t['sym']}({'WIN' if t['pnl'] >= 0 else 'LOSS'} ${t['pnl']:.2f})" for t in recent) or 'none'}

Be specific, data-driven, and actionable. Reference actual numbers. Use line breaks for readability."""

# ─────────────────────────────────────────────────────────────
#  HTTP ROUTES
# ─────────────────────────────────────────────────────────────
routes = web.RouteTableDef()

@routes.get("/")
async def index(req):
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        return web.FileResponse(index_path)
    return web.Response(text="APEX Trading AI — static files not found", status=404)

# ── State API ──
@routes.get("/api/state")
async def get_state(req):
    return web.json_response(STATE)

@routes.post("/api/state")
async def update_state(req):
    try:
        data = await req.json()
        STATE.update(data)
        save_state()
        return web.json_response({"ok": True})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=400)

# ── Trades API ──
@routes.get("/api/trades")
async def get_trades(req):
    return web.json_response(TRADES)

@routes.post("/api/trades")
async def add_trade(req):
    try:
        trade = await req.json()
        trade["timestamp"] = datetime.now().isoformat()
        TRADES.insert(0, trade)
        save_trades()
        # Update tax tracking
        pnl = trade.get("pnl", 0)
        held_days = trade.get("heldDays", 0)
        if pnl > 0:
            if held_days >= 365:
                STATE["taxYear"]["ltGains"] += pnl
            else:
                STATE["taxYear"]["stGains"] += pnl
        else:
            STATE["taxYear"]["losses"] += abs(pnl)
        save_state()
        return web.json_response({"ok": True, "count": len(TRADES)})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=400)

@routes.delete("/api/trades")
async def clear_trades(req):
    TRADES.clear()
    save_trades()
    return web.json_response({"ok": True})

# ── Optlog API ──
@routes.get("/api/optlog")
async def get_optlog(req):
    return web.json_response(OPTLOG)

@routes.post("/api/optlog")
async def add_optlog(req):
    try:
        entry = await req.json()
        entry["ts"] = datetime.now().strftime("%H:%M:%S")
        OPTLOG.append(entry)
        save_optlog()
        return web.json_response({"ok": True})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=400)

# ── Analyses API ──
@routes.get("/api/analyses")
async def get_analyses(req):
    return web.json_response(ANALYSES)

@routes.post("/api/analyses")
async def add_analysis(req):
    try:
        analysis = await req.json()
        analysis["savedAt"] = datetime.now().isoformat()
        ANALYSES.insert(0, analysis)
        save_analyses()
        return web.json_response({"ok": True, "count": len(ANALYSES)})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=400)

# ── Market Data ──
@routes.get("/api/prices")
async def get_prices(req):
    return web.json_response({"prices": STATE["prices"], "lastFetch": STATE.get("lastPriceFetch")})

@routes.post("/api/prices/fetch")
async def trigger_price_fetch(req):
    result = await fetch_all_prices()
    return web.json_response(result)

# ── Broker Balance ──
@routes.post("/api/broker/connect")
async def broker_connect(req):
    try:
        data = await req.json()
        # Save broker credentials to state (persisted server-side)
        STATE["brokerPlatform"] = data.get("platform", "")
        STATE["brokerUrl"] = data.get("url", "")
        STATE["brokerApiKey"] = data.get("apiKey", "")
        STATE["brokerApiSecret"] = data.get("apiSecret", "")
        STATE["connected"] = True
        save_state()
        log.info(f"Broker credentials saved: {data.get('platform')} @ {data.get('url', '')[:40]}")
        # Now attempt to fetch real balance
        result = await fetch_broker_balance()
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=400)

@routes.post("/api/broker/sync")
async def broker_sync(req):
    result = await fetch_broker_balance()
    return web.json_response(result)

@routes.post("/api/capital/manual")
async def set_manual_capital(req):
    try:
        data = await req.json()
        amount = float(data.get("amount", 0))
        if amount <= 0:
            return web.json_response({"ok": False, "error": "Amount must be > 0"}, status=400)
        STATE["portfolio"] = amount
        STATE["startPortfolio"] = amount
        STATE["brokerBalance"] = amount
        STATE["balanceFetched"] = True
        save_state()
        log.info(f"Manual capital set: ${amount:,.2f}")
        return web.json_response({"ok": True, "balance": amount})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=400)

# ── Claude AI ──
@routes.post("/api/claude/chat")
async def claude_chat(req):
    try:
        data = await req.json()
        user_prompt = data.get("prompt", "")
        max_tokens = int(data.get("maxTokens", 1000))
        if not user_prompt:
            return web.json_response({"ok": False, "error": "No prompt provided"}, status=400)

        # Allow overriding API key from request (if set in sidebar)
        if data.get("apiKey"):
            STATE["anthropicKey"] = data["apiKey"]

        result = await call_claude(user_prompt, build_context(), max_tokens)
        if result["ok"]:
            # Log the analysis
            ANALYSES.insert(0, {
                "type": "chat",
                "prompt": user_prompt[:100],
                "text": result["text"],
                "ts": datetime.now().strftime("%H:%M:%S"),
                "savedAt": datetime.now().isoformat(),
            })
            save_analyses()
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "text": str(e)}, status=500)

@routes.post("/api/claude/scan")
async def claude_scan(req):
    try:
        data = await req.json()
        scan_type = data.get("type", "full")
        if data.get("apiKey"):
            STATE["anthropicKey"] = data["apiKey"]

        prompts = {
            "full": """Perform a comprehensive market scan across all monitored symbols. For each symbol provide:
SYMBOL | SIGNAL | CONF% | Entry $X | Target $X | Stop $X | Reason (15 words max)
Then provide: MARKET OVERVIEW (3 sentences), TOP TRADE (best setup now with full details), RISK WARNING.""",
            "portfolio": """Review my open positions and portfolio. For each position: HOLD/EXIT/ADD recommendation with reasoning.
Also: allocation analysis, risk exposure, win rate pattern analysis, top 3 improvement actions.""",
            "tax": """Tax optimization strategy based on my YTD data:
1. Current liability calculation  2. Loss harvesting opportunities  3. LTCG staging candidates
4. Wash sale risks  5. Year-end moves  6. Estimated quarterly payments  7. Tax-efficient sizing""",
            "risk": """Risk assessment:
1. Portfolio heat map  2. Correlation risk  3. Max drawdown scenario  4. VIX exposure
5. Concentration risk  6. Liquidity risk  7. Risk-adjusted return  8. Immediate actions""",
        }

        prompt = prompts.get(scan_type, prompts["full"])
        result = await call_claude(prompt, build_context(), 1600)
        if result["ok"]:
            ANALYSES.insert(0, {
                "type": scan_type,
                "text": result["text"],
                "ts": datetime.now().strftime("%H:%M:%S"),
                "prices": dict(STATE["prices"]),
                "savedAt": datetime.now().isoformat(),
            })
            save_analyses()
            log.info(f"Claude {scan_type} scan complete")
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "text": str(e)}, status=500)

@routes.post("/api/claude/symbol")
async def claude_symbol(req):
    try:
        data = await req.json()
        sym = data.get("symbol", "SPY")
        if data.get("apiKey"):
            STATE["anthropicKey"] = data["apiKey"]
        price = STATE["prices"].get(sym, 0)
        prompt = f"""Deep dive on {sym} at ${price:,.2f}:
1. Technical picture (RSI/MACD/MAs/S&R)  2. Momentum  3. Exact entry price & trigger
4. T1 and T2 targets with reasoning  5. Stop loss level & why  6. Position size for my portfolio
7. R:R ratio  8. Time horizon  9. VERDICT: BUY/SELL/HOLD + confidence %  10. Key levels to watch"""
        result = await call_claude(prompt, build_context(), 1000)
        if result["ok"]:
            ANALYSES.insert(0, {
                "type": "deepDive", "sym": sym,
                "text": result["text"],
                "ts": datetime.now().strftime("%H:%M:%S"),
                "savedAt": datetime.now().isoformat(),
            })
            save_analyses()
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "text": str(e)}, status=500)

# ── Config ──
@routes.get("/api/config")
async def get_config(req):
    # Return non-sensitive config
    return web.json_response({
        "tradingMode": CFG["trading_mode"],
        "riskLevel": CFG["risk_level"],
        "taxBracket": CFG["tax_bracket"],
        "stopLossPct": CFG["stop_loss_pct"],
        "takeProfitPct": CFG["take_profit_pct"],
        "maxPositionPct": CFG["max_position_pct"],
        "dailyLossLimit": CFG["daily_loss_limit"],
        "autoAnalysisInterval": CFG["auto_analysis_interval"],
        "marketDataSource": CFG["market_data_source"],
        "brokerPlatform": CFG["broker_platform"],
        "hasAnthropicKey": bool(CFG["anthropic_api_key"]),
        "hasBrokerKey": bool(CFG["broker_api_key"]),
        "hasMarketKey": bool(CFG["market_data_key"]),
        "version": "1.0.0",
    })

@routes.post("/api/config/keys")
async def save_runtime_keys(req):
    """Save API keys entered in the UI at runtime (stored in state.json)."""
    try:
        data = await req.json()
        if "anthropicKey" in data:
            STATE["anthropicKey"] = data["anthropicKey"]
        if "mktSrc" in data:
            STATE["mktSrc"] = data["mktSrc"]
        if "mktApiKey" in data:
            STATE["mktApiKey"] = data["mktApiKey"]
        save_state()
        return web.json_response({"ok": True})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=400)

# ── Health ──
@routes.get("/api/health")
async def health(req):
    return web.json_response({
        "status": "ok",
        "version": "1.0.0",
        "uptime": time.time(),
        "trades": len(TRADES),
        "analyses": len(ANALYSES),
        "lastPriceFetch": STATE.get("lastPriceFetch"),
        "portfolio": STATE["portfolio"],
        "botActive": STATE["botActive"],
    })

# ── Static files ──
@routes.get("/{path:.*}")
async def static_files(req):
    path = req.match_info["path"] or "index.html"
    file_path = STATIC_DIR / path
    if file_path.exists() and file_path.is_file():
        return web.FileResponse(file_path)
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        return web.FileResponse(index_path)
    return web.Response(status=404, text=f"Not found: {path}")

# ─────────────────────────────────────────────────────────────
#  BACKGROUND TASKS
# ─────────────────────────────────────────────────────────────
async def price_refresh_loop():
    """Refresh prices every 30s if live source configured."""
    await asyncio.sleep(5)  # startup delay
    while True:
        try:
            src = STATE.get("mktSrc", CFG["market_data_source"])
            if src != "sim" and STATE.get("botActive", False):
                await fetch_all_prices()
        except Exception as e:
            log.error(f"Price refresh error: {e}")
        await asyncio.sleep(30)

async def sentiment_drift_loop():
    """Gently drift sentiment values to simulate live feed."""
    import random
    while True:
        await asyncio.sleep(15)
        try:
            limits = {"Fear/Greed": (0, 100), "VIX": (10, 60), "Put/Call": (0.4, 1.8), "Breadth": (10, 95)}
            for k, (lo, hi) in limits.items():
                v = STATE["sentData"].get(k, 50)
                v += random.uniform(-1.5, 1.5)
                STATE["sentData"][k] = round(max(lo, min(hi, v)), 2)
            save_state()
        except Exception:
            pass

# ─────────────────────────────────────────────────────────────
#  APP STARTUP
# ─────────────────────────────────────────────────────────────
async def on_startup(app):
    log.info("APEX Trading AI starting up...")
    # Apply HA config to state defaults (only if not user-overridden)
    if not STATE.get("tradingMode"):
        STATE["tradingMode"] = CFG["trading_mode"]
    if not STATE.get("riskLevel"):
        STATE["riskLevel"] = CFG["risk_level"]
    STATE.setdefault("taxBracket", CFG["tax_bracket"])
    # Start background tasks
    app["price_task"] = asyncio.create_task(price_refresh_loop())
    app["sentiment_task"] = asyncio.create_task(sentiment_drift_loop())
    log.info(f"APEX ready on port {PORT} | Mode: {CFG['trading_mode']} | Data: {CFG['market_data_source']}")

async def on_cleanup(app):
    log.info("APEX shutting down — saving state...")
    save_state()
    for task_name in ("price_task", "sentiment_task"):
        task = app.get(task_name)
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

def make_app():
    app = web.Application()
    app.add_routes(routes)

    # CORS headers for ingress
    async def cors_middleware(request, handler):
        response = await handler(request)
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        return response

    app.middlewares.append(web.middleware(cors_middleware))
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    return app

if __name__ == "__main__":
    log.info(f"Starting APEX Trading AI on port {PORT}")
    app = make_app()
    web.run_app(app, host="0.0.0.0", port=PORT, print=None)
