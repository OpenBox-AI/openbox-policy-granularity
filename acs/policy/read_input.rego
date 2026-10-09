# Precise shape of "keep the agent out of Globex's documents": only Globex.
package procurement.read_input

import rego.v1

default verdict := {"decision": "allow"}

verdict := {"decision": "deny", "reason": "no_globex_documents"} if {
	input.tool.id == "read_document"
	input.policy_target.value.tenant == "globex"
}
