# Broad shape of "keep the agent out of Globex's documents": no document reads.
package procurement.read_tool

import rego.v1

default verdict := {"decision": "allow"}

verdict := {"decision": "deny", "reason": "no_document_reads"} if {
	input.tool.id == "read_document"
}
