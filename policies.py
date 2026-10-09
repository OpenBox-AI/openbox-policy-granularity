"""The policy rules in this demo, and the policy sets the runs use.

Two kinds of rule:

    tool level    one condition on the tool name (activity_type). Matches every
                  call to that tool, whatever the tenant, recipient or other inputs.
    input level   the tool name plus a condition on one input field
                  (activity_input[0].<field>). Use it only when a value decides
                  the outcome, such as an amount over a limit.

OpenBox rules need at least one condition; a call that matches no rule is allowed.
"""

from __future__ import annotations


def _field(path: str, value_type: str = "string") -> dict:
    return {"kind": "field", "field": path, "transform": "value", "valueType": value_type}


def _literal(value: str, value_type: str = "string") -> dict:
    return {"kind": "literal", "value": value, "valueType": value_type}


def _tool_is(tool: str) -> dict:
    return {"id": "tool", "left": _field("activity_type"), "operator": "equals", "right": _literal(tool)}


RULES: dict[str, dict] = {
    # Tool level: no inputs referenced.
    "No outbound email": {
        "rule_name": "No outbound email",
        "description": "Tool-level rule: the agent may not send email, for any tenant or recipient.",
        "priority": 50,
        "match_mode": "all",
        "conditions": [_tool_is("send_email")],
        "decision": "BLOCK",
        "reason": "This agent is not allowed to send email.",
        "constraints": [],
    },
    # Input level: the amount decides.
    "Purchase orders over 500": {
        "rule_name": "Purchase orders over 500",
        "description": "Input-level rule: purchase orders above 500 are stopped; smaller ones go through.",
        "priority": 60,
        "match_mode": "all",
        "conditions": [
            _tool_is("create_purchase_order"),
            {"id": "amount", "left": _field("activity_input[0].amount", "number"),
             "operator": "greater_than", "right": _literal("500", "number")},
        ],
        "decision": "BLOCK",
        "reason": "Purchase orders above 500 need a person to raise them.",
        "constraints": [],
    },
}

# Same intent, two shapes: a broad tool-level rule and a precise input-level rule.
RULES.update({
    "No purchase orders": {
        "rule_name": "No purchase orders",
        "description": "Tool-level shape of 'stop large purchase orders': stops every purchase order.",
        "priority": 40,
        "match_mode": "all",
        "conditions": [_tool_is("create_purchase_order")],
        "decision": "BLOCK",
        "reason": "This agent may not raise purchase orders.",
        "constraints": [],
    },
    "Email only inside the tenant": {
        "rule_name": "Email only inside the tenant",
        "description": "Input-level shape of 'keep email inside the tenant': stops email whose recipient "
                       "does not contain the tenant's name. One rule for every tenant.",
        "priority": 55,
        "match_mode": "all",
        "conditions": [
            _tool_is("send_email"),
            {"id": "recipient", "left": _field("activity_input[0].to"), "operator": "not_contains",
             "right": _field("activity_input[0].tenant")},
        ],
        "decision": "BLOCK",
        "reason": "Email may only go to the tenant's own domain.",
        "constraints": [],
    },
    "No document reads": {
        "rule_name": "No document reads",
        "description": "Tool-level shape of 'keep the agent out of Globex documents': stops every read.",
        "priority": 30,
        "match_mode": "all",
        "conditions": [_tool_is("read_document")],
        "decision": "BLOCK",
        "reason": "This agent may not read documents.",
        "constraints": [],
    },
    "No Globex documents": {
        "rule_name": "No Globex documents",
        "description": "Input-level shape of 'keep the agent out of Globex documents': stops reads for one tenant.",
        "priority": 35,
        "match_mode": "all",
        "conditions": [
            _tool_is("read_document"),
            {"id": "tenant", "left": _field("activity_input[0].tenant"), "operator": "equals",
             "right": _literal("globex")},
        ],
        "decision": "BLOCK",
        "reason": "This agent may not read Globex documents.",
        "constraints": [],
    },
})

POLICY_SETS: dict[str, list[str]] = {
    "none": [],
    "tool-level": ["No outbound email"],
    "tool-and-input": ["No outbound email", "Purchase orders over 500"],
    # One rule each, for the same-intent-two-shapes comparison.
    "po-tool": ["No purchase orders"],
    "po-input": ["Purchase orders over 500"],
    "email-tool": ["No outbound email"],
    "email-input": ["Email only inside the tenant"],
    "read-tool": ["No document reads"],
    "read-input": ["No Globex documents"],
}

# Inputs for each rule's dry-run on OpenBox's /evaluate before it is activated.
TESTS: dict[str, list[tuple[dict, str]]] = {
    "No outbound email": [
        ({"activity_type": "send_email", "activity_input": [{"tenant": "any", "to": "x@y.example"}]}, "BLOCK"),
        ({"activity_type": "read_document", "activity_input": [{"tenant": "any"}]}, "ALLOW"),
    ],
    "No purchase orders": [
        ({"activity_type": "create_purchase_order", "activity_input": [{"amount": 120}]}, "BLOCK"),
        ({"activity_type": "send_email", "activity_input": [{"to": "a@b.example"}]}, "ALLOW"),
    ],
    "Email only inside the tenant": [
        ({"activity_type": "send_email", "activity_input": [{"tenant": "acme", "to": "finance@acme.example"}]}, "ALLOW"),
        ({"activity_type": "send_email", "activity_input": [{"tenant": "globex", "to": "sales@dell.example"}]}, "BLOCK"),
    ],
    "No document reads": [
        ({"activity_type": "read_document", "activity_input": [{"tenant": "acme"}]}, "BLOCK"),
        ({"activity_type": "send_email", "activity_input": [{"tenant": "acme"}]}, "ALLOW"),
    ],
    "No Globex documents": [
        ({"activity_type": "read_document", "activity_input": [{"tenant": "globex"}]}, "BLOCK"),
        ({"activity_type": "read_document", "activity_input": [{"tenant": "acme"}]}, "ALLOW"),
    ],
    "Purchase orders over 500": [
        ({"activity_type": "create_purchase_order", "activity_input": [{"amount": 501}]}, "BLOCK"),
        ({"activity_type": "create_purchase_order", "activity_input": [{"amount": 499}]}, "ALLOW"),
        ({"activity_type": "create_purchase_order", "activity_input": [{"amount": 500}]}, "ALLOW"),
    ],
}
