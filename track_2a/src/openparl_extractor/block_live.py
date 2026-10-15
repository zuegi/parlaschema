import hashlib
import json
import os
import time
from collections import Counter
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Literal

from pydantic import AwareDatetime, Field, TypeAdapter

from openparl_extractor.block_classification import (
    CATEGORIES, BlockInput, Category, ClassificationParseError, FrozenModel,
    DEFAULT_CONTRACT, DEFAULT_METHOD, ClassificationMethod, OutputContract, build_request,
    digest, method_prompt, parse_category, unique_object,
)
from openparl_extractor.block_http import CategoryHttpClient, completion_endpoint
from openparl_extractor.config import ConfigError, LlmConfig, load_llm_config
from openparl_extractor.schema import NonBlank


CALL_LIMIT = 18
INPUT_TOKEN_LIMIT = 16_384
OUTPUT_TOKEN_LIMIT = 64
TIMEOUT_SECONDS = 60
WALL_SECONDS = 1_200
CHAT_FRAMING_RESERVE = 512
MILLION = Decimal(1_000_000)
PositiveMoney = Annotated[Decimal, Field(gt=0, allow_inf_nan=False)]
Price = Annotated[Decimal, Field(ge=0, allow_inf_nan=False)]


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_object)


def code_sha256() -> str:
    directory = Path(__file__).parent
    names = sorted(path.name for path in directory.glob("*.py"))
    return digest({name: file_sha256(directory / name) for name in names})


def private_path(path: Path) -> Path:
    resolved = path.resolve()
    repository = Path(__file__).resolve().parents[3]
    if resolved.is_relative_to(repository):
        raise ValueError("live inputs and outputs must stay outside checkout/Docker context")
    return resolved


def request_body(
    block: BlockInput, model: str | None, contract: OutputContract = DEFAULT_CONTRACT,
    method: ClassificationMethod = DEFAULT_METHOD,
) -> bytes:
    request = build_request(block, contract, method)
    body = {
        "model": model, "temperature": 0, "top_p": 1, "max_tokens": OUTPUT_TOKEN_LIMIT,
        "messages": [
            {"role": "system", "content": request.system},
            {"role": "user", "content": request.user},
        ],
    }
    return json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def token_estimate(
    block: BlockInput, contract: OutputContract = DEFAULT_CONTRACT,
    method: ClassificationMethod = DEFAULT_METHOD,
) -> dict[str, object]:
    request = build_request(block, contract, method)
    byte_count = len(request.system.encode("utf-8")) + len(request.user.encode("utf-8"))
    return {
        "prompt_and_context_utf8_bytes": byte_count,
        "estimated_input_token_reservation": byte_count + CHAT_FRAMING_RESERVE,
        "method": "one token per UTF-8 byte plus 512 chat-framing reserve; NOT verified tokenizer count",
        "provider_token_usage": None,
    }


def load_cases(manifest_path: Path, labels_path: Path) -> list[tuple[BlockInput, Category]]:
    manifest, labels = read_json(manifest_path), read_json(labels_path)
    if labels["original_manifest_sha256"] != file_sha256(manifest_path):
        raise ValueError("agent label manifest hash mismatch")
    if labels["state"] != "agent_draft_audit_not_human_approved" or labels["human_approval"]:
        raise ValueError("requires separate provisional agent labels, not human gold")
    cases = [BlockInput.model_validate(case["block"]) for case in manifest["cases"]]
    mapping = {entry["block_id"]: entry["proposed_category"] for entry in labels["entries"]}
    ids = [block.block_id for block in cases]
    if len(ids) != CALL_LIMIT or len(set(ids)) != CALL_LIMIT or len(labels["entries"]) != CALL_LIMIT:
        raise ValueError("requires exactly 18 distinct blocks and 18 separate labels")
    if set(mapping) != set(ids) or any(value not in CATEGORIES for value in mapping.values()):
        raise ValueError("labels must cover every block with a valid category")
    if Counter(mapping.values()) != {"question": 7, "reasoning": 4, "answer": 4, "other": 3}:
        raise ValueError("requires the scoped exploratory 7/4/4/3 provisional labels")
    for block, item in zip(cases, manifest["cases"]):
        if block.input_sha256 != item["input_sha256"]:
            raise ValueError("original block input hash mismatch")
    return [(block, mapping[block.block_id]) for block in cases]


def make_plan(
    cases, manifest_path: Path, labels_path: Path, config: LlmConfig | None,
    contract: OutputContract = DEFAULT_CONTRACT,
    method: ClassificationMethod = DEFAULT_METHOD,
) -> dict:
    entries = [plan_entry(block, expected, config, contract, method) for block, expected in cases]
    plan = {
        "version": "exploratory-block-plan-v0.1", "label_status": "provisional_agent_not_gold",
        "manifest_sha256": file_sha256(manifest_path), "labels_sha256": file_sha256(labels_path),
        "code_sha256": code_sha256(), "prompt_sha256": digest(method_prompt(contract, method)),
        "output_contract": contract, "classification_method": method,
        "model": config.name if config else None,
        "endpoint": completion_endpoint(str(config.base_url)) if config else None,
        "max_calls": CALL_LIMIT, "max_input_tokens": INPUT_TOKEN_LIMIT,
        "max_output_tokens": OUTPUT_TOKEN_LIMIT, "timeout_seconds": TIMEOUT_SECONDS,
        "wall_seconds": WALL_SECONDS, "entries": entries,
        "blockers": [] if config else ["LLM_NAME/LLM_BASE_URL/LLM_API_KEY configuration missing"],
        "provider_support": "unverified", "prices": "unknown",
    }
    plan["plan_sha256"] = digest(plan)
    return plan


def plan_entry(
    block: BlockInput, expected: Category, config: LlmConfig | None,
    contract: OutputContract = DEFAULT_CONTRACT,
    method: ClassificationMethod = DEFAULT_METHOD,
) -> dict:
    body = request_body(block, config.name if config else None, contract, method)
    return {
        "block_id": block.block_id, "language": block.language, "expected": expected,
        "input_sha256": block.input_sha256, "source_text_sha256": block.source.text_sha256,
        "prompt_sha256": digest(build_request(block, contract, method).model_dump()),
        "output_contract": contract, "classification_method": method,
        "request_bytes": len(body), "request_sha256": hashlib.sha256(body).hexdigest(),
        "request_body": body.decode("utf-8"), "tokens": token_estimate(block, contract, method),
    }


class ExecutionApproval(FrozenModel):
    plan_sha256: NonBlank
    approved_by: NonBlank
    network_approved: Literal[True]
    private_source_transmission_approved: Literal[True]
    provisional_labels_accepted: Literal[True]
    unverified_token_estimate_accepted: Literal[True]
    model: NonBlank
    endpoint: NonBlank
    max_calls: Literal[18]


class LiveApproval(ExecutionApproval):
    version: Literal["exploratory-block-approval-v0.1"]
    approved_at: NonBlank
    provider_settings_and_limits_confirmed: Literal[True]
    pricing_confirmed: Literal[True]
    currency: NonBlank
    monetary_limit: PositiveMoney
    input_price_per_million: Price
    output_price_per_million: Price
    pricing_source: NonBlank


class QuotaApproval(ExecutionApproval):
    version: Literal["exploratory-block-quota-approval-v0.1"]
    approved_at: None
    authorization_recorded_at: AwareDatetime
    user_confirmed_covered_quota: Literal[True]
    coverage_statement_verbatim: NonBlank
    execution_statement_verbatim: NonBlank
    unverified_provider_support_risk_accepted: Literal[True]
    original_plan_sha256: NonBlank
    provider_support: Literal["unverified"]
    public_prices: Literal["unknown"]


BudgetApproval = LiveApproval | QuotaApproval


def verify_approval(plan: dict, approval: BudgetApproval) -> Decimal | None:
    verify_plan(plan)
    if plan["blockers"] or approval.plan_sha256 != plan["plan_sha256"]:
        raise ValueError("configuration blocked or approval does not bind current plan")
    if approval.model != plan["model"] or approval.endpoint != plan["endpoint"]:
        raise ValueError("approval model/endpoint mismatch")
    estimates = [e["tokens"]["estimated_input_token_reservation"] for e in plan["entries"]]
    if any(value > INPUT_TOKEN_LIMIT for value in estimates):
        raise ValueError("input exceeds token reservation; never truncate")
    return verify_money(approval)


def verify_money(approval: BudgetApproval) -> Decimal | None:
    if isinstance(approval, QuotaApproval):
        return None
    input_cost = CALL_LIMIT * INPUT_TOKEN_LIMIT * approval.input_price_per_million / MILLION
    output_cost = CALL_LIMIT * OUTPUT_TOKEN_LIMIT * approval.output_price_per_million / MILLION
    if input_cost + output_cost > approval.monetary_limit:
        raise ValueError("proposed reservation exceeds approved monetary ceiling")
    return input_cost + output_cost


def verify_plan(plan: dict) -> None:
    current = {key: value for key, value in plan.items() if key != "plan_sha256"}
    if digest(current) != plan["plan_sha256"] or plan["code_sha256"] != code_sha256():
        raise ValueError("plan or code changed since preparation")
    method = plan.get("classification_method", DEFAULT_METHOD)
    method_prompt(plan.get("output_contract", DEFAULT_CONTRACT), method)
    entries = plan["entries"]
    if len(entries) != CALL_LIMIT or len({e["block_id"] for e in entries}) != CALL_LIMIT:
        raise ValueError("plan requires exactly 18 distinct inputs")
    for entry in entries:
        if entry.get("classification_method", DEFAULT_METHOD) != method:
            raise ValueError("entry classification method differs from plan")
        raw = entry["request_body"].encode("utf-8")
        if hashlib.sha256(raw).hexdigest() != entry["request_sha256"]:
            raise ValueError("planned request byte hash mismatch")


class PrivateLog:
    def __init__(self, directory: Path) -> None:
        self.directory = private_path(directory)
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=False)

    def write(self, name: str, value: object) -> None:
        with (self.directory / name).open("x", encoding="utf-8") as stream:
            os.chmod(stream.name, 0o600)
            stream.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
            stream.flush()
            os.fsync(stream.fileno())

    def event(self, value: dict) -> None:
        path = self.directory / "events.jsonl"
        with path.open("a", encoding="utf-8") as stream:
            os.chmod(path, 0o600)
            stream.write(json.dumps(value, ensure_ascii=False) + "\n")
            stream.flush()
            os.fsync(stream.fileno())

    def snapshot(self, name: str, source: Path) -> None:
        with (self.directory / name).open("xb") as stream:
            os.chmod(stream.name, 0o600)
            stream.write(source.read_bytes())
            stream.flush()
            os.fsync(stream.fileno())


def result_record(entry: dict, result) -> dict:
    record = {"block_id": entry["block_id"], "expected": entry["expected"], "language": entry["language"],
              "output_contract": entry.get("output_contract", DEFAULT_CONTRACT),
              "classification_method": entry.get("classification_method", DEFAULT_METHOD),
              "input_sha256": entry["input_sha256"], "predicted": None, **result.model_dump()}
    if result.error_kind:
        record["outcome"] = result.error_kind
        return record
    try:
        record["predicted"] = parse_category(result.content, entry.get("output_contract", DEFAULT_CONTRACT))
    except ClassificationParseError:
        record.update(outcome="structure_error", error="invalid category-only output")
        return record
    record["outcome"] = (
        "abstention" if record["predicted"] == "unclear"
        else "correct" if record["predicted"] == entry["expected"] else "incorrect"
    )
    return record


def not_sent(entry: dict, reason: str) -> dict:
    return {
        "block_id": entry["block_id"], "expected": entry["expected"], "language": entry["language"],
        "input_sha256": entry["input_sha256"], "predicted": None, "outcome": "not_sent",
        "output_contract": entry.get("output_contract", DEFAULT_CONTRACT),
        "classification_method": entry.get("classification_method", DEFAULT_METHOD),
        "send_attempt": False, "error": reason, "latency_seconds": 0, "usage": None,
    }


def summary(records: list[dict]) -> dict:
    counts = Counter(r["outcome"] for r in records)
    matrix = Counter((r["expected"], r["predicted"]) for r in records)
    return {
        "denominator": len(records), "records": records, "counts": {
            name: counts[name] for name in
            ("correct", "incorrect", "abstention", "structure_error", "transport_error", "not_sent")
        },
        "confusion": {expected: {predicted: matrix[expected, predicted] for predicted in CATEGORIES}
                      for expected in CATEGORIES},
        "send_attempts": sum(r.get("send_attempt", False) for r in records),
        "latency_seconds_total": sum(r["latency_seconds"] for r in records),
        "usage_missing": sum(r.get("usage") is None for r in records if r.get("send_attempt")),
        "positive_class_gaps": ["request", "unclear"], "label_status": "provisional_agent_not_gold",
    }


def usage_totals(records: list[dict]) -> dict:
    values = [r["usage"] for r in records if r.get("usage")]
    return {key: sum(usage[key] for usage in values)
            for key in ("prompt_tokens", "completion_tokens", "total_tokens")}


def diagnostics(records: list[dict]) -> dict:
    return {
        "by_category": {name: summary([r for r in records if r["expected"] == name])
                        for name in CATEGORIES},
        "by_language": {name: summary([r for r in records if r["language"] == name])
                        for name in ("de", "fr", "it")},
    }


def run_live(plan: dict, config: LlmConfig, approval: BudgetApproval, log: PrivateLog, client=None) -> dict:
    reservation = verify_approval(plan, approval)
    if config.name != plan["model"] or completion_endpoint(str(config.base_url)) != plan["endpoint"]:
        raise ValueError("live configuration differs from approved plan")
    client = client or CategoryHttpClient(config)
    records, started, stop_reason = [], time.monotonic(), None
    for entry in plan["entries"]:
        if stop_reason or time.monotonic() - started > WALL_SECONDS - TIMEOUT_SECONDS:
            record = not_sent(entry, stop_reason or "wall time limit reached")
        else:
            record = send_one(entry, client, log)
        records.append(record)
        stop_reason = budget_stop(records, approval) or stop_reason
        log.event({"state": "result", **record})
    report = {**summary(records), **diagnostics(records)}
    report["output_contract"] = plan.get("output_contract", DEFAULT_CONTRACT)
    report["classification_method"] = plan.get("classification_method", DEFAULT_METHOD)
    report.update(financial_summary(records, approval, reservation, started))
    log.write("report.json", report)
    return report


def financial_summary(records: list[dict], approval: BudgetApproval, reservation: Decimal | None, started: float) -> dict:
    quota = isinstance(approval, QuotaApproval)
    return {
        "budget_mode": "user_confirmed_covered_quota" if quota else "monetary_ceiling",
        "cost_estimated_reservation": str(reservation) if reservation is not None else None,
        "currency": None if quota else approval.currency,
        "provider_usage_reported_totals": usage_totals(records),
        "elapsed_wall_seconds": time.monotonic() - started,
        "monetary_limit": None if quota else str(approval.monetary_limit),
        "actual_cost": actual_cost(records, approval),
    }


def budget_stop(records: list[dict], approval: BudgetApproval) -> str | None:
    sent = [r for r in records if r.get("send_attempt")]
    latest = sent[-1] if sent else None
    if latest and latest.get("usage"):
        usage = latest["usage"]
        if usage["prompt_tokens"] > INPUT_TOKEN_LIMIT or usage["completion_tokens"] > OUTPUT_TOKEN_LIMIT:
            return "provider usage exceeds approved per-call limit"
    cost = actual_cost(records, approval)
    if isinstance(approval, LiveApproval) and cost is not None and Decimal(cost) > approval.monetary_limit:
        return "reported cost exceeds approved monetary limit"
    return None


def send_one(entry: dict, client, log: PrivateLog) -> dict:
    log.event({"state": "sent", "block_id": entry["block_id"], "send_attempt": True,
               "meaning": "one HTTP submission attempt begins; not proof provider received bytes",
               "request_sha256": entry["request_sha256"]})
    result = client.post(entry["request_body"].encode("utf-8"), TIMEOUT_SECONDS)
    record = result_record(entry, result)
    record["send_attempt"] = True
    return record


def actual_cost(records: list[dict], approval: BudgetApproval) -> str | None:
    if isinstance(approval, QuotaApproval):
        return None
    sent = [r for r in records if r.get("send_attempt")]
    if any(r.get("usage") is None for r in sent):
        return None
    prompt = sum(r["usage"]["prompt_tokens"] for r in sent)
    completion = sum(r["usage"]["completion_tokens"] for r in sent)
    return str((prompt * approval.input_price_per_million +
                completion * approval.output_price_per_million) / MILLION)


def prepare_config() -> LlmConfig | None:
    try:
        config = load_llm_config()
    except ConfigError:
        return None
    if not config.name.strip() or not config.api_key.get_secret_value():
        raise ValueError("model and credential must be nonempty")
    completion_endpoint(str(config.base_url))
    return config


def exploratory_command(args) -> int:
    cases = load_cases(private_path(args.manifest), private_path(args.labels))
    config = prepare_config()
    plan = make_plan(cases, args.manifest, args.labels, config, args.output_contract, args.method)
    approval = TypeAdapter(BudgetApproval).validate_python(read_json(private_path(args.approval))) if args.approval else None
    if args.allow_network and (approval is None or config is None):
        raise ValueError("live run requires valid configuration and explicit approval file")
    if args.allow_network:
        verify_approval(plan, approval)
    log = PrivateLog(args.output)
    persist_prepared(log, plan, args, approval)
    if args.allow_network:
        run_live(plan, config, approval, log)
    else:
        records = [not_sent(e, "dry-run; network disabled") for e in plan["entries"]]
        log.write("report.json", {**summary(records), **diagnostics(records),
                                  "output_contract": plan["output_contract"],
                                  "classification_method": plan["classification_method"]})
    print("Exploratory plan saved privately; " + ("live run recorded" if args.allow_network else "dry-run, no calls"))
    return 0


def persist_prepared(log: PrivateLog, plan: dict, args, approval: BudgetApproval | None) -> None:
    log.write("plan.json", plan)
    log.snapshot("source-manifest.json", args.manifest)
    log.snapshot("provisional-labels.json", args.labels)
    if (file_sha256(log.directory / "source-manifest.json"),
        file_sha256(log.directory / "provisional-labels.json")) != (plan["manifest_sha256"], plan["labels_sha256"]):
        raise ValueError("private input files changed during preparation")
    if approval:
        log.write("approval.json", approval.model_dump(mode="json"))
    for entry in plan["entries"]:
        log.event({"state": "prepared", "block_id": entry["block_id"], "send_attempt": False,
                   "network_enabled": args.allow_network, "plan_sha256": plan["plan_sha256"]})
