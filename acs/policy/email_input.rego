# Precise shape of "keep email inside the tenant": the recipient must contain the tenant.
package procurement.email_input

import rego.v1

default verdict := {"decision": "allow"}

verdict := {"decision": "deny", "reason": "email_outside_tenant"} if {
	input.tool.id == "send_email"
	not contains(input.policy_target.value.to, input.policy_target.value.tenant)
}
