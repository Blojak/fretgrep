# Architektur

fretgrep ist ein Kommandozeilenprogramm in Python ohne Serverteil. Jeder
Aufruf von `fretgrep` öffnet die SQLite-Datei, erledigt eine Aufgabe und
endet. Nach außen gibt es genau eine Netzverbindung: die Abfrage des
Ollama-Servers für Embeddings.

## Überblick

```
 MP3-Ordner ──scan──────────►┌────────────────────────────┐
   (wird nur gelesen)        │  SQLite-Datei              │
                             │                            │
 faster-whisper ─transcribe─►│  recording                 │
   (lokal, CPU, ffmpeg)      │  auto_*   neu berechenbar  │──search──► Treffer
                             │  user_*   von Hand         │
 Ollama-Server ──embed──────►│  search_index (FTS5)       │
   (HTTP, /api/embed)        └────────────────────────────┘
        ▲                                  ▲
        └─────── search (Suchtext) ────────┘   tag / note / playlist schreiben user_*
```

## Bausteine

Der Code liegt in `src/fretgrep/`.

| Modul | Aufgabe |
|---|---|
| `cli.py` | Führt die Befehle von `fretgrep` aus: Ausgabe, Fehlermeldungen. Enthält keine Fachlogik. |
| `cli_playlist.py` | Die Befehle `fretgrep playlist …`. |
| `cli_chat.py` | Der Befehl `fretgrep chat`; Befehle mit `!` reicht er an `cli.main` zurück. |
| `cli_common.py` | Was die `cli*`-Module teilen: Exit-Codes, Fehlermeldungen, Ausgabe einer Aufnahme, Abspielen. |
| `banner.py` | Das Logo im Terminal; erzeugt auch `docs/logo.svg` für die README. |
| `arguments.py` | Beschreibt Befehle, Schalter und Hilfetexte (argparse); die ausführenden Funktionen bekommt es von `cli.py`. |
| `completion.py` | Erzeugt aus dem argparse-Parser die Skripte für die Tab-Vervollständigung in zsh und bash. Nur die Listennamen holt das Skript zur Laufzeit über `fretgrep playlist --names`. |
| `config.py` | Liest die Einstellungen aus Umgebungsvariablen. |
| `db.py` | Verbindung zur Datenbank, Migrationen ausführen, Schemastand prüfen. |
| `models.py` | Tabellen als SQLAlchemy-Modelle. |
| `migrations/` | Alembic-Revisionen, eine je Schemaänderung. |
| `scanner.py` | Gleicht den Ordner mit den `auto_*`-Tabellen ab. |
| `audio_info.py` | Liest Dauer, Abtastrate, Kanäle und Bitrate aus der Datei (mutagen). |
| `filename_parser.py` | Macht aus Datei- und Ordnernamen Tag-Vorschläge mit Konfidenz. |
| `vocabulary.toml` | Bekannte Schreibweisen, mehrdeutige Wörter, Füllwörter, Erklärungen zu Tag-Werten. |
| `user_meta.py` | Eigene Tags, Notizen und Wiedergabelisten. Nur dieses Modul schreibt in `user_*`. |
| `search.py` | FTS5-Suchindex aufbauen und abfragen. |
| `transcribe.py` | Spracherkennung mit faster-whisper. |
| `embeddings.py` | Vektoren vom Ollama-Server holen, Suche nach Bedeutung, Rangfusion. |
| `player.py` | Baut den mpv-Aufruf für die Wiedergabe und startet ihn; übergibt die Stücke mit Titel (ID) als temporäre `.m3u` und schreibt Wiedergabelisten für den Export. |
| `notes.py` | Notenerkennung mit basic-pitch, Speichern und Anzeigen der Noten. |
| `rhythm.py` | Schätzt Notenwerte aus den Einsatzzeiten der erkannten Noten. |
| `theory.py` | Rechnet die Töne von Akkorden und Skalen aus und schreibt sie nach Stufen richtig. |
| `assistant.py` | Chat mit einem Sprachmodell auf dem Ollama-Server, mit Werkzeugen (Tool-Calling) und Verlauf. |
| `chat_output.py` | Gibt die Antworten des Assistenten im Terminal aus, während sie eintreffen. |
| `sheet.py` | Schreibt die Noten als LilyPond-Quelltext, lässt LilyPond das Notenblatt zeichnen und öffnet es auf Wunsch in einem Fenster. |

Abhängigkeiten: SQLAlchemy, Alembic und mutagen sind Pflicht. faster-whisper
ist optional und wird erst beim Transkribieren geladen, basic-pitch erst
bei der Notenerkennung. Die Anbindung an
Ollama kommt mit der Standardbibliothek aus (`urllib`), die Vektorrechnung
ebenfalls.

Externe Programme werden als eigene Prozesse gestartet, nie eingebunden:

| Programm | Aufgerufen von | Zweck |
|---|---|---|
| ffmpeg | `transcribe.py`, `notes.py` | MP3 dekodieren; kommt auch mit beschädigten Stellen zurecht |
| mpv | `player.py` | Wiedergabe mit rubberband-Filter |
| lilypond | `sheet.py` | Notenblatt zeichnen |
| xdg-open (macOS: open) | `sheet.py` | Notenblatt im Standardbetrachter öffnen; läuft losgelöst weiter |
| Ollama | `embeddings.py`, `assistant.py` | Embeddings und Chat, über HTTP statt als Prozess |

## Datenmodell

Der Grundsatz: Was sich aus den Aufnahmen neu berechnen lässt, steht in
Tabellen mit dem Präfix `auto_`. Was von Hand eingegeben wurde, steht in
Tabellen mit dem Präfix `user_`. Beide hängen nur über `recording.id`
zusammen. So kann man alle `auto_*`-Daten verwerfen und neu erzeugen, ohne
eine einzige Notiz zu verlieren.

| Tabelle | Inhalt | Zeilen je Aufnahme |
|---|---|---|
| `recording` | Identität: ID und SHA-256 des Dateiinhalts | 1 |
| `auto_file` | Pfad, normalisierter Name, Größe, Änderungszeit, Audiodaten, nicht erkannte Namensteile, Kennzeichen „fehlt“ | 1 |
| `auto_tag` | Tag-Vorschlag: Kategorie, Wert, Konfidenz, Quelle (Dateiname oder Ordner), ursprüngliches Wort, Parser-Version | beliebig viele |
| `auto_transcript` | erkannter Text, Sprache, Modell. Leerer Text heißt: keine Sprache erkannt | 0 oder 1 |
| `auto_embedding` | Vektor als float32-Bytes, Modell, Hash des eingebetteten Textes | 0 oder 1 |
| `auto_notes` | erkannte Noten als JSON-Liste aus `[Beginn, Ende, MIDI-Tonhöhe, Lautstärke]`, Modell | 0 oder 1 |
| `user_tag` | eigener Tag | beliebig viele |
| `user_note` | eigene Notiz | 0 oder 1 |
| `user_playlist` | eigene Wiedergabeliste: Name (eindeutig, ohne Rücksicht auf Groß- und Kleinschreibung) | – |
| `user_playlist_entry` | Aufnahme in einer Wiedergabeliste mit Position; je Liste höchstens einmal | beliebig viele |
| `search_index` | FTS5-Volltextindex, abgeleitet aus allen Tabellen | 1 |
| `alembic_version` | Stand der Migrationen | – |

**Identität über den Inhalt.** Der Schlüssel einer Aufnahme ist der Hash
ihres Inhalts, nicht ihr Pfad. Umbenennen und Verschieben ändern deshalb
nur `auto_file.rel_path`. Der Preis: Wird eine Datei neu kodiert oder
geschnitten, ist sie für fretgrep eine neue Aufnahme.

**Suchindex.** `search_index` hat die Spalten `name`, `auto_tags`,
`user_tags`, `note` und `transcript`; die `rowid` ist die ID der Aufnahme.
Er enthält nur abgeleiteten Text und wird bei `db upgrade` und `scan`
komplett neu aufgebaut, bei `tag`, `note` und `transcribe` für die
betroffene Aufnahme.

## Abläufe

### Einlesen (`scan`)

1. Alle `.mp3`-Dateien im Ordner und seinen Unterordnern auflisten.
2. Je Datei: Stimmen Pfad, Größe und Änderungszeit mit der Datenbank
   überein, gilt sie als unverändert und wird nicht neu gelesen. Sonst wird
   der Hash berechnet und der Datei-Header ausgelesen.
3. Taucht derselbe Hash im selben Lauf zweimal auf, wird die zweite Datei
   als Duplikat gemeldet und übersprungen.
4. Der Parser erzeugt aus Datei- und Ordnernamen Tag-Vorschläge; die
   Zeilen in `auto_file` und `auto_tag` werden angelegt oder angepasst.
5. Aufnahmen, deren Datei nicht mehr gefunden wurde, erhalten das
   Kennzeichen „fehlt“. Gelöscht wird nichts.
6. Der Suchindex wird neu aufgebaut.

### Tag-Vorschläge (`filename_parser.py`)

Der Name wird in Unicode-Normalform NFC gebracht und an Leerzeichen,
Kommas und Punkten zerlegt. Dann wird jedes Wort der Reihe nach geprüft:
gegen das Vokabular (auch Schreibweisen aus mehreren Wörtern), gegen
Regeln für Lagen, Versionen und Nummern, und als Akkordsymbol. Die
Konfidenz zeigt, wie sicher der Treffer ist:

| Konfidenz | Bedeutung |
|---|---|
| 0,9 | Treffer im Vokabular oder vollständiges Akkordsymbol |
| 0,7 | schwächere Regel, z. B. „lage 10“ oder ein bloßes „Bbm“ |
| 0,5 | Tippfehler-Treffer, mehrdeutiges Wort oder bloße Zahl |
| 0,4 | einzelner Buchstabe, als Akkord gelesen |
| 0,3 | Hinweis nur aus dem Ordnernamen |

Ordnernamen zählen bewusst wenig, weil die Ordnerstruktur nicht
verlässlich ist. Was der Parser nicht einordnen kann, landet in
`auto_file.unparsed` und ist über `fretgrep show` sichtbar. Neue
Schreibweisen trägt man in `vocabulary.toml` ein; der nächste `scan`
berechnet die Vorschläge neu.

### Transkription (`transcribe`)

ffmpeg dekodiert die Datei zu Mono mit 16 kHz, faster-whisper erkennt den
Text auf der CPU. Ein Sprachfilter überspringt die Stellen, an denen nur
Gitarre zu hören ist, weil Whisper dort sonst Text erfindet. Jedes
Ergebnis wird einzeln gespeichert. Ein Transkript gilt als erledigt, wenn
es vom eingestellten Modell stammt; ein Modellwechsel macht alle wieder
fällig.

### Embeddings (`embed`)

Für jede Aufnahme wird ein Text gebaut: Pfad ohne Endung, die Werte der
Tag-Vorschläge, eigene Tags, Notiz und Transkript. Hat ein Tag-Wert im
Vokabular eine Erklärung (`[descriptions]`), steht sie in Klammern
dahinter, etwa „looper (mehrere Spuren übereinander)“. So erfährt das
Modell, was eigene Abkürzungen und Namen bedeuten. Diese Texte gehen in
Stapeln von 16 an `POST /api/embed` des Ollama-Servers. Der Vektor wird
zusammen mit dem Modellnamen und dem SHA-256 des Textes gespeichert.

Ein Vektor gilt als veraltet, wenn er fehlt, von einem anderen Modell
stammt oder der Hash nicht mehr zum aktuellen Text passt. Dadurch
berechnet `embed` nach einer geänderten Notiz genau eine Aufnahme neu.
Jeder Stapel wird einzeln gespeichert.

### Suche

**Stichwortsuche.** Aus den Suchwörtern entsteht eine FTS5-Abfrage. Jedes
Wort muss vorkommen, gilt auch als Wortanfang und wird um seine Bedeutung
aus dem Vokabular ergänzt („moll“ sucht auch nach „minor“). Füllwörter
fallen weg. Die Reihenfolge bestimmt BM25 mit Gewichten je Spalte: eigene
Tags 4, Name 3, Notiz 2, Transkript 1,5, Tag-Vorschläge 1.

**Suche nach Bedeutung (Standard, sobald ein Embedding-Modell eingestellt
ist).** Zwei Ranglisten werden gebildet und zusammengeführt:

1. die Stichwortsuche wie oben, aber gelockert: ein passendes Wort
   reicht. So zählt in einem ganzen Satz ein wörtlicher Treffer wie ein
   Name weiterhin mit,
2. die Ähnlichkeit zwischen dem Vektor des Suchtextes und den
   gespeicherten Vektoren (Kosinus). Dafür wird der Suchtext einmal an den
   Ollama-Server geschickt; verglichen wird in Python mit allen Vektoren.

Aus jeder Liste nehmen die besten 50 teil. Zusammengeführt wird mit
Reciprocal Rank Fusion: Jede Aufnahme erhält je Liste `1 / (60 + Rang)`
Punkte, die Summe bestimmt die Reihenfolge. Wer in beiden Listen steht,
landet oben. Das Verfahren braucht nur Ränge und kommt deshalb ohne
Abgleich der unterschiedlichen Bewertungsskalen aus.

Vor jeder Anfrage an Ollama fragt `first_reachable` die möglichen
Adressen der Reihe nach mit `GET /api/version` ab, je höchstens eine
Sekunde lang, und nimmt die erste, die antwortet. Antwortet keine oder
scheitert die Anfrage, fällt `search` auf die Stichwortsuche zurück; nur
mit `-s` endet der Befehl mit einem Fehler.

Bekannte Grenzen:

- Die Bedeutungsliste enthält immer Einträge, auch wenn nichts gut passt.
  Es gibt keine Schwelle für „zu unähnlich“.
- Erklärt sind nur Begriffe, die im Vokabular eine Erklärung haben.
  Alle anderen Abkürzungen und Namen bleiben für das Modell bloße Wörter.
- Der Vergleich mit allen Vektoren ist für einige hundert Aufnahmen
  gedacht, nicht für sehr große Sammlungen.

### Wiedergabe (`play`)

`play` schlägt die Pfade der Aufnahmen in der Datenbank nach und startet
mpv als Vordergrundprozess im Terminal, mit allen Dateien in einem
Aufruf; die Wiedergabeliste führt also mpv. `search --play` übergibt auf
demselben Weg die Dateien seiner Treffer. Die Bedienung während der
Wiedergabe ist die von mpv. Tempo und Tonhöhe laufen über den rubberband-Filter von
mpv, der beides unabhängig voneinander ändert. Halbtöne werden in den
Frequenzfaktor `2^(n/12)` umgerechnet. Der A-B-Loop nutzt die
mpv-Optionen `--ab-loop-a` und `--ab-loop-b`. In die Datenbank schreibt
`play` nichts.

### Notenerkennung (`notes`)

ffmpeg dekodiert die Aufnahme in eine temporäre WAV-Datei. basic-pitch,
ein kleines neuronales Netz von Spotify, erkennt darin Noten, auch
mehrere gleichzeitig. Es läuft über ONNX Runtime auf der CPU und braucht
für eine Aufnahme weniger als eine Sekunde. Gesucht wird nur im Tonumfang
der Gitarre, zwischen 80 und 1400 Hz.

Gespeichert werden alle erkannten Noten mit Beginn, Ende, MIDI-Tonhöhe
und Lautstärke. Erst die Anzeige filtert: Sie blendet Noten unter der
Lautstärke-Schwelle aus, fasst Noten mit fast gleichem Beginn (bis 0,05 s)
zu einem Zusammenklang zusammen und trennt Phrasen, wo länger als 0,75 s
nichts klingt. So lässt sich die Schwelle ändern, ohne neu zu erkennen.

Eine MIDI-Datei entsteht auf Wunsch aus denselben gespeicherten Noten
(pretty_midi). Sie ist eine Ausgabe, keine weitere Ablage.

Ein Notenblatt entsteht ebenfalls auf Wunsch. `sheet.py` übersetzt die
Phrasen der Anzeige in LilyPond-Quelltext und ruft das Programm
`lilypond` auf, das daraus PDF, SVG oder PNG macht. Jede Phrase wird eine
Notenzeile ohne Takt (`\cadenzaOn`), mit Notenköpfen ohne Hälse und dem
oktavierten Violinschlüssel.

### Notenwerte schätzen (`notes --sheet --rhythm`)

Die Erkennung liefert Einsatzzeiten in Sekunden. `rhythm.py` macht
daraus Positionen auf einem Raster aus Achteln:

1. **Tempo der Aufnahme.** Ausgangspunkt ist der übliche Abstand zweier
   Einsätze. Um diesen Wert herum (±36 %) wird das Tempo gesucht, das
   über alle längeren Phrasen am besten passt. Mit `--tempo` entfällt
   die Suche.
2. **Je Phrase** wird das Tempo um bis zu 8 % nachgestellt und geprüft,
   ob der erste Einsatz auf oder neben dem Schlag liegt.
3. **Mitlaufen.** Jeder Einsatz wird relativ zum vorigen eingeordnet und
   zieht danach Rasterposition und Tempo ein Stück zu sich. So summiert
   sich ein schwankendes Tempo nicht zu einem Fehler auf.
4. **Swing.** Gerade Rasterplätze sind Schläge. Auf einem ungeraden
   Platz darf ein Einsatz bis zu einem Drittel Achtel zu spät kommen,
   ohne als Abweichung zu zählen. Dadurch passt bei geswingtem Spiel nur
   die richtige Lage der Schläge gut, und sie lässt sich bestimmen.
5. **Notenwerte.** Eine Note dauert bis zum nächsten Einsatz; endet sie
   mindestens zwei Achtel früher, entsteht eine Pause. Zwei Einsätze auf
   einem Rasterplatz werden Sechzehntel.

Zwei Kosten entscheiden zwischen Lesarten, die ähnlich gut passen: Zwei
Einsätze auf einem Platz kosten extra, und von zwei Lesarten gewinnt
die, die weniger Achtel braucht. Letzteres bevorzugt „geswingte Achtel“
gegenüber „Viertel plus Achtel in schnellerem Tempo“.

`sheet.py` zeichnet das Ergebnis mit Notenwerten, verbalkt Achtel und
Sechzehntel innerhalb einer Zählzeit und lässt Taktstriche weg, weil die
Lage der Eins unbekannt ist.

Geprüft wird das Verfahren mit künstlichen Licks, deren Rhythmus bekannt
ist: Achtelketten, Auftakte und gemischte Notenwerte, jeweils mit Swing,
ungenauem Timing und Temposchwankung (`tests/test_rhythm.py`). Für echte
Aufnahmen gibt es keine Referenz; dort ist das Tempo die Hauptfehlerquelle.

Bekannte Grenzen:

- Die Sprechstimme wird als tiefe Noten erkannt. Die Schwelle entfernt
  sie nur teilweise.
- Die Textanzeige zeigt Tonhöhen und Reihenfolge, keinen Rhythmus.
  Die Lage auf dem Griffbrett kennt keine der Ausgaben.
- Notenwerte im Notenblatt sind eine Schätzung ohne Takte; bei gerade
  gespielten Achteln ist die Lage der Schläge nicht bestimmbar.
- basic-pitch verlangt laut seinen Paketangaben TensorFlow und wird
  deshalb mit `--no-deps` installiert, siehe [Benutzung](benutzung.md).

## Schemaänderungen

Das Schema entsteht ausschließlich durch Alembic-Migrationen in
`src/fretgrep/migrations/versions/`, nie durch `create_all()`. Regeln:

- Eine Revision je Änderung, fortlaufend nummeriert.
- `render_as_batch=True`, weil SQLite Tabellen kaum nachträglich ändern
  kann.
- FTS5-Tabellen erkennt Alembic nicht. Sie werden mit rohem SQL angelegt
  und sind vom automatischen Vergleich ausgenommen.
- Migrationen dürfen `user_*`-Daten nie verwerfen.

`fretgrep db upgrade` führt die Migrationen aus und baut den Suchindex neu
auf. Jeder andere Befehl prüft beim Öffnen, ob die Datenbank auf dem
neuesten Stand ist, und bricht sonst mit einem Hinweis ab (Exit-Code 2).

## Entwicklung und Tests

```sh
pip install -e ".[dev]"
pytest
pylint src tests
```

- Die Tests bauen ihre Datenbank immer über die Migrationen auf, in einem
  temporären Ordner.
- `tests/test_migrations.py` prüft, dass Modelle und Migrationen
  übereinstimmen und dass sich alles bis zum leeren Schema zurückdrehen
  lässt.
- Whisper und Ollama werden in den Tests durch einfache Stellvertreter
  ersetzt. Die Tests brauchen weder Netz noch Modelle.
- Der Code folgt PEP 8 mit 88 Zeichen Zeilenlänge; Pylint soll ohne
  Meldung durchlaufen.

Meldungen an den Benutzer sind deutsch, Code und Kommentare englisch.
