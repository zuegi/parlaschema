import io
import json
import urllib.error

import pytest

from openparl_extractor import quote_anchor_run as runner
from openparl_extractor.quote_anchor import (
    AnchorError, build_stream, normalize, parse_selection, resolve, search_mapping,
)
from openparl_extractor.source_document import Block, Page, SourceDocument, Span, reconstruct_text


def document(pages):
    return SourceDocument(
        document_id=7, sha256="a" * 64, extraction_method="synthetic",
        pages=tuple(Page(number=p, blocks=(Block(
            id=f"p{p:03d}-b001",
            spans=tuple(Span(id=f"p{p:03d}-b001-s{s:03d}", page=p, text=text)
                        for s, text in enumerate(lines, 1)),
        ),)) for p, lines in enumerate(pages, 1)),
    )


def selection(*pairs):
    return parse_selection(json.dumps({"blocks": [{"start": a, "end": b} for a, b in pairs]}))


def test_exact_short_and_subquestions_in_parent():
    doc = document([["1. What changes?", "a) First? b) Second?", "2. What changes next?"]])
    stream = build_stream(doc)
    result = resolve(stream, selection(("1. What changes?", "b) Second?"),
                                       ("2. What changes next?", "2. What changes next?")))
    assert result[0]["text"] == "1. What changes?\na) First? b) Second?"
    assert result[1]["text"] == "2. What changes next?"
    assert stream.original == reconstruct_text(doc, list(doc.spans_by_id()))


def test_cross_page_anchor_and_original_mapping():
    doc = document([[" \t1. Why\nnow?"], ["a) How?\t b) When?  "]])
    stream = build_stream(doc)
    result = resolve(stream, selection(("Why now? a)", "b) When?")))[0]
    assert result["text"] == "Why\nnow?\n\na) How?\t b) When?"
    assert result["pages"] == [1, 2]
    assert result["spans"][0]["local_start"] == 5
    assert [page["text"] for page in stream.pages] == ["1. Why now?", "a) How? b) When?"]
    assert " ".join(page["text"] for page in stream.pages) == stream.search
    assert normalize(result["text"]) == stream.search[result["search_start"]:result["search_end"]]


def test_mapping_whitespace_hyphens_bel_unicode_unchanged():
    text = " \tUn-\nchanged\u00ad \x07 café  \nend "
    search, mapping = search_mapping(text)
    assert search == "Un- changed\u00ad \x07 café end"
    assert text[mapping[0][0]:mapping[-1][1]] == "Un-\nchanged\u00ad \x07 café  \nend"
    assert mapping[3] == (5, 6)
    assert search_mapping("") == ("", ())
    assert search_mapping(" \t") == ("", ())


@pytest.mark.parametrize("pairs", [
    (("missing", "End"),), (("Start", "missing"),),
    (("End", "Start"),), (("Start", "End"), ("Middle", "End")),
    (("Middle", "End"), ("Start", "Middle")),
    (("Start Middle", "Start"),),
    ((" ", "End"),),
])
def test_invalid_ranges(pairs):
    with pytest.raises(AnchorError):
        resolve(build_stream(document([["Start Middle End"]])), selection(*pairs))


@pytest.mark.parametrize("text", ["Start End Start End", "Start Start End", "Start End End"])
def test_repeated_anchors_always_ambiguous(text):
    with pytest.raises(AnchorError, match="ambiguous"):
        resolve(build_stream(document([[text]])), selection(("Start", "End")))


@pytest.mark.parametrize("content", [
    '{"blocks":[', '{"blocks":[]} extra', '```json\n{"blocks":[]}\n```',
    '{"blocks":[],"extra":0}', '{"blocks":[],"blocks":[]}',
    '{"blocks":[{"start":"","end":"x"}]}', '{"blocks":[{"start":4,"end":"x"}]}',
])
def test_strict_json(content):
    with pytest.raises(ValueError):
        parse_selection(content)


def test_trailing_whitespace_empty_not_absence_and_twelve_pair_shape():
    assert parse_selection('{"blocks":[]} \n\t').blocks == ()
    pairs = [(f"[{i}]. What change do we need today?", f"When will measure {i} be ready now?")
             for i in range(1, 13)]
    doc = document([[f"{start} a) Who? b) How? {end}" for start, end in pairs]])
    assert len(resolve(build_stream(doc), selection(*pairs))) == 12
    assert len(selection(*pairs).model_dump_json()) < runner.MAX_TOKENS * 4


class FakeClient:
    def __init__(self, content='{"blocks":[]}', finish="stop"):
        self.calls = []
        self.raw = json.dumps({"choices": [{"finish_reason": finish, "message": {"content": content}}],
                               "usage": {"completion_tokens": 20}})

    def complete(self, body):
        self.calls.append(body)
        return self.raw


def test_fake_http_logging_exact_body_no_auth():
    doc = document([["1. Why?"]])
    body = runner.request_body(doc)
    client = FakeClient('{"blocks":[{"start":"1. Why?","end":"1. Why?"}]} \n')
    record = runner.run_one(client, doc, body)
    assert record["outcome"] == "localized" and record["result"][0]["text"] == "1. Why?"
    assert record["raw_response"] == client.raw and record["usage"]["completion_tokens"] == 20
    assert record["finish_reason"] == "stop" and record["seconds"] >= 0
    assert client.calls == [record["request_body"]]
    assert record["sent_body_sha256"] == runner.digest(runner.wire(body))
    assert "Authorization" not in json.dumps(record)
    assert not {"stop", "guided_json", "response_format"} & body.keys()
    assert "p001-b001" not in body["messages"][1]["content"]


@pytest.mark.parametrize("content,finish", [('{"blocks":[]}', "length"), ('{"blocks":[', "stop")])
def test_truncation_no_retry(content, finish):
    doc = document([["Why?"]])
    client = FakeClient(content, finish)
    result = runner.run_one(client, doc, runner.request_body(doc))
    assert result["outcome"] == "failed" and result["result"] is None
    assert len(client.calls) == 1 and result["raw_response"]


def test_http_error_logged_no_retry():
    class Client:
        calls = 0

        def complete(self, body):
            self.calls += 1
            raise urllib.error.HTTPError("https://example.test", 503, "unavailable", {},
                                         io.BytesIO(b'{"error":"unavailable"}'))

    doc = document([["Why?"]])
    client = Client()
    record = runner.run_one(client, doc, runner.request_body(doc))
    assert client.calls == 1 and record["raw_http_error"] == '{"error":"unavailable"}'
    assert record["error"] == "HTTPError: HTTP 503"


def test_actual_http_bytes_endpoint_timeout_and_no_retry(monkeypatch):
    calls = []
    doc = document([["Synthetic question?"]])
    body = runner.request_body(doc)

    def urlopen(request, timeout):
        calls.append((request, timeout))
        return io.BytesIO(FakeClient().raw.encode())

    monkeypatch.setattr(runner.urllib.request, "urlopen", urlopen)
    record = runner.run_one(runner.HttpClient("synthetic-not-a-secret"), doc, body)
    request, timeout = calls[0]
    assert len(calls) == 1 and timeout == 120 and request.full_url == runner.ENDPOINT
    assert request.data == runner.wire(body)
    assert runner.digest(request.data) == record["sent_body_sha256"]
    assert "synthetic-not-a-secret" not in json.dumps(record)


def test_freeze_four_attempts_no_overwrite_and_tamper(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    for did in runner.DOCUMENTS:
        doc = document([["Why?"]]).model_copy(update={"document_id": did})
        (source / f"{did}.source.json").write_text(doc.model_dump_json())
    artifacts = tmp_path / "private"
    runner.prepare(source, artifacts)
    client = FakeClient()
    records = runner.run(client, artifacts)
    assert len(records) == len(client.calls) == 4
    for did in runner.DOCUMENTS:
        sent = (artifacts / "live" / f"{did}.sent.json").read_bytes()
        record = json.loads((artifacts / "live" / f"{did}.result.json").read_bytes())
        assert runner.digest(sent) == record["sent_body_sha256"]
    with pytest.raises(FileExistsError):
        runner.run(client, artifacts)
    assert len(client.calls) == 4
    (artifacts / "freeze" / "541615.body.json").write_text("{}")
    with pytest.raises(AnchorError, match="changed"):
        runner.load_frozen(artifacts)
