# OpenBox policy granularity

How many OpenBox policy rules does an agent need? One per control, not one per
tenant, document or amount. Most controls are a single condition on the tool
name; reach into a tool's input only when its value decides the outcome.

**Report:** [`OpenBox-Policy-Granularity.pdf`](OpenBox-Policy-Granularity.pdf).
The same content as a web page is in [`report/index.html`](report/index.html).

## Results (9 Oct 2026)

A LangGraph procurement agent with three tools (`read_document`,
`create_purchase_order`, `send_email`) makes the same 8 calls for 3 tenants
under three policy sets:

| Policy set | Rules | Calls stopped |
|---|---|---|
| No rules | 0 | 0 of 8 |
| Tool level: no outbound email | 1 | 2 of 8 |
| Tool + input level: also purchase orders over 500 | 2 | 4 of 8 |

The tool-level rule stopped both emails without naming a tenant or recipient.
The input-level rule split purchase orders on the amount: 499 ran, 501 was
stopped. The report also writes each control in both shapes (tool level and
input level) and runs the same calls against Microsoft's Agent Control
Specification for comparison.

## Layout

- `agent/procurement.py`: the agent and the 8 calls
- `policies.py`: the rule shapes used by each policy set
- `run_demo.py`: applies a policy set to the agent and runs it under OpenBox
- `scripts/create_agent.py`: registers the agent and writes `.env`
- `acs/`: the same calls through the Agent Control Specification runtime
- `capture/`, `screenshots/`: dashboard screenshots
- `report/`: the write-up and the PDF renderer

## Running it

```bash
uv sync
uv run python scripts/create_agent.py          # needs OPENBOX_ORG_API_KEY
uv run python run_demo.py --policy-set none
uv run python run_demo.py --policy-set tool-level
uv run python run_demo.py --policy-set tool-and-input
uv run --with agent-control-spec==0.4.0a4 python acs/run_acs.py
```

Each run writes `runs/<policy-set>.json` with every call's outcome.
