"""Evaluate the same 8 tool calls against Microsoft's Agent Control Specification (ACS).

    uv run --with agent-control-spec==0.4.0a4 python acs/run_acs.py

Each manifest in acs/ binds one Rego rule to the pre_tool_call point, the
same six rule shapes the OpenBox runs use (policies.py). Every call in
agent/procurement.py BASE_REQUESTS goes through ACS's own runtime in enforce
mode, and the verdicts are written to runs/acs.json.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from agent_control_spec import AcsInterceptor
from agent_hooks import AgentContextBuilder, EnforcementMode, InterceptionBlocked, InterceptionEmitter

ACS = Path(__file__).resolve().parent
ROOT = ACS.parent
sys.path.insert(0, str(ROOT / "agent"))

from procurement import BASE_REQUESTS  # noqa: E402

SHAPES = ["po_tool", "po_input", "email_tool", "email_input", "read_tool", "read_input"]
TOOL_FOR = {"po": "create_purchase_order", "email": "send_email", "read": "read_document"}


async def evaluate(shape: str) -> list[dict]:
    emitter = InterceptionEmitter(mode=EnforcementMode.ENFORCE)
    emitter.register(AcsInterceptor(str(ACS / f"{shape}.yaml")), shape)
    builder = AgentContextBuilder(agent_id="procurement", framework="langgraph", session_id=shape)
    results = []
    for step, request in enumerate(BASE_REQUESTS, 1):
        context = builder.pre_tool_call(call_id=f"call-{step}", name=request["tool"], args=request["args"])
        try:
            outcome = await emitter.emit(context)
            record, stopped = outcome.record, False
        except InterceptionBlocked as blocked:
            record, stopped = blocked.result, True
        emitter.take_records()
        results.append({
            "step": step,
            "tool": request["tool"],
            "args": request["args"],
            "decision": record.verdict.decision.value,
            "reason": getattr(record.verdict, "reason", None),
            "outcome": "stopped" if stopped else "executed",
        })
    return results


def main() -> None:
    summary = {}
    for shape in SHAPES:
        results = asyncio.run(evaluate(shape))
        tool = TOOL_FOR[shape.split("_")[0]]
        mine = [r for r in results if r["tool"] == tool]
        others_stopped = sum(r["outcome"] == "stopped" for r in results if r["tool"] != tool)
        summary[shape] = {"stopped": sum(r["outcome"] == "stopped" for r in mine), "of": len(mine),
                          "other_tools_stopped": others_stopped, "results": results}
        print(f"{shape:<12} {summary[shape]['stopped']} of {len(mine)} {tool} calls stopped"
              f"  (other tools stopped: {others_stopped})")
        for r in mine:
            arg = r["args"].get("amount", r["args"].get("to", r["args"].get("document_id")))
            print(f"    {r['args']['tenant']:<8} {str(arg):<30} {r['decision']:<6} {r['reason'] or ''}")
    out = ROOT / "runs" / "acs.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(summary, indent=2))
    print(f"written to {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
