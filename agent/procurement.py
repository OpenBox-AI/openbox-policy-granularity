"""A small LangGraph procurement agent that serves several enterprise tenants.

The agent works through a fixed list of requests (build_requests), so every run makes exactly
the same tool calls with exactly the same inputs. Only the OpenBox policies on
the agent change between runs, which makes the effect of each policy visible.

Tools:
    read_document(tenant, document_id)
    create_purchase_order(tenant, vendor, amount, quantity)
    send_email(tenant, to, subject)

No model is involved: a scheduler node turns each request into a tool call.
"""

from __future__ import annotations

import json
from typing import Annotated, Any, TypedDict

from langchain_core.messages import AIMessage, AnyMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

# Three tenants, eight requests. Purchase orders straddle the 500 mark on purpose.
BASE_REQUESTS: list[dict[str, Any]] = [
    {"tool": "read_document", "args": {"tenant": "acme", "document_id": "acme/purchase-request-1001"}},
    {"tool": "create_purchase_order", "args": {"tenant": "acme", "vendor": "Staples", "amount": 120.0, "quantity": 10}},
    {"tool": "read_document", "args": {"tenant": "globex", "document_id": "globex/purchase-request-2001"}},
    {"tool": "create_purchase_order", "args": {"tenant": "globex", "vendor": "Dell", "amount": 2400.0, "quantity": 3}},
    {"tool": "create_purchase_order", "args": {"tenant": "initech", "vendor": "AWS", "amount": 499.0, "quantity": 1}},
    {"tool": "create_purchase_order", "args": {"tenant": "initech", "vendor": "AWS", "amount": 501.0, "quantity": 1}},
    {"tool": "send_email", "args": {"tenant": "acme", "to": "finance@acme.example", "subject": "PO 1001 raised"}},
    {"tool": "send_email", "args": {"tenant": "globex", "to": "sales@dell.example", "subject": "Quote request"}},
]

_EXTRA_AMOUNTS = [80.0, 650.0, 300.0, 1200.0]


def build_requests(extra_tenants: int = 0) -> list[dict[str, Any]]:
    """The three base tenants, plus any number of generated ones.

    Each generated tenant raises one purchase order (amounts cycle through
    80, 650, 300, 1200) and sends one email, so the policy count can be held
    against a growing number of tenants and calls.
    """
    requests = list(BASE_REQUESTS)
    for i in range(extra_tenants):
        tenant = f"tenant-{i + 1:03d}"
        requests.append({"tool": "create_purchase_order", "args": {
            "tenant": tenant, "vendor": "Grainger", "amount": _EXTRA_AMOUNTS[i % 4], "quantity": 2}})
        requests.append({"tool": "send_email", "args": {
            "tenant": tenant, "to": f"ops@{tenant}.example", "subject": "PO raised"}})
    return requests


_DOCUMENTS = {
    "acme/purchase-request-1001": "Purchase request: 10 boxes of printer paper from Staples, 120.00 USD.",
    "globex/purchase-request-2001": "Purchase request: 3 laptops from Dell, 2,400.00 USD.",
}


@tool
def read_document(tenant: str, document_id: str) -> str:
    """Read a stored document for one tenant."""
    return json.dumps({"document_id": document_id, "content": _DOCUMENTS.get(document_id, "")})


@tool
def create_purchase_order(tenant: str, vendor: str, amount: float, quantity: int) -> str:
    """Raise a purchase order with a vendor for one tenant."""
    return json.dumps({"tenant": tenant, "vendor": vendor, "amount": amount, "quantity": quantity, "status": "raised"})


@tool
def send_email(tenant: str, to: str, subject: str) -> str:
    """Send an email on behalf of one tenant."""
    return json.dumps({"to": to, "subject": subject, "status": "sent"})


TOOLS = [read_document, create_purchase_order, send_email]


class State(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    step: int
    results: list[dict[str, Any]]


def build_graph(requests: list[dict[str, Any]]):
    def schedule(state: State) -> dict:
        """Turn the next request into a tool call."""
        request = requests[state["step"]]
        call = {"name": request["tool"], "args": request["args"], "id": f"call-{state['step'] + 1}"}
        return {"messages": [AIMessage(content="", tool_calls=[call])]}

    def record(state: State) -> dict:
        """Store what happened to the call: executed, or stopped by OpenBox."""
        message = state["messages"][-1]
        assert isinstance(message, ToolMessage)
        request = requests[state["step"]]
        result = {
            "step": state["step"] + 1,
            "tool": request["tool"],
            "args": request["args"],
            "outcome": "stopped" if message.status == "error" else "executed",
            "detail": str(message.content)[:400],
        }
        return {"step": state["step"] + 1, "results": [*state.get("results", []), result]}

    def next_step(state: State) -> str:
        return "schedule" if state["step"] < len(requests) else END

    graph = StateGraph(State)
    graph.add_node("schedule", schedule)
    # A governance block surfaces as an error ToolMessage, and the agent carries on.
    graph.add_node("tools", ToolNode(TOOLS, handle_tool_errors=True))
    graph.add_node("record", record)
    graph.add_edge(START, "schedule")
    graph.add_edge("schedule", "tools")
    graph.add_edge("tools", "record")
    graph.add_conditional_edges("record", next_step, ["schedule", END])
    return graph.compile()


def initial_state() -> State:
    return {"messages": [], "step": 0, "results": []}
