# WealthAI Copilot — Architecture & Flow

## System Overview

```
 ┌──────────────────────────────────────────────────────────────────────────────┐
 │                              USERS / CLIENTS                                │
 │                                                                             │
 │  US Market Clients                      Indian Market Clients (Groww)       │
 │  ┌─────────────┐ ┌──────────────┐       ┌───────────┐ ┌─────────────────┐  │
 │  │ Sarah Chen  │ │ James Wilson │       │ Ramu DE   │ │ Ananya Sharma   │  │
 │  │ Aggressive  │ │ Moderate     │       │ Aggressive│ │ Moderate        │  │
 │  │ $2.1M NW   │ │ $850K NW     │       │ ₹90L NW  │ │ ₹24.5L stocks  │  │
 │  └──────┬──────┘ └──────┬───────┘       └────┬──────┘ └───────┬─────────┘  │
 │         │               │                    │                │            │
 └─────────┼───────────────┼────────────────────┼────────────────┼────────────┘
           │               │                    │                │
           └───────────────┴────────────────────┴────────────────┘
                                    │
                                    ▼
 ┌──────────────────────────────────────────────────────────────────────────────┐
 │                        FRONTEND (Amazon S3 Static Site)                      │
 │                                                                             │
 │  ┌───────────┐  ┌────────────────────┐  ┌──────────────┐  ┌─────────────┐  │
 │  │ index.html│  │client-dashboard.html│  │observability │  │ performance │  │
 │  │ Login     │  │ Agent Chat UI       │  │  .html       │  │ -tuning.html│  │
 │  │ Register  │  │ Portfolio View      │  │ CloudWatch   │  │ 16 Scenario │  │
 │  │ Demo Auth │  │ Multi-Agent Tabs    │  │ Dashboard    │  │ Optim. Lab  │  │
 │  │ US + Groww│  │ Indian Market View  │  │ Metrics View │  │ Fault Inject│  │
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
           │  │ Marcus   │ │ Sophia   │ │ Olivia │ │ Victor   │ │
           │  │ Market   │ │ Financial│ │ Tax    │ │Compliance│ │
           │  │ Analyst  │ │ Planner  │ │Optimizer│ │ Checker │ │
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
│ Amazon       │ │ AgentCore│ │ DynamoDB │  │ Groww API    │
│ Bedrock      │ │ Memory   │ │ 12 Tables│  │ (Read-Only)  │
│ Claude       │ │ Service  │ │          │  │              │
│ Haiku/Sonnet │ │          │ │ Profiles │  │ Holdings     │
│              │ │ Summary  │ │ Portfolios│  │ Positions   │
│ Foundation   │ │ Semantic │ │ Txns     │  │ MF SIPs     │
│ Model        │ │Preference│ │ Tax      │  │ Orders      │
│              │ │          │ │ Compliance│  │ NSE Quotes  │
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

### Marcus — Market Analyst (Strands Framework)

```
┌─────────────────────────────────────────────────────────────────┐
│  MARCUS — Market Analyst                                        │
│  Framework: Strands SDK  |  Runtime: Amazon Bedrock AgentCore   │
│  Model: Claude Haiku 4.5 / Sonnet 4                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  US MARKET TOOLS (9)              INDIAN MARKET TOOLS (5)       │
│  ┌─────────────────────────┐      ┌──────────────────────────┐  │
│  │ get_client_portfolio    │      │ get_indian_market_status │  │
│  │ analyze_market_sector   │      │ get_nse_stock_quote      │  │
│  │ get_market_indicators   │      │ calculate_india_tax      │  │
│  │ assess_portfolio_risk   │      │ sync_groww_portfolio     │  │
│  │ get_stock_analysis      │      │ analyze_indian_sector    │  │
│  │ get_memory_context      │      └──────────────────────────┘  │
│  │ save_conversation_memory│                                    │
│  │ consult_financial_planner│  CROSS-AGENT (2)                  │
│  │ consult_tax_optimizer   │  ┌──────────────────────────────┐  │
│  └─────────────────────────┘  │ consult_financial_planner    │  │
│                               │ consult_tax_optimizer         │  │
│                               └──────────────────────────────┘  │
│                                                                 │
│  Indian Market Capabilities:                                    │
│  • NSE/BSE stock quotes with INR pricing                       │
│  • NIFTY50 sector analysis (30+ stocks mapped)                 │
│  • Groww portfolio sync to DynamoDB                            │
│  • Indian capital gains tax (STCG 20%, LTCG 12.5%)            │
│  • Market hours awareness (IST 9:15 AM – 3:30 PM)             │
└─────────────────────────────────────────────────────────────────┘
```

### Sophia — Financial Planner (Strands Framework)

```
┌─────────────────────────────────────────────────────────────────┐
│  SOPHIA — Financial Planner                                     │
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

### Olivia — Tax Optimizer (CrewAI Framework)

```
┌─────────────────────────────────────────────────────────────────┐
│  OLIVIA — Tax Optimizer                                         │
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

### Victor — Compliance Checker (LangGraph + Flask)

```
┌─────────────────────────────────────────────────────────────────┐
│  VICTOR — Compliance Checker                                    │
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
│           Marcus  Sophia  Olivia  Victor                                │
│               │      │      │      │                                    │
│               └──────┴──────┴──────┘                                    │
│                      │                                                  │
│              invoke_peer_agent()                                        │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────┐       │
│  │            PEER COMMUNICATION MATRIX                         │       │
│  │                                                              │       │
│  │  FROM ╲ TO    Marcus    Sophia    Olivia    Victor           │       │
│  │  ─────────────────────────────────────────────────           │       │
│  │  Marcus         —        ✓         ✓         —              │       │
│  │  Sophia         ✓        —         ✓         ✓              │       │
│  │  Olivia         ✓        ✓         —         —              │       │
│  │  Victor         ✓        ✓         ✓         —              │       │
│  └──────────────────────────────────────────────────────────────┘       │
└──────────────────────────────────────────────────────────────────────────┘
```

### Flow 1 — Portfolio Analysis with Tax Impact (Indian Client)

```
User: "Analyze my Groww portfolio and tell me tax implications"

  User ──▶ API Gateway ──▶ Agent Router ──▶ Marcus (Market Analyst)
                                               │
                          ┌────────────────────┘
                          │
                          ▼
              sync_groww_portfolio()
              ┌──────────────────────┐
              │ Groww API (read-only)│
              │ GET /v1/api/stocks/  │
              │     holdings/v2      │
              │ GET /v1/api/mutual/  │
              │     funds            │
              └──────────┬───────────┘
                         │
                         ▼ holdings synced to DynamoDB
              get_nse_stock_quote() × N stocks
              analyze_indian_sector()
              assess_portfolio_risk()
                         │
                         ▼
              consult_tax_optimizer(Olivia)
              ┌──────────────────────────────────┐
              │ Olivia receives:                  │
              │  - Portfolio holdings from Marcus │
              │  - Current market values          │
              │                                   │
              │ Runs:                              │
              │  calculate_indian_capital_gains_tax│
              │  get_india_tax_saving_suggestions  │
              │                                   │
              │ Returns:                           │
              │  - STCG: ₹X at 20%               │
              │  - LTCG: ₹Y at 12.5% (>1.25L)   │
              │  - STT impact                     │
              │  - 80C/80D/80CCD savings options  │
              └──────────────────────────────────┘
                         │
                         ▼
              Marcus combines:
              ┌─────────────────────────────────────┐
              │ Response to User:                    │
              │ • Portfolio: ₹58.5L in 10 NSE stocks│
              │ • Sector breakdown (IT, Banking...)  │
              │ • Risk assessment: High (beta 1.3)   │
              │ • Tax impact: STCG ₹1.2L, LTCG ₹0  │
              │ • Tax-saving: invest ₹1.5L in ELSS  │
              │ • Action: harvest losses in WIPRO    │
              └─────────────────────────────────────┘
```

### Flow 2 — Compliance Check with Cross-Agent Validation

```
User: "Is my portfolio compliant? Run a full check."

  User ──▶ Agent Router ──▶ Victor (Compliance Checker)
                                │
              LangGraph State Machine
              classify ──▶ route ──▶ regulatory
                                       │
                          ┌────────────┘
                          │
                          ▼
              consult_market_analyst(Marcus)
              ┌────────────────────────────┐
              │ Marcus returns:            │
              │ • Portfolio risk score     │
              │ • Concentration analysis   │
              │ • Sector exposure          │
              └────────────┬───────────────┘
                           │
                           ▼
              consult_financial_planner(Sophia)
              ┌────────────────────────────┐
              │ Sophia returns:            │
              │ • Suitability assessment   │
              │ • Risk tolerance match     │
              │ • Allocation vs target     │
              └────────────┬───────────────┘
                           │
                           ▼
              consult_tax_optimizer(Olivia)
              ┌────────────────────────────┐
              │ Olivia returns:            │
              │ • Tax compliance status    │
              │ • Wash sale alerts         │
              │ • Indian STCG/LTCG rules  │
              └────────────┬───────────────┘
                           │
                           ▼
              Victor generates:
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
    │ Marcus         │ │ Sophia        │ │ Olivia         │ │ Victor         │
    │                │ │               │ │                │ │                │
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

## Groww Integration Architecture (Read-Only)

```
┌──────────────────────────────────────────────────────────────────────────┐
│                    GROWW BROKERAGE INTEGRATION                           │
│                    (Indian Stock Market — NSE/BSE)                       │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────┐       │
│  │                    SECURITY MODEL                            │       │
│  │                                                              │       │
│  │  • READ-ONLY access — never places orders or modifies data  │       │
│  │  • Auth token from browser session (Bearer JWT)             │       │
│  │  • Token stored in .env file (gitignored, never committed)  │       │
│  │  • Fallback: environment variable GROWW_AUTH_TOKEN           │       │
│  │  • Token expires periodically — manual refresh needed       │       │
│  └──────────────────────────────────────────────────────────────┘       │
│                                                                         │
│  Credential Locations (priority order):                                 │
│  ┌────────────────────────────────────────────────────────────┐         │
│  │  1. shared/.env                (project-level)             │         │
│  │  2. wealth-mgmt-copilot/.env   (root-level)               │         │
│  │  3. ~/.wealthai/.env           (user home)                 │         │
│  │  4. Environment variable       (GROWW_AUTH_TOKEN)          │         │
│  └────────────────────────────────────────────────────────────┘         │
│                                                                         │
│  ┌─────────────────┐       ┌──────────────────────────────────┐        │
│  │ GrowwConnector  │       │  Groww API Endpoints             │        │
│  │ (shared/groww_  │       │  (groww.in/v1/api/*)             │        │
│  │  connector.py)  │       │                                  │        │
│  │                 │ HTTPS │  GET /stocks/holdings/v2         │        │
│  │ get_holdings()──┼──────▶│    → Current stock holdings      │        │
│  │                 │       │                                  │        │
│  │ get_positions()─┼──────▶│  GET /stocks/positions           │        │
│  │                 │       │    → Open positions (day)        │        │
│  │ get_mutual_     │       │                                  │        │
│  │   funds()───────┼──────▶│  GET /mutual-funds/holdings      │        │
│  │                 │       │    → MF SIP portfolio            │        │
│  │ get_order_      │       │                                  │        │
│  │   history()─────┼──────▶│  GET /stocks/orders              │        │
│  │                 │       │    → Trade history               │        │
│  │ get_stock_      │       │                                  │        │
│  │   quote()───────┼──────▶│  GET /stocks/quote/{symbol}      │        │
│  │                 │       │    → Live NSE price              │        │
│  │ get_nse_        │       │                                  │        │
│  │   indices()─────┼──────▶│  GET /indices/nifty50            │        │
│  │                 │       │    → NIFTY50 index value         │        │
│  └────────┬────────┘       └──────────────────────────────────┘        │
│           │                                                            │
│           │ sync_to_dynamodb(client_id)                                │
│           ▼                                                            │
│  ┌─────────────────────────────────────────────────┐                   │
│  │  DynamoDB: wealth_mgmt_portfolios               │                  │
│  │                                                  │                  │
│  │  { client_id: "client_ramu_de",                 │                  │
│  │    portfolio_id: "groww_stocks",                 │                  │
│  │    portfolio_type: "groww_stocks",               │                  │
│  │    source: "groww_live_sync",                    │                  │
│  │    holdings: [                                   │                  │
│  │      { ticker: "RELIANCE.NS", shares: 50,       │                  │
│  │        avg_price: 2450, current: 2680 },         │                  │
│  │      { ticker: "TCS.NS", shares: 30,            │                  │
│  │        avg_price: 3200, current: 3450 },         │                  │
│  │      ...                                         │                  │
│  │    ],                                            │                  │
│  │    total_value: 5850000,                         │                  │
│  │    currency: "INR",                              │                  │
│  │    last_synced: "2024-01-15T10:30:00Z" }        │                  │
│  └─────────────────────────────────────────────────┘                   │
│                                                                         │
│  Indian Tax Engine:                                                     │
│  ┌─────────────────────────────────────────────────┐                   │
│  │  INDIA_TAX_RATES (FY 2024-25)                   │                  │
│  │                                                  │                  │
│  │  Equity:                                         │                  │
│  │    STCG (< 12 months)  → 20%                    │                  │
│  │    LTCG (≥ 12 months)  → 12.5% above ₹1.25L    │                  │
│  │    STT on sell         → 0.025%                  │                  │
│  │                                                  │                  │
│  │  Mutual Funds (Equity):                          │                  │
│  │    STCG → 20%  |  LTCG → 12.5% above ₹1.25L   │                  │
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
│  │ country          │  │   (manual/groww) │                            │
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
│  │  │ • Token Usage    │  │ • ECS CPU/Memory (Victor)     │     │      │
│  │  │ • Error Rate     │  │ • Groww API Latency           │     │      │
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
Browser      API GW     Agent Router    AgentCore      Agent       Bedrock     DynamoDB   Groww API
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
  │            │             │              │            │ sync_groww │            │          │
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
│           │               │ 11. compliance_audit_load — Victor perf  │   │
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
│  (Groww / Custom)                         (Current System)               │
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
│     Marcus: risk score, sector exposure, technical indicators            │
│                                                                          │
│  2. COMPLIANCE GATE                                                      │
│     Trading Platform ──▶ POST /agent {agent:"victor"}                   │
│     "Pre-trade compliance check for client_ramu_de buying RELIANCE"     │
│     Victor: KYC status, concentration limits, regulatory flags           │
│                                                                          │
│  3. TAX-AWARE TRADING                                                    │
│     Trading Platform ──▶ POST /agent {agent:"olivia"}                   │
│     "Tax impact of selling TCS position — held 8 months"                │
│     Olivia: STCG ₹X at 20%, STT ₹Y, suggest waiting 4 months for LTCG │
│                                                                          │
│  4. PORTFOLIO REBALANCE                                                  │
│     Trading Platform ──▶ POST /agent {agent:"orchestrator"}             │
│     "Full review before quarterly rebalance"                            │
│     All 4 agents: combined market + plan + tax + compliance report       │
│                                                                          │
│  5. REAL-TIME DATA SYNC                                                  │
│     Groww executions ──▶ DynamoDB transactions table                     │
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
│ Compute (Container)    │ Amazon ECS Fargate (Victor)                     │
│ AI Agents              │ Amazon Bedrock AgentCore Runtime                │
│ Agent Framework 1      │ Strands SDK (Marcus, Sophia)                    │
│ Agent Framework 2      │ CrewAI 1.3.0 (Olivia)                          │
│ Agent Framework 3      │ LangGraph + Flask (Victor)                      │
│ Foundation Model       │ Anthropic Claude Haiku 4.5 / Sonnet 4          │
│ Agent Memory           │ AgentCore Memory (summary, semantic, preference)│
│ Database               │ Amazon DynamoDB (12 tables, 1 GSI)              │
│ Brokerage Integration  │ Groww API (Read-Only, Indian Market)            │
│ Indian Market Data     │ NSE/BSE via Groww (NIFTY50, sector mapping)     │
│ Indian Tax Engine      │ Custom (STCG/LTCG/STT/80C/80D/80CCD)          │
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
│   ├── market-analyst/              # Marcus (Strands) — 14 tools
│   │   ├── market_analyst.py        # ~1,400 lines
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   │
│   ├── financial-planner/           # Sophia (Strands) — 11 tools
│   │   ├── financial_planner.py     # ~1,499 lines
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   │
│   ├── tax-optimizer/               # Olivia (CrewAI) — 9 tools (incl. Indian tax)
│   │   ├── tax_optimizer.py         # ~1,400 lines
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   │
│   └── compliance-checker/          # Victor (LangGraph + Flask) — 9 tools
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
│   ├── groww_connector.py           # ~350 lines — Groww API integration
│   ├── .env.example                 # Groww credential template
│   └── .env                         # (gitignored) actual credentials
│
├── frontend/
│   ├── index.html                   # Login (US + Groww quick-login)
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
│   └── seed_data.py                 # 7 clients (4 US + 3 Indian), portfolios, txns
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
| ECS Service | Victor (compliance-checker) on Fargate |

---

## Demo Accounts

| Email | Client ID | Market | Risk Profile |
|-------|-----------|--------|--------------|
| sarah.chen@email.com | client_sarah_chen | US | Aggressive, $2.1M |
| james.wilson@email.com | client_james_wilson | US | Moderate, $850K |
| priya.patel@email.com | client_priya_patel | US | Moderate, $620K |
| alex.rodriguez@email.com | client_alex_rodriguez | US | Conservative, $1.5M |
| ramu@groww.in | client_ramu_de | India (Groww) | Aggressive, ₹90L |
| ananya@groww.in | client_ananya_sharma | India (Groww) | Moderate, ₹24.5L |
| vikram@groww.in | client_vikram_patel | India (Groww) | Conservative, ₹2.5Cr |

**Password for all demo accounts:** `demo123`
