# Changelog

All notable changes to APEX Trading AI are documented here.

## [1.0.0] - 2025-03-25

### Added
- Initial release as a Home Assistant OS add-on
- Claude AI market analysis via claude-sonnet-4-5
  - Full market scan across all monitored symbols
  - Portfolio review and position assessment
  - Tax optimization strategy
  - Risk assessment and drawdown analysis
  - Symbol deep-dive analysis
  - Auto-scheduled scans (configurable interval)
- Live market data (server-side, no CORS)
  - Yahoo Finance (free, no key)
  - Finnhub (free API key)
  - Alpha Vantage (free API key)
  - Simulated offline mode
- Broker integration (server-side, no CORS)
  - Alpaca Markets (paper + live)
  - Binance
  - Coinbase Advanced
  - Kraken
  - Interactive Brokers
  - Generic broker auto-detection
- Persistent storage in `/data/apex/`
  - Trade history (up to 500 records)
  - Claude AI analyses (up to 50 reports)
  - Optimization log (up to 400 entries)
  - Full portfolio state
- Self-optimization engine
  - Auto-adjusts strategy weights after every trade
  - Kelly criterion position sizing
  - Sharpe ratio strategy ranking
- Tax engine
  - YTD short-term and long-term gain tracking
  - Tax-loss harvesting identification
  - Wash sale monitoring
  - LTCG staging recommendations
- Trading dashboard (port 7123)
  - Live price chart with signals
  - Market sentiment indicators
  - Position management
  - Strategy performance tracking
  - Full trade history with CSV export
- HA ingress support (sidebar panel)
- Multi-architecture support: amd64, aarch64, armv7, armhf, i386
- Self-installer script (`install.sh`)
- GitHub Actions CI/CD (build, lint, release)
