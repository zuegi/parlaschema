import pytest

from openparl_extractor.candidates import Anchor, generate_candidates, slice_text
from openparl_extractor.source_document import (
    Block,
    Page,
    SourceDocument,
    SourceDocumentError,
    Span,
    reconstruct_text,
)

SHA = "0" * 64


def make_document(pages: list[list[list[str]]]) -> SourceDocument:
    """pages -> blocks -> lines; mirrors the Phase-1 id scheme."""
    built = []
    for p, blocks in enumerate(pages, start=1):
        page_blocks = []
        for b, lines in enumerate(blocks, start=1):
            block_id = f"p{p:03d}-b{b:03d}"
            spans = tuple(Span(id=f"{block_id}-s{s:03d}", page=p, text=t) for s, t in enumerate(lines, start=1))
            page_blocks.append(Block(id=block_id, spans=spans))
        built.append(Page(number=p, blocks=tuple(page_blocks)))
    return SourceDocument(document_id=1, sha256=SHA, extraction_method="test", pages=tuple(built))


def texts(document: SourceDocument, field: str) -> list[str]:
    return [c.text for c in generate_candidates(document).candidates if c.field == field]


def test_inner_line_title_german_parenthesized():
    document = make_document(
        [[["883. Anfrage (Neue Abläufe für", "Baugesuche: Welche Wege sind möglich?)"], ["Kantonsrätin Anna Muster, Zürich, hat am 6. Juli folgende Anfrage eingereicht:"]]]
    )
    assert texts(document, "title") == ["Neue Abläufe für\nBaugesuche: Welche Wege sind möglich?"]


def test_french_dash_title_spans_blocks_up_to_reference():
    document = make_document(
        [[["Réponse du Conseil d'Etat"], ["à l'interpellation Marc Dupont et consorts - Mobilité locale : des solutions pour les "], ["villages ? (99_INT_10)"]]]
    )
    assert "Mobilité locale : des solutions pour les \n\nvillages ?" in texts(document, "title")


def test_title_label_to_block_end():
    document = make_document([[["Betreffend"], ["Wartezeiten bei Gesuchen"]]])
    assert texts(document, "title") == ["Wartezeiten bei Gesuchen"]


def test_title_label_and_title_in_same_block():
    document = make_document([[["Betreffend", "Wartezeiten bei Gesuchen"]]])
    assert texts(document, "title") == ["Wartezeiten bei Gesuchen"]


def test_label_excluded_from_submitter_name_inside_line():
    document = make_document([[["Presentata da: Luca Esempio"]]])
    candidates = generate_candidates(document).candidates
    assert [c.text for c in candidates if c.kind == "name_only"] == ["Luca Esempio"]
    assert candidates[0].start.offset == len("Presentata da: ")


def test_multiple_submitters_and_group_marker_noted():
    document = make_document([[["von Anna Muster (SP, Zürich)"], ["von Hans Beispiel (FDP, Bern)"], ["interpellation Marc Dupont et consorts - Sujet"]]])
    result = generate_candidates(document)
    submitters = [c for c in result.candidates if c.kind == "name_only"]
    assert [c.text for c in submitters] == ["Anna Muster", "Hans Beispiel", "Marc Dupont"]
    assert submitters[2].notes == ("unnamed_group_marker",)


def test_numbered_items_and_subitems_are_separate_candidates():
    document = make_document(
        [[["1. Wie viele Gesuche gab es?"], ["2. Welche Schritte gibt es?"], ["a. Schritt eins"], ["b. Schritt zwei"], ["3. Was kostet es?"]]]
    )
    questions = texts(document, "question_or_request")
    assert "Wie viele Gesuche gab es?" in questions
    assert "Schritt eins" in questions and "Schritt zwei" in questions
    assert sum(1 for q in questions if q.startswith(("Wie viele", "Welche", "Was kostet"))) == 3


def test_numbered_item_across_page_break():
    document = make_document([[["1. Wie viele Gesuche"], ["gab es im Jahr"]], [["2025 insgesamt?"], ["2. Zweite Frage?"]]])
    candidate = next(c for c in generate_candidates(document).candidates if c.text.startswith("Wie viele"))
    assert candidate.pages == (1, 2)
    assert candidate.text.endswith("2025 insgesamt?")


def test_answer_section_numbers_not_questions():
    document = make_document(
        [[["1. Erste Frage?"], ["2. Zweite Frage?"], ["Antwort des Regierungsrates"], ["1. Die Antwort lautet ja."], ["2. Und nein."]]]
    )
    questions = texts(document, "question_or_request")
    assert not any("Antwort lautet" in q or "Und nein" in q for q in questions)


def test_background_numbers_without_sequence_are_not_questions():
    document = make_document([[["Im Jahr 2005. Es gab 12. Gesuche"], ["3. Kapitel ohne Folge"], ["Ende"]]])
    result = generate_candidates(document)
    assert texts(document, "question_or_request") == []
    assert "question_or_request" in result.missing


def test_italian_questions_after_intro():
    document = make_document([[["si chiede al Consiglio di Stato:"], ["1. Come valuta il calo?"], ["2. Quali sono le cause?"]]])
    assert texts(document, "question_or_request") == ["Come valuta il calo?", "Quali sono le cause?"]


def test_missing_fields_reported_explicitly():
    result = generate_candidates(make_document([[["Nur Fliesstext ohne Struktur"]]]))
    assert set(result.missing) == {"title", "submitters", "question_or_request"}


def test_offsets_reconstruct_unchanged_text_and_match_span_text():
    document = make_document([[["Presentata da: Luca Esempio"], ["1. Frage eins?"], ["2. Frage zwei?"]]])
    for candidate in generate_candidates(document).candidates:
        assert slice_text(document, candidate.start, candidate.end) == candidate.text
        full = reconstruct_text(document, list(candidate.span_ids))
        assert candidate.text in full


def test_hyphenation_kept_verbatim():
    document = make_document([[["1. Wie lange dauert das Ver-", "fahren im Kanton?"], ["2. Zweite Frage?"]]])
    assert "Wie lange dauert das Ver-\nfahren im Kanton?" in texts(document, "question_or_request")


@pytest.mark.parametrize(
    ("start", "end"),
    [
        (Anchor(span_id="p001-b999-s001", offset=0), Anchor(span_id="p001-b001-s001", offset=2)),
        (Anchor(span_id="p001-b001-s001", offset=99), Anchor(span_id="p001-b001-s001", offset=100)),
        (Anchor(span_id="p001-b001-s001", offset=3), Anchor(span_id="p001-b001-s001", offset=1)),
        (Anchor(span_id="p001-b001-s001", offset=2), Anchor(span_id="p001-b001-s001", offset=2)),
    ],
)
def test_invalid_anchors_rejected(start, end):
    document = make_document([[["Hallo Welt"]]])
    with pytest.raises(SourceDocumentError):
        slice_text(document, start, end)


def test_generation_is_deterministic():
    document = make_document([[["von Anna Muster (SP)"], ["1. Frage?"], ["2. Frage zwei?"]]])
    assert generate_candidates(document) == generate_candidates(document)


def layout_document(headings: list[list[str]]) -> SourceDocument:
    blocks = [["Parlament"], *headings, ["Presentata da: Anna Muster"], ["Ein langer Absatz."]]
    document = make_document([blocks])
    positioned = []
    for index, block in enumerate(document.pages[0].blocks):
        y = 40 + index * 40 if index < len(blocks) - 1 else 600
        spans = tuple(
            span.model_copy(update={"bbox": (80.0, float(y + line * 12), 400.0, float(y + line * 12 + 10))})
            for line, span in enumerate(block.spans)
        )
        positioned.append(block.model_copy(update={"spans": spans}))
    return document.model_copy(update={"pages": (Page(number=1, blocks=tuple(positioned)),)})


@pytest.mark.parametrize("heading", [
    ["Schule unter Druck: bessere Unterstützung nötig"],
    ["Economie circulaire : des solutions durables"],
    ["Scuola sotto pressione: competenze da difendere"],
    ["Schule unter Druck:", "Neue Wege für bessere Unterstützung"],
])
def test_markerless_layout_heading_exact_offsets(heading):
    document = layout_document([heading])
    result = generate_candidates(document)
    candidates = [c for c in result.candidates if c.rule == "title.early-isolated-layout"]
    assert [c.text for c in candidates] == ["\n".join(heading)]
    assert "title" in result.needs_review
    assert all(slice_text(document, c.start, c.end) == c.text for c in result.candidates)
    assert generate_candidates(document) == result


def test_markerless_headings_are_ambiguous_not_selected():
    result = generate_candidates(layout_document([
        ["Bessere Unterstützung für unsere Schulen"],
        ["Neue Wege für bessere Bildung"],
    ]))
    assert len([c for c in result.candidates if c.field == "title"]) == 2
    assert result.needs_review["title"].startswith("ambiguous:")


def test_markerless_title_without_layout_stays_missing():
    result = generate_candidates(make_document([[["Bessere Unterstützung für unsere Schulen"]]]))
    assert "title" in result.missing and "title" in result.needs_review


def test_name_and_context_are_separate_unchanged_candidates():
    document = make_document([[["von Anna Muster (SP, Zürich)"]]])
    candidates = generate_candidates(document).candidates
    assert [(c.kind, c.text) for c in candidates] == [
        ("name_only", "Anna Muster"), ("context", "von Anna Muster (SP, Zürich)"),
    ]
    assert all(c.role == "potential_submitter" for c in candidates)
    assert all(slice_text(document, c.start, c.end) == c.text for c in candidates)


def test_context_remains_when_name_regex_is_incomplete():
    document = make_document([[["von Anna Muster Beispiel Weitere Person (SP, Zürich)"]]])
    result = generate_candidates(document)
    context = next(c for c in result.candidates if c.kind == "context")
    assert not any(c.kind == "name_only" for c in result.candidates)
    assert context.text == "von Anna Muster Beispiel Weitere Person (SP, Zürich)"
    assert "context_not_role_confirmation" in context.notes


def test_soft_hyphen_never_repaired_in_heading():
    document = layout_document([["Neue Wege für bessere Unter\u00adstützung"]])
    candidate = next(c for c in generate_candidates(document).candidates if c.field == "title")
    assert "\u00ad" in candidate.text
