# Selection/coverage: freigegebener einzelner Dev-Livetest

Genau ein Durchlauf, maximal zwölf Attempts: vier bestehende Dev-PDFs541615,902686,922604,926587
mal title/submitters/question_or_request. Jeder gesendete Attempt zählt, auch HTTP-/Schemafehler.
Kein Retry/Repair/Fallback/Judge/best-of/Heldout. Alte Inputs/Logs/Referenzen unverändert.

Minimaler Runner `selection_coverage_live.py` nutzt unverändert eingefrorene Inputs aus
`output/analysis/selection_coverage_v1_offline/snapshot/`.
Vor erstem Call prepare friert tatsächliche Bodies, Prompts, Schema, Code/Tests/Doku und
Inputbytes unter `output/analysis/selection_coverage_v1_live_setup/` ein/hash.
Keine Kandidaten-/Klassifikatoränderung.

Modell liefert nur items{id,evidence,interpretation?}: vollständige Kandidatenwerte wählen,
submitter-Rollen nur mit eigenem explizitem Kontext, keine globale Status-/Vollständigkeitsaufgabe.
Klare supplied Frageart übernimmt Code; Interpretation dafür null/fehlend, nicht redundant.
Heuristische Lücke bleibt offen; keine null→echte-Ambiguität oder unbelegte Interpretation.
Parent/Child/Duplikation/Rollen-/Offsetfehler unverändert ablehnen, keine Reparatur.

Apertus swiss-ai/Apertus-v1.5-70B, CSCS, temp0/top_p1/timeout120s, Budgets400/800/2048.
Bestehender HTTPClient lädt Key ausschließlich aus lokaler Config; kein Auth im Log.
Kein stop/guided_json. Vollständiges JSON+nur trailing whitespace parsebar; Truncation failed.
Dateien in neuem `output/selection_coverage_v1_live/`:
actualBody/Hash/Inputhash, Raw/HTTPError, finish/Usage/Zeit, Validierungsfehler,
Originalwerte/Provenienz, Kategorienherkunft und getrenntes Abdeckungsprotokoll.
Alle Felder bleiben semantic_coverage=unverified, semantic_review=null.

Einmalige Reproduktion nur bei vorliegender Freigabe:

```sh
uv run python -m openparl_extractor.selection_coverage_live prepare
uv run python -m openparl_extractor.selection_coverage_live live
```

Keine bestehenden Outputordner überschreiben. Offlinebewertung aller zwölf Felder trennt
Integrität, Werte/Originaltreue/Rollen/Codeart, fehlende/falsche Zusätze/Referenzkonflikte,
unverifizierte semantische Dokumentabdeckung und nicht gelieferten Domainstatus.
Keine Domainvollpunkte oder 80%-Gate aus Integrität. Diagnose failed-Rawwerte separat.
Referenzen read-only, Rejoin/20251/BEL/approved-vs-draft-Konflikte weiterhin offen.
Nach maximal zwölf Attempts+Bewertung stoppen, keine neue Livefreigabe ableiten.
