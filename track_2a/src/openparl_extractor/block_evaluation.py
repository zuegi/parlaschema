from collections import Counter
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from openparl_extractor.block_classification import (
    CATEGORIES, BlockInput, Category, ClassificationRequest, FrozenModel,
    DEFAULT_CONTRACT, DEFAULT_METHOD, ClassificationMethod, Language, OutputContract,
    SourceRange, TransportError, classify_block, method_prompt,
)
from openparl_extractor.schema import NonBlank, PositiveId


Outcome = Literal["correct", "incorrect", "abstention", "structure_error", "transport_error"]
OUTCOMES: tuple[Outcome, ...] = (
    "correct", "incorrect", "abstention", "structure_error", "transport_error",
)


class ReplayResponse(FrozenModel):
    raw: str | None = None
    transport_error: NonBlank | None = None

    @model_validator(mode="after")
    def validate_response(self) -> Self:
        if (self.raw is None) == (self.transport_error is None):
            raise ValueError("replay requires either raw response or transport_error")
        return self


class EvaluationCase(FrozenModel):
    block: BlockInput
    expected: Category
    responses: Annotated[tuple[ReplayResponse, ...], Field(min_length=1)]


class ReplayDataset(FrozenModel):
    version: Literal["block-classification-replay-v0.1"]
    label_status: Literal["synthetic", "unreviewed"]
    attempts_per_case: PositiveId
    output_contract: OutputContract = DEFAULT_CONTRACT
    classification_method: ClassificationMethod = DEFAULT_METHOD
    cases: Annotated[tuple[EvaluationCase, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def validate_cases(self) -> Self:
        method_prompt(self.output_contract, self.classification_method)
        if self.classification_method == DEFAULT_METHOD and any(c.block.assignment for c in self.cases):
            raise ValueError("assignment context requires source-function-v0.2")
        ids = [case.block.block_id for case in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError("block IDs must be unique")
        if any(len(case.responses) != self.attempts_per_case for case in self.cases):
            raise ValueError("every block requires exactly attempts_per_case replay responses")
        return self


class ReplayTransport:
    def __init__(self, response: ReplayResponse) -> None:
        self.response = response

    def complete(self, request: ClassificationRequest) -> str:
        if self.response.transport_error is not None:
            raise TransportError(self.response.transport_error)
        if self.response.raw is None:
            raise ValueError("replay response missing")
        return self.response.raw


class AttemptRecord(FrozenModel):
    block_id: NonBlank
    attempt: PositiveId
    input_sha256: NonBlank
    document_id: PositiveId
    source_text_sha256: NonBlank
    text_representation: NonBlank
    ranges: tuple[SourceRange, ...]
    language: Language
    expected: Category
    predicted: Category | None
    outcome: Outcome
    error: str | None
    classification_method: ClassificationMethod = DEFAULT_METHOD
    assignment: tuple[SourceRange, ...] = ()


def evaluate_attempt(
    case: EvaluationCase, index: int, contract: OutputContract = DEFAULT_CONTRACT,
    method: ClassificationMethod = DEFAULT_METHOD,
) -> AttemptRecord:
    result = classify_block(case.block, ReplayTransport(case.responses[index]), contract, method)
    outcome: Outcome = result.error_kind or (
        "abstention" if result.category == "unclear"
        else "correct" if result.category == case.expected else "incorrect"
    )
    block = result.block
    return AttemptRecord(
        block_id=block.block_id, attempt=index + 1, input_sha256=result.input_sha256,
        document_id=block.source.document_id, source_text_sha256=block.source.text_sha256,
        text_representation=block.source.text_representation, ranges=block.ranges,
        language=block.language, expected=case.expected, predicted=result.category,
        outcome=outcome, error=result.error, classification_method=method, assignment=block.assignment,
    )


def summarize(records: list[AttemptRecord]) -> dict[str, object]:
    counts = Counter(record.outcome for record in records)
    confusion = Counter((record.expected, record.predicted) for record in records)
    return {
        "denominator": len(records),
        "blocks": len({record.block_id for record in records}),
        "counts": {outcome: counts[outcome] for outcome in OUTCOMES},
        "confusion": {
            expected: {
                predicted: confusion[expected, predicted] for predicted in CATEGORIES
            } for expected in CATEGORIES
        },
    }


def evaluate_replay(dataset: ReplayDataset) -> dict[str, object]:
    records = [
        evaluate_attempt(case, index, dataset.output_contract, dataset.classification_method)
        for case in dataset.cases for index in range(dataset.attempts_per_case)
    ]
    return {
        "version": dataset.version, "mode": "offline_replay",
        "output_contract": dataset.output_contract,
        "classification_method": dataset.classification_method,
        "label_status": dataset.label_status, "attempts_per_case": dataset.attempts_per_case,
        "total": summarize(records),
        "by_category": {
            category: summarize([r for r in records if r.expected == category])
            for category in CATEGORIES
        },
        "by_language": {
            language: summarize([r for r in records if r.language == language])
            for language in ("de", "fr", "it")
        },
        "records": [record.model_dump(mode="json") for record in records],
    }
