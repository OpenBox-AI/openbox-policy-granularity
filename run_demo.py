"""Apply one policy set to the procurement agent, then run the agent under OpenBox.

    uv run python run_demo.py --policy-set none
    uv run python run_demo.py --policy-set tool-level
    uv run python run_demo.py --policy-set tool-and-input
    uv run python run_demo.py --policy-set tool-and-input --extra-tenants 20

Rules in the chosen set are created (or re-activated) on the agent and dry-run
with OpenBox's /evaluate first; rules outside the set are deactivated. The run
waits for OPA to load the new bundle, executes every request, and writes
runs/<policy-set>[-<n>t].json with each call's outcome.

Reads ./.env (written by scripts/create_agent.py). The org key for managing
rules comes from OPENBOX_ORG_API_KEY, here or in the file named by ORG_ENV_FILE.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
import uuid
from collections import Counter
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "agent"))

from policies import POLICY_SETS, RULES, TESTS  # noqa: E402
from procurement import build_graph, build_requests, initial_state  # noqa: E402

OPA_URL = os.environ.get("OPA_URL", "http://localhost:8181").rstrip("/")
OPA_SETTLE_SECONDS = int(os.environ.get("OPA_SETTLE_SECONDS", "90"))


def _unwrap(body):
    return body.get("data", body) if isinstance(body, dict) else body


def apply_policy_set(name: str) -> list[dict]:
    """Make exactly the rules in the set active on the agent. Returns them."""
    base_url = os.environ.get("OPENBOX_BACKEND_URL", "http://localhost:3000").rstrip("/")
    agent_id = os.environ["PROCUREMENT_AGENT_ID"]
    client = httpx.Client(base_url=base_url, headers={"X-API-Key": os.environ["OPENBOX_ORG_API_KEY"]}, timeout=30)
    path = f"/agent/{agent_id}/policy-rule"

    page = _unwrap(client.get(path, params={"limit": 200}).raise_for_status().json())
    current = {r["rule_name"]: r for r in (page.get("data", page) if isinstance(page, dict) else page)
               if r.get("is_current_version", True)}
    wanted = POLICY_SETS[name]
    active = []
    for rule_name, payload in RULES.items():
        existing = current.get(rule_name)
        if rule_name not in wanted:
            if existing and existing.get("is_active"):
                client.put(f"{path}/{existing['id']}/status", json={"is_active": False}).raise_for_status()
                print(f"  deactivated  {rule_name}")
            continue
        if existing is None:
            existing = _unwrap(client.post(path, json={**payload, "is_active": False}).raise_for_status().json())
            print(f"  created      {rule_name}")
        for test_input, expect in TESTS[rule_name]:
            result = _unwrap(client.post(f"{path}/{existing['id']}/evaluate", json={
                "input": {"event_type": "ActivityStarted", "agent_id": agent_id, **test_input}}).raise_for_status().json())
            got = (result.get("result", result) or {}).get("decision") or result.get("decision")
            if got != expect:
                sys.exit(f"dry-run of '{rule_name}' on {test_input} gave {got}, expected {expect}")
        if not existing.get("is_active"):
            client.put(f"{path}/{existing['id']}/status", json={"is_active": True}).raise_for_status()
        print(f"  active       {rule_name}  (dry-run passed: {len(TESTS[rule_name])} cases)")
        active.append(payload)
    return active


def wait_for_opa(policy_set: str) -> None:
    """Wait until OPA answers every test input the way the policy set says it should.

    Rule changes reach OPA through an org bundle that is rebuilt asynchronously
    and polled, which can take a minute. Querying OPA directly avoids running
    against the previous rule set. Without a reachable OPA (a hosted
    environment), wait OPA_SETTLE_SECONDS instead.
    """
    agent = os.environ["PROCUREMENT_AGENT_ID"].replace("-", "")
    active = POLICY_SETS[policy_set]
    expected = [(i, d) for name in active for i, d in TESTS[name]]
    try:
        policies = httpx.get(f"{OPA_URL}/v1/policies", timeout=5).json()["result"]
    except (httpx.HTTPError, KeyError, ValueError):
        print(f"OPA not reachable at {OPA_URL}; waiting {OPA_SETTLE_SECONDS}s for the bundle ...")
        time.sleep(OPA_SETTLE_SECONDS)
        return
    started = time.time()
    while time.time() - started < 300:
        policies = httpx.get(f"{OPA_URL}/v1/policies", timeout=5).json()["result"]
        module = next((m for m in policies if f"agent_{agent}" in m["id"]), None)
        if module:
            package = module["raw"].split("\n", 1)[0].removeprefix("package ").strip()
            url = f"{OPA_URL}/v1/data/{package.replace('.', '/')}/result"
            names_ok = all(f'"rule_name": "{n}"' in module["raw"] for n in active) and not any(
                f'"rule_name": "{n}"' in module["raw"] for n in RULES if n not in active)
            got = [httpx.post(url, json={"input": {"event_type": "ActivityStarted", **i}}, timeout=5)
                   .json().get("result", {}).get("decision") for i, _ in expected]
            if names_ok and got == [d for _, d in expected]:
                print(f"OPA has the new rules ({time.time() - started:.0f}s)")
                return
        time.sleep(3)
    sys.exit("OPA did not pick up the policy set within 5 minutes")


async def run(requests: list[dict], session_id: str) -> list[dict]:
    from openbox_langgraph import create_openbox_graph_handler

    governed = create_openbox_graph_handler(
        graph=build_graph(requests),
        api_url=os.environ.get("OPENBOX_API_URL", "http://localhost:8086"),
        api_key=os.environ["PROCUREMENT_OPENBOX_" + "API_KEY"],
        agent_name=os.environ.get("PROCUREMENT_AGENT_NAME", "MultiTenantProcurementAgent"),
        workload_private_key=os.environ.get("PROCUREMENT_OPENBOX_WORKLOAD_PRIVATE_KEY") or None,
        session_id=session_id,
        task_queue="policy-granularity",
        on_api_error="fail_closed",
        tool_type_map={"read_document": "builtin", "create_purchase_order": "builtin", "send_email": "builtin"},
        send_tool_start_event=True,
        send_tool_end_event=True,
    )
    state = await governed.ainvoke(
        initial_state(),
        config={"configurable": {"thread_id": session_id}, "recursion_limit": 10 * len(requests) + 10},
    )
    return state["results"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--policy-set", choices=sorted(POLICY_SETS), required=True)
    parser.add_argument("--extra-tenants", type=int, default=0)
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    if os.environ.get("ORG_ENV_FILE"):
        load_dotenv(os.environ["ORG_ENV_FILE"])

    print(f"policy set: {args.policy_set}")
    rules = apply_policy_set(args.policy_set)
    wait_for_opa(args.policy_set)

    requests = build_requests(args.extra_tenants)
    session_id = f"{args.policy_set}-{len(requests)}calls-{uuid.uuid4().hex[:6]}"
    started = time.time()
    results = asyncio.run(run(requests, session_id))

    tenants = sorted({r["args"]["tenant"] for r in results})
    outcome = Counter((r["tool"], r["outcome"]) for r in results)
    summary = {
        "policy_set": args.policy_set,
        "rules": len(rules),
        "rule_names": [r["rule_name"] for r in rules],
        "tenants": len(tenants),
        "calls": len(results),
        "stopped": sum(r["outcome"] == "stopped" for r in results),
        "by_tool": {f"{tool} {status}": n for (tool, status), n in sorted(outcome.items())},
        "session_id": session_id,
        "seconds": round(time.time() - started, 1),
        "results": results,
    }
    suffix = f"-{len(tenants)}t" if args.extra_tenants else ""
    out = ROOT / "runs" / f"{args.policy_set}{suffix}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(summary, indent=2))

    for r in results:
        arg = r["args"].get("amount", r["args"].get("to", r["args"].get("document_id")))
        print(f"  {r['step']:>3}  {r['args']['tenant']:<11} {r['tool']:<22} {str(arg):<28} {r['outcome']}")
    print(f"{summary['rules']} rules · {summary['tenants']} tenants · {summary['calls']} calls · "
          f"{summary['stopped']} stopped · written to {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
