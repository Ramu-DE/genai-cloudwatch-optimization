# WealthAI Copilot — Architecture & Flow

## System Architecture

```
                                    +------------------------------------------+
                                    |          Amazon CloudFront (CDN)          |
                                    |     wealth-mgmt-frontend-*.cloudfront.net |
                                    +--------------------+---------------------+
                                                         |
                                                         v
                                    +------------------------------------------+
                                    |            Amazon S3 (Frontend)           |
                                    |  wealth-mgmt-frontend-{account-id}       |
                                    |                                          |
                                    |  index.html          (Login/Register)    |
                                    |  client-dashboard.html (Agent Chat)      |
                                    |  observability.html  (CloudWatch View)   |
                                    |  performance-tuning.html (Optimization)  |
                                    |  loadtest.html       (Load Testing)      |
                                    |  styles.css / config.template.js         |
                                    +----+----------------+--------------------+
                                         |                |
                          REST API calls |                | WebSocket
                                         v                v
                    +--------------------+--+    +---------+-----------+
                    |  API Gateway (REST)   |    | API Gateway (WSS)   |
                    |  /auth/{proxy+}       |    | $connect            |
                    |  /agent               |    | $disconnect         |
                    |  /loadtest            |    | $default            |
                    |  /optimization        |    +----------+----------+
                    +--+--+--+--+----------+               |
                       |  |  |  |                          v
          +------------+  |  |  +----------+    +----------+----------+
          |               |  |             |    |  WebSocket Lambda   |
          v               v  |             v    |  (Connection Mgmt)  |
+---------+----+ +--------++ | +-----------+-+  +----------+----------+
| Auth Lambda  | | Agent   | | | Optimization|             |
| (Login/Reg/  | | Router  | | | Lambda      |             v
|  Validate)   | | Lambda  | | | (16 Fault   |  +----------+----------+
+---------+----+ +----+----+ | | Scenarios)  |  |      DynamoDB       |
          |           |      | +-------------+  | websocket_connections|
          v           |      v                  +---------------------+
  +-------+-------+  |  +---+----------+
  |   DynamoDB    |  |  | Load Tester  |
  | user_auth     |  |  | Lambda       |
  | (GSI: token)  |  |  | (Concurrent) |
  +---------------+  |  +--------------+
                     |
    +----------------+----------------+
    |         AGENT ROUTING           |
    |   (Single Agent or Fan-Out)     |
    +--+-------+-------+----------+--+
       |       |       |          |
       v       v       v          v
+------+--+ +--+-----+ +-+------+ +--+--------+
| Marcus  | | Sophia | | Olivia | | Victor    |
| Market  | | Fin.   | | Tax    | | Compliance|
| Analyst | | Planner| | Optim. | | Checker   |
|         | |        | |        | |           |
| Strands | | Strands| | CrewAI | | LangGraph |
+----+----+ +---+----+ +---+----+ +----+------+
     |          |           |           |
     +----------+-----------+-----------+
     |   Amazon Bedrock AgentCore       |    +---> ECS Fargate (Victor)
     |   (Managed Agent Runtime)        |    |     Port 8080, Flask
     +--+----------+----------+----+----+    |     LangGraph StateGraph
        |          |          |    |         |
        v          v          v    +---------+
+-------+---+ +---+------+ +-+--------+
| Bedrock   | | AgentCore| | DynamoDB |
| Foundation| | Memory   | | (12 Tables)|
| Models    | | Service  | |          |
+-----------+ +----------+ +----------+
```

## Detailed Component Architecture

### Agent Layer

```
+------------------------------------------------------------------+
|                    AGENT RUNTIME LAYER                            |
|                                                                  |
|  +-------------------+  +-------------------+                    |
|  | Marcus (Strands)  |  | Sophia (Strands)  |                   |
|  | AgentCore Runtime |  | AgentCore Runtime |                   |
|  |                   |  |                   |                    |
|  | Tools:            |  | Tools:            |                   |
|  | - get_client_     |  | - get_client_     |                   |
|  |   portfolio       |  |   portfolio       |                   |
|  | - analyze_market_ |  | - create_         |                   |
|  |   sector          |  |   allocation_plan |                   |
|  | - get_market_     |  | - calculate_      |                   |
|  |   indicators      |  |   retirement_     |                   |
|  | - assess_         |  |   projection      |                   |
|  |   portfolio_risk  |  | - rebalance_      |                   |
|  | - get_stock_      |  |   portfolio       |                   |
|  |   analysis        |  | - schedule_       |                   |
|  | - get_memory_     |  |   consultation    |                   |
|  |   context         |  | - get_memory_     |                   |
|  | - save_convo_     |  |   context         |                   |
|  |   memory          |  | - save_convo_     |                   |
|  | - consult_        |  |   memory          |                   |
|  |   financial_      |  | - consult_        |                   |
|  |   planner         |  |   market_analyst  |                   |
|  | - consult_tax_    |  | - consult_tax_    |                   |
|  |   optimizer       |  |   optimizer       |                   |
|  +-------------------+  | - consult_        |                   |
|                         |   compliance_     |                   |
|  +-------------------+  |   checker         |                   |
|  | Olivia (CrewAI)   |  +-------------------+                   |
|  | AgentCore Runtime |                                          |
|  |                   |  +-------------------+                    |
|  | Tools:            |  | Victor (LangGraph)|                   |
|  | - analyze_tax_    |  | ECS Fargate       |                   |
|  |   situation       |  |                   |                    |
|  | - find_tax_loss_  |  | Tools:            |                   |
|  |   harvest_opps    |  | - verify_kyc      |                   |
|  | - calculate_      |  | - screen_aml      |                   |
|  |   capital_gains   |  | - check_          |                   |
|  | - optimize_tax_   |  |   regulatory_     |                   |
|  |   bracket         |  |   compliance      |                   |
|  | - get_memory_     |  | - review_         |                   |
|  |   context         |  |   transaction     |                   |
|  | - save_convo_     |  | - generate_       |                   |
|  |   memory          |  |   audit_report    |                   |
|  | - consult_        |  | - get_compliance_ |                   |
|  |   market_analyst  |  |   history         |                   |
|  | - consult_        |  | - consult_        |                   |
|  |   financial_      |  |   market_analyst  |                   |
|  |   planner         |  | - consult_        |                   |
|  +-------------------+  |   financial_      |                   |
|                         |   planner         |                   |
|                         | - consult_tax_    |                   |
|                         |   optimizer       |                   |
|                         +-------------------+                    |
+------------------------------------------------------------------+
```

### Cross-Agent Communication Flow

```
                    +-------------------+
                    |   Agent Router    |
                    |   Lambda          |
                    +--------+----------+
                             |
              +--------------+--------------+
              |   Orchestrator Mode         |
              |   (Fan-out to all agents)   |
              +-+------+------+----------+--+
                |      |      |          |
                v      v      v          v
            Marcus  Sophia  Olivia    Victor
                |      |      |          |
                +------+------+----------+
                |  Cross-Agent Calls      |
                |  via AgentCore Runtime  |
                +-------------------------+

  Example Flows:

  1. "Review my portfolio and tax implications"
     User --> Router --> Marcus (portfolio + risk)
                           |
                           +--> consult_tax_optimizer(Olivia)
                           |        |
                           |        +--> Tax-loss harvesting analysis
                           |
                           +--> Response with market + tax view

  2. "Is my portfolio compliant?"
     User --> Router --> Victor (compliance check)
                           |
                           +--> consult_market_analyst(Marcus)
                           |        |
                           |        +--> Portfolio risk data
                           |
                           +--> consult_financial_planner(Sophia)
                           |        |
                           |        +--> Suitability verification
                           |
                           +--> Compliance report

  3. "Give me a complete financial review" (Orchestrator)
     User --> Router --> [Fan-out to ALL 4 agents in parallel]
                           |
                           +--> Marcus: Market analysis
                           +--> Sophia: Planning review
                           +--> Olivia: Tax optimization
                           +--> Victor: Compliance status
                           |
                           +--> Combined response
```

### Data Flow

```
+-------------------------------------------------------------------------+
|                          DATA LAYER                                     |
|                                                                         |
|  +------------------+  +------------------+  +-------------------+      |
|  | Client Profiles  |  | Portfolios       |  | Transactions      |     |
|  | client_id (PK)   |  | client_id (PK)   |  | transaction_id(PK)|     |
|  | full_name        |  | portfolio_type   |  | client_id         |     |
|  | risk_tolerance   |  |   (SK)           |  | type, amount      |     |
|  | investment_goals |  | holdings[]       |  | ticker, status    |     |
|  | net_worth        |  | total_value      |  | timestamp         |     |
|  | kyc_status       |  | cash_balance     |  +-------------------+      |
|  +------------------+  +------------------+                             |
|                                                                         |
|  +------------------+  +------------------+  +-------------------+      |
|  | Tax Records      |  | Compliance Recs  |  | Audit Log         |     |
|  | client_id (PK)   |  | record_id (PK)   |  | audit_id (PK)     |     |
|  | tax_year (SK)    |  | client_id        |  | timestamp (SK)    |     |
|  | capital_gains    |  | check_type       |  | agent, action     |     |
|  | tax_loss_harvest |  | status           |  | client_id         |     |
|  | deductions       |  | findings         |  | details           |     |
|  +------------------+  +------------------+  +-------------------+      |
|                                                                         |
|  +------------------+  +------------------+  +-------------------+      |
|  | Consultations    |  | Advisor Schedule |  | Market Data       |     |
|  | consultation_id  |  | advisor_id (PK)  |  | symbol (PK)       |     |
|  |   (PK)           |  | date (SK)        |  | data_type (SK)    |     |
|  | client_id        |  | slots[]          |  | price, volume     |     |
|  | agent, type      |  | booked[]         |  | metrics           |     |
|  +------------------+  +------------------+  +-------------------+      |
|                                                                         |
|  +------------------+  +------------------+  +-------------------+      |
|  | User Auth        |  | WebSocket Conns  |  | Load Test Results |     |
|  | email (PK)       |  | connectionId(PK) |  | test_id (PK)      |     |
|  | password_hash    |  | client_id        |  | timestamp (SK)    |     |
|  | session_token    |  | ttl              |  | metrics           |     |
|  | client_id        |  +------------------+  +-------------------+      |
|  | GSI: session_    |                                                   |
|  |   token-index    |                                                   |
|  +------------------+                                                   |
+-------------------------------------------------------------------------+
```

### Observability Architecture

```
+-------------------------------------------------------------------------+
|                     OBSERVABILITY LAYER                                  |
|                                                                         |
|  +-----------------------------+                                        |
|  |   MetricsEmitter (Shared)   |                                       |
|  |   Used by all 4 agents      |                                       |
|  +------+----------+-----------+                                       |
|         |          |                                                    |
|         v          v                                                    |
|  +------+------+  ++-----------+  +------------------+                  |
|  | CloudWatch  |  | EMF Logs   |  | X-Ray Traces     |                 |
|  | Custom      |  | (Embedded  |  | (Annotations)    |                 |
|  | Metrics     |  |  Metric    |  |                  |                  |
|  |             |  |  Format)   |  | agent_name       |                 |
|  | Namespace:  |  |            |  | tool_name        |                 |
|  | WealthMgmt/ |  | Auto-      |  | client_id        |                 |
|  |   Agents    |  | extracted  |  | success/failure  |                 |
|  +------+------+  | to CW     |  +--------+---------+                  |
|         |         | Metrics    |           |                            |
|         |         +------+-----+           |                            |
|         |                |                 |                            |
|         v                v                 v                            |
|  +------+----------------+--+--------------+----------+                 |
|  |              CloudWatch Console                    |                 |
|  |                                                    |                  |
|  |  Dashboard: wealth_mgmt_copilot_dashboard          |                 |
|  |  +----------------------------------------------+ |                  |
|  |  | Bedrock Metrics  | Agent Performance          | |                 |
|  |  | - Invocations    | - Lambda Duration          | |                 |
|  |  | - Latency        | - Errors vs Invocations    | |                 |
|  |  | - Token Usage    | - Concurrent Executions    | |                 |
|  |  | - Errors         | - ECS CPU/Memory           | |                 |
|  |  +----------------------------------------------+ |                  |
|  |  | API & Data Layer | Custom Agent Metrics        | |                 |
|  |  | - API Requests   | - Response Time by Agent   | |                 |
|  |  | - API Latency    | - Cost Per Agent ($)       | |                 |
|  |  | - DynamoDB Cap.  | - Tool Calls Per Request   | |                 |
|  |  |                  | - Tool Latency (Marcus)    | |                 |
|  |  |                  | - Memory Hit Rate (%)      | |                 |
|  |  |                  | - Compliance Events        | |                 |
|  |  +----------------------------------------------+ |                  |
|  |  | Logs & Traces                                 | |                  |
|  |  | - Bedrock Invocations Log                     | |                 |
|  |  | - Agent Router Activity Log                   | |                 |
|  |  +----------------------------------------------+ |                  |
|  +----------------------------------------------------+                 |
|                                                                         |
|  Alarms (10):                                                           |
|  +-------------------------------------------------------------------+  |
|  | Threshold (7)                  | Anomaly Detection (3)            |  |
|  | - Bedrock high latency >10s   | - Latency anomaly (band=2)       |  |
|  | - Bedrock throttling >5/min   | - Token usage anomaly (band=3)   |  |
|  | - Agent router errors >5%     | - Agent response time anomaly    |  |
|  | - Router duration >25s        |   (band=2)                       |  |
|  | - ECS CPU >80%                |                                   |  |
|  | - Token usage spike >500K     | All use ANOMALY_DETECTION_BAND() |  |
|  | - DynamoDB throttle           |                                   |  |
|  +-------------------------------------------------------------------+  |
|                                                                         |
|  Log Insights Queries (10):                                             |
|  - Token usage per agent    - Compliance flagging rate                  |
|  - Slowest tools (P95)      - Response time distribution                |
|  - Error patterns           - Top clients by spend                      |
|  - Memory hit rate          - DynamoDB latency per table                |
|  - Load test results        - Bedrock invocation analysis               |
+-------------------------------------------------------------------------+
```

### Optimization / Fault Injection Framework

```
+-------------------------------------------------------------------------+
|                  PERFORMANCE OPTIMIZATION LAB                            |
|                                                                         |
|  Frontend (performance-tuning.html)                                     |
|       |                                                                 |
|       v                                                                 |
|  POST /optimization                                                     |
|       |                                                                 |
|       v                                                                 |
|  +-------------------+     +-------------------+                        |
|  | Optimization      |     | scenarios.json    |                       |
|  | Lambda            +---->| (16 scenarios)    |                       |
|  |                   |     +-------------------+                        |
|  | - scenario_router |                                                  |
|  | - fault_injectors |     Scenarios:                                   |
|  | - metrics_collect |     +-----------------------------------+        |
|  | - optimization_   |     | 1.  context_bloat                 |       |
|  |   executors       |     | 2.  tool_failure                  |       |
|  +--------+----------+     | 3.  latency_injection             |       |
|           |                | 4.  structuring_detection          |       |
|           v                | 5.  prompt_injection_defense       |       |
|  +--------+----------+    | 6.  model_comparison               |       |
|  | Baseline Run       |    | 7.  token_optimization             |       |
|  | (Normal agent call)|    | 8.  concurrent_load                |       |
|  +--------+----------+    | 9.  cold_start_analysis            |       |
|           |                | 10. memory_retrieval_perf          |       |
|           v                | 11. compliance_audit_load          |       |
|  +--------+----------+    | 12. cross_agent_latency            |       |
|  | Scenario Run       |    | 13. dynamodb_throttle_sim          |       |
|  | (With fault inject)|    | 14. response_quality_check         |       |
|  +--------+----------+    | 15. multi_turn_conversation        |       |
|           |                | 16. error_recovery                 |       |
|           v                +-----------------------------------+        |
|  +--------+----------+                                                  |
|  | Compare & Report  |    Emits to: WealthMgmt/Optimization             |
|  | baseline_ms       |    - ScenarioLatency                             |
|  | scenario_ms       |    - BaselineLatency                             |
|  | improvement_%     |    - ImprovementPercent                          |
|  +-------------------+                                                  |
+-------------------------------------------------------------------------+
```

### Authentication Flow

```
  Browser                    API Gateway              Auth Lambda           DynamoDB
    |                            |                        |                    |
    |  POST /auth/login          |                        |                    |
    |  {email, password}         |                        |                    |
    +--------------------------->|                        |                    |
    |                            +----------------------->|                    |
    |                            |                        |  GetItem(email)    |
    |                            |                        +------------------->|
    |                            |                        |<-------------------+
    |                            |                        |  Verify password   |
    |                            |                        |  Generate token    |
    |                            |                        |  UpdateItem(token) |
    |                            |                        +------------------->|
    |                            |<-----------------------+                    |
    |  {token, client_id, name}  |                        |                    |
    |<---------------------------+                        |                    |
    |                            |                        |                    |
    |  POST /auth/validate       |                        |                    |
    |  {token}                   |                        |                    |
    +--------------------------->+----------------------->|                    |
    |                            |                        | Query GSI          |
    |                            |                        | session_token-index|
    |                            |                        +------------------->|
    |                            |                        |<-------------------+
    |  {valid, client_id, role}  |<-----------------------+                    |
    |<---------------------------+                        |                    |
```

### Agent Chat Flow (End-to-End with Tracing)

```
  Browser          API GW        Agent Router       AgentCore         Agent        Bedrock       DynamoDB
    |                |   X-Ray        |                  |              |             |              |
    |  POST /agent   |  Trace ID      |                  |              |             |              |
    |  {agent,msg,   |  propagated    |                  |              |             |              |
    |   client_id}   |  throughout    |                  |              |             |              |
    +--------------->+--------------->|                  |              |             |              |
    |                |                | validate_input() |              |             |              |
    |                |                | map_username()   |              |             |              |
    |                |                +----------------->|              |             |              |
    |                |                | invoke_agent_    |  route to    |             |              |
    |                |                | runtime()        |  container   |             |              |
    |                |                |  + traceId       +------------->|             |              |
    |                |                |  + traceParent   |              |             |              |
    |                |                |                  |              | @tool calls |              |
    |                |                |                  |              +------------>|              |
    |                |                |                  |              |  GetItem    |              |
    |                |                |                  |              +------------>+------------->|
    |                |                |                  |              |<------------+-<------------+
    |                |                |                  |              |             |              |
    |                |                |                  |              | Agent()     |              |
    |                |                |                  |              | system_prompt              |
    |                |                |                  |              +------------>|              |
    |                |                |                  |              |  InvokeModel|              |
    |                |                |                  |              |<------------|              |
    |                |                |                  |              |             |              |
    |                |                |                  |              | MetricsEmitter.emit()      |
    |                |                |                  |              +---> CloudWatch             |
    |                |                |                  |              +---> X-Ray Annotation       |
    |                |                |                  |              +---> EMF Log                |
    |                |                |                  |              |             |              |
    |                |                |                  |<-------------+             |              |
    |                |                |<-----------------+              |             |              |
    |                |                |                  |              |             |              |
    |                |                | put_metric_data  |              |             |              |
    |                |                | (RouterLatency,  |              |             |              |
    |                |                |  RouterInvocations)             |             |              |
    |                |                | EMF log          |              |             |              |
    |                |<---------------+                  |              |             |              |
    |  {response,    |                |                  |              |             |              |
    |   duration_ms, |                |                  |              |             |              |
    |   trace_id}    |                |                  |              |             |              |
    |<---------------+                |                  |              |             |              |
```

## Extension Point: Trading Platform Integration

```
+-------------------------------------------------------------------------+
|                                                                         |
|  YOUR TRADING PLATFORM                 WEALTHAI COPILOT                 |
|  (Future Integration)                  (Current System)                  |
|                                                                         |
|  +---------------------+              +---------------------+           |
|  | Trading Engine      |   REST API   | Agent Router Lambda |           |
|  | - Order Execution   +------------->| POST /agent         |           |
|  | - Position Mgmt     |              | {agent: "marcus",   |           |
|  | - Real-time Quotes  |              |  message: "analyze  |           |
|  +----------+----------+              |  AAPL before buy"}  |           |
|             |                         +---------------------+           |
|             |                                                           |
|  +----------v----------+              +---------------------+           |
|  | Trading API         |   WebSocket  | WebSocket API       |           |
|  | - Market Data Feed  +<------------>| Real-time agent     |           |
|  | - Order Status      |              | responses           |           |
|  | - Portfolio Sync    |              +---------------------+           |
|  +----------+----------+                                                |
|             |                         +---------------------+           |
|  +----------v----------+   DynamoDB   | Shared Data Layer   |           |
|  | Trading Database    +<------------>| - Client Profiles   |           |
|  | - Orders            |   (sync)     | - Portfolios        |           |
|  | - Executions        |              | - Transactions      |           |
|  | - P&L               |              +---------------------+           |
|  +---------------------+                                                |
|                                                                         |
|  Suggested Integration Points:                                          |
|                                                                         |
|  1. PRE-TRADE ANALYSIS                                                  |
|     Trading Platform --> POST /agent {agent:"marcus"}                   |
|     "Analyze risk before executing $50K AAPL buy"                       |
|                                                                         |
|  2. COMPLIANCE GATE                                                     |
|     Trading Platform --> POST /agent {agent:"victor"}                   |
|     "Pre-trade compliance check for client_sarah_chen"                  |
|                                                                         |
|  3. TAX-AWARE TRADING                                                   |
|     Trading Platform --> POST /agent {agent:"olivia"}                   |
|     "Tax impact of selling MSFT position at current gains"              |
|                                                                         |
|  4. PORTFOLIO REBALANCE                                                 |
|     Trading Platform --> POST /agent {agent:"orchestrator"}             |
|     "Full review before quarterly rebalance"                            |
|     (Fans out to all 4 agents simultaneously)                           |
|                                                                         |
|  5. REAL-TIME SYNC                                                      |
|     Trading executions --> DynamoDB transactions table                   |
|     Portfolio updates --> DynamoDB portfolios table                      |
|     Agents always see latest positions                                  |
|                                                                         |
|  6. NEW AGENTS TO ADD:                                                  |
|     +-------------------+  +-------------------+                        |
|     | Trading Agent     |  | Risk Manager      |                       |
|     | (Order execution, |  | (Real-time P&L,   |                       |
|     |  algo strategies, |  |  margin checks,   |                       |
|     |  market making)   |  |  position limits) |                       |
|     +-------------------+  +-------------------+                        |
+-------------------------------------------------------------------------+
```

## Technology Stack

```
+-----------------------+--------------------------------------------------+
| Layer                 | Technology                                       |
+-----------------------+--------------------------------------------------+
| Frontend              | HTML5, CSS3 (custom), Vanilla JS                 |
| CDN                   | Amazon CloudFront                                |
| Static Hosting        | Amazon S3 (website mode)                         |
| REST API              | Amazon API Gateway (Regional)                    |
| WebSocket API         | Amazon API Gateway (WebSocket)                   |
| Compute (Serverless)  | AWS Lambda (Python 3.12)                         |
| Compute (Container)   | Amazon ECS Fargate (Victor)                      |
| AI Agents             | Amazon Bedrock AgentCore Runtime                 |
| Agent Framework 1     | Strands SDK (Marcus, Sophia)                     |
| Agent Framework 2     | CrewAI 1.3.0 (Olivia)                            |
| Agent Framework 3     | LangGraph + Flask (Victor)                       |
| Foundation Model      | Anthropic Claude Haiku 4.5 / Sonnet 4            |
| Agent Memory          | AgentCore Memory (summary, semantic, preference) |
| Database              | Amazon DynamoDB (12 tables, 1 GSI)               |
| Observability         | Amazon CloudWatch (Metrics, Logs, Dashboard)      |
| Tracing               | AWS X-Ray (active tracing, annotations)           |
| Structured Logging    | EMF (Embedded Metric Format)                     |
| Custom Metrics        | CloudWatch put_metric_data (WealthMgmt/Agents)   |
| Alarms                | CloudWatch Alarms + Anomaly Detection             |
| Notifications         | Amazon SNS                                       |
| Container Registry    | Amazon ECR                                       |
| IaC                   | AWS CloudFormation                               |
+-----------------------+--------------------------------------------------+
```

## File Structure

```
wealth-mgmt-copilot/
|
+-- agents/
|   +-- market-analyst/          # Marcus (Strands)
|   |   +-- market_analyst.py    # 1,273 lines - 9 tools
|   |   +-- Dockerfile
|   |   +-- requirements.txt
|   |
|   +-- financial-planner/       # Sophia (Strands)
|   |   +-- financial_planner.py # 1,499 lines - 11 tools
|   |   +-- Dockerfile
|   |   +-- requirements.txt
|   |
|   +-- tax-optimizer/           # Olivia (CrewAI)
|   |   +-- tax_optimizer.py     # 1,181 lines - 9 tools
|   |   +-- Dockerfile
|   |   +-- requirements.txt
|   |
|   +-- compliance-checker/      # Victor (LangGraph + Flask)
|       +-- app.py               # 1,177 lines - 9 tools
|       +-- config_reader.py
|       +-- config/config.conf
|       +-- Dockerfile
|       +-- requirements.txt
|       +-- .dockerignore
|
+-- lambdas/
|   +-- agent-router/            # Routes to agents via AgentCore
|   |   +-- lambda_function.py   # 401 lines
|   |
|   +-- auth/                    # Authentication
|   |   +-- lambda_function.py   # 308 lines
|   |
|   +-- websocket/               # Real-time chat
|   |   +-- websocket_handler.py # 177 lines
|   |
|   +-- load-tester/             # Stress testing
|   |   +-- lambda_function.py   # 466 lines
|   |
|   +-- optimization/            # Fault injection lab
|       +-- lambda_handler.py    # 288 lines
|       +-- fault_injectors.py   # 272 lines
|       +-- metrics_collector.py # 202 lines
|       +-- optimization_executors.py # 447 lines
|       +-- scenario_router.py   # 156 lines
|       +-- config/scenarios.json # 16 scenarios
|
+-- shared/
|   +-- metrics_emitter.py       # 290 lines - CloudWatch + EMF + X-Ray
|   +-- cross_agent.py           # 109 lines - Peer agent invocation
|
+-- frontend/
|   +-- index.html               # Login / Register
|   +-- client-dashboard.html    # Agent chat + portfolio
|   +-- observability.html       # CloudWatch viewer
|   +-- performance-tuning.html  # 16-scenario optimization lab
|   +-- loadtest.html            # Load testing console
|   +-- styles.css               # Navy/Gold theme
|   +-- config.template.js       # API endpoint config
|   +-- websocket-client.js      # WebSocket client
|   +-- favicon.svg
|
+-- cloudwatch/
|   +-- dashboard.json           # 20+ widget dashboard
|   +-- alarms.json              # 7 threshold + 3 anomaly alarms
|   +-- log_insights_queries.json # 10 pre-built queries
|
+-- dynamodb/
|   +-- create_tables.py         # 12 tables + GSI
|   +-- seed_data.py             # 5 clients, portfolios, transactions
|
+-- infra/
|   +-- cloudformation.yaml      # 801 lines - complete IaC
|
+-- scripts/
|   +-- deploy.sh                # One-command deployment
|
+-- ARCHITECTURE.md              # This file
```
