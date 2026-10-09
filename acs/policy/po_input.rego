# Precise shape of "stop large purchase orders": only amounts over 500.
package procurement.po_input

import rego.v1

default verdict := {"decision": "allow"}

verdict := {"decision": "deny", "reason": "purchase_order_over_500"} if {
	input.tool.id == "create_purchase_order"
	input.policy_target.value.amount > 500
}
