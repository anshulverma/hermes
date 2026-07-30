"""Dependency-free JSON schema subset validator and envelope layering.

Supports type, required, properties, additionalProperties:false, enum, items.
Raises ContractError on first violation with a JSON path.
"""
import hashlib
import json


def payload_sha256(payload) -> str:
    """SHA-256 hex digest of a payload's canonical JSON encoding.

    Canonical = sorted keys, no whitespace (``separators=(",", ":")``). This is
    the single source of truth used by the transport (which STAMPS the digest
    into the envelope) and the agent adapters (which RECOMPUTE it over the
    received payload and flag ``contract_fail`` on mismatch).
    """
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class ContractError(Exception):
    """Contract validation error carrying JSON path and detail."""

    def __init__(self, path: str, detail: str):
        self.path = path
        self.detail = detail
        super().__init__(f"{path}: {detail}")


def validate(instance, schema, path="$"):
    """Validate instance against a JSON schema subset.

    Args:
        instance: The document to validate
        schema: The schema dict (subset: type, required, properties,
                additionalProperties, enum, items)
        path: Current JSON path (for error reporting)

    Raises:
        ContractError: On first validation failure with JSON path
    """
    # Check type
    if "type" in schema:
        expected_type = schema["type"]

        # Handle union types like ["string", "null"]
        if isinstance(expected_type, list):
            if not _matches_any_type(instance, expected_type):
                type_names = ", ".join(expected_type)
                raise ContractError(
                    path,
                    f"Expected one of [{type_names}], got {_type_name(instance)}"
                )
        else:
            if not _matches_type(instance, expected_type):
                raise ContractError(
                    path,
                    f"Expected {expected_type}, got {_type_name(instance)}"
                )

    # Check enum
    if "enum" in schema:
        if instance not in schema["enum"]:
            raise ContractError(
                path,
                f"Value {instance!r} not in enum {schema['enum']}"
            )

    # For objects: check required, properties, additionalProperties
    if isinstance(instance, dict):
        # Check required keys
        if "required" in schema:
            for key in schema["required"]:
                if key not in instance:
                    raise ContractError(
                        path,
                        f"Required key '{key}' is missing"
                    )

        # Check properties recursively
        if "properties" in schema:
            for key, sub_schema in schema["properties"].items():
                if key in instance:
                    validate(instance[key], sub_schema, f"{path}.{key}")

        # Check additionalProperties
        if schema.get("additionalProperties") is False:
            allowed_keys = set(schema.get("properties", {}).keys())
            actual_keys = set(instance.keys())
            extra_keys = actual_keys - allowed_keys
            if extra_keys:
                extra = next(iter(extra_keys))  # First extra key
                raise ContractError(
                    path,
                    f"Additional property '{extra}' not allowed"
                )

    # For arrays: check items
    if isinstance(instance, list):
        if "items" in schema:
            item_schema = schema["items"]
            for i, item in enumerate(instance):
                validate(item, item_schema, f"{path}[{i}]")


def _matches_type(value, type_name: str) -> bool:
    """Check if value matches a single JSON schema type."""
    if type_name == "null":
        return value is None
    elif type_name == "boolean":
        return isinstance(value, bool)
    elif type_name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    elif type_name == "string":
        return isinstance(value, str)
    elif type_name == "array":
        return isinstance(value, list)
    elif type_name == "object":
        return isinstance(value, dict)
    else:
        return False


def _matches_any_type(value, type_names: list) -> bool:
    """Check if value matches any of the types in the list."""
    return any(_matches_type(value, tn) for tn in type_names)


def _type_name(value) -> str:
    """Get JSON schema type name for a Python value."""
    if value is None:
        return "null"
    elif isinstance(value, bool):
        return "boolean"
    elif isinstance(value, int) or isinstance(value, float):
        return "number"
    elif isinstance(value, str):
        return "string"
    elif isinstance(value, list):
        return "array"
    elif isinstance(value, dict):
        return "object"
    else:
        return type(value).__name__


# Schema definitions per

# GOAL_ENVELOPE is the single source of truth for the goal envelope schema.
# DISPATCH_ENVELOPE references it rather than duplicating (future extension).
GOAL_ENVELOPE = {
    "type": "object",
    "required": ["goal", "driver", "done_contract", "guardrails"],
    "properties": {
        "goal": {"type": "string"},
        "driver": {
            "type": "object",
            "required": ["command", "args", "loop"],
            "properties": {
                "command": {"type": ["string", "null"]},
                "args": {"type": "object"},
                "loop": {"type": ["string", "null"]},
            },
            "additionalProperties": False,
        },
        "done_contract": {"type": "object"},
        "guardrails": {
            "type": "object",
            "required": ["no_ship"],
            "properties": {
                "no_ship": {"type": "boolean"},
            },
        },
    },
    "additionalProperties": False,
}

DISPATCH_ENVELOPE = {
    "type": "object",
    "required": [
        "ticket_id", "run_id", "phase", "resource_req", "base_ref",
        "payload", "payload_sha256", "timeout_s", "site_context",
        "goal_envelope"
    ],
    "properties": {
        "ticket_id": {"type": "string"},
        "run_id": {"type": "string"},
        "phase": {"type": "string"},
        "resource_req": {"type": "string"},
        "base_ref": {"type": "string"},
        "payload": {"type": "object"},
        "payload_sha256": {"type": "string"},
        "timeout_s": {"type": "number"},
        "site_context": {"type": "object"},
        "goal_envelope": GOAL_ENVELOPE,  # Reference, not inline copy (future extension)
    },
    "additionalProperties": False,
}

RESULT_OUTER = {
    "type": "object",
    "required": [
        "outcome", "termination_reason", "result_ref", "evidence_ref",
        "started_at", "ended_at", "error_summary", "payload"
    ],
    "properties": {
        "outcome": {
            "type": "string",
            "enum": ["ok", "driver_failed", "infra_failed"],
        },
        "termination_reason": {
            "type": "string",
            "enum": [
                "goal_met", "contract_fail", "driver_error",
                "timeout", "transport_error"
            ],
        },
        "result_ref": {"type": ["string", "null"]},
        "evidence_ref": {"type": ["string", "null"]},
        "started_at": {"type": "number"},
        "ended_at": {"type": "number"},
        "error_summary": {"type": ["string", "null"]},
        "detail": {"type": ["string", "null"]},
        "payload": {"type": "object"},
    },
    "additionalProperties": False,
}


def validate_envelope(envelope: dict, payload_schema: dict):
    """Validate a dispatch envelope including playbook payload.

    Args:
        envelope: The dispatch envelope dict
        payload_schema: The playbook's payload_schema for this phase

    Raises:
        ContractError: On validation failure
    """
    # Validate outer envelope shape
    validate(envelope, DISPATCH_ENVELOPE)

    # Validate payload against playbook schema
    validate(envelope["payload"], payload_schema, "$.payload")


def validate_result(result: dict, result_schema: dict):
    """Validate a Result including playbook result payload.

    Args:
        result: The result dict
        result_schema: The playbook's result_schema for this phase

    Raises:
        ContractError: On validation failure

    Notes:
        The payload sub-doc is validated against result_schema only when
        outcome == "ok". Driver/infra failures skip payload validation.
    """
    # Validate outer result shape
    validate(result, RESULT_OUTER)

    # Validate payload only when outcome == "ok"
    if result["outcome"] == "ok":
        validate(result["payload"], result_schema, "$.payload")
