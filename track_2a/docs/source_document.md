# SourceDocument (Evidence Layer, Phase 1)

Deterministic, model-free representation of a PDF. Code: `source_document.py`, `pdf_extraction.py`.

## Experimental freeze

Evidence reconstruction and candidate contracts are experimental, not a reliable converter
or a completed Track acceptance. The latest bounded classification experiment made two
requests; both failed local integrity validation. No further calls were made or authorized.
Semantic document coverage remains unverified; technical validity is not field completeness.
The separate selection/coverage contract is documented in `selection_coverage.md`.
Private source documents, references, requests, responses and evaluation details remain
only in ignored local `output/`; repository tests use synthetic source text.

## Model

`SourceDocument` → `pages[]` → `blocks[]` → `spans[]`

- Document: `document_id`, `affair_id`, `sha256` (of the PDF bytes), `extraction_method`, `warnings[]`.
- Span: `id` (`p003-b012-s004` = page-block-span, 1-based), physical `page`, exact `text`, optional `bbox`, `source` (`native_text`/`ocr`/`api_text`).
- Block = PyMuPDF text block; span = one text line. Pages are never merged before span creation.
- Warnings: `empty_page`, `no_text_layer` (image-only page, OCR needed; OCR is not implemented). Every page has spans or a warning (validated).

## Reconstruction

`reconstruct_text(document, span_ids)` derives original text from an ordered id list. Ids must exist and be in strictly ascending document order. Separators: `\n` within a block, `\n\n` across blocks or pages. Text comes only from spans.

## Decision

Evidence-first: a later model step only selects span ids and closed categories; code copies original text from spans and builds provenance. The model never emits `original` text or quotes; unknown stays unknown.

## CLI

`uv run openparl-extractor extract-source file.pdf --document-id 922604 [--affair-id N] [--out-dir output/source]`

Output goes to `output/` (git-ignored). PDFs are not committed (redistribution rights unclear).

## Phase 2: span-id selection

`span_selection.py`, `selection_run.py`; CLI `select-fields source.json... [--out-dir output/selection]` (needs `LLM_NAME`, `LLM_BASE_URL`, `LLM_API_KEY`; max 12 requests).

One request per field (`title`, `submitters`, `question_or_request`). The model returns only `status` (known/partial/unknown), `reason`, and `blocks[]` of `span_ids` (+ `kind` question/request or null for `question_or_request`). Code validates (ids exist, ascending without overlap, status/id consistency, kind enum, title = one block) and derives text via `reconstruct_text`, whitespace-normalised; the leading question number is removed for `question_or_request`. No retry/repair/fallback; failed requests are `failed`, never `unknown`. Each request logs payload hash, sent body (no key), raw response, usage and duration under `output/`. Technical validity only — correctness is reviewed manually.

## Phase 2b: local-id ranges (`range-v1`)

`range_selection.py`, `range_run.py`; CLI `select-ranges source.json... [--out-dir output/selection_range_v1]` (new directory per run, max 12 requests).

Motivation (run 1, id lists): 12 requests, 3 valid. 5 truncated at `max_tokens` (objects cut after endless whitespace), 3 invented span ids, 1 order error. Baseline logs stay untouched in `output/selection/`.

Changes: short local ids `L1…Ln` (unique per document, deterministic mapping to stable span ids); the model returns closed `first`/`last` ranges, expanded by code across block/page boundaries (no `reason`); status `known`/`partial`/`not_found` (`not_found` = not found, not proof of absence). Compact one-line JSON requested; `max_tokens` per field (title 300, submitters 600, questions 2048); no stop sequences. Parsing accepts one complete JSON value followed by whitespace only (also with `finish_reason=length`, both recorded); truncated JSON, extra prose, unknown/reversed/overlapping/unordered ranges, title with >1 range fail. No retry/repair/sorting/merging. Titles >3 lines or >300 chars get `needs_review` (heuristic only).

Guarantees are syntactic and local. The schema lists the presented ids as enums, but server-side constrained decoding is NOT demonstrated (run 1 output ignored the schema's property order); local validation is mandatory.

## Phase 3: Kandidatengenerator (offline, Development-Test)

`candidates.py` erzeugt deterministisch Kandidaten für `title`, `submitters`, `question_or_request` mit exakten
Zeichen-Offsets auf unveränderte Span-Texte (`Anchor(span_id, offset)`); Text und Provenienz (Spans, Seiten) werden nur aus den
Offsets abgeleitet (`slice_text`), ohne Dehyphenierung oder Wortergänzung. Regeln (de/fr/it, Layout-/Schlüsselwort-basiert):
Titel-Label, Titel in Klammern/nach Gedankenstrich nach Instrumenttyp; Einreicherlabel/Amtsbezeichnung/Instrument + Name (innerhalb
einer Zeile); lückenlose Nummernfolge 1..n vor dem Antwortteil, Unterfragen a., b., ... separat markiert (`subpart`). Mehrere
Kandidaten sind normal; es wird nichts als korrekt ausgewählt, fehlende Felder stehen in `missing`.
CLI: `generate-candidates <source.json>...` (v1-Ausgabe `output/candidates/`). Ein Kandidat ist keine Aussage über Korrektheit.

### candidates-v2: Arbeitsannahmen dieses Offline-Development-Schritts

Keine allgemeine Garantie, keine unabhängige Generalisierung: dieselben vier bekannten Dev-Dokumente,
keine API-Hints, Modellcalls oder Promptänderungen. Alte Kandidaten/Snapshots bleiben unverändert.
CLI schreibt jetzt standardmäßig nach `output/candidates_v2/`.

- Originaltreue: unveränderte PDF-Spans einschließlich Trennstrichen, Soft-Hyphen und Steuerzeichen.
  Coverage strikt nur mit Whitespace-Normalisierung und Entfernung führender Fragenummern;
  Rejoin ausschließlich diagnostisch im Bewertungsartefakt, nicht im Generator.
- `Candidate.kind`: `heading`, `name_only`, `context`, `main_item`, `subitem`.
  `role=potential_submitter` ist ein Suchhinweis, keine bestätigte Rolle. Name und vollständige
  zugehörige Source-Zeile werden getrennt angeboten. Namenregex kann unvollständig/falsch sein;
  Kontext bleibt erhalten, kein Referenztext wird zum Zuschneiden verwendet. Folgt dem
  Regex-Treffer ein weiterer Namenstoken, entfällt der unsicher abgeschnittene Name-only-Kandidat.
- Markerlose Titel: zusätzliche isolierte Blöcke auf Seite 1, im oberen 40% der Textausdehnung,
  mindestens vier Wörter, höchstens drei Zeilen/300 Zeichen, Abstand ober-/unterhalb mindestens
  halbe Zeilenhöhe. Labels, Instrumenttypen, nummerierte Items, Amts-/Einreichersätze, Satzende
  mit Punkt/Doppelpunkt/Semikolon werden ausgeschlossen; Suche endet vor Begründungs-/Antwortmarkern.
  Grenzen betreffen nur diese Heuristik, nicht fachliche Titelgültigkeit. Bbox fehlt/uneindeutig:
  `missing`/`needs_review`; mehrere Titel: `ambiguous`, keine Auswahl.
- Source-Offsets bleiben `start`/`end` (exklusives Ende), Span-IDs/Seiten und rekonstruierter Text.
  Fragenregeln und Haupt-/Unterfrageninhalte bleiben gegenüber v1 unverändert.
- Referenzabweichungen (`\x07`, `2025 1`, Unterfragenlabels), Name-only-vs-Kontext und
  approved-vs-draft bleiben offene Referenz-/Policy-Fälle. Match-Metadaten gehören ausschließlich
  in getrennte Offlinebewertungen, niemals in Generatorinput oder Kandidatenentscheidung.

Ein späterer Auswahltest müsste Titelalternativen und Name/Kontext unterscheiden, Einreicherrolle
prüfen sowie vollständige Haupt-/Unterfragen ohne doppelte Überlappung wählen. Diese Leistungen sind
hier nicht erbracht. Vor Referenzvergleich werden Code, Regeln, Source-Inputs und Kandidaten gehasht.

### candidates-v2: begrenzter Live-Auswahltest

`select-candidates` verwendet ausschließlich die vier gehashten Kandidatensätze aus
`output/analysis/candidates_v2_snapshot_final/`, nicht komplette PDFs, API-Hints oder alte
Modellantworten. Zwei unabhängige Läufe, jeweils vier Dev-Dokumente mal drei Felder:
**genau 24 Versuche**, keine Wiederholung/Repair/Fallback/Judge/best-of. Neuer Ausgabeordner
`output/selection_candidates_v2_runs/` muss fehlen; existierender Ordner wird nicht überschrieben.
Key nur aus Env, ausschließlich bisheriger CSCS-Endpoint/Apertus, Timeout 120s.

Requestlokale IDs `C1..Cn`, nur `status` (`known`, `partial`, `needs_review`, `unknown`) und
`candidate_ids[]`, keine Ranges, freien Gründe, Texte oder Kategorien. `unknown` braucht leere
IDs und beweist keine Abwesenheit; `known`/`partial` brauchen IDs, `needs_review` darf leer sein
oder einen belegten Teil enthalten. Modell bestätigt hier keine unabhängig geprüfte Rolle.
Frage-/Forderungsart wird gemäß IDs-/Status-only-Ausgabe **nicht erhoben**; daher können
inhaltliche Fragenmatches keine vollen fachlichen Feldpunkte mit Pflichtart belegen.

Lokale Prüfung: geschlossene ID-Menge, Statuskonsistenz, ein Titelmaximum, keine gleichen IDs,
Quellenreihenfolge, keine Offsetüberlappung (auch Name/Kontext und Haupt-/Unterfrage),
keine identischen Name-only-Werte an mehreren Quellenstellen. Keine Sortierung oder
semantische Zusammenführung der Auswahl. Text wird mit unveränderten Offsets rekonstruiert;
Kandidatenkind/-rolle, Seiten, Span-IDs und Offsetanker bleiben als Provenienz erhalten.

Sampling: temperature 0, top_p 1; max_tokens title 300, submitters 600, questions 1200
(höchstens 16 kurze Dev-Kandidaten-IDs, großzügiger JSON-Spielraum unter bisherigem 2048).
Keine Stop-Sequenzen/guided_json. JSON-Schema mit tatsächlichen ID-Enums ist nur Anforderung,
kein Nachweis serverseitigen Constrained Decodings. Vollständiges JSON + trailing Whitespace
wird auch bei `finish_reason=length` akzeptiert, abgeschnittenes JSON bleibt failed.

Pro Versuch: tatsächlich gesendeter Body ohne Auth, Payload-/Inputhash, vollständige Raw-Response,
finish_reason, Usage, Dauer, Fehler und technisches Ergebnis. HTTP-Fehler zählen ebenfalls,
keine Ersatzcalls. Übersicht enthält Originaltexte, Quellenanker und Kandidatenrollen.
Technische Validität, Auswahlübereinstimmung zweier Läufe und diagnostischer v0.1-Referenzvergleich
werden separat berichtet; Übereinstimmung beweist keine fachliche Richtigkeit.

### Transport v3: Kategorie-/Statusbelege, einmaliger Dev-Lauf

Vor Lauf eingefroren, Development-Test nach Kenntnis der v2-Fehler, keine Generalisierung.
`prepare-candidates-v3` erzeugt `output/analysis/candidate_selection_v3_setup/` mit Inputs,
allen tatsächlichen Request-Bodies, SourceDocuments, Code/Tests/Doku und SHA-256-Manifest.
`select-candidates-v3` liest nur diesen Freeze: einmal vier bekannte Dev-Dokumente mal drei
Felder, maximal zwölf gesendete Attempts, keine zweite Wiederholung/Ersatzcalls. Zielordner
`output/selection_candidates_v3/` darf nicht existieren. Frühere Inputs/Logs bleiben unverändert.

Originalwerte aus eingefrorenen candidates-v2 bleiben wort-/zeichengenau. Kontextkandidaten
werden **nicht** als Ersatzwerte auswählbar. Deterministische neue Evidence-IDs:
für Namen der vollständige zugehörige Source-Block (auch mehrzeiliges `Anfrage eingereicht:`);
für Frageblöcke unveränderte Kandidatenpassage einschließlich Präfix ihrer ersten Source-Zeile,
für Titel die unveränderten Titeloffsets. Herkunft/Offsets/Span-IDs/Seiten für jede Ergänzung.
Keine Referenzwerte, API-Hints oder alten Modellantworten im Input.

Exakt gleiche Name-only-Werte dürfen nur bei gleicher expliziter Einreicher-Kontextpassage
(Whitespace-normalisiert identischer Block mit Label/Einreichungs-/Interpellationsmarker)
eine Gruppe mit mehreren Quellen bilden. Namensgleichheit allein reicht nicht. Unterschiedliche
Kontexte/Rollen bleiben getrennte Kandidaten; keine Personenidentität daraus behaupten.
Wiederholung desselben ungruppierten Namens wird bei der Auswahl abgelehnt. In 922604 bleiben
Einreichersatz und Antwort-Wiederholung daher getrennt; der explizite Einreichersatz ist auswählbar.

Ausgabe kompakt, **status zuerst**, danach `reason`, `status_evidence`, `items`:
`{"status":"known","reason":null,"status_evidence":[],"items":[{"id":"C1","category":"question","evidence":["E1"]}]}`
Nur geschlossene IDs/Kategorien/Codes, keine frei produzierten Originaltexte oder Gründe.
- Titel: höchstens ein Item, `category=null`, zugeordneter Titelbeleg.
- Einreicher: `submitter` nur mit zugeordnetem tatsächlichen Rollen-/Einreicherkontext;
  ein Name oder Code-Hinweis ist kein Rollenbeweis. Echte Ambiguität: null + needs_review.
- Fragen: je vollständigem Block `question`/`request`, bei echter Ambiguität null + needs_review;
  jede Kategorie verweist auf zugeordneten Quelltext, Fragen-/Unterfragenüberlappung verboten.
- known: mindestens ein Item, reason null, keine Statusbelege; keine Vollständigkeitsbehauptung
  aus bloßer Namens-/ID-Existenz. Zugeordnete unbenannte Gruppe widerspricht known.
- partial: mindestens ein Item und zugeordneter Statusbeleg; reason `unenumerated_members`
  benötigt expliziten Gruppenhinweis (z.B. et consorts), sonst `incomplete` mit belegbarer Grenze.
  Keine erfundenen Mitglieder oder unbelegte Abwesenheit, Grenzen fachlich separat prüfen.
- needs_review: reason `ambiguous`, null-Kategorien/leer ausgewählte Items zulässig;
  vorhandene Statusbelege müssen zur Auswahl gehören.
- not_found: reason `not_found`, leere Items/Statusbelege. Nur Nichtfund **in diesen Inputs**,
  keine negative Behauptung über das gesamte Dokument; keine Gutschrift für Abwesenheit ohne Prüfung.

Validator prüft Kategorien-/Feldkompatibilität, Beleg-IDs/Zuordnung, Statuskonsistenz,
Gruppenhinweise, Quellenreihenfolge/Offsetdisjunktheit, keine ID-/Personenduplikate,
Originaltext und Evidenzprovenienz exakt gegen SourceDocument. Keine Sortierung, Reparatur,
Dehyphenierung oder semantische Zusammenführung. Quellenhint und syntaktisch gültige
Belegzuordnung garantieren **nicht** fachliche Kategorien-/Status-/Vollständigkeitsrichtigkeit.

Offlinebefund v2 926587/questions: JSONDecoder.raw_decode scheitert; IDs-Liste beendet,
danach nur Whitespace **innerhalb** eines offenen Objekts, Status/Schlussklammer fehlen.
Nicht Fall "vollständiges JSON plus trailing whitespace". Status-first ist lediglich eine
Hypothese gegen diese Form; Constrained Decoding/Propertyreihenfolge nicht nachgewiesen.

Budgets vor Lauf: title 400, submitters 800, questions 2048. Erwartbare vollständige
Ausgabe umfasst wenige Titel/Personen und höchstens 16 kurze Frage-Items mit Kategorien/Evidence-IDs
(je etwa 60–90 Zeichen plus Statusheader). Großzügiger Spielraum für Belege, keine bloße
Budgeterhöhung als Lösung des Whitespace-Abbruchs. temperature 0, top_p 1, Timeout 120s,
bisheriges CSCS/Apertus, keine Stop-Sequenzen/guided_json/Retry/Repair/Judge/Fallback.
Abgeschnittene Objekte bleiben failed, vollständiges JSON mit ausschließlich nachfolgendem
Whitespace bleibt parsbar auch bei finish_reason length (Rohfinish getrennt erhalten).

Bewertung nach Lauf: zwölf Felder, failed=0; Werte, Rolle/Frageart, Status, Belegstützung und
Vollständigkeit für volle Punkte. Strikter Originalvergleich getrennt von diagnostischem Rejoin;
Referenzabweichungen/approved-vs-draft bleiben offen. Verbesserung gegenüber v2 getrennt als
Inhalts-, Status-, Kategorien- oder bloße Transportänderung; keine Acht-Felder-/Track-Abnahme.

### v4: ausschließlich Offline-Vertragskorrektur

`candidate_v4.py` nutzt unveränderte eingefrorene candidates-v2-Werte und die v3-Quellkontexte.
Historische v2/v3-Parser, Inputs, Logs und Wertungen werden nicht geändert. Kein Live-Kommando
für v4; Offline-Diagnose und vorbereitete Inputs/Bodies unter `output/analysis/v4_contract_diagnostic/`.

Transportfix: `known` darf positive `status_evidence` haben. Existenz, Auswahlzuordnung und
Offset-/Quellentreue bleiben zwingend; positive Evidenz allein beweist keine Vollständigkeit.
Property-Reihenfolge wird weder geparst noch als fachliches Kriterium validiert. Keine automatische
Sortierung, Deduplizierung, Status-/Kategorienkorrektur oder Freitextproduktion.

Kandidateninput-Fix, **keine Modellleistung**:
- Fragen `kind=question/request/null` separat von `block_role=main_item/subitem`.
  Konservative Regeln de/fr/it: Fragezeichen **und** explizites Fragewort am Satz-/Teilsatzanfang
  oder begrenzte Inversionsform; request nur bei expliziter Aufforderungsformel ohne konkurrierende
  Fragesignale. Sonst null, `ambiguous_or_no_supported_formula`: kann echte Mehrdeutigkeit
  **oder unzureichende Heuristik** sein, keine Behauptung semantischer Unentscheidbarkeit.
  `allowed_kinds` ist geschlossen pro Kandidat; Modell darf weder Art frei ergänzen noch
  bei eindeutig klassifiziertem Kandidaten null liefern. Null braucht needs_review.
  Deklarative Untergliederungslabels werden nicht allein aus Parentmitgliedschaft als Frage klassifiziert.
- Vollständige Hauptblöcke einschließlich Unterfragen bleiben auswählbar; Source-Containment
  erzeugt `parent_id`/`child_ids`. Policy dieses Dev-Vergleichs: zusammengesetzter vollständiger
  Hauptblock entspricht den zwölf ZH-Referenzitems. Eltern- und Unteritem zugleich sind verboten.
  Unteritems allein dürfen kein known für die ausgelassene Hauptfrage behaupten. Keine neue
  disjunkte Unterfragensegmentierung/Word-Ergänzung; falls Schema später andere Unterblöcke verlangt,
  separat klären statt Parenttext still verlieren.
- `group_hints` verbindet Kandidaten- und Evidence-ID mit explizitem unbenanntem Gruppenlimit.
  Bei gewählter benannter Person mit diesem Hinweis sind partial/unenumerated_members und
  zugeordneter Statusbeleg konsistent; known wird abgelehnt, Mitglieder nie erfunden.
  Status wird weiterhin ausgegeben/gewählt, nicht vom Validator repariert.
- Titel `title_role=full_title/heading/heading_fragment/instrument_label`: Fragment durch
  exakte Quell-Containment/Prefixbeziehung zu längerem Titelkandidaten, Volltitelhinweis durch
  vorhandene generische Titelregel, Instrumentlabel durch Präfix. Vollständiger 541615-Titel
  unverändert vorhanden; kein ID-/Referenzwortlaut-Sonderfall. Rollen sind nachvollziehbare
  Kandidatenhinweise, keine allgemeine fachliche Garantie. known+Fragment/Instrumentlabel abgelehnt.

Offline-Fake-Auswahlen prüfen Vertragsfähigkeit, nicht erwartete Apertus-Auswahl.
Historische v3-Rohantworten können unverändert zusätzlich unter v4 geprüft werden; ihre ursprünglichen
Wertungen bleiben failed=0. Separate hypothetische vollständige Auswahlen niemals als Modellleistung
ausgeben. Positive Trefferdaten, Quellenlimits, strikte Referenzkonflikte und diagnostischer Rejoin
bleiben getrennt. Ein späterer maximal zwölf Requests umfassender Lauf benötigt neue Freigabe.

### Freigegebener v4-Einzellauf

`prepare-candidates-v4` kopiert den bestehenden Offline-Freeze unverändert in
`output/analysis/candidate_selection_v4_setup/` und ergänzt Runner/CLI/Loggingtests sowie
wiederverwendete Komponenten. Alle tatsächlichen Bodies/Inputs und Codes gehasht vor erstem Call.
`select-candidates-v4` sendet ausschließlich diese zwölf Bodies, genau einen Dev-Durchlauf
541615/902686/922604/926587 mal drei Felder. Ausgabe `output/selection_candidates_v4/`
muss neu sein. Keine Heuristik-/Promptänderungen, Retry/Repair/Fallback/Judge/best-of, Stop-Sequenzen
oder guided_json. Sampling/Budgets und CSCS/Apertus wie offline vorbereitet, Timeout120s.
Jeder Attempt inklusive HTTP-Fehler zählt; Body ohne Auth, Hashes, Raw, finish, Usage/Zeit,
Validatorfehler und Offsetresultate werden persistiert. Keine Auswahl-/Status-/Kategorienreparatur.
Deterministische Frageart bleibt Codeleistung; Modellwahl/-status separat bewerten.
Nach zwölf Attempts offline Referenzvergleich mit failed=0, Quellenlimit partial ohne Vollpunkt,
strikten/offenen Referenzkonflikten, getrenntem Rejoin und Vergleich gegen Idealfixtures/v2/v3.
Keine weitere Lauf-/Heldoutfreigabe oder Track-Abnahme.
