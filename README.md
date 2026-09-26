# Marketing-Souvenir Goods Bulk-Order Execution & Reliability

## 1. Challenge requirement

Build an agentic application for a promotional-products fulfillment business.

The application must:

1. Ingest:
   - `promo_merch_catalog.csv`
   - `promo_merch_orders.csv`
   - `alt_warehouse_inventory.csv`
2. Use an in-house LLM to interpret each order line, including ambiguous product descriptions.
3. Reconcile each line against the catalog.
4. Check primary inventory through a tool.
5. Decide how each line should be fulfilled.
6. Handle back-orders safely.
7. Auto-dispatch only low-risk orders.
8. If a line is out of stock in the primary warehouse, independently check the alternate warehouse and reroute that line when possible.
9. Persist orders, reconciliation decisions, dispatch/reroute actions, and human overrides.
10. Provide a human-review path where an operator can inspect the decision trace and override it.

## 2. Low-risk assumption

The brief does not define an exact low-risk policy. This implementation uses a conservative configurable policy.

An order can be auto-dispatched only when:

- client type is `one-time order`;
- every line has a clear catalog match;
- reconciliation confidence is at least the configured threshold;
- every line can be fulfilled;
- primary warehouse has enough stock for every line;
- no alternate-warehouse reroute is required;
- no back-order is required;
- estimated order value is below `AUTO_DISPATCH_MAX_TOTAL`.

Anything else becomes `PENDING_REVIEW`.

This assumption should be replaced with the exact business rule if the judges provide one.

## 3. Architecture

```text
CSV files
   |
   v
Ingestion Service
   |
   v
SQLite / SQLAlchemy
   |
   v
Agent Orchestrator
   |
   +--> LLM interpretation
   |
   +--> Catalog reconciliation tool
   |
   +--> Primary inventory tool
   |       |
   |       +--> enough --> primary fulfillment
   |       |
   |       +--> not enough --> alternate inventory tool
   |                              |
   |                              +--> enough --> line reroute
   |                              |
   |                              +--> not enough --> back-order
   |
   v
Risk / Policy Engine
   |
   +--> LOW RISK --> dispatch tool
   |
   +--> REVIEW --> human override
   |
   v
Audit / Decision Trace
```

The LLM is not allowed to directly modify inventory or dispatch an order. Business actions are deterministic tool calls behind policy checks.

## 4. Why this is agentic

This is intentionally not one giant LLM call.

For each order the agent performs multiple steps:

1. Interpret the line item.
2. Reconcile it against the catalog.
3. Check primary stock.
4. If needed, check alternate stock.
5. Decide primary fulfillment, alternate reroute, back-order, or review.
6. Apply the risk policy.
7. Dispatch only if policy allows.
8. Persist each significant event.

The decision trace is available to a human reviewer.

## 5. Model/provider agnostic design

`app/llm.py` contains an `LLMClient` interface.

Two implementations are included:

- `MockLLMClient`: deterministic local development/demo mode.
- `HttpLLMClient`: generic HTTP adapter for an in-house LLM endpoint.

The rest of the application does not depend on a particular LLM vendor.

For the actual hackathon, change only the HTTP adapter if the internal LLM has a different request/response contract.

## 6. Project structure

```text
marketing_souvenir_agent/
├── app/
│   ├── __init__.py
│   ├── agent.py
│   ├── config.py
│   ├── db.py
│   ├── llm.py
│   ├── main.py
│   ├── models.py
│   ├── policy.py
│   ├── reconciler.py
│   ├── schemas.py
│   ├── service.py
│   └── tools.py
├── data/
│   ├── promo_merch_catalog.csv
│   ├── promo_merch_orders.csv
│   └── alt_warehouse_inventory.csv
├── tests/
│   └── test_core.py
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md
```

## 7. Required libraries

Only these are required for this implementation:

- `fastapi` - REST API and Swagger UI
- `uvicorn` - run FastAPI
- `pandas` - CSV/data processing support
- `SQLAlchemy` - database persistence
- `pydantic` - validated request/domain objects
- `python-dotenv` - environment configuration
- `requests` - call the in-house LLM endpoint

`scikit-learn`, `numpy`, `matplotlib`, and `seaborn` are NOT required for this architecture because this challenge is centered on an LLM-powered agent and deterministic fulfillment tools, not a traditional trained classifier.

## 8. Setup on Windows

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

If PowerShell blocks activation:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

Then activate again.

## 9. Run

```powershell
uvicorn app.main:app --reload
```

Open:

```text
http://127.0.0.1:8000/docs
```

Swagger gives a simple UI for the hackathon demo.

## 10. API

### Health

`GET /health`

### Ingest CSVs

`POST /ingest`

### Process one order

`POST /orders/{order_id}/process`

Example:

`POST /orders/ORD-7002/process`

### Process all orders

`POST /process-all`

### List orders

`GET /orders`

### View order + decision trace

`GET /orders/{order_id}`

### Human override

`POST /orders/{order_id}/override`

Body:

```json
{
  "decision": "APPROVE",
  "reason": "Reviewed the ambiguous item and approved fulfillment."
}
```

## 11. LLM integration

Development:

```env
LLM_MODE=mock
```

Real internal LLM:

```env
LLM_MODE=http
LLM_BASE_URL=http://<internal-endpoint>
LLM_API_KEY=<optional-key>
LLM_MODEL=<model-name>
```

The included HTTP adapter expects:

`POST <LLM_BASE_URL>/interpret-line`

Example request:

```json
{
  "model": "in-house-model",
  "line_text": "4x Polo Shirt - White",
  "catalog_candidates": ["Polo Shirt - Navy", "Polo Shirt - White"],
  "instruction": "Interpret one promotional merchandise line. Return JSON with quantity, sku if known, confidence, and reason. Never invent a SKU."
}
```

Expected response:

```json
{
  "quantity": 4,
  "sku": "PRM-203",
  "confidence": 0.98,
  "reason": "Direct catalog match."
}
```

If your in-house endpoint has another contract, adapt only `HttpLLMClient.interpret_line()`.

## 12. Edge cases

The code explicitly considers:

- empty order description;
- malformed line;
- zero/negative quantity;
- unknown product;
- exact catalog match;
- punctuation/case variation;
- fuzzy match;
- ambiguous match;
- multiple line items;
- primary stock = 0;
- primary stock < requested quantity;
- alternate stock = 0;
- alternate stock < requested quantity;
- negative alternate stock;
- back-order;
- low-confidence interpretation;
- LLM failure;
- malformed LLM response;
- duplicate ingestion;
- already-dispatched order;
- dispatch failure;
- human override;
- audit trace.

## 13. Demo scenarios

### A. Low-risk primary fulfillment

Expected:

```text
LLM_INTERPRETATION
CATALOG_RECONCILIATION
PRIMARY_INVENTORY_CHECK
POLICY_DECISION
DISPATCH
AGENT_FINISHED
```

### B. Primary unavailable, alternate available

Expected:

```text
PRIMARY_INVENTORY_CHECK -> unavailable
ALTERNATE_INVENTORY_CHECK -> available
ALTERNATE_REROUTE -> review/fulfillment decision
```

### C. Neither warehouse can fulfill

Expected:

```text
BACKORDER -> PENDING_REVIEW
```

No automatic dispatch.

### D. Ambiguous item

Expected:

```text
AMBIGUOUS_MATCH -> PENDING_REVIEW
```

No automatic dispatch.

## 14. Production improvements

For production:

- PostgreSQL instead of SQLite.
- Transactional inventory reservation.
- Idempotency keys for dispatch.
- Authentication/RBAC for overrides.
- Queue-based fulfillment.
- Structured LLM output/function calling.
- Retry/circuit breaker around LLM.
- Inventory concurrency control.
- Better observability.
- Evaluation dataset for reconciliation accuracy.
- Human feedback loop.
"# marketing_souvenir_agent_project" 
