"""Register the procurement agent in an OpenBox org.

    uv run python scripts/create_agent.py

Needs OPENBOX_BACKEND_URL and OPENBOX_ORG_API_KEY (an org key, obx_key_...),
read from the environment or from the file named by ORG_ENV_FILE (default
./.env). Writes the new agent's id, runtime key and workload private key to
./.env, which is gitignored. Safe to re-run: an existing PROCUREMENT_AGENT_ID
in ./.env is kept.
"""

from __future__ import annotations

import base64
import hashlib
import os
import sys
from pathlib import Path

import httpx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
ENV = ROOT / ".env"
AGENT_NAME = os.environ.get("PROCUREMENT_AGENT_NAME", "MultiTenantProcurementAgent")


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


def workload_keypair() -> tuple[str, dict[str, str]]:
    """RSA workload key: PKCS8 PEM kept by the agent, public JWK registered with OpenBox."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()
    numbers = key.public_key().public_numbers()
    jwk = {
        "kid": hashlib.sha256(numbers.n.to_bytes(256, "big")).hexdigest()[:32],
        "kty": "RSA",
        "alg": "RS256",
        "use": "sig",
        "n": _b64url(numbers.n.to_bytes((numbers.n.bit_length() + 7) // 8, "big")),
        "e": _b64url(numbers.e.to_bytes((numbers.e.bit_length() + 7) // 8, "big")),
    }
    return pem, jwk


def main() -> None:
    load_dotenv(ENV)
    load_dotenv(os.environ.get("ORG_ENV_FILE", ENV))
    if os.environ.get("PROCUREMENT_AGENT_ID"):
        print(f"keep {AGENT_NAME} {os.environ['PROCUREMENT_AGENT_ID']}")
        return
    base = os.environ.get("OPENBOX_BACKEND_URL", "http://localhost:3000").rstrip("/")
    client = httpx.Client(base_url=base, headers={"X-API-Key": os.environ["OPENBOX_ORG_API_KEY"]}, timeout=30)

    pem, jwk = workload_keypair()
    response = client.post(
        "/agent/create",
        json={
            "agent_name": AGENT_NAME,
            "agent_type": "langgraph",
            "description": "Procurement agent serving several enterprise tenants (policy granularity demo)",
            "attestation_mode": "kms",
            "identity_verification": {
                "method": "keycloak_workload",
                "mode": "generate",
                "source_type": "openbox",
                "public_jwk": jwk,
            },
            "icon": "https://api.iconify.design/carbon/shopping-cart.svg",
            "aivss_config": {
                "base_security": {"attack_vector": 1, "attack_complexity": 1, "privileges_required": 2,
                                  "user_interaction": 1, "scope": 1},
                "ai_specific": {"model_robustness": 2, "data_sensitivity": 2, "ethical_impact": 2,
                                "decision_criticality": 2, "adaptability": 2},
                "impact": {"confidentiality_impact": 2, "integrity_impact": 2, "availability_impact": 2,
                           "safety_impact": 1},
            },
            "tags": ["policy-granularity-demo"],
        },
    )
    if response.status_code >= 300:
        sys.exit(f"create failed: {response.status_code} {response.text[:300]}")
    body = response.json()
    result = body.get("data") or body.get("result") or body  # { status, data: { agent, token } }
    agent = result.get("agent", result)
    agent_id = agent.get("id") or agent.get("agent_id")
    runtime_key = result.get("token") or result.get("api_key") or ""
    values = {
        "OPENBOX_BACKEND_URL": base,
        "PROCUREMENT_AGENT_ID": agent_id,
        "PROCUREMENT_AGENT_NAME": AGENT_NAME,
        "PROCUREMENT_OPENBOX_" + "API_KEY": runtime_key,
        "PROCUREMENT_OPENBOX_WORKLOAD_PRIVATE_" + "KEY": '"' + pem.replace("\n", "\\n") + '"',
    }
    with ENV.open("a") as handle:
        handle.write("\n" + "".join(f"{name}={value}\n" for name, value in values.items()))
    print(f"created {AGENT_NAME} {agent_id}; credentials written to .env")


if __name__ == "__main__":
    main()
