# Marketing Souvenir Fulfillment Agent

An AI-assisted fulfillment platform that converts promotional
merchandise orders into reliable, auditable fulfillment decisions.

------------------------------------------------------------------------

## About

### Problem

Promotional merchandise orders often contain natural-language
descriptions, quantities, product variations, and ambiguous wording. A
fulfillment system must reconcile these descriptions with a controlled
product catalog, verify inventory availability, apply business policies,
and determine whether an order can be dispatched automatically or
requires human review.

### Solution

The **Marketing Souvenir Fulfillment Agent** combines an in-house Large
Language Model (LLM) with deterministic business rules.

The LLM is responsible for understanding order-line language. The
application code remains responsible for catalog validation, inventory
decisions, risk evaluation, dispatch permissions, and audit persistence.

This separation provides:

-   AI-assisted language understanding
-   Deterministic fulfillment decisions
-   Primary and alternate warehouse routing
-   Backorder protection
-   Human-in-the-loop approval
-   Auditable decision history
-   Model/provider independence

### Core Design Principle

> **Use AI to understand the order; use deterministic business rules to
> decide what can actually be fulfilled.**

### Technology Stack

  Component           Technology
  ------------------- ----------------------------
  API                 FastAPI
  Language            Python
  Database            SQLite / SQLAlchemy
  Validation          Pydantic
  Data ingestion      CSV / Pandas
  LLM integration     OpenAI-compatible HTTP API
  Current model       `gpt-oss-120b-ITG`
  API documentation   Swagger / OpenAPI
  HTTP client         Requests

------------------------------------------------------------------------

## How It Works

### High-Level Flow

``` text
                         ORDER DATA
                             |
                             v
                    +----------------+
                    | Data Ingestion |
                    +-------+--------+
                            |
                            v
                    +----------------+
                    | Order Processor |
                    +-------+--------+
                            |
                            v
                    +----------------+
                    |   LLM Layer    |
                    |                |
                    | Understand     |
                    | order language |
                    +-------+--------+
                            |
                            v
              +-----------------------------+
              | Deterministic Reconciliation|
              |                             |
              | Catalog / SKU / Attributes  |
              +-------------+---------------+
                            |
                            v
                 +----------------------+
                 | Inventory Evaluation |
                 +----------+-----------+
                            |
                 +----------+----------+
                 |                     |
                 v                     v
             PRIMARY               ALTERNATE
             AVAILABLE             AVAILABLE
                 |                     |
                 v                     v
          PRIMARY_FULFILLMENT   ALTERNATE_REROUTE
                 |                     |
                 +----------+----------+
                            |
                            v
                     Risk / Policy
                       Evaluation
                            |
                 +----------+----------+
                 |                     |
                 v                     v
              LOW RISK              HIGH RISK
                 |                     |
                 v                     v
          AUTO DISPATCH          HUMAN REVIEW
                                       |
                                       v
                                    OVERRIDE
                                       |
                                       v
                                    DISPATCH
                            |
                            v
                       AUDIT TRAIL
```

### 1. Data Ingestion

The application ingests:

-   Promotional merchandise catalog
-   Promotional merchandise orders
-   Alternate warehouse inventory

The data is persisted into the application database and becomes the
source of truth for reconciliation and inventory checks.

### 2. LLM Interpretation

The LLM interprets an order line such as:

``` text
34x Custom Notebook - A5 Hardcover
```

and extracts structured information such as:

``` text
quantity = 34
product description = Custom Notebook - A5 Hardcover
```

The LLM is **not trusted to invent a SKU**.

### 3. Catalog Reconciliation

The interpreted product description is matched against the catalog.

The reconciliation layer can consider:

-   Product name
-   Exact matches
-   Product attributes
-   Specifications such as A5, A4, 16oz, etc.
-   Similarity/confidence

Example:

``` text
Custom Notebook - A5 Hardcover
             |
             v
       Catalog matching
             |
             v
PRM-213 / Notebook - A5
```

The final SKU comes from the catalog, not from an arbitrary LLM
response.

### 4. Inventory Evaluation

The system first checks the primary warehouse.

``` text
Requested quantity
        |
        v
Primary inventory sufficient?
       / \
     YES  NO
      |    |
      v    v
  PRIMARY  Check alternate
 FULFILLMENT    |
                v
       Alternate sufficient?
             /     \
           YES      NO
            |        |
            v        v
       ALTERNATE   BACKORDER
       REROUTE
```

For an alternate reroute:

``` text
primary_stock < requested_quantity <= alternate_stock
```

For a backorder:

``` text
requested_quantity > primary_stock
AND
requested_quantity > alternate_stock
```

### 5. Risk and Policy Evaluation

The policy engine determines whether an order can be automatically
dispatched.

A typical low-risk order must satisfy:

-   Client type is `one-time order`
-   Order value is within the configured auto-dispatch limit
-   Catalog reconciliation confidence is above the configured threshold
-   Every line is `PRIMARY_FULFILLMENT`

Otherwise:

``` text
PENDING_REVIEW
risk_level = HIGH
auto_dispatch_allowed = false
```

### 6. Human-in-the-Loop

A reviewer can approve a reviewable order or provide a catalog
correction.

Example:

``` json
{
  "decision": "APPROVE",
  "reason": "Reviewed the order and approved for dispatch.",
  "line_corrections": []
}
```

A catalog correction can be supplied when the product mapping needs
human clarification.

The system does **not** allow human approval to bypass a physical
inventory shortage.

### 7. Audit Trail

Important processing steps are persisted as audit events.

Typical sequence:

``` text
ORDER_CREATED
      |
      v
LLM_INTERPRETATION
      |
      v
CATALOG_RECONCILIATION
      |
      v
LINE_DECISION
      |
      v
POLICY_DECISION
      |
      +----> AUTO_DISPATCH
      |
      +----> PENDING_REVIEW
                  |
                  v
               OVERRIDE
                  |
                  v
               DISPATCH
```

LLM failures are also recorded as `LLM_ERROR` events.

------------------------------------------------------------------------

## API

The application exposes an OpenAPI/Swagger interface.

### Start the application

``` powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

Swagger UI:

``` text
http://127.0.0.1:8001/docs
```

### Main Endpoints

  Method   Endpoint                        Purpose
  -------- ------------------------------- ------------------------------
  GET      `/health`                       Application health
  POST     `/ingest`                       Load source CSV data
  GET      `/orders`                       List orders
  POST     `/orders/{order_id}/process`    Process one order
  POST     `/process-all`                  Process all orders
  GET      `/orders/{order_id}`            View order and audit history
  POST     `/orders/{order_id}/override`   Human review/override

------------------------------------------------------------------------

## Development

### Prerequisites

-   Python 3.10+
-   Access to the internal LLM API
-   Valid LLM API credentials
-   Company CA certificate if required by the internal HTTPS endpoint

### Project Structure

``` text
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
+-- certs/
|   +-- company CA certificate
|
+-- data/
|   +-- promo_merch_catalog.csv
|   +-- promo_merch_orders.csv
|   +-- alt_warehouse_inventory.csv
|
+-- orders.db
+-- .env
+-- .env.example
+-- .gitignore
+-- requirements.txt
+-- README.md
```

### Environment Setup

Create and activate a virtual environment:

``` powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install dependencies:

``` powershell
pip install -r requirements.txt
```

### Environment Configuration

Create `.env` in the project root.

Example:

``` env
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

### LLM Client Abstraction

The application uses an interface-based LLM design:

``` text
LLMClient
   |
   +-- MockLLMClient
   |
   +-- HttpLLMClient
```

The fulfillment workflow depends on `LLMClient`, rather than directly
depending on a specific provider.

The current HTTP client communicates with an OpenAI-compatible internal
endpoint:

``` text
POST {LLM_BASE_URL}/chat/completions
```

Current model:

``` text
gpt-oss-120b-ITG
```

### Certificate Configuration

For an internal HTTPS endpoint using a company CA:

``` env
LLM_SSL_VERIFY=true
LLM_CA_BUNDLE=C:\path\to\company-ca.crt
```

The application passes the CA bundle to the HTTP client for certificate
verification.

Do not use `verify=False` in the final configuration.

### Running Locally

``` powershell
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

Open:

``` text
http://127.0.0.1:8001/docs
```

### Fresh Database

To reset the local demo database:

``` powershell
Ctrl + C
Remove-Item .\orders.db
```

Restart the application:

``` powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

Then ingest the source data:

``` text
POST /ingest
```

### Development Workflow

``` text
1. Start FastAPI
        |
        v
2. Open Swagger
        |
        v
3. POST /ingest
        |
        v
4. Process an order
        |
        v
5. Inspect decision
        |
        v
6. Inspect audit trail
        |
        v
7. Perform human override when required
```

### Testing Scenarios

#### Low-risk auto dispatch

Expected:

``` text
READY_TO_DISPATCH
LOW
auto_dispatch_allowed = true
```

#### High-value order

Expected:

``` text
PENDING_REVIEW
HIGH
auto_dispatch_allowed = false
```

Then use the override endpoint.

#### Alternate warehouse

Use a product where:

``` text
primary_stock < requested_quantity <= alternate_stock
```

Expected:

``` text
ALTERNATE_REROUTE
```

#### Backorder

Use:

``` text
requested_quantity > primary_stock
AND
requested_quantity > alternate_stock
```

Expected:

``` text
BACKORDER
```

#### Unknown/ambiguous product

Expected:

``` text
NO_CATALOG_MATCH
```

or:

``` text
AMBIGUOUS_MATCH
```

Auto-dispatch must remain disabled.

------------------------------------------------------------------------

## Security and Configuration Guidelines

Never commit secrets or local runtime state.

Recommended `.gitignore` entries:

``` gitignore
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

If an API key is accidentally exposed, revoke or rotate it.

------------------------------------------------------------------------

## Design Decisions

### Why use an LLM?

Traditional string matching alone can struggle with natural-language
product descriptions and variations.

The LLM provides semantic interpretation while deterministic code
controls the actual fulfillment decision.

### Why not let the LLM choose the final SKU?

Fulfillment is a business-critical decision. The catalog is the source
of truth.

The LLM can interpret:

``` text
Custom Notebook - A5 Hardcover
```

but the deterministic reconciliation layer decides whether that maps to:

``` text
PRM-213
```

based on the catalog.

### Why deterministic inventory rules?

Inventory availability must be predictable and auditable.

The application explicitly checks:

``` text
Primary -> Alternate -> Backorder
```

rather than allowing the model to make an inventory decision.

### Why human review?

Orders can exceed configured risk limits or contain unresolved
catalog/inventory issues.

Human review provides a controlled escalation path without allowing the
reviewer to bypass physical inventory constraints.

### Why model/provider agnostic?

The agent uses an `LLMClient` abstraction.

Changing the underlying model or provider should not require rewriting
the catalog, inventory, policy, or audit logic.

------------------------------------------------------------------------

## Demo Checklist

Before a demonstration:

-   [ ] Start the correct FastAPI process and port
-   [ ] Open the current Swagger URL
-   [ ] Confirm `/health`
-   [ ] Reset the database if a clean run is required
-   [ ] Run `/ingest`
-   [ ] Verify LLM connectivity
-   [ ] Demonstrate low-risk auto dispatch
-   [ ] Demonstrate high-risk human review
-   [ ] Demonstrate alternate warehouse rerouting
-   [ ] Demonstrate backorder protection
-   [ ] Demonstrate unknown/ambiguous product handling
-   [ ] Show the audit trail
-   [ ] Remove temporary debug prints
-   [ ] Verify `.env` is not committed
-   [ ] Verify API credentials are not committed

------------------------------------------------------------------------

## Summary

The Marketing Souvenir Fulfillment Agent combines AI-powered language
understanding with deterministic fulfillment controls.

The system is designed around three principles:

1.  **Understand orders with AI.**
2.  **Validate fulfillment with deterministic business rules.**
3.  **Keep humans in control of high-risk or unresolved decisions.**

This creates an auditable and extensible fulfillment workflow that can
adapt to different LLM providers while keeping core business logic
stable.
