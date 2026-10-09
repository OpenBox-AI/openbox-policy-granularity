# Broad shape of "keep email inside the tenant": no email at all.
package procurement.email_tool

import rego.v1

default verdict := {"decision": "allow"}

verdict := {"decision": "deny", "reason": "no_outbound_email"} if {
	input.tool.id == "send_email"
}
