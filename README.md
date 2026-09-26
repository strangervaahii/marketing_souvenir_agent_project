# Marketing Souvenir Fulfillment Agent

## 1. Overview

The **Marketing Souvenir Fulfillment Agent** is an AI-assisted order fulfillment system for promotional merchandise.

The application accepts promotional merchandise orders, interprets natural-language order lines using an in-house LLM, reconciles products against a controlled catalog, checks primary and alternate warehouse inventory, applies risk-based fulfillment policies, autonomously dispatches eligible orders, supports alternate-warehouse rerouting, and persists an auditable processing history.

The architecture deliberately separates:

- **LLM-based language understanding**
- **Deterministic catalog reconciliation**
- **Deterministic inventory decisions**
- **Risk and dispatch policy**
- **Fulfillment tool execution**
- **Human review and override**
- **Persistence and auditability**

> **AI understands the order; deterministic application logic decides what can actually be fulfilled.**

---

## 2. Architecture

```text
                         +----------------------+
                         |   Promotional Order  |
                         +----------+-----------+
                                    |
                                    v
                         +----------------------+
                         |     FastAPI API      |
                         |      main.py         |
                         +----------+-----------+
                                    |
                                    v
                         +----------------------+
                         |    Fulfillment       |
                         |       Agent          |
                         |      agent.py        |
                         +----------+-----------+
                                    |
                    +---------------+---------------+
                    |                               |
                    v                               v
          +-------------------+           +----------------------+
          |   In-house LLM    |           | Catalog Reconciler   |
          |     llm.py        |           |   reconciler.py      |
          +---------+---------+           +----------+-----------+
                    |                                |
                    +---------------+----------------+
                                    |
                                    v
                         +----------------------+
                         | Inventory / Tools    |
                         |      tools.py        |
                         +----------+-----------+
                                    |
                         Check PRIMARY inventory
                                    |
                    +---------------+---------------+
                    |                               |
              Sufficient                       Insufficient
                    |                               |
                    v                               v
        +---------------------+          Check ALTERNATE inventory
        | PRIMARY_FULFILLMENT |                     |
        +----------+----------+              +------+------+
                   |                         |             |
                   |                    Sufficient     Insufficient
                   |                         |             |
                   |                         v             v
                   |               +----------------+  +------------+
                   |               | ALTERNATE       |  | BACKORDER  |
                   |               | REROUTE TOOL    |  +------------+
                   |               +-------+--------+
                   |                       |
                   +-----------+-----------+
                               |
                               v
                     +----------------------+
                     | Risk / Policy Engine |
                     |      policy.py       |
                     +----------+-----------+
                                |
                    +-----------+-----------+
                    |                       |
                 Low Risk                High Risk
                    |                       |
                    v                       v
          +--------------------+    +--------------------+
          | Autonomous         |    | Human Review /     |
          | Fulfillment        |    | Override           |
          +---------+----------+    +---------+----------+
                    |                         |
                    v                         v
          +--------------------+    +--------------------+
          | dispatch() /       |    | dispatch() after   |
          | reroute() tool     |    | valid approval     |
          +---------+----------+    +---------+----------+
                    |                         |
                    +------------+------------+
                                 |
                                 v
                       +----------------------+
                       | SQLite / SQLAlchemy  |
                       | Orders + Audit Trail |
                       +----------------------+
```

---

## 3. End-to-End Agent Flow

The agent processes an order using the following sequence:

```text
Order
  |
  v
Parse / split order lines
  |
  v
LLM interpretation
  |
  v
Catalog reconciliation
  |
  v
Primary inventory check
  |
  +---- sufficient -----------------> PRIMARY_FULFILLMENT
  |
  +---- insufficient
              |
              v
       Alternate inventory check
              |
        +-----+-----+
        |           |
    sufficient   insufficient
        |           |
        v           v
ALTERNATE_REROUTE  BACKORDER
        |
        v
Risk / policy evaluation
        |
   +----+----------------+
   |                     |
Low risk              High risk
   |                     |
   v                     v
Autonomous           Human review
fulfillment              |
   |                     v
   |                  Override
   |                     |
   +----------+----------+
              |
              v
          Audit trail
```

---

## 4. Data Ingestion

The application ingests:

- `promo_merch_catalog.csv`
- `promo_merch_orders.csv`
- `alt_warehouse_inventory.csv`

The source data is loaded through:

```text
POST /ingest
```

The application persists the required data in SQLite using SQLAlchemy.

The catalog is treated as the source of truth for product/SKU mapping.

---

## 5. LLM Interpretation

LLM integration is implemented in:

```text
app/llm.py
```

The application uses an abstraction:

```text
LLMClient
   |
   +-- MockLLMClient
   |
   +-- HttpLLMClient
```

The current demo configuration uses the internal OpenAI-compatible HTTP endpoint.

The LLM is responsible for understanding natural-language order descriptions, including:

- Requested quantity
- Product description
- Product wording variations
- Semantic interpretation of order lines

Example:

```text
34x Custom Notebook - A5 Hardcover
```

The LLM can interpret this as:

```text
quantity = 34
product description = Custom Notebook - A5 Hardcover
```

The LLM is explicitly instructed not to invent catalog SKUs.

---

## 6. Catalog Reconciliation

Catalog reconciliation is implemented in:

```text
app/reconciler.py
```

The reconciliation layer is deterministic and catalog-driven.

It supports:

- Exact product-name matching
- Normalized text comparison
- Attribute-aware matching
- Similarity/confidence evaluation
- No-match handling
- Ambiguous-match handling

Relevant attributes can include:

```text
A5
A4
16oz
10000mAh
16GB
```

Example:

```text
Custom Notebook - A5 Hardcover
              |
              v
       Catalog reconciliation
              |
              v
PRM-213 / Notebook - A5
```

A product that cannot be confidently reconciled is not automatically dispatched.

Possible outcomes include:

```text
NO_CATALOG_MATCH
AMBIGUOUS_MATCH
```

---

## 7. Inventory and Fulfillment Tools

Inventory and fulfillment operations are encapsulated in:

```text
app/tools.py
```

The agent uses deterministic inventory checks.

### Primary warehouse

The primary warehouse is checked first.

```text
requested_quantity <= primary_stock
```

Result:

```text
PRIMARY_FULFILLMENT
```

### Alternate warehouse reroute

If the primary warehouse cannot fulfill the requested quantity, the agent checks the alternate warehouse.

The reroute condition is:

```text
primary_stock < requested_quantity
AND
requested_quantity <= alternate_stock
```

Result:

```text
ALTERNATE_REROUTE
```

When the policy allows autonomous fulfillment, the agent explicitly invokes the reroute tool:

```text
tools.reroute(sku, quantity)
```

The reroute tool:

1. Validates alternate warehouse stock.
2. Confirms the requested quantity can be fulfilled.
3. Reduces/reserves the corresponding alternate inventory.
4. Returns a structured fulfillment action.
5. Persists the `ALTERNATE_REROUTE` action in the audit history.

Example:

```text
Primary stock:     5
Requested:        13
Alternate stock:  50

Primary -> insufficient
Alternate -> sufficient
        |
        v
ALTERNATE_REROUTE
        |
        v
tools.reroute(...)
        |
        v
Alternate fulfillment
```

### Backorder

If neither warehouse can fulfill the requested quantity:

```text
requested_quantity > primary_stock
AND
requested_quantity > alternate_stock
```

Result:

```text
BACKORDER
```

A backordered line cannot be dispatched merely through human approval when physical inventory is unavailable.

---

## 8. Risk and Policy Engine

Policy evaluation is implemented in:

```text
app/policy.py
```

The policy engine determines whether an order is eligible for autonomous fulfillment.

The current low-risk criteria include:

1. Client type is `one-time order`
2. Total order value does not exceed `AUTO_DISPATCH_MAX_TOTAL`
3. Reconciliation confidence meets `MIN_RECONCILIATION_CONFIDENCE`
4. Every line is physically fulfillable through `PRIMARY_FULFILLMENT` or `ALTERNATE_REROUTE`

If all conditions pass:

```text
READY_TO_DISPATCH
risk_level = LOW
auto_dispatch_allowed = true
```

Otherwise:

```text
PENDING_REVIEW
risk_level = HIGH
auto_dispatch_allowed = false
```

This creates a clear boundary between autonomous fulfillment and human decision-making.

---

## 9. Autonomous Fulfillment

When an order is low risk, the agent executes the appropriate fulfillment tool.

### Primary fulfillment

```text
PRIMARY_FULFILLMENT
        |
        v
tools.dispatch(...)
        |
        v
DISPATCH
```

### Alternate fulfillment

```text
ALTERNATE_REROUTE
        |
        v
tools.reroute(...)
        |
        v
ALTERNATE_REROUTE audit event
        |
        v
DISPATCHED
```

This means `ALTERNATE_REROUTE` is not merely a decision label. It represents an actual fulfillment action executed by the agent through the fulfillment tool.

---

## 10. Human-in-the-Loop

Human review is exposed through:

```text
POST /orders/{order_id}/override
```

Example approval:

```json
{
  "decision": "APPROVE",
  "reason": "Reviewed the order and approved for dispatch.",
  "line_corrections": []
}
```

A reviewer can also correct a product mapping:

```json
{
  "decision": "APPROVE",
  "reason": "Reviewed and corrected the product mapping.",
  "line_corrections": [
    {
      "raw_text": "20x Stainless Tumbler - 16oz",
      "sku": "PRM-217"
    }
  ]
}
```

The override mechanism can resolve reviewable policy or catalog issues, but it does not bypass physical inventory constraints.

For example:

```text
BACKORDER
```

does not become a valid dispatch simply because a reviewer approves it.

---

## 11. Audit Trail and Persistence

Persistence is implemented through:

```text
app/db.py
app/models.py
```

The current local database is:

```text
SQLite
```

using SQLAlchemy.

Important processing events are persisted, including:

```text
ORDER_CREATED
LLM_INTERPRETATION
LLM_ERROR
CATALOG_RECONCILIATION
INVENTORY_CHECK
LINE_DECISION
POLICY_DECISION
AUTO_DISPATCH
ALTERNATE_REROUTE
DISPATCH
OVERRIDE
AGENT_FINISHED
```

For an alternate reroute, the audit trail can show:

```text
INVENTORY_CHECK
    warehouse = PRIMARY
    available = false
          |
          v
INVENTORY_CHECK
    warehouse = ALTERNATE
    available = true
          |
          v
LINE_DECISION
    decision = ALTERNATE_REROUTE
          |
          v
POLICY_DECISION
    READY_TO_DISPATCH
          |
          v
ALTERNATE_REROUTE
    warehouse = ALTERNATE
    sku = PRM-201
    quantity = 13
          |
          v
AGENT_FINISHED
    status = DISPATCHED
```

The order detail endpoint provides the order and its processing history:

```text
GET /orders/{order_id}
```

This allows reviewers and judges to understand what the agent decided and what autonomous action was executed.

---

## 12. API

The application is implemented using FastAPI.

Swagger UI:

```text
http://127.0.0.1:8001/docs
```

### Main endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/health` | Application health |
| POST | `/ingest` | Load source CSV data |
| GET | `/orders` | List orders |
| POST | `/orders/{order_id}/process` | Process one order |
| POST | `/process-all` | Process all orders |
| GET | `/orders/{order_id}` | View order and audit history |
| POST | `/orders/{order_id}/override` | Human review/override |

---

## 13. Project Structure

```text
marketing_souvenir_agent/
|
+-- app/
|   +-- agent.py
|   +-- config.py
|   +-- db.py
|   +-- llm.py
|   +-- main.py
|   +-- models.py
|   +-- policy.py
|   +-- reconciler.py
|   +-- schemas.py
|   +-- service.py
|   +-- tools.py
|
+-- README.md
+-- MANIFEST.md
+-- requirements.txt
|
+-- promo_merch_catalog.csv
+-- promo_merch_orders.csv
+-- alt_warehouse_inventory.csv
|
+-- .env                  # local only; do not commit
+-- orders.db             # local runtime state; do not commit
```

---

## 14. Running Locally

### Prerequisites

- Python 3.10+
- Access to the internal LLM API
- Valid LLM API credentials
- Company CA certificate if required by the internal HTTPS endpoint

### Create virtual environment

```powershell
python -m venv .venv
```

### Activate

```powershell
.\.venv\Scripts\Activate.ps1
```

### Install dependencies

```powershell
pip install -r requirements.txt
```

### Start application

```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

Open Swagger:

```text
http://127.0.0.1:8001/docs
```

---

## 15. Environment Configuration

Create `.env` in the project root.

Example:

```env
APP_ENV=dev
DATABASE_URL=sqlite:///./orders.db

LLM_MODE=http
LLM_BASE_URL=https://<internal-llm-host>/v1/openai
LLM_API_KEY=<your-api-key>
LLM_MODEL=gpt-oss-120b-ITG
LLM_TIMEOUT_SECONDS=60

LLM_SSL_VERIFY=true
LLM_CA_BUNDLE=C:\path\to\company-ca.crt

AUTO_DISPATCH_MAX_TOTAL=500
MIN_RECONCILIATION_CONFIDENCE=0.90
```

Do not commit `.env` or API credentials.

---

## 16. Testing Scenarios

### Scenario 1 — Low-risk primary fulfillment

Use a valid catalog product with sufficient primary stock and an order value within the auto-dispatch limit.

Expected:

```text
READY_TO_DISPATCH
LOW
PRIMARY_FULFILLMENT
AUTO DISPATCH
DISPATCHED
```

### Scenario 2 — High-value order

Use an order whose value exceeds the configured auto-dispatch limit.

Expected:

```text
PENDING_REVIEW
HIGH
auto_dispatch_allowed = false
```

Then use the override endpoint to demonstrate human approval.

### Scenario 3 — Unknown or ambiguous product

Use a product description that does not confidently map to the catalog.

Expected:

```text
NO_CATALOG_MATCH
```

or:

```text
AMBIGUOUS_MATCH
```

Expected behavior:

```text
PENDING_REVIEW
No automatic dispatch
```

### Scenario 4 — Backorder

Use a quantity greater than both primary and alternate inventory.

Expected:

```text
BACKORDER
PENDING_REVIEW
No dispatch
```

### Scenario 5 — Alternate warehouse autonomous reroute

Use a product where:

```text
primary_stock < requested_quantity <= alternate_stock
```

and ensure the order satisfies the low-risk policy.

Expected sequence:

```text
PRIMARY inventory check
        |
        v
insufficient
        |
        v
ALTERNATE inventory check
        |
        v
sufficient
        |
        v
LINE_DECISION
ALTERNATE_REROUTE
        |
        v
POLICY_DECISION
READY_TO_DISPATCH
        |
        v
tools.reroute(...)
        |
        v
ALTERNATE_REROUTE audit event
        |
        v
DISPATCHED
```

This scenario demonstrates the autonomous alternate-warehouse requirement.

---

## 17. Design Decisions

### Why use an LLM?

Natural-language product descriptions can contain variations that are difficult to handle with fixed string matching alone.

The LLM provides language understanding while deterministic code controls the actual fulfillment decision.

### Why is the catalog the source of truth?

The LLM is not trusted to invent or validate SKUs.

The catalog determines whether a product mapping is valid.

### Why deterministic inventory rules?

Inventory availability must be predictable and auditable.

The application explicitly follows:

```text
Primary
   |
   +--> Fulfill if sufficient
   |
   +--> Otherwise check Alternate
             |
             +--> Reroute if sufficient
             |
             +--> Otherwise Backorder
```

### Why use a separate reroute tool?

The challenge requires the agent to perform an autonomous alternate-warehouse action, not merely classify the line as a reroute.

Therefore the implementation separates:

```text
Decision:
ALTERNATE_REROUTE
```

from:

```text
Action:
tools.reroute(...)
```

The action is then persisted in the audit trail.

### Why human review?

Orders can exceed configured risk limits or contain unresolved catalog/inventory issues.

Human review provides controlled escalation without bypassing physical inventory constraints.

### Why provider/model abstraction?

The fulfillment workflow depends on `LLMClient`, allowing the underlying LLM provider or model to be changed without rewriting the fulfillment engine.

---

## 18. Security Guidelines

Never commit:

```text
.env
orders.db
*.pem
*.key
.venv/
__pycache__/
*.pyc
.idea/
```

Never hard-code an API key into Python source.

For internal HTTPS endpoints, use the trusted company CA bundle rather than disabling TLS verification.

Do not use:

```python
verify=False
```

in the final configuration.

If credentials are accidentally exposed, revoke or rotate them.

---

## 19. Development Corrections

Several implementation issues were identified and corrected during development.

### Attribute-aware catalog matching

Natural-language descriptions such as:

```text
Custom Notebook - A5 Hardcover
```

are reconciled using product attributes instead of relying only on generic text similarity.

### Historical decision handling

Override processing uses the latest `LINE_DECISION` for each order line so that an older audit event cannot incorrectly override a newer reconciliation result.

### TLS certificate validation

The internal LLM endpoint requires company certificate trust. The HTTP client uses a company CA bundle while keeping TLS verification enabled.

### Inventory safety

A `BACKORDER` cannot be dispatched when neither warehouse has sufficient inventory.

### Autonomous alternate reroute

The alternate-warehouse path was strengthened so that:

```text
ALTERNATE_REROUTE
```

is both:

1. A fulfillment decision, and
2. An actual tool execution through:

```text
tools.reroute(...)
```

The tool validates alternate stock and records the resulting action.

---

## 20. Future Improvements

With additional development time, the system could be extended with:

1. Automated unit and integration tests for all fulfillment paths.
2. Structured JSON-schema enforcement for LLM responses.
3. Retry/backoff and circuit-breaker handling for transient LLM failures.
4. Stronger authentication and authorization for human overrides.
5. PostgreSQL support for production-scale persistence.
6. Transactional inventory reservation to prevent concurrent overselling.
7. Metrics and operational monitoring.
8. A richer reviewer interface.
9. Regression tests for catalog matching and attribute extraction.
10. Multiple alternate-warehouse routing strategies.
11. Real warehouse/fulfillment-provider integrations.
12. Idempotency controls for repeated fulfillment requests.

---

## 21. Demo Checklist

Before the demonstration:

```text
[ ] Start FastAPI on port 8001
[ ] Open Swagger
[ ] POST /ingest
[ ] Process a low-risk primary-warehouse order
[ ] Demonstrate automatic dispatch
[ ] Process a high-value order
[ ] Demonstrate PENDING_REVIEW
[ ] Demonstrate human override
[ ] Process an unknown/ambiguous product
[ ] Demonstrate BACKORDER
[ ] Process an alternate-warehouse order
[ ] Show ALTERNATE_REROUTE decision
[ ] Show tools.reroute() result in audit history
[ ] Show final DISPATCHED status
[ ] Show GET /orders/{order_id} audit trail
```

---

## 22. Key Demo Message

The main architectural idea is:

```text
             LLM
              |
       Understand language
              |
              v
     Deterministic Agent
              |
      +-------+--------+
      |                |
   Catalog          Inventory
      |                |
      |          +-----+-----+
      |          |           |
      |       PRIMARY      ALTERNATE
      |          |           |
      |          |        reroute()
      |          |           |
      +----------+-----------+
                 |
                 v
             Risk Policy
                 |
          +------+------+
          |             |
       Low Risk      High Risk
          |             |
       Tool Call     Human Review
          |             |
          +------+------+
                 |
                 v
             Audit Trail
```

> **The LLM interprets language, deterministic logic protects business rules, tools execute fulfillment actions, and the audit trail records every important decision and action.**
