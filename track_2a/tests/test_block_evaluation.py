import json
import socket
from pathlib import Path

import pytest
from pydantic import ValidationError

from openparl_extractor.block_evaluation import (
    EvaluationCase, ReplayDataset, ReplayResponse, evaluate_replay,
)
from openparl_extractor.cli import evaluate_blocks, main
from test_block_classification import synthetic_block


# Invented texts only; labels exercise the harness, not Apertus semantics.
EXAMPLES = [
    ("de", "question", "1. Welche Kosten erwartet der Regierungsrat?", "Fragen\n"),
    ("de", "request", "Kann der Regierungsrat bitte bis Dezember einen Bericht vorlegen?", ""),
    ("de", "answer", "Zu Frage 1: Welche Kosten? Der Rat rechnet mit zehn Franken.", ""),
    ("de", "reasoning", "Warum weiter warten? Die Verzögerung schadet dem Dorf.", "Begründung\n"),
    ("de", "other", "1. Eingang: 3. Mai 2030. Unterschrift: Person Beispiel.", ""),
    ("de", "unclear", "Die Kosten sind hoch. Welche Lösung? Der Rat soll handeln.", ""),
    ("fr", "question", "1. Quel calendrier le Conseil prévoit-il?", "Questions\n"),
    ("fr", "request", "Le Conseil pourrait-il remettre un rapport avant décembre?", ""),
    ("fr", "answer", "Question 1: Quel calendrier? Les travaux débuteront en juin.", ""),
    ("fr", "reasoning", "Pourquoi attendre encore? Le retard pénalise le village.", "Motifs\n"),
    ("fr", "other", "1. Dépôt: 3 mai 2030. Signature: Personne Exemple.", ""),
    ("fr", "unclear", "Le coût est élevé. Quelle solution? Le Conseil doit agir.", ""),
    ("it", "question", "1. Quali costi prevede il Consiglio?", "Domande\n"),
    ("it", "request", "Il Consiglio potrebbe presentare un rapporto entro dicembre?", ""),
    ("it", "answer", "Domanda 1: Quali costi? Il Consiglio prevede dieci franchi.", ""),
    ("it", "reasoning", "Perché aspettare ancora? Il ritardo danneggia il paese.", "Motivazione\n"),
    ("it", "other", "1. Deposito: 3 maggio 2030. Firma: Persona Esempio.", ""),
    ("it", "unclear", "Il costo è alto. Quale soluzione? Il Consiglio deve agire.", ""),
]


def synthetic_dataset():
    cases = []
    for index, (language, expected, text, previous) in enumerate(EXAMPLES):
        data = synthetic_block(text, language, previous).model_dump()
        data["block_id"] = f"synthetic-{index}"
        cases.append(EvaluationCase(
            block=data, expected=expected,
            responses=(ReplayResponse(raw=json.dumps({"category": expected})),) * 2,
        ))
    return ReplayDataset(
        version="block-classification-replay-v0.1", label_status="synthetic",
        attempts_per_case=2, cases=tuple(cases),
    )


def test_fixed_denominators_and_diagnostic_groups():
    report = evaluate_replay(synthetic_dataset())
    assert report["total"]["denominator"] == 36
    assert report["total"]["blocks"] == 18
    assert report["total"]["counts"] == {
        "correct": 30, "incorrect": 0, "abstention": 6,
        "structure_error": 0, "transport_error": 0,
    }
    assert len(report["records"]) == 36
    assert len({(r["block_id"], r["attempt"]) for r in report["records"]}) == 36
    for group in (*report["by_category"].values(), *report["by_language"].values()):
        assert sum(group["counts"].values()) == group["denominator"]
    assert all(group["denominator"] == 6 for group in report["by_category"].values())
    assert all(group["denominator"] == 12 for group in report["by_language"].values())
    assert report["by_category"]["unclear"]["counts"]["correct"] == 0


def test_wrong_abstention_structure_and_transport_are_distinct():
    data = synthetic_dataset().model_dump()
    data["cases"] = data["cases"][:3]
    responses = [
        [{"raw": '{"category":"answer"}'}, {"raw": '{"category":"unclear"}'}],
        [{"raw": '{"category":"request"}'}, {"raw": '{"category":"request","confidence":1}'}],
        [{"transport_error": "synthetic timeout"}, {"raw": "not json"}],
    ]
    for case, replay in zip(data["cases"], responses):
        case["responses"] = replay
    report = evaluate_replay(ReplayDataset.model_validate(data))
    assert report["total"]["counts"] == {
        "correct": 1, "incorrect": 1, "abstention": 1,
        "structure_error": 2, "transport_error": 1,
    }
    assert report["total"]["denominator"] == 6
    assert report["total"]["confusion"]["question"]["answer"] == 1
    assert report["by_language"]["fr"]["denominator"] == 0
    for record in report["records"]:
        case = next(c for c in data["cases"] if c["block"]["block_id"] == record["block_id"])
        assert record["input_sha256"]
        assert record["document_id"] == case["block"]["source"]["document_id"]
        assert record["ranges"] == list(case["block"]["ranges"])


def test_expected_unclear_with_forced_category_is_incorrect():
    data = synthetic_dataset().model_dump()
    data["cases"] = [data["cases"][5]]
    data["cases"][0]["responses"] = [
        {"raw": '{"category":"question"}'}, {"raw": '{"category":"unclear"}'},
    ]
    report = evaluate_replay(ReplayDataset.model_validate(data))
    assert report["total"]["counts"]["correct"] == 0
    assert report["total"]["counts"]["incorrect"] == 1
    assert report["total"]["counts"]["abstention"] == 1
    assert report["total"]["denominator"] == 2


@pytest.mark.parametrize("language,text,question_context,reasoning_context", [
    ("de", "Warum warten?", "Fragen an den Regierungsrat\n", "Begründung der Forderung\n"),
    ("fr", "Pourquoi attendre?", "Questions au Conseil\n", "Motifs de la demande\n"),
    ("it", "Perché aspettare?", "Domande al Consiglio\n", "Motivazione della richiesta\n"),
])
def test_same_candidate_with_controlled_context(language, text, question_context, reasoning_context):
    cases = []
    for expected, context in [("question", question_context), ("reasoning", reasoning_context)]:
        data = synthetic_block(text, language, previous=context).model_dump()
        data["block_id"] = f"synthetic-context-{language}-{expected}"
        cases.append(EvaluationCase(
            block=data, expected=expected,
            responses=(ReplayResponse(raw=json.dumps({"category": expected})),),
        ))
    dataset = ReplayDataset(
        version="block-classification-replay-v0.1", label_status="synthetic",
        attempts_per_case=1, cases=tuple(cases),
    )
    report = evaluate_replay(dataset)
    assert report["records"][0]["input_sha256"] != report["records"][1]["input_sha256"]
    assert report["total"]["denominator"] == 2
    assert [r["expected"] for r in report["records"]] == ["question", "reasoning"]


@pytest.mark.parametrize("change", ["missing", "extra", "duplicate", "approval", "zero"])
def test_incomplete_or_misrepresented_datasets_rejected(change):
    data = synthetic_dataset().model_dump(mode="json")
    if change == "missing":
        data["cases"][0]["responses"].pop()
    elif change == "extra":
        data["cases"][0]["responses"].append({"raw": '{"category":"question"}'})
    elif change == "duplicate":
        data["cases"][1]["block"]["block_id"] = data["cases"][0]["block"]["block_id"]
    elif change == "approval":
        data["label_status"] = "human_approved"
    else:
        data["attempts_per_case"] = 0
    with pytest.raises(ValidationError):
        ReplayDataset.model_validate(data)


@pytest.mark.parametrize("value", [{}, {"raw": "x", "transport_error": "timeout"}])
def test_replay_response_requires_one_outcome(value):
    with pytest.raises(ValidationError):
        ReplayResponse.model_validate(value)


def test_offline_cli_ignores_llm_env_and_never_connects(monkeypatch, capsys):
    def forbidden(*args, **kwargs):
        raise AssertionError("offline replay must not open sockets")

    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setenv("LLM_API_KEY", "not-a-real-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://invalid.example")
    fixture = Path(__file__).parent / "fixtures" / "block-replay-synthetic.json"
    monkeypatch.setattr("sys.argv", ["openparl-extractor", "evaluate-blocks", str(fixture)])
    assert main() == 0
    report = json.loads(capsys.readouterr().out)
    assert report["mode"] == "offline_replay"
    assert report["label_status"] == "synthetic"
    assert report["total"]["denominator"] == 3


def test_invalid_cli_dataset_has_no_report_or_source_leak(tmp_path, capsys):
    path = tmp_path / "invalid.json"
    path.write_text('{"private_source": "never print this"}', encoding="utf-8")
    assert evaluate_blocks(path) == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert "invalid replay dataset" in output.err
    assert "never print this" not in output.err
    assert evaluate_blocks(tmp_path / "missing.json") == 1


@pytest.mark.parametrize("content", [
    "{not-json", '{"cases":[],"cases":[]}', '{"private_source":"never print this"} trailing',
])
def test_cli_rejects_malformed_or_duplicate_input_without_leak(content, tmp_path, capsys):
    path = tmp_path / "invalid.json"
    path.write_text(content, encoding="utf-8")
    assert evaluate_blocks(path) == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert "Block evaluation input error" in output.err
    assert "never print this" not in output.err


def test_cli_check_config_stays_available(monkeypatch, capsys):
    monkeypatch.setenv("LLM_NAME", "synthetic-model")
    monkeypatch.setenv("LLM_BASE_URL", "https://invalid.example/v1")
    monkeypatch.setenv("LLM_API_KEY", "not-a-real-key")
    monkeypatch.setattr("sys.argv", ["openparl-extractor", "check-config"])
    assert main() == 0
    assert "LLM configuration valid" in capsys.readouterr().out


def test_word_replay_is_explicit_no_fallback_and_unclear_abstains():
    data = synthetic_dataset().model_dump()
    data["cases"] = data["cases"][:2]
    data["output_contract"] = "category-word-v0.1"
    data["cases"][0]["responses"] = [{"raw": " question\n"}, {"raw": '{"category":"question"}'}]
    data["cases"][1]["responses"] = [{"raw": "unclear"}, {"raw": "request"}]
    report = evaluate_replay(ReplayDataset.model_validate(data))
    assert report["output_contract"] == "category-word-v0.1"
    assert report["total"]["counts"] == {
        "correct": 2, "incorrect": 0, "abstention": 1, "structure_error": 1, "transport_error": 0,
    }


def test_function_replay_method_bound_and_unclear_abstains():
    from test_block_classification import synthetic_assigned_block
    data = synthetic_dataset().model_dump()
    data.update(output_contract="category-word-v0.1", classification_method="source-function-v0.2")
    data["cases"] = data["cases"][:1]
    data["cases"][0]["block"] = synthetic_assigned_block().model_dump()
    data["cases"][0]["responses"] = [{"raw": "unclear"}, {"raw": "question"}]
    report = evaluate_replay(ReplayDataset.model_validate(data))
    assert report["classification_method"] == "source-function-v0.2"
    assert all(r["classification_method"] == "source-function-v0.2" for r in report["records"])
    assert report["total"]["counts"]["abstention"] == 1
    assert report["records"][0]["assignment"] == (
        synthetic_assigned_block().model_dump(mode="json")["assignment"]
    )
    data["classification_method"] = "unknown-method"
    with pytest.raises(ValidationError):
        ReplayDataset.model_validate(data)
    data["classification_method"] = "legacy-v0.1"
    with pytest.raises(ValidationError, match="assignment context requires"):
        ReplayDataset.model_validate(data)
