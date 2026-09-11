# WealthAI Copilot — Architecture & Flow

## System Overview

```
 ┌──────────────────────────────────────────────────────────────────────────────┐
 │                              USERS / CLIENTS                                │
 │                                                                             │
 │  Registered via Login/Register flow                                        │
 │  Portfolios synced from connected trading platform (Dhan)                  │
 │                                                                             │
 │  ┌───────────────────────┐       ┌───────────────────────────┐             │
 │  │  Client Accounts      │       │  Admin Accounts           │             │
 │  │  (self-registration)  │       │  admin@wealthai.com       │             │
 │  └───────────┬───────────┘       └─────────────┬─────────────┘             │
 │              │                                 │                           │
 └──────────────┼─────────────────────────────────┼───────────────────────────┘
                │                                 │
                └─────────────────────────────────┘
                                    │
                                    ▼
 ┌──────────────────────────────────────────────────────────────────────────────┐
 │                        FRONTEND (Amazon S3 Static Site)                      │
 │                                                                             │
 │  ┌───────────┐  ┌────────────────────┐  ┌──────────────┐  ┌─────────────┐  │
 │  │ index.html│  │client-dashboard.html│  │observability │  │ performance │  │
 │  │ Login     │  │ Agent Chat UI       │  │  .html       │  │ -tuning.html│  │
 │  │ Register  │  │ Portfolio View      │  │ CloudWatch   │  │ 16 Scenario │  │
 │  │           │  │ Multi-Agent Tabs    │  │ Dashboard    │  │ Optim. Lab  │  │
 │  │           │  │ Indian Market View  │  │ Metrics View │  │ Fault Inject│  │
 │  └─────┬─────┘  └─────────┬──────────┘  └──────┬───────┘  └──────┬──────┘  │
 │        │                  │                     │                 │         │
 └────────┼──────────────────┼─────────────────────┼─────────────────┼─────────┘
          │                  │                     │                 │
          └──────────────────┴─────────────────────┴─────────────────┘
                                    │
                          REST API  │  WebSocket
                                    ▼
 ┌──────────────────────────────────────────────────────────────────────────────┐
 │                        API GATEWAY LAYER                                     │
 │                                                                             │
 │  ┌─────────────────────────────┐     ┌─────────────────────────────────┐    │
 │  │  REST API (av9tutyi9h)      │     │  WebSocket API                  │    │
 │  │  POST /auth/login           │     │  $connect / $disconnect         │    │
 │  │  POST /auth/register        │     │  $default (real-time chat)      │    │
 │  │  POST /auth/validate        │     └────────────────┬────────────────┘    │
 │  │  POST /agent                │                      │                     │
 │  │  POST /loadtest             │                      ▼                     │
 │  │  POST /optimization         │     ┌────────────────────────────────┐     │
 │  └──────────┬──────────────────┘     │  WebSocket Lambda              │     │
 │             │                        │  Connection management         │     │
 │             │                        │  DynamoDB: websocket_conns     │     │
 │             │                        └────────────────────────────────┘     │
 └─────────────┼───────────────────────────────────────────────────────────────┘
               │
    ┌──────────┼──────────┬──────────────┬──────────────┐
    │          │          │              │              │
    ▼          ▼          ▼              ▼              ▼
┌───────┐ ┌────────┐ ┌─────────┐ ┌───────────┐ ┌─────────────┐
│ Auth  │ │ Agent  │ │ Load    │ │Optimization│ │ WebSocket   │
│Lambda │ │ Router │ │ Tester  │ │ Lambda     │ │ Handler     │
│       │ │ Lambda │ │ Lambda  │ │ 16 Fault   │ │             │
│Login  │ │        │ │Concurrent│ │ Scenarios │ │ Conn Mgmt   │
│Reg    │ │Routes  │ │ Stress  │ │ Injection  │ │ Message     │
│Validate│ │to Agent│ │ Tests  │ │ Lab        │ │ Relay       │
└───┬───┘ └───┬────┘ └────────┘ └───────────┘ └─────────────┘
    │         │
    │         │
    ▼         ▼
┌───────┐ ┌──────────────────────────────────────────────────────┐
│DynamoDB│ │              AGENT ROUTING ENGINE                    │
│user_   │ │                                                     │
│auth    │ │  1. Validate token (GSI: session_token-index)       │
│(+GSI)  │ │  2. Parse agent type from request                   │
│        │ │  3. Route: single agent OR orchestrator fan-out      │
└────────┘ │  4. Invoke via AgentCore Runtime / ECS Fargate       │
           │  5. Emit metrics (CloudWatch + EMF + X-Ray)          │
           └──────────┬───────────┬───────────┬───────────┬──────┘
                      │           │           │           │
                      ▼           ▼           ▼           ▼
           ┌──────────────────────────────────────────────────────┐
           │              AI AGENT LAYER                          │
           │                                                     │
           │  ┌──────────┐ ┌──────────┐ ┌────────┐ ┌──────────┐ │
           │  │ Market   │ │Financial │ │ Tax    │ │Compliance│ │
           │  │ Analyst  │ │ Planner  │ │Optimizer│ │ Checker │ │
           │  │          │ │          │ │        │ │          │ │
           │  │          │ │          │ │        │ │          │ │
           │  │ Strands  │ │ Strands  │ │ CrewAI │ │LangGraph │ │
           │  │ AgentCore│ │ AgentCore│ │AgentCore│ │ECS      │ │
           │  │          │ │          │ │        │ │Fargate   │ │
           │  │ 14 Tools │ │ 11 Tools │ │ 9 Tools│ │ 9 Tools │ │
           │  └──────────┘ └──────────┘ └────────┘ └──────────┘ │
           │                                                     │
           │  Cross-Agent: invoke_peer_agent() via AgentCore     │
           └──────────┬──────────────────────────────────────────┘
                      │
        ┌─────────────┼─────────────┬────────────────┐
        │             │             │                │
        ▼             ▼             ▼                ▼
┌──────────────┐ ┌──────────┐ ┌──────────┐  ┌──────────────┐
│ Amazon       │ │ AgentCore│ │ DynamoDB │  │ Dhan API     │
│ Bedrock      │ │ Memory   │ │ 12 Tables│  │(Read-Only)   │
│ Claude       │ │ Service  │ │          │  │              │
│ Haiku/Sonnet │ │          │ │ Profiles │  │ Equity       │
│              │ │ Summary  │ │ Portfolios│  │ F&O Posns   │
│ Foundation   │ │ Semantic │ │ Txns     │  │ Opt Chain   │
│ Model        │ │Preference│ │ Tax      │  │ Orders      │
│              │ │          │ │ Compliance│  │ Margins     │
└──────────────┘ └──────────┘ │ Audit    │  └──────────────┘
                              │ Market   │
                              │ Schedule │
                              │ Consult  │
                              │ Auth     │
                              │ WS Conns │
                              │ Load Test│
                              └──────────┘
```

---

## Agent Architecture — Tools & Capabilities

### Market Analyst (Strands Framework)

```
┌─────────────────────────────────────────────────────────────────┐
│  MARKET ANALYST                                                 │
│  Framework: Strands SDK  |  Runtime: Amazon Bedrock AgentCore   │
│  Model: Claude Haiku 4.5 / Sonnet 4                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  US MARKET TOOLS (7)              DHAN BROKERAGE TOOLS (13)     │
│  ┌─────────────────────────┐      ┌──────────────────────────┐  │
│  │ get_client_portfolio    │      │ sync_dhan_portfolio      │  │
│  │ analyze_market_sector   │      │ get_dhan_holdings        │  │
│  │ get_market_indicators   │      │ get_nse_stock_quote      │  │
│  │ assess_portfolio_risk   │      │ get_indian_market_status │  │
│  │ get_stock_analysis      │      │ calculate_india_tax      │  │
│  │ get_memory_context      │      │ analyze_indian_sector    │  │
│  │ save_conversation_memory│      │ get_fno_positions        │  │
│  └─────────────────────────┘      │ get_option_chain         │  │
│                                   │ calculate_greeks         │  │
│  CROSS-AGENT (2)                  │ analyze_fno_tax          │  │
│  ┌─────────────────────────┐      │ get_fno_strategy_analysis│  │
│  │ consult_financial_planner│      │ get_fund_limits          │  │
│  │ consult_tax_optimizer   │      │ get_expiry_list          │  │
│  └─────────────────────────┘      └──────────────────────────┘  │
│                                                                 │
│  Indian Market Capabilities:                                    │
│  • Dhan official API — proper developer tokens (not browser)   │
│  • Equity holdings, positions, orders with live P&L            │
│  • F&O: futures positions, option chain, OI analysis           │
│  • Option Greeks: Black-Scholes (Delta/Gamma/Theta/Vega)       │
│  • F&O strategy detection (Straddle, Spread, Iron Condor...)   │
│  • F&O tax: business income (Sec 43(5)), audit thresholds      │
│  • NSE/BSE stock quotes with INR pricing                       │
│  • NIFTY50 sector analysis (30+ stocks mapped)                 │
│  • Indian capital gains tax (STCG 20%, LTCG 12.5%)            │
│  • Market hours awareness (IST 9:15 AM – 3:30 PM)             │
│  • Fund limits / margin status from brokerage                  │
└─────────────────────────────────────────────────────────────────┘
```

### Financial Planner (Strands Framework)

```
┌─────────────────────────────────────────────────────────────────┐
│  FINANCIAL PLANNER                                              │
│  Framework: Strands SDK  |  Runtime: Amazon Bedrock AgentCore   │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  PLANNING TOOLS (8)               CROSS-AGENT (3)               │
│  ┌─────────────────────────────┐  ┌──────────────────────────┐  │
│  │ get_client_portfolio        │  │ consult_market_analyst   │  │
│  │ create_allocation_plan      │  │ consult_tax_optimizer    │  │
│  │ calculate_retirement_       │  │ consult_compliance_      │  │
│  │   projection                │  │   checker                │  │
│  │ rebalance_portfolio         │  └──────────────────────────┘  │
│  │ schedule_consultation       │                                │
│  │ get_memory_context          │                                │
│  │ save_conversation_memory    │                                │
│  │ analyze_cash_flow           │                                │
│  └─────────────────────────────┘                                │
└─────────────────────────────────────────────────────────────────┘
```

### Tax Optimizer (CrewAI Framework)

```
┌─────────────────────────────────────────────────────────────────┐
│  TAX OPTIMIZER                                                  │
│  Framework: CrewAI 1.3.0  |  Runtime: Amazon Bedrock AgentCore  │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  US TAX TOOLS (4)                 INDIAN TAX TOOLS (2)          │
│  ┌─────────────────────────────┐  ┌──────────────────────────┐  │
│  │ analyze_tax_situation       │  │ calculate_indian_        │  │
│  │ find_tax_loss_harvest_opps  │  │   capital_gains_tax      │  │
│  │ calculate_capital_gains     │  │ get_india_tax_saving_    │  │
│  │ optimize_tax_bracket        │  │   suggestions            │  │
│  └─────────────────────────────┘  └──────────────────────────┘  │
│                                                                 │
│  MEMORY (2)                       CROSS-AGENT (2)               │
│  ┌─────────────────────────────┐  ┌──────────────────────────┐  │
│  │ get_memory_context          │  │ consult_market_analyst   │  │
│  │ save_conversation_memory    │  │ consult_financial_planner│  │
│  └─────────────────────────────┘  └──────────────────────────┘  │
│                                                                 │
│  Indian Tax Capabilities:                                       │
│  • STCG 20% (held < 12 months)                                 │
│  • LTCG 12.5% above ₹1.25L exemption                          │
│  • STT (Securities Transaction Tax) calculation                │
│  • Section 80C (₹1.5L) / 80D (₹25K) / 80CCD (₹50K) advice   │
│  • ELSS mutual fund recommendations                            │
│  • NPS (National Pension System) optimization                  │
│  • Tax-loss harvesting for Indian portfolios                   │
└─────────────────────────────────────────────────────────────────┘
```

### Compliance Checker (LangGraph + Flask)

```
┌─────────────────────────────────────────────────────────────────┐
│  COMPLIANCE CHECKER                                             │
│  Framework: LangGraph + Flask  |  Runtime: ECS Fargate :8080    │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  COMPLIANCE TOOLS (6)             CROSS-AGENT (3)               │
│  ┌─────────────────────────────┐  ┌──────────────────────────┐  │
│  │ verify_kyc                  │  │ consult_market_analyst   │  │
│  │ screen_aml                  │  │ consult_financial_planner│  │
│  │ check_regulatory_compliance │  │ consult_tax_optimizer    │  │
│  │ review_transaction          │  └──────────────────────────┘  │
│  │ generate_audit_report       │                                │
│  │ get_compliance_history      │                                │
│  └─────────────────────────────┘                                │
│                                                                 │
│  LangGraph State Machine:                                       │
│    classify → route → [kyc|aml|regulatory|review] → respond    │
└─────────────────────────────────────────────────────────────────┘
```

---

## Cross-Agent Communication Flow

```
┌──────────────────────────────────────────────────────────────────────────┐
│                    CROSS-AGENT ORCHESTRATION                             │
│                                                                         │
│  Each agent can invoke peers via invoke_peer_agent() through            │
│  Amazon Bedrock AgentCore Runtime (managed inter-agent RPC).            │
│                                                                         │
│                    ┌──────────────┐                                      │
│                    │ Agent Router │                                      │
│                    │   Lambda     │                                      │
│                    └──────┬───────┘                                      │
│                           │                                             │
│            ┌──────────────┼──────────────┐                              │
│            │  Orchestrator Fan-Out Mode  │                              │
│            │  (Parallel to all 4 agents) │                              │
│            └──┬──────┬──────┬──────┬─────┘                              │
│               │      │      │      │                                    │
│               ▼      ▼      ▼      ▼                                    │
│         Market   Financial  Tax     Compliance                          │
│         Analyst  Planner    Optim.  Checker                             │
│               │      │      │      │                                    │
│               └──────┴──────┴──────┘                                    │
│                      │                                                  │
│              invoke_peer_agent()                                        │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────┐       │
│  │            PEER COMMUNICATION MATRIX                         │       │
│  │                                                              │       │
│  │  FROM ╲ TO    Mkt.Anlst Fin.Plan  Tax.Opt   Compliance      │       │
│  │  ─────────────────────────────────────────────────           │       │
│  │  Mkt.Anlst      —        ✓         ✓         —              │       │
│  │  Fin.Plan       ✓        —         ✓         ✓              │       │
│  │  Tax.Opt        ✓        ✓         —         —              │       │
│  │  Compliance     ✓        ✓         ✓         —              │       │
│  └──────────────────────────────────────────────────────────────┘       │
└──────────────────────────────────────────────────────────────────────────┘
```

### Flow 1 — Portfolio + F&O Analysis with Tax Impact (Indian Client)

```
User: "Analyze my Dhan portfolio and F&O positions, what are the tax implications?"

  User ──▶ API Gateway ──▶ Agent Router ──▶ Market Analyst
                                               │
                          ┌────────────────────┘
                          │
                          ▼
              sync_dhan_portfolio()
              ┌──────────────────────┐
              │ Dhan API (read-only) │
              │ GET /v2/holdings     │
              │ GET /v2/positions    │
              │ GET /v2/orders       │
              │ GET /v2/fundlimit    │
              └──────────┬───────────┘
                         │
                         ▼ equity + F&O synced to DynamoDB
              get_dhan_holdings()
              get_fno_positions()
              analyze_indian_sector()
              assess_portfolio_risk()
                         │
                         ▼
              consult_tax_optimizer()
              ┌──────────────────────────────────┐
              │ Tax Optimizer receives:           │
              │  - Equity holdings               │
              │  - F&O positions + turnover       │
              │                                   │
              │ Runs:                              │
              │  calculate_india_tax (equity)      │
              │  analyze_fno_tax (F&O business)    │
              │                                   │
              │ Returns:                           │
              │  - Equity STCG: ₹X at 20%        │
              │  - Equity LTCG: ₹Y at 12.5%      │
              │  - F&O: business income at slab   │
              │  - F&O turnover: ₹Z (audit/no)   │
              │  - STT on options + futures        │
              │  - 80C/80D/80CCD savings options  │
              └──────────────────────────────────┘
                         │
                         ▼
              Market Analyst combines:
              ┌─────────────────────────────────────┐
              │ Response to User:                    │
              │ • Equity: ₹58.5L in 10 NSE stocks  │
              │ • F&O: 3 open positions (₹+15K P&L)│
              │ • Sector breakdown (IT, Banking...)  │
              │ • Risk assessment: High (beta 1.3)   │
              │ • Equity tax: STCG ₹1.2L, LTCG ₹0  │
              │ • F&O tax: biz income, no audit req  │
              │ • Tax-saving: invest ₹1.5L in ELSS  │
              └─────────────────────────────────────┘
```

### Flow 2 — Compliance Check with Cross-Agent Validation

```
User: "Is my portfolio compliant? Run a full check."

  User ──▶ Agent Router ──▶ Compliance Checker
                                │
              LangGraph State Machine
              classify ──▶ route ──▶ regulatory
                                       │
                          ┌────────────┘
                          │
                          ▼
              consult_market_analyst()
              ┌────────────────────────────┐
              │ Market Analyst returns:    │
              │ • Portfolio risk score     │
              │ • Concentration analysis   │
              │ • Sector exposure          │
              └────────────┬───────────────┘
                           │
                           ▼
              consult_financial_planner()
              ┌────────────────────────────┐
              │ Financial Planner returns: │
              │ • Suitability assessment   │
              │ • Risk tolerance match     │
              │ • Allocation vs target     │
              └────────────┬───────────────┘
                           │
                           ▼
              consult_tax_optimizer()
              ┌────────────────────────────┐
              │ Tax Optimizer returns:     │
              │ • Tax compliance status    │
              │ • Wash sale alerts         │
              │ • Indian STCG/LTCG rules  │
              └────────────┬───────────────┘
                           │
                           ▼
              Compliance Checker generates:
              ┌─────────────────────────────────┐
              │ Compliance Report:              │
              │ ✅ KYC: Verified                │
              │ ✅ AML: No suspicious activity  │
              │ ⚠️  Concentration: 40% in IT    │
              │ ✅ Suitability: Matches profile │
              │ ✅ Tax: No wash sale violations │
              │ → Audit log written to DynamoDB │
              └─────────────────────────────────┘
```

### Flow 3 — Full Financial Review (Orchestrator Fan-Out)

```
User: "Give me a complete financial review"

  User ──▶ Agent Router ──▶ Orchestrator Mode (Fan-Out)
                                │
              ┌─────────────────┼─────────────────┐
              │                 │                  │
    ┌─────────▼──────┐ ┌───────▼───────┐ ┌───────▼────────┐ ┌────────────────┐
    │ Market Analyst │ │ Fin. Planner  │ │ Tax Optimizer  │ │ Compliance     │
    │                │ │               │ │                │ │   Checker      │
    │ • Market data  │ │ • Allocation  │ │ • Tax position │ │ • KYC status   │
    │ • Risk metrics │ │ • Retirement  │ │ • Harvesting   │ │ • AML screen   │
    │ • Sector view  │ │ • Rebalance   │ │ • STCG/LTCG   │ │ • Regulatory   │
    │ • NSE quotes   │ │ • Cash flow   │ │ • 80C/80D     │ │ • Audit trail  │
    └────────┬───────┘ └───────┬───────┘ └───────┬────────┘ └───────┬────────┘
             │                 │                  │                  │
             └─────────────────┴──────────────────┴──────────────────┘
                                        │
                                        ▼
                              Combined Response:
                    ┌────────────────────────────────────┐
                    │ Market: Strong, NIFTY at 21,450    │
                    │ Plan: Rebalance IT → Banking       │
                    │ Tax: Save ₹2.1L via ELSS           │
                    │ Compliance: All clear              │
                    └────────────────────────────────────┘
```

---

## Dhan Brokerage Integration (Read-Only)

```
┌──────────────────────────────────────────────────────────────────────────┐
│                    DHAN BROKERAGE INTEGRATION                            │
│              (Indian Market — NSE/BSE Equity + F&O + Currency)           │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────┐       │
│  │                    SECURITY MODEL                            │       │
│  │                                                              │       │
│  │  • READ-ONLY access — never places orders or modifies data  │       │
│  │  • Official API at api.dhan.co/v2 with developer tokens     │       │
│  │  • Headers: access-token + client-id (from dhanhq.co)       │       │
│  │  • Credentials stored in .env file (gitignored)             │       │
│  │  • Fallback: DHAN_ACCESS_TOKEN / DHAN_CLIENT_ID env vars    │       │
│  └──────────────────────────────────────────────────────────────┘       │
│                                                                         │
│  Credential Locations (priority order):                                 │
│  ┌────────────────────────────────────────────────────────────┐         │
│  │  1. shared/.env                (project-level)             │         │
│  │  2. wealth-mgmt-copilot/.env   (root-level)               │         │
│  │  3. ~/.wealthai/.env           (user home)                 │         │
│  │  4. Environment variables      (DHAN_ACCESS_TOKEN)         │         │
│  └────────────────────────────────────────────────────────────┘         │
│                                                                         │
│  ┌─────────────────┐       ┌──────────────────────────────────┐        │
│  │ DhanConnector   │       │  Dhan API Endpoints              │        │
│  │ (shared/dhan_   │       │  (api.dhan.co/v2/*)              │        │
│  │  connector.py)  │       │                                  │        │
│  │                 │ HTTPS │                                  │        │
│  │ EQUITY:         │       │  EQUITY:                         │        │
│  │ get_holdings()──┼──────▶│  GET /holdings                   │        │
│  │ get_positions()─┼──────▶│  GET /positions (all segments)   │        │
│  │ get_orders()────┼──────▶│  GET /orders                     │        │
│  │ get_trades()────┼──────▶│  GET /trades                     │        │
│  │                 │       │                                  │        │
│  │ F&O:            │       │  F&O:                            │        │
│  │ get_fno_        │       │                                  │        │
│  │  positions()────┼──────▶│  GET /positions (NSE_FNO filter) │        │
│  │ get_option_     │       │                                  │        │
│  │  chain()────────┼──────▶│  POST /optionchain               │        │
│  │ get_expiry_     │       │                                  │        │
│  │  list()─────────┼──────▶│  POST /optionchain/expirylist    │        │
│  │                 │       │                                  │        │
│  │ MARKET DATA:    │       │  MARKET DATA:                    │        │
│  │ get_ltp()───────┼──────▶│  POST /marketfeed/ltp            │        │
│  │ get_market_     │       │                                  │        │
│  │  quote()────────┼──────▶│  POST /marketfeed/quote          │        │
│  │                 │       │                                  │        │
│  │ ACCOUNT:        │       │  ACCOUNT:                        │        │
│  │ get_fund_       │       │                                  │        │
│  │  limits()───────┼──────▶│  GET /fundlimit                  │        │
│  └────────┬────────┘       └──────────────────────────────────┘        │
│           │                                                            │
│           │ sync_to_dynamodb(client_id)                                │
│           ▼                                                            │
│  ┌─────────────────────────────────────────────────┐                   │
│  │  DynamoDB: wealth_mgmt_portfolios               │                  │
│  │                                                  │                  │
│  │  Equity Record:                                  │                  │
│  │  { client_id: "...",                             │                  │
│  │    portfolio_id: "dhan_equity",                  │                  │
│  │    portfolio_type: "dhan_equity",                │                  │
│  │    source: "dhan",                               │                  │
│  │    holdings: [{ticker, qty, avg, current, pnl}], │                  │
│  │    sector_allocation: {...},                      │                  │
│  │    total_value, currency: "INR" }                │                  │
│  │                                                  │                  │
│  │  F&O Record:                                     │                  │
│  │  { client_id: "...",                             │                  │
│  │    portfolio_id: "dhan_fno",                     │                  │
│  │    portfolio_type: "dhan_fno",                   │                  │
│  │    positions: [{symbol, segment, qty, pnl}],     │                  │
│  │    total_pnl, open_positions }                   │                  │
│  └─────────────────────────────────────────────────┘                   │
│                                                                         │
│  F&O Analytics Engine:                                                  │
│  ┌─────────────────────────────────────────────────┐                   │
│  │  Option Chain Analysis:                          │                  │
│  │    • PCR (Put-Call Ratio) with interpretation    │                  │
│  │    • Max OI strikes → support/resistance levels  │                  │
│  │    • IV (Implied Volatility) per strike          │                  │
│  │                                                  │                  │
│  │  Option Greeks (Black-Scholes):                  │                  │
│  │    • Delta, Gamma, Theta, Vega                   │                  │
│  │    • Risk-free rate: 6.5% (India 10Y yield)      │                  │
│  │    • Moneyness detection (ITM/ATM/OTM)           │                  │
│  │                                                  │                  │
│  │  Strategy Detection:                              │                  │
│  │    • Long/Short Straddle, Strangle               │                  │
│  │    • Bull/Bear Call/Put Spread                    │                  │
│  │    • Iron Condor, Covered Call, Protective Put    │                  │
│  │    • Max profit/loss + breakeven calculation      │                  │
│  │                                                  │                  │
│  │  Lot Sizes (25+ contracts):                      │                  │
│  │    NIFTY(25), BANKNIFTY(15), FINNIFTY(25)        │                  │
│  │    RELIANCE(250), TCS(150), HDFCBANK(550)...     │                  │
│  └─────────────────────────────────────────────────┘                   │
│                                                                         │
│  Indian Tax Engine:                                                     │
│  ┌─────────────────────────────────────────────────┐                   │
│  │  INDIA_TAX_RATES (FY 2024-25)                   │                  │
│  │                                                  │                  │
│  │  Equity:                                         │                  │
│  │    STCG (< 12 months)  → 20%                    │                  │
│  │    LTCG (≥ 12 months)  → 12.5% above ₹1.25L    │                  │
│  │    STT delivery sell   → 0.1%                    │                  │
│  │                                                  │                  │
│  │  F&O (Business Income — Section 43(5)):          │                  │
│  │    Tax type    → Income tax slab rate (NOT CG)   │                  │
│  │    STT options → 0.0625% on sell premium         │                  │
│  │    STT futures → 0.0125% on sell value           │                  │
│  │    Turnover calc: abs(sell - buy) per trade       │                  │
│  │    Audit required if turnover > ₹10Cr            │                  │
│  │    Sec 44AD presumptive: 6% if turnover < ₹2Cr  │                  │
│  │    Losses carry forward 8 years (biz income only)│                  │
│  │                                                  │                  │
│  │  Tax Saving Instruments:                         │                  │
│  │    Section 80C  → ₹1,50,000 (ELSS, PPF, EPF)   │                  │
│  │    Section 80D  → ₹25,000 (Health Insurance)    │                  │
│  │    Section 80CCD→ ₹50,000 (NPS additional)      │                  │
│  │                                                  │                  │
│  │  INR/USD Rate: 0.012                             │                  │
│  └─────────────────────────────────────────────────┘                   │
│                                                                         │
│  NSE Sector Mapping (30+ NIFTY50 stocks):                              │
│  ┌──────────────────────────────────────────────────┐                  │
│  │  IT:       TCS, INFY, WIPRO, HCLTECH, TECHM     │                  │
│  │  Banking:  HDFCBANK, ICICIBANK, SBIN, KOTAKBANK  │                  │
│  │  Energy:   RELIANCE, ONGC, NTPC, POWERGRID       │                  │
│  │  Pharma:   SUNPHARMA, DRREDDY, CIPLA, DIVISLAB   │                  │
│  │  Auto:     TATAMOTORS, M&M, MARUTI, BAJAJ-AUTO   │                  │
│  │  FMCG:     HINDUNILVR, ITC, NESTLEIND, BRITANNIA │                  │
│  │  Metals:   TATASTEEL, JSWSTEEL, HINDALCO         │                  │
│  │  Cement:   ULTRACEMCO, SHREECEM, GRASIM          │                  │
│  │  Telecom:  BHARTIARTL                             │                  │
│  │  Finance:  BAJFINANCE, BAJAJFINSV, HDFCLIFE      │                  │
│  └──────────────────────────────────────────────────┘                  │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## Data Layer — DynamoDB Tables

```
┌──────────────────────────────────────────────────────────────────────────┐
│                     DATA LAYER (12 DynamoDB Tables)                      │
│                                                                         │
│  CORE TABLES                                                            │
│  ┌──────────────────┐  ┌──────────────────┐  ┌───────────────────┐     │
│  │ Client Profiles  │  │ Portfolios       │  │ Transactions      │     │
│  │ PK: client_id    │  │ PK: client_id    │  │ PK: transaction_id│     │
│  │                  │  │ SK: portfolio_id  │  │                   │     │
│  │ full_name        │  │                  │  │ client_id         │     │
│  │ email            │  │ portfolio_type   │  │ type (buy/sell)   │     │
│  │ risk_tolerance   │  │ holdings[]       │  │ ticker, amount    │     │
│  │ investment_goals │  │ total_value      │  │ currency (USD/INR)│     │
│  │ net_worth        │  │ currency         │  │ status, timestamp │     │
│  │ kyc_status       │  │ source           │  └───────────────────┘     │
│  │ country          │  │   (manual/dhan)  │                            │
│  └──────────────────┘  └──────────────────┘                            │
│                                                                         │
│  TAX & COMPLIANCE                                                       │
│  ┌──────────────────┐  ┌──────────────────┐  ┌───────────────────┐     │
│  │ Tax Records      │  │ Compliance Recs  │  │ Audit Log         │     │
│  │ PK: client_id    │  │ PK: record_id    │  │ PK: audit_id      │     │
│  │ SK: tax_year     │  │                  │  │ SK: timestamp     │     │
│  │                  │  │ client_id        │  │                   │     │
│  │ capital_gains    │  │ check_type       │  │ agent_name        │     │
│  │ tax_loss_harvest │  │ status           │  │ action            │     │
│  │ deductions       │  │ findings[]       │  │ client_id         │     │
│  │ indian_stcg      │  │ jurisdiction     │  │ details           │     │
│  │ indian_ltcg      │  │   (US/India)     │  │                   │     │
│  └──────────────────┘  └──────────────────┘  └───────────────────┘     │
│                                                                         │
│  SCHEDULING & MARKET                                                    │
│  ┌──────────────────┐  ┌──────────────────┐  ┌───────────────────┐     │
│  │ Consultations    │  │ Advisor Schedule │  │ Market Data       │     │
│  │ PK: consult_id   │  │ PK: advisor_id   │  │ PK: symbol        │     │
│  │                  │  │ SK: date         │  │ SK: data_type     │     │
│  │ client_id        │  │ available_slots[]│  │                   │     │
│  │ agent_name       │  │ booked_slots[]   │  │ price, volume     │     │
│  │ type, notes      │  │                  │  │ exchange (NYSE/   │     │
│  └──────────────────┘  └──────────────────┘  │   NSE/BSE)       │     │
│                                               └───────────────────┘     │
│  AUTH & INFRA                                                           │
│  ┌──────────────────┐  ┌──────────────────┐  ┌───────────────────┐     │
│  │ User Auth        │  │ WebSocket Conns  │  │ Load Test Results │     │
│  │ PK: email        │  │ PK: connectionId │  │ PK: test_id       │     │
│  │                  │  │                  │  │ SK: timestamp     │     │
│  │ password_hash    │  │ client_id        │  │                   │     │
│  │ session_token    │  │ connected_at     │  │ concurrent_users  │     │
│  │ client_id        │  │ ttl              │  │ avg_latency_ms    │     │
│  │ role             │  │                  │  │ error_rate        │     │
│  │                  │  └──────────────────┘  └───────────────────┘     │
│  │ GSI: session_    │                                                   │
│  │   token-index    │  ← O(1) token validation (replaced table scan)  │
│  └──────────────────┘                                                   │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## Observability Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│                     OBSERVABILITY LAYER                                   │
│                                                                          │
│  ┌──────────────────────────────────┐                                    │
│  │   MetricsEmitter (shared/)       │                                   │
│  │   Used by all 4 agents + router  │                                   │
│  └──────┬──────────┬───────┬────────┘                                   │
│         │          │       │                                             │
│         ▼          ▼       ▼                                             │
│  ┌──────────┐ ┌─────────┐ ┌────────────┐                                │
│  │CloudWatch│ │ EMF     │ │ X-Ray      │                                │
│  │ Custom   │ │ Logs    │ │ Traces     │                                │
│  │ Metrics  │ │         │ │            │                                │
│  │          │ │Embedded │ │Annotations:│                                │
│  │Namespace:│ │ Metric  │ │ agent_name │                                │
│  │WealthMgmt│ │ Format  │ │ tool_name  │                                │
│  │/Agents   │ │         │ │ client_id  │                                │
│  │          │ │Auto-    │ │ success    │                                │
│  │Metrics:  │ │extract  │ │ market     │                                │
│  │•Response │ │to CW    │ │  (US/India)│                                │
│  │  Time    │ │Metrics  │ │            │                                │
│  │•Cost ($) │ │         │ │Trace ID    │                                │
│  │•Tool     │ │         │ │propagated  │                                │
│  │  Calls   │ │         │ │end-to-end  │                                │
│  │•Memory   │ │         │ │            │                                │
│  │  Hit Rate│ │         │ │            │                                │
│  └────┬─────┘ └────┬────┘ └─────┬──────┘                                │
│       │            │            │                                        │
│       └────────────┴────────────┘                                        │
│                    │                                                     │
│                    ▼                                                     │
│  ┌────────────────────────────────────────────────────────────────┐      │
│  │         CloudWatch Dashboard: wealth_mgmt_copilot_dashboard   │      │
│  │                                                                │      │
│  │  ┌──────────────────┐  ┌────────────────────────────────┐     │      │
│  │  │ Bedrock Metrics  │  │ Agent Performance              │     │      │
│  │  │ • Invocations    │  │ • Lambda Duration              │     │      │
│  │  │ • Latency (P50/  │  │ • Errors vs Invocations       │     │      │
│  │  │   P90/P99)       │  │ • Concurrent Executions       │     │      │
│  │  │ • Token Usage    │  │ • ECS CPU/Memory (Compliance)  │     │      │
│  │  │ • Error Rate     │  │ • Dhan API Latency            │     │      │
│  │  └──────────────────┘  └────────────────────────────────┘     │      │
│  │  ┌──────────────────┐  ┌────────────────────────────────┐     │      │
│  │  │ API & Data Layer │  │ Custom Agent Metrics           │     │      │
│  │  │ • API Requests   │  │ • Response Time by Agent       │     │      │
│  │  │ • API Latency    │  │ • Cost Per Agent ($)           │     │      │
│  │  │ • DynamoDB       │  │ • Tool Calls Per Request       │     │      │
│  │  │   Capacity       │  │ • Memory Hit Rate (%)          │     │      │
│  │  │ • 4xx/5xx Errors │  │ • Compliance Events            │     │      │
│  │  └──────────────────┘  └────────────────────────────────┘     │      │
│  └────────────────────────────────────────────────────────────────┘      │
│                                                                          │
│  Alarms (10):                                                            │
│  ┌────────────────────────────────────────────────────────────────┐      │
│  │ Threshold (7):                  Anomaly Detection (3):        │      │
│  │ • Bedrock latency > 10s        • Latency anomaly (band=2)    │      │
│  │ • Bedrock throttling > 5/min   • Token usage anomaly (band=3)│      │
│  │ • Agent router errors > 5%     • Agent response time anomaly │      │
│  │ • Router duration > 25s                                      │      │
│  │ • ECS CPU > 80%                All → SNS Notification        │      │
│  │ • Token spike > 500K                                         │      │
│  │ • DynamoDB throttle                                          │      │
│  └────────────────────────────────────────────────────────────────┘      │
│                                                                          │
│  Log Insights Queries (10):                                              │
│  • Token usage per agent           • Compliance flagging rate            │
│  • Slowest tools (P95)             • Response time distribution          │
│  • Error patterns by agent         • Top clients by API spend            │
│  • Memory hit rate trend           • DynamoDB latency per table          │
│  • Load test result analysis       • Bedrock invocation breakdown        │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## Authentication Flow

```
  Browser                   API Gateway             Auth Lambda            DynamoDB
    │                           │                       │                     │
    │ POST /auth/login          │                       │                     │
    │ {email, password}         │                       │                     │
    ├──────────────────────────▶│                       │                     │
    │                           ├──────────────────────▶│                     │
    │                           │                       │ GetItem(email)      │
    │                           │                       ├────────────────────▶│
    │                           │                       │◀───────────────────┤│
    │                           │                       │ bcrypt.verify()     │
    │                           │                       │ Generate UUID token │
    │                           │                       │ UpdateItem(token)   │
    │                           │                       ├────────────────────▶│
    │                           │◀──────────────────────┤                     │
    │ {token, client_id, name}  │                       │                     │
    │◀──────────────────────────┤                       │                     │
    │                           │                       │                     │
    │ POST /auth/validate       │                       │                     │
    │ {session_token}           │                       │                     │
    ├──────────────────────────▶├──────────────────────▶│                     │
    │                           │                       │ Query GSI:          │
    │                           │                       │ session_token-index │
    │                           │                       │ O(1) lookup         │
    │                           │                       ├────────────────────▶│
    │                           │                       │◀───────────────────┤│
    │ {valid, client_id, role}  │◀──────────────────────┤                     │
    │◀──────────────────────────┤                       │                     │
```

---

## End-to-End Request Trace (with X-Ray)

```
Browser      API GW     Agent Router    AgentCore      Agent       Bedrock     DynamoDB   Dhan API
  │            │  X-Ray      │              │            │            │            │          │
  │ POST       │ Trace ID    │              │            │            │            │          │
  │ /agent     │ propagated  │              │            │            │            │          │
  │{agent,msg} │ end-to-end  │              │            │            │            │          │
  ├───────────▶├────────────▶│              │            │            │            │          │
  │            │             │ validate()   │            │            │            │          │
  │            │             │ detect mkt   │            │            │            │          │
  │            │             │ (US/India)   │            │            │            │          │
  │            │             ├─────────────▶│            │            │            │          │
  │            │             │ invoke_agent │ route      │            │            │          │
  │            │             │ + traceId    ├───────────▶│            │            │          │
  │            │             │              │            │            │            │          │
  │            │             │              │            │ @tool:     │            │          │
  │            │             │              │            │ sync_dhan  │            │          │
  │            │             │              │            ├────────────┼────────────┼─────────▶│
  │            │             │              │            │◀───────────┼────────────┼──────────┤
  │            │             │              │            │            │            │          │
  │            │             │              │            │ @tool:     │            │          │
  │            │             │              │            │ get_client │            │          │
  │            │             │              │            │ _portfolio │            │          │
  │            │             │              │            ├────────────┼───────────▶│          │
  │            │             │              │            │◀───────────┼────────────┤          │
  │            │             │              │            │            │            │          │
  │            │             │              │            │ Agent()    │            │          │
  │            │             │              │            │ prompt     │            │          │
  │            │             │              │            ├───────────▶│            │          │
  │            │             │              │            │ Invoke     │            │          │
  │            │             │              │            │◀───────────┤            │          │
  │            │             │              │            │            │            │          │
  │            │             │              │            │ MetricsEmitter.emit()   │          │
  │            │             │              │            ├──▶ CloudWatch           │          │
  │            │             │              │            ├──▶ X-Ray Annotation     │          │
  │            │             │              │            ├──▶ EMF Structured Log   │          │
  │            │             │              │            │            │            │          │
  │            │             │              │◀───────────┤            │            │          │
  │            │             │◀─────────────┤            │            │            │          │
  │            │             │              │            │            │            │          │
  │            │             │ emit_router  │            │            │            │          │
  │            │             │ _metrics()   │            │            │            │          │
  │            │◀────────────┤              │            │            │            │          │
  │{response,  │             │              │            │            │            │          │
  │ duration,  │             │              │            │            │            │          │
  │ trace_id}  │             │              │            │            │            │          │
  │◀───────────┤             │              │            │            │            │          │
```

---

## Performance Optimization Lab

```
┌──────────────────────────────────────────────────────────────────────────┐
│                  PERFORMANCE OPTIMIZATION LAB (16 Scenarios)             │
│                                                                         │
│  Frontend: performance-tuning.html                                      │
│       │                                                                 │
│       ▼                                                                 │
│  POST /optimization                                                     │
│       │                                                                 │
│       ▼                                                                 │
│  ┌──────────────────┐     ┌─────────────────────────────────────────┐   │
│  │ Optimization     │     │ 16 Fault Injection Scenarios            │   │
│  │ Lambda           │     │                                         │   │
│  │                  │     │  1. context_bloat — oversized prompts   │   │
│  │ • scenario_      │────▶│  2. tool_failure — tool error handling  │   │
│  │   router         │     │  3. latency_injection — slow responses  │   │
│  │ • fault_         │     │  4. structuring_detection — format      │   │
│  │   injectors      │     │  5. prompt_injection_defense — security │   │
│  │ • metrics_       │     │  6. model_comparison — Haiku vs Sonnet  │   │
│  │   collector      │     │  7. token_optimization — reduce tokens  │   │
│  │ • optimization_  │     │  8. concurrent_load — parallel requests │   │
│  │   executors      │     │  9. cold_start_analysis — Lambda init   │   │
│  └────────┬─────────┘     │ 10. memory_retrieval_perf — recall spd  │   │
│           │               │ 11. compliance_audit_load — Compliance   │   │
│           │               │ 12. cross_agent_latency — peer calls     │   │
│           ▼               │ 13. dynamodb_throttle_sim — DB limits    │   │
│  ┌────────────────┐       │ 14. response_quality_check — accuracy   │   │
│  │ Baseline Run   │       │ 15. multi_turn_conversation — memory    │   │
│  │ (No faults)    │       │ 16. error_recovery — resilience         │   │
│  └───────┬────────┘       └─────────────────────────────────────────┘   │
│          │                                                              │
│          ▼                Emits to: WealthMgmt/Optimization             │
│  ┌────────────────┐       • ScenarioLatency                            │
│  │ Scenario Run   │       • BaselineLatency                            │
│  │ (With faults)  │       • ImprovementPercent                         │
│  └───────┬────────┘                                                    │
│          │                                                              │
│          ▼                                                              │
│  ┌────────────────────────────────────┐                                │
│  │ Compare & Report                   │                                │
│  │ • baseline_ms: 2340               │                                │
│  │ • scenario_ms: 1870              │                                │
│  │ • improvement: 20.1%              │                                │
│  └────────────────────────────────────┘                                │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## Trading Platform Extension Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│                                                                          │
│  YOUR TRADING PLATFORM                    WEALTHAI COPILOT               │
│  (Dhan Brokerage)                         (Current System)               │
│                                                                          │
│  ┌──────────────────────┐                ┌──────────────────────┐       │
│  │ Trading Engine        │   REST API    │ Agent Router Lambda  │       │
│  │ • Order Execution     ├──────────────▶│ POST /agent          │       │
│  │ • Position Management │               │                      │       │
│  │ • Real-time Quotes    │               │ Pre-trade analysis:  │       │
│  └──────────┬────────────┘               │ "Analyze RELIANCE    │       │
│             │                            │  before I buy 100    │       │
│             │                            │  shares"             │       │
│  ┌──────────▼────────────┐               └──────────────────────┘       │
│  │ Trading API Layer     │                                              │
│  │ • Market Data Feed    │   WebSocket   ┌──────────────────────┐       │
│  │ • Order Status Events ├◀────────────▶│ WebSocket API        │       │
│  │ • Portfolio Sync      │               │ Real-time agent      │       │
│  └──────────┬────────────┘               │ responses            │       │
│             │                            └──────────────────────┘       │
│             │                                                           │
│  ┌──────────▼────────────┐   DynamoDB    ┌──────────────────────┐       │
│  │ Trading Database      │◀────────────▶│ Shared Data Layer    │       │
│  │ • Orders & Fills      │    (sync)     │ • Client Profiles    │       │
│  │ • Executions          │               │ • Portfolios         │       │
│  │ • P&L Tracking        │               │ • Transactions       │       │
│  └───────────────────────┘               └──────────────────────┘       │
│                                                                          │
│  ═══════════════════════════════════════════════════════════════════     │
│  INTEGRATION POINTS                                                      │
│  ═══════════════════════════════════════════════════════════════════     │
│                                                                          │
│  1. PRE-TRADE ANALYSIS                                                   │
│     Trading Platform ──▶ POST /agent {agent:"marcus"}                   │
│     "Analyze risk of buying 100 RELIANCE at ₹2680"                      │
│     Market Analyst: risk score, sector exposure, technical indicators    │
│                                                                          │
│  2. COMPLIANCE GATE                                                      │
│     Trading Platform ──▶ POST /agent {agent:"victor"}                   │
│     "Pre-trade compliance check for client_ramu_de buying RELIANCE"     │
│     Compliance Checker: KYC status, concentration limits, regulatory flags│
│                                                                          │
│  3. TAX-AWARE TRADING                                                    │
│     Trading Platform ──▶ POST /agent {agent:"olivia"}                   │
│     "Tax impact of selling TCS position — held 8 months"                │
│     Tax Optimizer: STCG ₹X at 20%, STT ₹Y, wait 4 months for LTCG     │
│                                                                          │
│  4. PORTFOLIO REBALANCE                                                  │
│     Trading Platform ──▶ POST /agent {agent:"orchestrator"}             │
│     "Full review before quarterly rebalance"                            │
│     All 4 agents: combined market + plan + tax + compliance report       │
│                                                                          │
│  5. REAL-TIME DATA SYNC                                                  │
│     Dhan executions ──▶ DynamoDB transactions table                      │
│     Portfolio updates ──▶ DynamoDB portfolios table                     │
│     Agents always see latest positions                                  │
│                                                                          │
│  6. FUTURE AGENTS TO ADD                                                 │
│     ┌─────────────────────┐  ┌─────────────────────────────┐           │
│     │ Trading Agent       │  │ Risk Manager Agent          │           │
│     │ • Order execution   │  │ • Real-time P&L tracking    │           │
│     │ • Algo strategies   │  │ • Margin requirement checks │           │
│     │ • Market making     │  │ • Position limit monitoring │           │
│     │ • Smart order route │  │ • VaR (Value at Risk) calc  │           │
│     └─────────────────────┘  └─────────────────────────────┘           │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## Technology Stack

```
┌────────────────────────┬─────────────────────────────────────────────────┐
│ Layer                  │ Technology                                      │
├────────────────────────┼─────────────────────────────────────────────────┤
│ Frontend               │ HTML5, CSS3 (custom), Vanilla JS                │
│ Static Hosting         │ Amazon S3 (website mode)                        │
│ CDN                    │ Amazon CloudFront                               │
│ REST API               │ Amazon API Gateway (Regional)                   │
│ WebSocket API          │ Amazon API Gateway (WebSocket)                  │
│ Compute (Serverless)   │ AWS Lambda (Python 3.12)                        │
│ Compute (Container)    │ Amazon ECS Fargate (Compliance Checker)          │
│ AI Agents              │ Amazon Bedrock AgentCore Runtime                │
│ Agent Framework 1      │ Strands SDK (Market Analyst, Financial Planner)  │
│ Agent Framework 2      │ CrewAI 1.3.0 (Tax Optimizer)                   │
│ Agent Framework 3      │ LangGraph + Flask (Compliance Checker)          │
│ Foundation Model       │ Anthropic Claude Haiku 4.5 / Sonnet 4          │
│ Agent Memory           │ AgentCore Memory (summary, semantic, preference)│
│ Database               │ Amazon DynamoDB (12 tables, 1 GSI)              │
│ Brokerage Integration  │ Dhan API (Read-Only, official developer tokens)  │
│ F&O Analytics          │ Option chain, Greeks, strategy detection, PCR   │
│ Indian Market Data     │ NSE/BSE via Dhan (NIFTY50, sector mapping)      │
│ Indian Tax Engine      │ Equity (STCG/LTCG) + F&O (Sec 43(5) business)  │
│ Observability          │ Amazon CloudWatch (Metrics, Logs, Dashboard)    │
│ Tracing                │ AWS X-Ray (active tracing, annotations)         │
│ Structured Logging     │ EMF (Embedded Metric Format)                    │
│ Custom Metrics         │ CloudWatch put_metric_data (WealthMgmt/Agents)  │
│ Alarms                 │ CloudWatch Alarms + Anomaly Detection           │
│ Notifications          │ Amazon SNS                                      │
│ Container Registry     │ Amazon ECR                                      │
│ IaC                    │ AWS CloudFormation                              │
└────────────────────────┴─────────────────────────────────────────────────┘
```

---

## File Structure

```
wealth-mgmt-copilot/
│
├── agents/
│   ├── market-analyst/              # Market Analyst (Strands) — 22 tools
│   │   ├── market_analyst.py        # ~1,400 lines
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   │
│   ├── financial-planner/           # Financial Planner (Strands) — 11 tools
│   │   ├── financial_planner.py     # ~1,499 lines
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   │
│   ├── tax-optimizer/               # Tax Optimizer (CrewAI) — 9 tools (incl. Indian tax)
│   │   ├── tax_optimizer.py         # ~1,400 lines
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   │
│   └── compliance-checker/          # Compliance Checker (LangGraph + Flask) — 9 tools
│       ├── app.py                   # ~1,177 lines
│       ├── config_reader.py
│       ├── config/config.conf
│       ├── Dockerfile
│       ├── requirements.txt
│       └── .dockerignore
│
├── lambdas/
│   ├── agent-router/                # Routes requests to agents
│   │   └── lambda_function.py       # 401 lines
│   │
│   ├── auth/                        # Login / Register / Validate
│   │   └── lambda_function.py       # 308 lines (GSI token validation)
│   │
│   ├── websocket/                   # Real-time chat connections
│   │   └── websocket_handler.py     # 177 lines
│   │
│   ├── load-tester/                 # Concurrent stress testing
│   │   └── lambda_function.py       # 466 lines
│   │
│   └── optimization/                # 16-scenario fault injection lab
│       ├── lambda_handler.py        # 288 lines
│       ├── fault_injectors.py       # 272 lines
│       ├── metrics_collector.py     # 202 lines
│       ├── optimization_executors.py # 447 lines
│       ├── scenario_router.py       # 156 lines
│       └── config/scenarios.json    # 16 scenarios
│
├── shared/
│   ├── metrics_emitter.py           # 290 lines — CloudWatch + EMF + X-Ray
│   ├── cross_agent.py               # 109 lines — invoke_peer_agent()
│   ├── dhan_connector.py            # ~550 lines — Dhan API + F&O + Greeks
│   ├── groww_connector.py           # ~350 lines — Groww API (legacy)
│   ├── .env.example                 # Dhan credential template
│   └── .env                         # (gitignored) actual credentials
│
├── frontend/
│   ├── index.html                   # Login / Register
│   ├── client-dashboard.html        # Agent chat + portfolio view
│   ├── observability.html           # CloudWatch dashboard viewer
│   ├── performance-tuning.html      # 16-scenario optimization lab
│   ├── loadtest.html                # Load testing console
│   ├── styles.css                   # Navy/Gold theme
│   ├── config.template.js           # API endpoint config
│   ├── websocket-client.js          # WebSocket client
│   └── favicon.svg
│
├── cloudwatch/
│   ├── dashboard.json               # 20+ widget dashboard
│   ├── alarms.json                  # 7 threshold + 3 anomaly alarms
│   └── log_insights_queries.json    # 10 pre-built queries
│
├── dynamodb/
│   ├── create_tables.py             # 12 tables + GSI creation
│   └── seed_data.py                 # Admin account + advisor schedules
│
├── infra/
│   └── cloudformation.yaml          # 801 lines — complete IaC
│
├── scripts/
│   └── deploy.sh                    # One-command deployment
│
├── ARCHITECTURE.md                  # This file
└── .gitignore                       # .env excluded
```

---

## Deployed Infrastructure

| Resource | Value |
|----------|-------|
| Frontend | `http://wealth-mgmt-frontend-250679205511.s3-website-us-west-2.amazonaws.com` |
| API Gateway | `https://av9tutyi9h.execute-api.us-west-2.amazonaws.com/prod` |
| Region | `us-west-2` |
| CloudWatch Dashboard | `wealth_mgmt_copilot_dashboard` |
| DynamoDB Tables | 12 tables + 1 GSI |
| Lambda Functions | 5 (auth, agent-router, websocket, load-tester, optimization) |
| ECS Service | Compliance Checker on Fargate |

---

## Default Accounts

| Email | Role | Notes |
|-------|------|-------|
| admin@wealthai.com | admin | Password: `admin123` |

Client accounts are created via the Register flow.
Portfolio data syncs from your connected trading platform (Dhan) at runtime.
