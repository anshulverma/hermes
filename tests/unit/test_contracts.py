"""Tests for the dependency-free contract validator.

TDD: write these FIRST, watch them fail for the expected reason,
then implement engine/contracts.py minimally.
"""
import pytest


def test_validate_accepts_valid_simple_object():
    """Validator accepts a valid simple object."""
    from engine.contracts import validate

    schema = {
        "type": "object",
        "required": ["name", "count"],
        "properties": {
            "name": {"type": "string"},
            "count": {"type": "number"},
        },
        "additionalProperties": False,
    }

    doc = {"name": "test", "count": 42}
    # Should not raise
    validate(doc, schema)


def test_validate_rejects_wrong_type():
    """Validator rejects wrong type with correct JSON path."""
    from engine.contracts import validate, ContractError

    schema = {
        "type": "object",
        "required": ["value"],
        "properties": {"value": {"type": "number"}},
    }

    doc = {"value": "not-a-number"}

    with pytest.raises(ContractError) as exc_info:
        validate(doc, schema)

    err = exc_info.value
    assert err.path == "$.value"
    assert "type" in str(err).lower() or "number" in str(err).lower()


def test_validate_rejects_missing_required_key():
    """Validator rejects missing required key."""
    from engine.contracts import validate, ContractError

    schema = {
        "type": "object",
        "required": ["name", "age"],
        "properties": {
            "name": {"type": "string"},
            "age": {"type": "number"},
        },
    }

    doc = {"name": "Alice"}

    with pytest.raises(ContractError) as exc_info:
        validate(doc, schema)

    err = exc_info.value
    assert "age" in str(err).lower()
    assert "required" in str(err).lower()


def test_validate_rejects_unexpected_key_when_additional_properties_false():
    """Validator rejects unexpected key when additionalProperties:false."""
    from engine.contracts import validate, ContractError

    schema = {
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "additionalProperties": False,
    }

    doc = {"name": "test", "extra": "field"}

    with pytest.raises(ContractError) as exc_info:
        validate(doc, schema)

    err = exc_info.value
    assert "extra" in str(err).lower() or "additional" in str(err).lower()


def test_validate_rejects_value_not_in_enum():
    """Validator rejects value not in enum."""
    from engine.contracts import validate, ContractError

    schema = {
        "type": "object",
        "required": ["state"],
        "properties": {
            "state": {"type": "string", "enum": ["ok", "failed"]},
        },
    }

    doc = {"state": "unknown"}

    with pytest.raises(ContractError) as exc_info:
        validate(doc, schema)

    err = exc_info.value
    assert err.path == "$.state"
    assert "enum" in str(err).lower()


def test_validate_rejects_bad_array_element():
    """Validator rejects bad element inside items."""
    from engine.contracts import validate, ContractError

    schema = {
        "type": "object",
        "required": ["tags"],
        "properties": {
            "tags": {
                "type": "array",
                "items": {"type": "string"},
            },
        },
    }

    doc = {"tags": ["valid", 123, "also-valid"]}

    with pytest.raises(ContractError) as exc_info:
        validate(doc, schema)

    err = exc_info.value
    assert "$.tags[1]" in err.path


def test_validate_supports_nullable_union():
    """Validator supports nullable unions like ['string', 'null']."""
    from engine.contracts import validate

    schema = {
        "type": "object",
        "required": ["maybe"],
        "properties": {
            "maybe": {"type": ["string", "null"]},
        },
    }

    # Should accept string
    validate({"maybe": "value"}, schema)

    # Should accept null
    validate({"maybe": None}, schema)


def test_validate_rejects_nullable_union_wrong_type():
    """Validator rejects wrong type in nullable union."""
    from engine.contracts import validate, ContractError

    schema = {
        "type": "object",
        "properties": {
            "maybe": {"type": ["string", "null"]},
        },
    }

    doc = {"maybe": 123}

    with pytest.raises(ContractError):
        validate(doc, schema)


def test_validate_nested_object_builds_correct_path():
    """Validator builds correct JSON path for nested objects."""
    from engine.contracts import validate, ContractError

    schema = {
        "type": "object",
        "required": ["goal_envelope"],
        "properties": {
            "goal_envelope": {
                "type": "object",
                "required": ["driver"],
                "properties": {
                    "driver": {
                        "type": "object",
                        "required": ["command"],
                        "properties": {
                            "command": {"type": ["string", "null"]},
                        },
                    },
                },
            },
        },
    }

    doc = {
        "goal_envelope": {
            "driver": {
                "command": 123,  # Wrong type
            },
        },
    }

    with pytest.raises(ContractError) as exc_info:
        validate(doc, schema)

    err = exc_info.value
    assert err.path == "$.goal_envelope.driver.command"


def test_validate_envelope_valid():
    """validate_envelope accepts a valid dispatch envelope with payload."""
    from engine.contracts import validate_envelope

    envelope = {
        "ticket_id": "run-1/t-0",
        "run_id": "run-1",
        "phase": "work",
        "resource_req": "cpu",
        "base_ref": "main",
        "payload": {"task": "hello"},
        "payload_sha256": "abc123",
        "timeout_s": 3600,
        "site_context": {},
        "goal_envelope": {
            "goal": "Do the thing",
            "driver": {
                "command": "/solve",
                "args": {},
                "loop": None,
            },
            "done_contract": {
                "type": "object",
                "required": ["result"],
                "properties": {"result": {"type": "string"}},
            },
            "guardrails": {"no_ship": True},
        },
    }

    payload_schema = {
        "type": "object",
        "required": ["task"],
        "properties": {"task": {"type": "string"}},
    }

    # Should not raise
    validate_envelope(envelope, payload_schema)


def test_validate_envelope_missing_required_field():
    """validate_envelope rejects envelope missing required field."""
    from engine.contracts import validate_envelope, ContractError

    envelope = {
        "ticket_id": "run-1/t-0",
        "run_id": "run-1",
        "phase": "work",
        # Missing resource_req
        "base_ref": "main",
        "payload": {},
        "payload_sha256": "abc",
        "timeout_s": 3600,
        "site_context": {},
        "goal_envelope": {
            "goal": "test",
            "driver": {"command": None, "args": {}, "loop": None},
            "done_contract": {},
            "guardrails": {"no_ship": True},
        },
    }

    with pytest.raises(ContractError):
        validate_envelope(envelope, {})


def test_validate_envelope_extra_field():
    """validate_envelope rejects envelope with extra field (additionalProperties:false)."""
    from engine.contracts import validate_envelope, ContractError

    envelope = {
        "ticket_id": "run-1/t-0",
        "run_id": "run-1",
        "phase": "work",
        "resource_req": "cpu",
        "base_ref": "main",
        "payload": {},
        "payload_sha256": "abc",
        "timeout_s": 3600,
        "site_context": {},
        "goal_envelope": {
            "goal": "test",
            "driver": {"command": None, "args": {}, "loop": None},
            "done_contract": {},
            "guardrails": {"no_ship": True},
        },
        "extra_field": "should-fail",
    }

    with pytest.raises(ContractError):
        validate_envelope(envelope, {})


def test_validate_envelope_bad_payload():
    """validate_envelope rejects envelope with payload violating playbook schema."""
    from engine.contracts import validate_envelope, ContractError

    envelope = {
        "ticket_id": "run-1/t-0",
        "run_id": "run-1",
        "phase": "work",
        "resource_req": "cpu",
        "base_ref": "main",
        "payload": {"wrong": "field"},
        "payload_sha256": "abc",
        "timeout_s": 3600,
        "site_context": {},
        "goal_envelope": {
            "goal": "test",
            "driver": {"command": None, "args": {}, "loop": None},
            "done_contract": {},
            "guardrails": {"no_ship": True},
        },
    }

    payload_schema = {
        "type": "object",
        "required": ["expected"],
        "properties": {"expected": {"type": "string"}},
    }

    with pytest.raises(ContractError):
        validate_envelope(envelope, payload_schema)


def test_validate_result_ok_with_valid_payload():
    """validate_result accepts ok result with valid payload."""
    from engine.contracts import validate_result

    result = {
        "outcome": "ok",
        "termination_reason": "goal_met",
        "result_ref": "ref-123",
        "evidence_ref": None,
        "started_at": 1234567890.0,
        "ended_at": 1234567900.0,
        "error_summary": None,
        "payload": {"answer": 42},
    }

    result_schema = {
        "type": "object",
        "required": ["answer"],
        "properties": {"answer": {"type": "number"}},
    }

    # Should not raise
    validate_result(result, result_schema)


def test_validate_result_ok_bad_payload():
    """validate_result rejects ok result with payload violating result_schema."""
    from engine.contracts import validate_result, ContractError

    result = {
        "outcome": "ok",
        "termination_reason": "goal_met",
        "result_ref": None,
        "evidence_ref": None,
        "started_at": 1234567890.0,
        "ended_at": 1234567900.0,
        "error_summary": None,
        "payload": {"wrong": "field"},
    }

    result_schema = {
        "type": "object",
        "required": ["answer"],
        "properties": {"answer": {"type": "number"}},
    }

    with pytest.raises(ContractError):
        validate_result(result, result_schema)


def test_validate_result_driver_failed_skips_payload_validation():
    """validate_result skips payload validation when outcome != ok."""
    from engine.contracts import validate_result

    result = {
        "outcome": "driver_failed",
        "termination_reason": "contract_fail",
        "result_ref": None,
        "evidence_ref": None,
        "started_at": 1234567890.0,
        "ended_at": 1234567900.0,
        "error_summary": "Something failed",
        "payload": {"this": "is-ignored-not-validated"},
    }

    result_schema = {
        "type": "object",
        "required": ["answer"],
        "properties": {"answer": {"type": "number"}},
    }

    # Should not raise (payload not validated)
    validate_result(result, result_schema)


def test_contract_error_includes_path_in_str():
    """ContractError.__str__() includes the JSON path."""
    from engine.contracts import ContractError

    err = ContractError("$.goal_envelope.driver.command", "Expected string, got number")

    error_str = str(err)
    assert "$.goal_envelope.driver.command" in error_str
    assert "Expected string" in error_str
