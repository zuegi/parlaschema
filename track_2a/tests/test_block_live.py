import json
import socket
from decimal import Decimal

import pytest

from openparl_extractor.block_classification import digest
from openparl_extractor.block_http import CategoryHttpClient, HttpResult, completion_endpoint
from openparl_extractor.block_live import (
    INPUT_TOKEN_LIMIT, OUTPUT_TOKEN_LIMIT, LiveApproval, PrivateLog, actual_cost,
    code_sha256, file_sha256, load_cases, make_plan,
    private_path, run_live, verify_approval,
)
from openparl_extractor.cli import main
from openparl_extractor.config import load_llm_config
from test_block_classification import synthetic_block


def synthetic_config():
    return load_llm_config({
        "LLM_NAME": "synthetic-model", "LLM_BASE_URL": "https://invalid.example/v1",
        "LLM_API_KEY": "synthetic-private-key",
    })


def test_function_plan_request_record_and_dry_run_cli(tmp_path, monkeypatch, capsys):
    from openparl_extractor.block_live import result_record, verify_plan
    manifest, labels = synthetic_files(tmp_path)
    config = synthetic_config()
    monkeypatch.setattr(socket, "socket", lambda *a, **k: pytest.fail("network forbidden"))
    for key, value in (
        ("LLM_NAME", config.name), ("LLM_BASE_URL", str(config.base_url)),
        ("LLM_API_KEY", "synthetic-private-key"),
    ):
        monkeypatch.setenv(key, value)
    output = tmp_path / "function-dry-run"
    monkeypatch.setattr("sys.argv", [
        "openparl-extractor", "prepare-block-test", "--manifest", str(manifest),
        "--labels", str(labels), "--output", str(output),
        "--output-contract", "category-word-v0.1", "--method", "source-function-v0.2",
    ])
    assert main() == 0
    plan = json.loads((output / "plan.json").read_text())
    verify_plan(plan)
    report = json.loads((output / "report.json").read_text())
    assert plan["classification_method"] == report["classification_method"] == "source-function-v0.2"
    assert report["send_attempts"] == 0
    for entry in plan["entries"]:
        assert entry["classification_method"] == "source-function-v0.2"
        assert "assignment" in json.loads(json.loads(entry["request_body"])["messages"][1]["content"])
    record = result_record(plan["entries"][0], HttpResult(content="unclear", latency_seconds=0))
    assert record["classification_method"] == "source-function-v0.2"
    assert record["outcome"] == "abstention"
    assert "synthetic-private-key" not in capsys.readouterr().out


def test_unknown_method_cli_fails_without_network_or_output(tmp_path, monkeypatch):
    output = tmp_path / "should-not-exist"
    monkeypatch.setattr("sys.argv", [
        "openparl-extractor", "prepare-block-test", "--manifest", "unused",
        "--labels", "unused", "--output", str(output), "--method", "unknown-method",
    ])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2 and not output.exists()


def synthetic_files(tmp_path):
    cases, entries = [], []
    labels = ["question"] * 7 + ["reasoning"] * 4 + ["answer"] * 4 + ["other"] * 3
    for index, label in enumerate(labels):
        block = synthetic_block("Synthetic invented text?", ("de", "fr", "it")[index % 3])
        data = block.model_dump(mode="json")
        data["block_id"] = f"synthetic-{index}"
        from openparl_extractor.block_classification import BlockInput
        block = BlockInput.model_validate(data)
        cases.append({"block": data, "input_sha256": block.input_sha256})
        entries.append({"block_id": block.block_id, "proposed_category": label})
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"cases": cases}), encoding="utf-8")
    audit = tmp_path / "labels.json"
    audit.write_text(json.dumps({
        "state": "agent_draft_audit_not_human_approved", "human_approval": False,
        "original_manifest_sha256": file_sha256(manifest), "entries": entries,
    }), encoding="utf-8")
    return manifest, audit


def synthetic_plan(tmp_path, config=None):
    manifest, audit = synthetic_files(tmp_path)
    return make_plan(load_cases(manifest, audit), manifest, audit, config or synthetic_config())


def approval_for(plan, **changes):
    values = {
        "version": "exploratory-block-approval-v0.1", "plan_sha256": plan["plan_sha256"],
        "approved_by": "Synthetic test approver", "approved_at": "Synthetic test only",
        "network_approved": True, "private_source_transmission_approved": True,
        "provisional_labels_accepted": True, "provider_settings_and_limits_confirmed": True,
        "pricing_confirmed": True,
        "unverified_token_estimate_accepted": True, "model": plan["model"],
        "endpoint": plan["endpoint"], "max_calls": 18, "currency": "TEST",
        "monetary_limit": "1", "input_price_per_million": "1",
        "output_price_per_million": "1", "pricing_source": "synthetic test prices",
    }
    return LiveApproval.model_validate({**values, **changes})


class FakeResponse:
    def __init__(self, raw, status=200):
        self.raw, self.status = raw, status

    def read(self, limit):
        return self.raw[:limit]


class FakeConnection:
    def __init__(self, response=None, error=None):
        self.response, self.error, self.calls, self.closed = response, error, [], False

    def request(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        if self.error:
            raise self.error

    def getresponse(self):
        return self.response

    def close(self):
        self.closed = True


def provider_body(content='{"category":"question"}', finish="stop", usage=True):
    value = {"choices": [{"message": {"content": content}, "finish_reason": finish}]}
    if usage:
        value["usage"] = {"prompt_tokens": 100, "completion_tokens": 6, "total_tokens": 106}
    return json.dumps(value).encode("utf-8")


def test_fake_http_one_post_no_headers_or_secret_in_result():
    connection = FakeConnection(FakeResponse(provider_body()))
    client = CategoryHttpClient(synthetic_config(), lambda *a, **kw: connection)
    result = client.post(b'{"synthetic":"request"}', 60)
    assert result.content == '{"category":"question"}'
    assert result.finish_reason == "stop" and result.usage["prompt_tokens"] == 100
    assert len(connection.calls) == 1 and connection.closed
    assert connection.calls[0][0] == ("POST", "/v1/chat/completions")
    assert "Authorization" not in result.model_dump_json()
    assert "synthetic-private-key" not in result.model_dump_json()


@pytest.mark.parametrize("raw,status,error_kind", [
    (b"not-json", 200, "structure_error"),
    (provider_body(finish="length"), 200, "structure_error"),
    (b'{"choices":[]}', 200, "structure_error"),
    (provider_body(), 429, "transport_error"),
    (provider_body(), 302, "transport_error"),
])
def test_http_errors_not_abstention_and_no_retry(raw, status, error_kind):
    connection = FakeConnection(FakeResponse(raw, status))
    result = CategoryHttpClient(synthetic_config(), lambda *a, **k: connection).post(b"{}", 60)
    assert result.error_kind == error_kind
    assert result.content is None
    assert result.raw_response
    assert len(connection.calls) == 1


def test_transport_timeout_records_attempt_once():
    connection = FakeConnection(error=TimeoutError("do not log secrets here"))
    result = CategoryHttpClient(synthetic_config(), lambda *a, **k: connection).post(b"{}", 60)
    assert result.error_kind == "transport_error" and result.error == "TimeoutError"
    assert len(connection.calls) == 1 and connection.closed


def test_response_credential_echo_redacted():
    raw = provider_body('synthetic-private-key')
    connection = FakeConnection(FakeResponse(raw))
    result = CategoryHttpClient(synthetic_config(), lambda *a, **k: connection).post(b"{}", 60)
    assert "synthetic-private-key" not in result.model_dump_json()
    assert "[REDACTED_CREDENTIAL]" in result.raw_response


@pytest.mark.parametrize("url", [
    "http://invalid.example/v1", "https://user:pass@invalid.example/v1",
    "https://invalid.example/v1?secret=value", "https://invalid.example/v1#fragment",
])
def test_unsafe_endpoint_rejected(url):
    with pytest.raises(ValueError):
        completion_endpoint(url)


@pytest.mark.parametrize("change", ["manifest", "label", "duplicate", "count"])
def test_source_and_agent_labels_bound_exactly(tmp_path, change):
    manifest, audit = synthetic_files(tmp_path)
    labels = json.loads(audit.read_text())
    if change == "manifest":
        manifest.write_text(manifest.read_text() + " ")
    elif change == "label":
        labels["entries"][0]["proposed_category"] = "request"
    elif change == "duplicate":
        labels["entries"][0]["block_id"] = labels["entries"][1]["block_id"]
    else:
        labels["entries"].pop()
    audit.write_text(json.dumps(labels))
    with pytest.raises(ValueError):
        load_cases(manifest, audit)


def test_plan_binds_real_request_prompt_context_code_and_prices(tmp_path):
    plan = synthetic_plan(tmp_path)
    copy = {k: v for k, v in plan.items() if k != "plan_sha256"}
    assert plan["plan_sha256"] == digest(copy)
    assert plan["code_sha256"] == code_sha256()
    assert len(plan["entries"]) == 18
    entry = plan["entries"][0]
    body = json.loads(entry["request_body"])
    assert body["max_tokens"] == 64
    assert body["temperature"] == 0 and body["top_p"] == 1
    assert len(body["messages"]) == 2
    assert "provider_token_usage" in entry["tokens"]
    assert entry["tokens"]["provider_token_usage"] is None
    assert entry["tokens"]["estimated_input_token_reservation"] > len("Synthetic invented text?")
    assert verify_approval(plan, approval_for(plan)) == (
        Decimal(18 * INPUT_TOKEN_LIMIT + 18 * OUTPUT_TOKEN_LIMIT) / Decimal(1_000_000)
    )


@pytest.mark.parametrize("changes", [
    {"plan_sha256": "wrong"}, {"model": "wrong"}, {"endpoint": "https://else.invalid/v1"},
    {"monetary_limit": "0.000001"},
])
def test_approval_rejects_mismatch_or_insufficient_money(tmp_path, changes):
    plan = synthetic_plan(tmp_path)
    with pytest.raises(ValueError):
        verify_approval(plan, approval_for(plan, **changes))


@pytest.mark.parametrize("field", [
    "network_approved", "private_source_transmission_approved", "pricing_confirmed",
    "provider_settings_and_limits_confirmed", "unverified_token_estimate_accepted",
])
def test_all_explicit_authorizations_required(tmp_path, field):
    plan = synthetic_plan(tmp_path)
    with pytest.raises(ValueError):
        approval_for(plan, **{field: False})


def test_tampered_plan_and_oversize_input_refused_before_calls(tmp_path):
    plan = synthetic_plan(tmp_path)
    approval = approval_for(plan)
    plan["entries"][0]["request_body"] += " "
    with pytest.raises(ValueError, match="plan or code changed"):
        verify_approval(plan, approval)
    plan = synthetic_plan(tmp_path)
    plan["entries"][0]["tokens"]["estimated_input_token_reservation"] = INPUT_TOKEN_LIMIT + 1
    plan["plan_sha256"] = digest({k: v for k, v in plan.items() if k != "plan_sha256"})
    with pytest.raises(ValueError, match="never truncate"):
        verify_approval(plan, approval_for(plan))


def test_nonstop_finish_preserves_reported_usage():
    connection = FakeConnection(FakeResponse(provider_body(finish="length")))
    result = CategoryHttpClient(synthetic_config(), lambda *a, **k: connection).post(b"{}", 60)
    assert result.error_kind == "structure_error"
    assert result.finish_reason == "length" and result.usage["completion_tokens"] == 6


def test_invalid_utf8_cannot_become_valid_category():
    connection = FakeConnection(FakeResponse(b'{"choices":[{"message":{"content":"\xff"},"finish_reason":"stop"}]}'))
    result = CategoryHttpClient(synthetic_config(), lambda *a, **k: connection).post(b"{}", 60)
    assert result.error_kind == "structure_error"


def test_response_size_limit_never_retries():
    from openparl_extractor.block_http import MAX_RESPONSE_BYTES
    connection = FakeConnection(FakeResponse(b"x" * (MAX_RESPONSE_BYTES + 2)))
    result = CategoryHttpClient(synthetic_config(), lambda *a, **k: connection).post(b"{}", 60)
    assert result.error_kind == "transport_error"
    assert len(connection.calls) == 1


class FakeClient:
    def __init__(self):
        self.calls = []

    def post(self, body, timeout):
        self.calls.append(body)
        responses = [
            HttpResult(content='{"category":"unclear"}', latency_seconds=0.1),
            HttpResult(error_kind="transport_error", error="synthetic timeout", latency_seconds=0.2),
            HttpResult(content='{"category":"question","confidence":1}', latency_seconds=0.3),
        ]
        return responses[(len(self.calls) - 1) % 3]


def test_full_fake_live_accounting_sent_result_and_no_retry(tmp_path):
    plan = synthetic_plan(tmp_path)
    client = FakeClient()
    log = PrivateLog(tmp_path / "private-output")
    report = run_live(plan, synthetic_config(), approval_for(plan), log, client)
    assert len(client.calls) == report["send_attempts"] == report["denominator"] == 18
    assert report["counts"]["abstention"] == 6
    assert report["counts"]["structure_error"] == 6
    assert report["counts"]["transport_error"] == 6
    assert report["actual_cost"] is None
    events = [json.loads(line) for line in (log.directory / "events.jsonl").read_text().splitlines()]
    assert [event["state"] for event in events] == ["sent", "result"] * 18
    assert report["confusion"]["question"]["unclear"] == 3
    assert sum(group["denominator"] for group in report["by_language"].values()) == 18


def test_provider_limit_breach_stops_remaining_inputs_without_losing_denominator(tmp_path):
    class ExcessClient:
        def post(self, body, timeout):
            return HttpResult(content='{"category":"question"}', latency_seconds=0,
                              usage={"prompt_tokens": INPUT_TOKEN_LIMIT + 1,
                                     "completion_tokens": 6, "total_tokens": INPUT_TOKEN_LIMIT + 7})

    plan = synthetic_plan(tmp_path)
    report = run_live(plan, synthetic_config(), approval_for(plan),
                      PrivateLog(tmp_path / "out"), ExcessClient())
    assert report["denominator"] == 18 and report["send_attempts"] == 1
    assert report["counts"]["not_sent"] == 17
    assert "provider usage" in report["records"][-1]["error"]


def test_actual_cost_only_from_provider_usage(tmp_path):
    plan = synthetic_plan(tmp_path)
    approval = approval_for(plan)
    assert actual_cost([{"send_attempt": True, "usage": None}], approval) is None
    assert actual_cost([{"send_attempt": True, "usage": {
        "prompt_tokens": 100, "completion_tokens": 6,
    }}], approval) == "0.000106"


def quota_for(plan, **changes):
    from openparl_extractor.block_live import QuotaApproval
    monetary = approval_for(plan).model_dump()
    remove = ("version", "approved_at", "provider_settings_and_limits_confirmed",
              "pricing_confirmed", "currency", "monetary_limit", "input_price_per_million",
              "output_price_per_million", "pricing_source")
    base = {key: value for key, value in monetary.items() if key not in remove}
    return QuotaApproval.model_validate({
        **base, "version": "exploratory-block-quota-approval-v0.1", "approved_at": None,
        "authorization_recorded_at": "2026-10-12T12:00:00Z",
        "user_confirmed_covered_quota": True, "coverage_statement_verbatim": "Synthetic covered quota",
        "execution_statement_verbatim": "Synthetic test approval only",
        "unverified_provider_support_risk_accepted": True,
        "original_plan_sha256": plan["plan_sha256"], "provider_support": "unverified",
        "public_prices": "unknown", **changes,
    })


def test_quota_mode_requires_explicit_confirmation_and_never_fabricates_cost(tmp_path):
    plan = synthetic_plan(tmp_path)
    quota = quota_for(plan)
    assert verify_approval(plan, quota) is None
    assert actual_cost([{"send_attempt": True, "usage": {
        "prompt_tokens": 100, "completion_tokens": 6,
    }}], quota) is None
    for field in ("user_confirmed_covered_quota", "unverified_provider_support_risk_accepted"):
        with pytest.raises(ValueError):
            quota_for(plan, **{field: False})
    with pytest.raises(ValueError):
        quota_for(plan, public_prices="free")
    with pytest.raises(ValueError):
        verify_approval(plan, quota_for(plan, plan_sha256="wrong"))


def test_quota_fake_run_keeps_caps_and_unknown_financials(tmp_path):
    plan = synthetic_plan(tmp_path)
    client = FakeClient()
    report = run_live(plan, synthetic_config(), quota_for(plan),
                      PrivateLog(tmp_path / "quota-out"), client)
    assert len(client.calls) == report["denominator"] == 18
    assert report["budget_mode"] == "user_confirmed_covered_quota"
    assert report["actual_cost"] is report["cost_estimated_reservation"] is None
    assert report["currency"] is report["monetary_limit"] is None

def test_cli_dry_run_default_no_config_no_network(tmp_path, monkeypatch, capsys):
    manifest, labels = synthetic_files(tmp_path)
    monkeypatch.setattr(socket, "socket", lambda *a, **kw: pytest.fail("unexpected socket"))
    for key in ("LLM_NAME", "LLM_BASE_URL", "LLM_API_KEY"):
            monkeypatch.delenv(key, raising=False)
    output = tmp_path / "dry-run"
    monkeypatch.setattr("sys.argv", [
        "openparl-extractor", "prepare-block-test", "--manifest", str(manifest),
        "--labels", str(labels), "--output", str(output),
    ])
    assert main() == 0
    plan = json.loads((output / "plan.json").read_text())
    report = json.loads((output / "report.json").read_text())
    assert plan["blockers"] and plan["model"] is None
    assert report["counts"]["not_sent"] == report["denominator"] == 18
    assert report["send_attempts"] == 0
    assert (output / "source-manifest.json").read_bytes() == manifest.read_bytes()
    assert (output / "provisional-labels.json").read_bytes() == labels.read_bytes()
    assert "no calls" in capsys.readouterr().out
    assert len((output / "events.jsonl").read_text().splitlines()) == 18


def test_cli_live_without_approval_refused_before_network_or_output(tmp_path, monkeypatch, capsys):
    manifest, labels = synthetic_files(tmp_path)
    monkeypatch.setattr(socket, "socket", lambda *a, **kw: pytest.fail("unexpected socket"))
    config = synthetic_config()
    monkeypatch.setenv("LLM_NAME", config.name)
    monkeypatch.setenv("LLM_BASE_URL", str(config.base_url))
    monkeypatch.setenv("LLM_API_KEY", config.api_key.get_secret_value())
    output = tmp_path / "refused"
    monkeypatch.setattr("sys.argv", [
        "openparl-extractor", "prepare-block-test", "--manifest", str(manifest),
        "--labels", str(labels), "--output", str(output), "--allow-network",
    ])
    assert main() == 1
    assert not output.exists()
    assert "synthetic-private-key" not in capsys.readouterr().err


def test_configured_dry_run_with_approval_still_cannot_connect(tmp_path, monkeypatch):
    manifest, labels = synthetic_files(tmp_path)
    config = synthetic_config()
    plan = make_plan(load_cases(manifest, labels), manifest, labels, config)
    approval = tmp_path / "approval.json"
    approval.write_text(approval_for(plan).model_dump_json())
    for key, value in (("LLM_NAME", config.name), ("LLM_BASE_URL", str(config.base_url)),
                       ("LLM_API_KEY", config.api_key.get_secret_value())):
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(socket, "socket", lambda *a, **k: pytest.fail("unexpected socket"))
    monkeypatch.setattr("sys.argv", [
        "openparl-extractor", "prepare-block-test", "--manifest", str(manifest),
        "--labels", str(labels), "--output", str(tmp_path / "still-dry"),
        "--approval", str(approval),
    ])
    assert main() == 0
    report = json.loads((tmp_path / "still-dry" / "report.json").read_text())
    assert report["send_attempts"] == 0 and report["counts"]["not_sent"] == 18


def test_cli_approved_fake_http_is_exactly_18_attempts(tmp_path, monkeypatch):
    manifest, labels = synthetic_files(tmp_path)
    config = synthetic_config()
    plan = make_plan(load_cases(manifest, labels), manifest, labels, config)
    approval = tmp_path / "approval.json"
    approval.write_text(approval_for(plan).model_dump_json())
    for key, value in (("LLM_NAME", config.name), ("LLM_BASE_URL", str(config.base_url)),
                       ("LLM_API_KEY", config.api_key.get_secret_value())):
        monkeypatch.setenv(key, value)
    client = FakeClient()
    monkeypatch.setattr("openparl_extractor.block_live.CategoryHttpClient", lambda *a: client)
    monkeypatch.setattr(socket, "socket", lambda *a, **k: pytest.fail("unexpected socket"))
    monkeypatch.setattr("sys.argv", [
        "openparl-extractor", "prepare-block-test", "--manifest", str(manifest),
        "--labels", str(labels), "--output", str(tmp_path / "fake-approved"),
        "--approval", str(approval), "--allow-network",
    ])
    assert main() == 0
    assert len(client.calls) == 18
    events = [json.loads(line) for line in (tmp_path / "fake-approved" / "events.jsonl").read_text().splitlines()]
    assert sum(e["state"] == "prepared" for e in events) == 18
    assert sum(e["state"] == "sent" for e in events) == 18
    assert sum(e["state"] == "result" for e in events) == 18


def test_private_output_refuses_checkout_and_existing_results(tmp_path):
    from pathlib import Path
    with pytest.raises(ValueError):
        private_path(Path.cwd() / "private-results")
    PrivateLog(tmp_path / "existing")
    with pytest.raises(FileExistsError):
        PrivateLog(tmp_path / "existing")


def test_word_plan_opt_in_and_result_parsing_no_autodetect(tmp_path):
    from openparl_extractor.block_live import result_record
    manifest, labels = synthetic_files(tmp_path)
    cases = load_cases(manifest, labels)
    old = make_plan(cases, manifest, labels, synthetic_config())
    new = make_plan(cases, manifest, labels, synthetic_config(), "category-word-v0.1")
    assert old["output_contract"] == "category-json-v0.1"
    assert new["output_contract"] == "category-word-v0.1"
    assert old["plan_sha256"] != new["plan_sha256"]
    assert old["entries"][0]["input_sha256"] == new["entries"][0]["input_sha256"]
    response = HttpResult(content="question", latency_seconds=0)
    assert result_record(old["entries"][0], response)["outcome"] == "structure_error"
    word = result_record(new["entries"][0], response)
    assert word["predicted"] == "question" and word["outcome"] == "correct"
    assert word["output_contract"] == "category-word-v0.1"
    response = HttpResult(content='{"category":"question"}', latency_seconds=0)
    assert result_record(new["entries"][0], response)["outcome"] == "structure_error"


def test_cli_explicit_word_contract_dry_run(tmp_path, monkeypatch):
    manifest, labels = synthetic_files(tmp_path)
    for key in ("LLM_NAME", "LLM_BASE_URL", "LLM_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(socket, "socket", lambda *a, **k: pytest.fail("unexpected socket"))
    output = tmp_path / "word-dry"
    monkeypatch.setattr("sys.argv", [
        "openparl-extractor", "prepare-block-test", "--manifest", str(manifest),
        "--labels", str(labels), "--output", str(output), "--output-contract", "category-word-v0.1",
    ])
    assert main() == 0
    assert json.loads((output / "plan.json").read_text())["output_contract"] == "category-word-v0.1"
    assert json.loads((output / "report.json").read_text())["output_contract"] == "category-word-v0.1"
