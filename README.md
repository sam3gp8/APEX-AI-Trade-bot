# 📈 APEX Trading AI — Home Assistant Add-on

<div align="center">

[![Build Status](https://github.com/YOUR_GITHUB_USERNAME/apex-trading-addon/actions/workflows/build.yml/badge.svg)](https://github.com/YOUR_GITHUB_USERNAME/apex-trading-addon/actions)
[![Release](https://img.shields.io/github/v/release/YOUR_GITHUB_USERNAME/apex-trading-addon?style=flat)](https://github.com/YOUR_GITHUB_USERNAME/apex-trading-addon/releases)
[![License](https://img.shields.io/github/license/YOUR_GITHUB_USERNAME/apex-trading-addon)](LICENSE)
[![HA Addon](https://img.shields.io/badge/Home%20Assistant-Add--on-41BDF5?logo=home-assistant)](https://www.home-assistant.io/addons/)

**AI-powered trading bot running permanently inside Home Assistant OS.**  
Claude AI market analysis · Real prices server-side · Broker API (no CORS) · Persistent storage

[Installation](#-installation) · [Configuration](#-configuration) · [Brokers](#-supported-brokers) · [Docs](docs/INSTALL_GUIDE.html) · [Issues](https://github.com/YOUR_GITHUB_USERNAME/apex-trading-addon/issues)

</div>

---

## ✨ Features

| Feature | Detail |
|---|---|
| 🤖 **Claude AI Analysis** | Full market scans, portfolio review, tax strategy, risk assessment via claude-sonnet-4-5 |
| 📡 **Live Market Data** | Yahoo Finance (free), Finnhub, Alpha Vantage — fetched server-side, no CORS |
| 🔌 **Broker Integration** | Alpaca, Binance, Coinbase, Kraken, IBKR — real balance sync and order execution |
| 💾 **Persistent Storage** | All data in `/data/apex/` — survives restarts, HA updates, and reboots |
| 🧠 **Self-Optimization** | Strategy weights auto-adjust after every trade using historical performance |
| 💰 **Tax Engine** | YTD P&L tracking, LTCG staging, loss harvesting, wash sale detection |
| 24/7 **Always Running** | Runs as a background service — no browser needed for auto-analysis |
| 🏠 **HA Ingress** | Appears in your HA sidebar, accessible via standard HA authentication |

## 🚀 Installation

### One-Click (via HA Add-on Repository)

[![Add Repository to HA](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2FYOUR_GITHUB_USERNAME%2Fapex-trading-addon)

Or manually:
1. In HA: **Settings → Add-ons → Store → ⋮ → Repositories**
2. Add: `https://github.com/YOUR_GITHUB_USERNAME/apex-trading-addon`
3. Find **APEX Trading AI** → Install

### Self-Installer Script (SSH / Terminal Add-on)

```bash
# From the HA Terminal add-on or SSH session:
curl -fsSL https://raw.githubusercontent.com/YOUR_GITHUB_USERNAME/apex-trading-addon/main/install.sh | bash
```

### Manual (Samba / File Share)

1. Download the [latest release zip](https://github.com/YOUR_GITHUB_USERNAME/apex-trading-addon/releases/latest)
2. Map HA as a network drive via the **Samba share** add-on
3. Copy `apex_trading/` into the `addons` share
4. In HA: Settings → Add-ons → Store → ⋮ → Check for updates → Install APEX Trading AI

📖 **[Full illustrated installation guide →](docs/INSTALL_GUIDE.html)**

---

## ⚙️ Configuration

After installing, go to **Settings → Add-ons → APEX Trading AI → Configuration**:

```yaml
# Required for AI features
anthropic_api_key: "sk-ant-YOUR-KEY"   # from console.anthropic.com

# Market data (yahoo = free, no key needed)
market_data_source: "yahoo"            # yahoo | finnhub | alphavantage | sim
market_data_key: ""                    # only for finnhub/alphavantage

# Trading
trading_mode: "paper"                  # paper (safe) | live (real orders)
risk_level: "moderate"                 # conservative | moderate | aggressive
stop_loss_pct: 2.0
take_profit_pct: 6.0
max_position_pct: 5.0

# Broker (optional - for balance sync & live trading)
broker_platform: "alpaca"
broker_api_url: "https://paper-api.alpaca.markets/v2"
broker_api_key: "YOUR-ALPACA-KEY"
broker_api_secret: "YOUR-ALPACA-SECRET"

# Claude auto-scan interval (seconds, 0 = manual only)
auto_analysis_interval: 600
```

---

## 🔌 Supported Brokers

All broker API calls happen **server-side inside the HA container** — no CORS restrictions.

| Broker | Balance | Orders | API URL |
|---|---|---|---|
| **Alpaca** (paper) | ✅ | ✅ | `paper-api.alpaca.markets/v2` |
| **Alpaca** (live) | ✅ | ✅ | `api.alpaca.markets/v2` |
| **Binance** | ✅ | ✅ | `api.binance.com/api/v3` |
| **Coinbase Advanced** | ✅ | ✅ | `api.coinbase.com/api/v3` |
| **Kraken** | ✅ | ✅ | `api.kraken.com/0` |
| **Interactive Brokers** | ✅ | ✅ | `localhost:5000/v1/api` |
| **TD Ameritrade** | ✅ | ⚠️ | `api.tdameritrade.com/v1` |
| Custom/Other | ✅ | — | Auto-detected |

---

## 📡 Market Data Sources

| Source | API Key | Rate Limit | Notes |
|---|---|---|---|
| **Yahoo Finance** | None (free) | ~2000/hr | Default. Works immediately. |
| **Finnhub** | Free at [finnhub.io](https://finnhub.io) | 60/min | Reliable, stocks + crypto |
| **Alpha Vantage** | Free at [alphavantage.co](https://alphavantage.co) | 25/day | |
| **Simulated** | None | ∞ | Realistic drift, offline use |

---

## 🏗️ Architecture

```
Home Assistant OS
└── APEX Add-on Container (port 7123)
    ├── Python aiohttp server
    │   ├── /api/broker/*    → Direct broker calls (server-side, no CORS)
    │   ├── /api/prices/*    → Yahoo/Finnhub/AlphaVantage fetch
    │   ├── /api/claude/*    → Anthropic API proxy
    │   └── /static/         → Dashboard UI
    └── /data/apex/          → Persistent JSON storage
        ├── state.json       (portfolio, prices, strategy weights)
        ├── trades.json      (full trade history)
        ├── analyses.json    (Claude AI analyses)
        └── optlog.json      (optimization log)
```

---

## 📊 Dashboard

Access via:
- **HA Sidebar**: "APEX Trading" (added automatically)
- **Direct**: `http://YOUR-HA-IP:7123`
- **HA Ingress**: `http://homeassistant.local:8123/hassio/ingress/apex_trading`

---

## 🗂️ Repository Structure

```
apex-trading-addon/
├── .github/
│   ├── workflows/
│   │   ├── build.yml          # Build & publish Docker images + GitHub releases
│   │   └── lint.yml           # Validate config and syntax on every PR
│   └── ISSUE_TEMPLATE/        # Bug report & feature request templates
├── apex_trading/
│   ├── config.yaml            # HA add-on configuration schema
│   ├── Dockerfile             # Alpine + Python 3 + aiohttp
│   ├── translations/
│   │   └── en.json            # HA UI configuration labels
│   └── rootfs/
│       ├── etc/s6-overlay/    # s6 process supervisor service definitions
│       └── opt/apex/
│           ├── server.py      # Main Python aiohttp backend
│           └── static/
│               └── index.html # Trading dashboard frontend
├── docs/
│   └── INSTALL_GUIDE.html     # Illustrated installation guide
├── install.sh                 # Self-installer script
├── repository.json            # HA add-on repository descriptor
├── CHANGELOG.md               # Version history
└── README.md                  # This file
```

---

## 🔒 Security

- API keys are stored in **HA's encrypted config store** (add-on Configuration tab) or in `/data/apex/state.json` (when set via the UI)
- All outbound calls to brokers/Claude use **HTTPS**
- The dashboard is only accessible within your local HA instance (or via HA ingress with HA authentication)
- No telemetry, no external data collection

---

## 📦 Updating

```bash
# Via SSH or HA Terminal:
curl -fsSL https://raw.githubusercontent.com/YOUR_GITHUB_USERNAME/apex-trading-addon/main/install.sh | bash

# The installer backs up your /data/apex/ data before upgrading
```

Or update from the HA UI: Settings → Add-ons → APEX → Update (when available).

---

## 🤝 Contributing

1. Fork the repository
2. Create a branch: `git checkout -b feature/my-feature`
3. Make changes and test on your HAOS instance
4. Validate: `bash -n install.sh && python3 -m py_compile apex_trading/rootfs/opt/apex/server.py`
5. Submit a Pull Request

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.

---

## ⚠️ Disclaimer

APEX Trading AI is for educational and informational purposes. It does not constitute financial advice. Paper trading (simulation) is enabled by default. Always start with paper trading before enabling live trading. You are solely responsible for any trading decisions made using this software.
