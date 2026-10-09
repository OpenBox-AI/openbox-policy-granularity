# Broad shape of "stop large purchase orders": every purchase order.
package procurement.po_tool

import rego.v1

default verdict := {"decision": "allow"}

verdict := {"decision": "deny", "reason": "no_purchase_orders"} if {
	input.tool.id == "create_purchase_order"
}
