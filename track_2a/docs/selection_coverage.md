# Schlanker Auswahltransport und separates Abdeckungsprotokoll (offline)

`selection-coverage-v1-offline` verwendet unveränderte eingefrorene v4-Kandidatenwerte,
SourceOffsets, Kontext-IDs und Frageartheuristik. Kein neuer Kandidatengenerator oder Domainumbau.

Transport: `{"items":[{"id":"C1","evidence":["E1"],"interpretation":"submitter"}]}`.
Titel und eindeutig klassifizierte Fragen benötigen keine `interpretation`.
Leere Auswahl: `{"items":[]}`. Kein globaler known/not_found/reason-Status.
Unbekannte IDs, doppelte Items/Personen, ungeeignete Rollenbelege, falsche Offset-/Kontextdaten,
Quellenreihenfolge und Parent/Subitem-Overlaps bleiben Fehler. Keine Reparatur oder Umsortierung.
Vollständiges JSON mit trailing whitespace parsbar; Truncation abgelehnt.

Ergebnis enthält getrennt:

- `selection_integrity` und operative `selection_state` (`selection_present`/`no_selection`);
- `original_values` mit unveränderten Texten/Quellen, keine freie Textgenerierung;
- `categories`: `code-derived` für eindeutige supplied question/request, ansonsten eigene
  Modellrolleninterpretation oder ausdrücklich offene Heuristiklücke;
- `coverage`: Inputversion/-hash und Parenthash, vollständiges **SourceDocument**-Seiteninventar,
  tatsächlich vorgelegte Kandidaten-/Kontextbereiche, nicht vorgelegte Quellseiten, Warnungen,
  ausgewählte/nicht ausgewählte Kandidaten mit Parent/Child-Beziehungen, Gruppenlimits,
  unklassifizierte Kandidaten und offene Interpretationen.

Inventarisierte SourceDocument-Seiten sind kein Beweis, dass sämtliche physischen PDF-Seiten
vorliegen (`pdf_page_count_verified=false`); leere/gescannte Seiten und OCR-/Extraktionsgrenzen
bleiben sichtbar. Vorlegen aller Kandidaten belegt keine Modellaufmerksamkeit. Prüfung aller
Inputanker belegt weder Generatorrecall noch vollständige fachliche Feldabdeckung.
`model_attention_verified=false`, `semantic_coverage=unverified`, `semantic_review=null` immer.
Unbenannte Gruppen werden auch bei leerer Personenwahl gezeigt, niemals Personen ergänzt.

Heuristisch unklassifizierte Frageart bedeutet **nicht** nachgewiesene echte Mehrdeutigkeit.
Null bleibt offen. Eine dort ausgegebene nicht-null Interpretation wird derzeit ohne separat
verifizierbare semantische Stützung abgelehnt; kein ungetesteter Interpretationsfallback.
Auch Rollenregex ist nur konservatives Integritätsgate, keine vollständige semantische Prüfung.
Quellenbelege müssen von einer gesonderten fachlichen Prüfung interpretiert werden.

## Noch nicht erfüllte Domainpflichten

Kein Domain-v0.1-Status/Grund, keine fachliche Vollständigkeits- oder Dokumentabwesenheitsprüfung.
`selection_present` ist nicht known-complete, `no_selection` nicht unknown-absent.
Bestehende Regeln verlangen alle Originalwerte/Mitglieder/Unterfragen, belegte Rollen/Fragearten,
keine zusätzlichen falschen Inhalte sowie korrekten Status/Grund und semantisch stützende Belege.
Consorts bleibt Quellenlimit ohne vollen Feldpunkt. Titel-/Namens-/Fragenumfang und echte
Mehrdeutigkeit benötigen fachliche Prüfung; Kandidatenmenge ist kein Abdeckungsbeweis.

Es existiert bewusst kein Setter für known-complete/unknown-absent und kein automatischer
Domainadapter. Solche Aussagen dürften nur durch eine getrennte tatsächlich vorhandene,
dokumentierte fachliche Prüfung entstehen (Quellenumfang, Reviewer/Verfahren, Evidenz,
Prüfzeitpunkt, Grenzen und Begründung). Hier ist diese produktive Prüfung **nicht implementiert**.
Historische Dev-Referenzbewertung bleibt separate Offlineevaluation, keine fingierte HumanApproval.
Kein neuer Domain-Erfolgsscore.

## Ausschließlich offline reproduzieren

In `track_2a/`:

```sh
uv run pytest -q tests/test_selection_coverage.py
uv run python -m openparl_extractor.selection_coverage_run prepare
uv run python -m openparl_extractor.selection_coverage_run replay
```

Eigener ignorierter Ordner `output/analysis/selection_coverage_v1_offline/`, kein Überschreiben.
Prepare friert Methode/Code/Tests/Doku/zwölf versionierte Inputs/SourceDocuments **vor** Replay ein.
Replay projiziert ausschließlich vorhandene v4-Rohitems: redundant gelieferte Frageart wird
getrennt dokumentiert, Rawstatus/reason/status_evidence bleiben als verworfene Modellentscheidung
sichtbar. Kein neues Modellresultat, kein produktiv akzeptiertes historisches Ergebnis.
Nur Diagnose-Auswahlintegrität und separates Abdeckungsprotokoll. Keine HTTP-Schnittstelle,
Livecalls oder neue Freigabe.
