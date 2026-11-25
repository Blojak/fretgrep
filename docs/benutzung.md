# Benutzung

## Voraussetzungen

Python 3.11 oder neuer ist Pflicht. Alles Weitere wird nur für einzelne
Befehle gebraucht:

| Werkzeug | Wofür | Installation |
|---|---|---|
| ffmpeg | `transcribe`, `notes` | `sudo apt install ffmpeg` |
| faster-whisper | `transcribe` | `pip install -e ".[transcribe]"` |
| Ollama mit Embedding-Modell | `embed`, Suche nach Bedeutung | Ollama installieren, dann `ollama pull bge-m3` |
| Ollama mit Sprachmodell | `chat` | auf dem Server `ollama pull qwen3.8:27b` |
| mpv mit rubberband-Filter | `play` | `sudo apt install mpv` |
| basic-pitch | `notes` | zwei pip-Befehle, siehe Installation |
| LilyPond | `notes --sheet`, `notes --show` | `sudo apt install lilypond` |
| ein PDF-Betrachter und xdg-open | `notes --show` | meist vorhanden; sonst `sudo apt install xdg-utils atril` |
| sqlite3 | Blick in die Datenbank | `sudo apt install sqlite3` |

Ohne diese Werkzeuge funktionieren Einlesen, Tags, Notizen und die
Stichwortsuche trotzdem. Fehlt eines, sagt der betroffene Befehl, was zu
installieren ist.

## Installation

Die Abhängigkeiten stehen in `pyproject.toml`; eine `requirements.txt` gibt
es nicht.

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,transcribe]"
```

`dev` bringt pytest und Pylint mit, `transcribe` die Spracherkennung
(faster-whisper). Beides kann man weglassen. Danach steht im aktivierten
venv der Befehl `fretgrep` bereit.

Soll `fretgrep` überall und ohne aktiviertes venv laufen, genügt ein Link
in einen Ordner, der im `PATH` steht:

```sh
mkdir -p ~/.local/bin
ln -s "$PWD/.venv/bin/fretgrep" ~/.local/bin/fretgrep
```

Der Link zeigt auf das Startskript im venv. Änderungen am Code wirken
weiterhin sofort. Wird der Projektordner verschoben oder das venv neu
angelegt, muss der Link neu gesetzt werden.

Die Notenerkennung wird in zwei Schritten installiert:

```sh
pip install -e ".[notes]"
pip install --no-deps basic-pitch==0.4.0
```

Der Umweg ist nötig, weil basic-pitch TensorFlow als Pflicht angibt und es
TensorFlow für Python 3.13 und neuer nicht gibt. fretgrep nutzt
stattdessen das mitgelieferte ONNX-Modell; `--no-deps` verhindert, dass
pip TensorFlow verlangt. Die übrigen Bibliotheken bringt das Extra `notes`
mit. Sobald basic-pitch ohne TensorFlow installierbar ist, entfällt der
zweite Schritt.

## Tab-Vervollständigung

Die Shell kann Befehle und Schalter von `fretgrep` mit der Tab-Taste
ergänzen: `fretgrep se` und Tab ergibt `fretgrep search`, `fretgrep
notes 83 --sh` und zweimal Tab zeigt `--sheet` und `--show` mit ihrer
Erklärung. Nach `--library` und `scan` werden Ordner vorgeschlagen, nach
`--sheet` und `--midi` Dateien, bei `playlist` und `search --save` die
Namen der Wiedergabelisten.

Das Skript dafür erzeugt `fretgrep completion zsh` (oder `bash`). Für die
zsh einmal als Datei ablegen:

```sh
mkdir -p ~/.zfunc
fretgrep completion zsh > ~/.zfunc/_fretgrep
```

und in der `~/.zshrc` **vor** der Zeile mit `compinit` ergänzen:

```sh
fpath=(~/.zfunc $fpath)
```

Danach eine neue Shell öffnen. Kommt mit einer neuen Version ein Befehl
oder Schalter dazu, den ersten Befehl wiederholen; bei Problemen hilft
`rm ~/.cache/zcompdump*` (bzw. `~/.zcompdump*`), dann neue Shell.

Einfacher, aber jede neue Shell startet dann etwa eine halbe Sekunde
später, weil dabei jedes Mal Python läuft: in der `~/.zshrc` **nach**
`compinit` die Zeile

```sh
eval "$(fretgrep completion zsh)"
```

Für bash steht in der `~/.bashrc`: `eval "$(fretgrep completion bash)"`.

Ergänzt werden nur Befehle, Schalter, Ordner, Dateien und die Namen der
Wiedergabelisten. IDs und Suchwörter kennt die Vervollständigung nicht.
Nur für die Listennamen startet ein Tab Python, weil sie in der Datenbank
stehen; das dauert einen Moment.

## Logo und Version

`fretgrep` ohne Argumente und `fretgrep --help` zeigen die Übersicht,
`fretgrep --version` die Version. Im Terminal steht darüber das Logo.
Es erscheint nicht, wenn die Ausgabe in eine Datei oder ein anderes
Programm geht, und nie bei den übrigen Befehlen. Ist die Variable
`NO_COLOR` gesetzt, bleibt es einfarbig.

## Einstellungen

Alle Einstellungen sind Umgebungsvariablen. Eine `.env`-Datei liest das
Programm nicht. Am einfachsten stehen die `export`-Zeilen in der `~/.zshrc`
oder in einer eigenen Datei, die man bei Bedarf mit `source` lädt.

| Variable | Bedeutung | Standard |
|---|---|---|
| `FRETGREP_DB` | Pfad der Datenbankdatei | `~/.local/share/fretgrep/fretgrep.db` |
| `FRETGREP_LIBRARY` | Ordner mit den Aufnahmen | keiner |
| `FRETGREP_OLLAMA_URL` | Adresse des Ollama-Servers | `http://localhost:11434`, danach `http://192.168.122.1:11434` |
| `FRETGREP_EMBED_MODEL` | Name des Embedding-Modells; schaltet die Suche nach Bedeutung ein | keiner |
| `FRETGREP_CHAT_MODEL` | Sprachmodell für `fretgrep chat` | `qwen3.8:27b` |
| `FRETGREP_WHISPER_MODEL` | Whisper-Modell für die Transkription | `small` |
| `FRETGREP_WHISPER_LANGUAGE` | Sprache der Erklärungen, z. B. `de` | wird je Datei erkannt |

Beispiel:

```sh
export FRETGREP_LIBRARY=~/pfad/zu/lick-library
export FRETGREP_EMBED_MODEL=bge-m3:latest
```

Ohne `FRETGREP_LIBRARY` muss der Ordner bei `scan` als Argument und bei
`transcribe`, `play` und `notes` mit `--library` angegeben werden.

**Früherer Name.** Das Projekt hieß früher Woodshed. Die alten Namen
`WOODSHED_…` gelten weiter, solange die neue Variable nicht gesetzt ist.
Ohne `FRETGREP_DB` wird die alte Datei
`~/.local/share/woodshed/woodshed.db` benutzt, bis es die neue gibt. Zum
Umstellen:

```sh
mkdir -p ~/.local/share/fretgrep
mv ~/.local/share/woodshed/woodshed.db ~/.local/share/fretgrep/fretgrep.db
sed -i 's/WOODSHED_/FRETGREP_/' ~/.zshrc
```

Eine vorhandene Installation einmal neu einrichten, weil das Python-Paket
jetzt `fretgrep` heißt: `pip uninstall woodshed && pip install -e .`

**Adresse des Ollama-Servers.** fretgrep probiert mehrere Adressen der
Reihe nach und nimmt die erste, an der ein Server antwortet: zuerst die
aus `FRETGREP_OLLAMA_URL`, dann `http://localhost:11434`, dann
`http://192.168.122.1:11434`. Die letzte ist die übliche Adresse des
Hosts einer virtuellen Maschine (libvirt); sie gilt in der VM und auf
dem Host selbst. In diesen beiden Fällen braucht es die Variable also
nicht. Lauscht Ollama woanders, trägt man die Adresse ein, mehrere
werden durch Kommas getrennt:

```sh
export FRETGREP_OLLAMA_URL=http://server:11434,http://10.0.0.5:11434
```

Auf dem Rechner mit Ollama zeigt `ss -ltnp | grep 11434` die Adresse.
Jede Adresse, die nicht antwortet, kostet höchstens eine Sekunde. Eine
Anmeldung verlangt der Server nicht.

## Auf einem weiteren Rechner einrichten

Im Repository liegt nur der Code. Aufnahmen und Datenbank bleiben auf
dem jeweiligen Rechner.

```sh
git clone git@github.com:Blojak/fretgrep.git   # später: git pull
cd fretgrep
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,transcribe]"
```

Danach fehlen noch:

- **Aufnahmen:** Der Ordner mit den MP3-Dateien muss selbst kopiert
  werden; `lick-library/` ist von Git ausgenommen.
- **Datenbank:** Entweder die Datei
  `~/.local/share/fretgrep/fretgrep.db` vom anderen Rechner kopieren oder
  neu aufbauen (`db upgrade`, `scan`, `transcribe`, `embed`). Eigene Tags
  und Notizen stecken nur in dieser Datei. Da Aufnahmen über ihren Inhalt
  erkannt werden, passt eine kopierte Datenbank auch dann, wenn der
  Ordner auf dem anderen Rechner woanders liegt.
- **Einstellungen:** Die Umgebungsvariablen sind je Rechner zu setzen.
- **Werkzeuge:** Siehe Voraussetzungen.

Nach jedem `git pull` einmal `fretgrep db upgrade` ausführen; ändert
sich das Vokabular, zusätzlich `fretgrep scan` und `fretgrep embed`.

## Aufnahmen einlesen

Beim ersten Mal in dieser Reihenfolge:

```sh
fretgrep db upgrade     # 1. Datenbank anlegen
fretgrep scan           # 2. Dateien einlesen, Tags aus den Namen vorschlagen
fretgrep transcribe     # 3. optional: Gesprochenes mitschreiben
fretgrep embed          # 4. optional: Vektoren für die Suche nach Bedeutung
```

Was die Schritte tun:

1. **`db upgrade`** legt die Datenbank an oder bringt sie auf den neuesten
   Stand.
2. **`scan`** sucht im Ordner und allen Unterordnern nach `.mp3`-Dateien.
   Jede Aufnahme wird über den Hash ihres Inhalts erkannt, nicht über den
   Pfad. Eine umbenannte oder verschobene Datei behält deshalb ihre Tags,
   ihre Notiz und ihr Transkript. Zwei Dateien mit gleichem Inhalt gelten
   als Duplikat; die zweite wird übersprungen und gemeldet.
3. **`transcribe`** schreibt mit, was in den Aufnahmen gesprochen wird. Das
   läuft auf der CPU und dauert. Beim ersten Lauf lädt faster-whisper das
   Modell aus dem Internet. Jede Datei wird einzeln gespeichert, ein
   abgebrochener Lauf macht beim nächsten Start dort weiter.
4. **`embed`** schickt den Text jeder Aufnahme (Name, Tags, Notiz,
   Transkript) an den Ollama-Server und speichert den Vektor, den das
   Modell zurückgibt.

## Wann welcher Befehl nötig ist

| Was ist passiert | Was ausführen |
|---|---|
| Neue Version von fretgrep geholt | `fretgrep db upgrade` |
| Dateien hinzugefügt, umbenannt, verschoben oder gelöscht | `fretgrep scan`, danach bei Bedarf `transcribe` und `embed` |
| Tags oder Notiz geändert | `fretgrep embed`, wenn die Suche nach Bedeutung sie kennen soll |
| Schreibweisen oder Namen in `vocabulary.toml` geändert | `fretgrep scan`, danach `fretgrep embed` |
| Erklärungen in `vocabulary.toml` geändert | `fretgrep embed` |
| Neue Transkripte erzeugt | `fretgrep embed` |
| Anderes Embedding-Modell eingestellt | `fretgrep embed` |

Jeder dieser Befehle kann beliebig oft laufen. `scan` liest unveränderte
Dateien nicht neu, `transcribe` und `embed` bearbeiten nur, was fehlt oder
veraltet ist. Die Stichwortsuche ist nach `scan`, `tag`, `note` und
`transcribe` sofort aktuell.

Gelöschte Dateien verschwinden nicht aus der Datenbank. Sie werden als
fehlend markiert (`[fehlt]`), damit Tags und Notizen erhalten bleiben,
falls die Datei wieder auftaucht.

## Suchen

```sh
fretgrep search trauriger blues von wes
fretgrep search -n 5 blues über 251
fretgrep search -k chet baker moll
```

Ist `FRETGREP_EMBED_MODEL` gesetzt, sucht `fretgrep search` nach
Bedeutung. Sonst, oder mit `-k`, ist es die Stichwortsuche.

**Stichwortsuche** (`-k` oder `--keyword`):

- Alle Wörter müssen vorkommen, in Name, Ordner, Tags, Notiz oder
  Transkript.
- Ein Wort passt auch als Wortanfang: `harr` findet „harris“.
- Groß- und Kleinschreibung und Umlaute spielen keine Rolle: `flussig`
  findet „flüssig“.
- Bekannte Schreibweisen werden übersetzt: `moll` findet auch „minor“,
  `cmaj7` auch „Cj7“.
- Füllwörter wie „mit“, „und“, „über“ werden ignoriert.

**Suche nach Bedeutung** (der Standard) kombiniert die
Stichwortsuche mit der Ähnlichkeit der Vektoren. Auf der Stichwortseite
reicht hier ein einziges passendes Wort; je mehr Wörter passen, desto
weiter oben steht die Aufnahme. Sie findet auch Aufnahmen,
in denen die Suchwörter nicht wörtlich vorkommen, und eignet sich für
ganze Sätze. Sie liefert immer eine Rangliste, auch wenn nichts wirklich
passt; die besten Treffer stehen oben. Voraussetzung sind
`FRETGREP_EMBED_MODEL`, ein erreichbarer Ollama-Server und ein Lauf von
`fretgrep embed`. Fehlen Vektoren oder sind sie veraltet, weist die Suche
darauf hin.

Antwortet der Server nicht, sucht `fretgrep search` nach Stichwörtern
und sagt das in einem Hinweis. Mit `-s` (`--semantic`) gibt es
stattdessen eine Fehlermeldung und keine Treffer; das ist für Skripte
gedacht, die sich auf die Bedeutung verlassen.

`-n` begrenzt die Trefferzahl, der Standard ist 20.

**Treffer abspielen.** Mit `--play` laufen die Treffer nach der Liste
als Wiedergabeliste, der beste zuerst:

```sh
fretgrep search -n 5 trauriger blues --play
fretgrep search -k chet baker --play --speed 0.7
```

`--speed` und `--pitch` gelten für alle Stücke und wirken wie bei
`fretgrep play`; die Kurzformen `-s` und `-p` gibt es hier nicht, weil
`-s` bei `search` schon vergeben ist. Treffer, deren Datei fehlt, werden
übersprungen. Die Tasten stehen im Abschnitt Abspielen.

**Treffer speichern.** `--save LISTE` hängt die Treffer an eine eigene
Wiedergabeliste an und legt sie bei Bedarf an, siehe Wiedergabelisten.
Zusammen mit `--play` wird erst gespeichert, dann abgespielt.

**Eigene Begriffe erklären.** Das Modell kennt deine Abkürzungen und
Namen nicht: dass „looper“ mehrere Spuren übereinander meint, weiß es
nicht. Deshalb stehen in
`src/fretgrep/vocabulary.toml` im Abschnitt `[descriptions]` kurze
Erklärungen zu einzelnen Tag-Werten:

```toml
[descriptions]
"looper" = "mehrere Spuren übereinander"
"hm5" = "Harmonisch-Moll-5, Mixolydisch b9 b13"
```

Sie werden mit eingebettet, sodass `fretgrep search mehrere Spuren
übereinander` die looper-Aufnahmen findet. Der Schlüssel muss ein Wert
sein, der weiter oben in der Datei unter `[vocabulary.…]` steht. Nach einer
Änderung bringt `fretgrep embed` die betroffenen Vektoren auf Stand. Auf
die Stichwortsuche wirken die Erklärungen nicht.

## Abspielen

```sh
fretgrep play 21                 # normal abspielen
fretgrep play 21 -s 0.7          # 70 % Tempo, gleiche Tonhöhe
fretgrep play 21 -p -2           # zwei Halbtöne tiefer, gleiches Tempo
fretgrep play 21 -l 5-12.5       # Sekunde 5 bis 12,5 in Schleife
fretgrep play 21 -s 0.5 -l 5-12  # beides zusammen
fretgrep play 21 34 95           # mehrere nacheinander
```

Mehrere IDs ergeben eine Wiedergabeliste in der angegebenen Reihenfolge.
Tempo und Tonhöhe gelten dann für alle Stücke; ein Loop (`-l`) geht nur
mit einer einzelnen Aufnahme. Die Treffer einer Suche spielt
`fretgrep search … --play` ab, siehe Suchen.

`play` startet mpv im Terminal. Zu Beginn jedes Stücks steht dort seine
ID, etwa `Spielt: ID 21  251/dm7 G7 v.lage.mp3`; auch die Liste unter `F8`
zeigt zu jedem Stück die ID. Das gilt ebenso für `search … --play` und
`playlist play`. Während der Wiedergabe gelten die Tasten von mpv:

| Taste | Wirkung |
|---|---|
| Leertaste | Pause |
| Pfeil links / rechts | 5 Sekunden zurück / vor |
| `[` / `]` | Tempo um 10 % senken / erhöhen |
| Rücktaste | Tempo zurücksetzen |
| `l` | A-B-Loop: erster Druck setzt den Anfang, zweiter das Ende, dritter hebt ihn auf |
| `L` | ganze Datei wiederholen |
| `<` / `>` | voriges / nächstes Stück der Wiedergabeliste |
| `F8` | Wiedergabeliste zeigen, das laufende Stück ist hervorgehoben |
| `q` | beenden, auch die ganze Wiedergabeliste |

Die Tonhöhe lässt sich nur beim Start mit `-p` einstellen. Eigene
Einstellungen aus `~/.config/mpv` gelten weiter.

## Wiedergabelisten

Eigene Wiedergabelisten speichern eine Auswahl, etwa alle Licks, die
du gerade übst:

```sh
fretgrep playlist new "hm5 üben"               # leere Liste anlegen
fretgrep playlist add "hm5 üben" 46 63 81      # hinten anhängen
fretgrep search -n 5 hm5 --save "hm5 üben"     # Treffer einer Suche anhängen
fretgrep playlist                              # alle Listen
fretgrep playlist show "hm5 üben"              # Inhalt zeigen
fretgrep playlist show "hm5 üben" --play -s 0.7   # zeigen und abspielen
fretgrep playlist play "hm5 üben" -s 0.7 -p -2    # nur abspielen
fretgrep playlist remove "hm5 üben" 63         # Aufnahme herausnehmen
fretgrep playlist export "hm5 üben" -o hm5.m3u # für andere Player
fretgrep playlist delete "hm5 üben"            # Liste löschen
```

- Eine Aufnahme steht in einer Liste höchstens einmal, kann aber in
  beliebig vielen Listen stehen. `add` und `--save` überspringen, was
  schon darin steht, und legen die Liste an, wenn es sie noch nicht gibt.
- Groß- und Kleinschreibung im Namen spielt keine Rolle. Namen mit
  Leerzeichen gehören in Anführungszeichen. Wer den Namen vergessen hat:
  `fretgrep playlist` zeigt alle Listen, und mit eingerichteter
  Tab-Vervollständigung ergänzt Tab den Namen (`fretgrep playlist play hm`
  und Tab).
- Abgespielt wird wie bei `fretgrep play`, in der Reihenfolge der Liste;
  `-s` und `-p` gelten für alle Stücke, die Tasten stehen oben. Fehlende
  Dateien werden mit Hinweis übersprungen.
- Die Listen stehen in der Datenbank und folgen den Aufnahmen auch nach
  Umbenennen oder Verschieben. `delete` löscht nur die Liste, nicht die
  Aufnahmen.
- `export` schreibt eine `.m3u`-Datei mit absoluten Pfaden, ohne `-o` auf
  die Standardausgabe. Fehlende Dateien werden weggelassen.

## Noten anzeigen

```sh
fretgrep notes 83            # Noten erkennen und anzeigen
fretgrep notes 83 -m 0.6     # nur lautere Noten zeigen
fretgrep notes 83 -m 0       # alles zeigen, was erkannt wurde
fretgrep notes 83 --redo     # neu erkennen
fretgrep notes 83 --midi wes.mid   # zusätzlich als MIDI-Datei speichern
fretgrep notes 83 --show    # zusätzlich als Notenblatt in einem Fenster
fretgrep notes 83 -w --rhythm      # dasselbe mit geschätzten Notenwerten
fretgrep notes 83 --sheet wes.pdf  # zusätzlich als Notenblatt speichern
fretgrep notes 83 --sheet wes.pdf --rhythm      # mit geschätzten Notenwerten
fretgrep notes 83 --sheet wes.pdf --tempo 110   # dasselbe, Tempo vorgegeben
```

Beim ersten Aufruf für eine Aufnahme erkennt basic-pitch die Noten und
speichert sie; das dauert ein bis zwei Sekunden. Jeder weitere Aufruf
liest sie aus der Datenbank. Die Ausgabe sieht so aus:

```
83  251/unsortiert/251 mixo wes.mp3
basic-pitch 0.4.0: 49 von 65 Noten, ab Lautstärke 0.5
   7.8s  Db3 Bb3 F4 C3 Db3 F3 Ab3 C4 Eb4 Bb3
  13.6s  Eb4 Eb4 Bb3 Bb3 C3 Db3 Ab3 C4 Eb4 Bb3
```

- Jede Zeile ist eine Phrase und beginnt mit ihrer Startzeit in Sekunden.
  Eine neue Zeile beginnt, wenn länger als eine Dreiviertelsekunde nichts
  klingt. Die Zeit passt zu `fretgrep play 83 -l 7.8-13`.
- Noten in eckigen Klammern beginnen gleichzeitig, z. B. `[C3 E4]`.
- Die Zahl hinter dem Notennamen ist die Oktave; C4 ist das mittlere C.
  Gezeigt wird die klingende Tonhöhe, also eine Oktave tiefer als in
  Gitarrennoten üblich.
- Halbtöne heißen Db, Eb, F#, Ab und Bb. Die Erkennung kennt keine
  Tonart und kann deshalb nicht zwischen C# und Db unterscheiden.
- Der Rhythmus wird in der Textausgabe nicht angezeigt.

**MIDI.** `--midi DATEI` schreibt genau die angezeigten Noten in eine
MIDI-Datei, also nach Anwendung der Schwelle; mit `-m 0` landet alles
darin. Die Datei enthält Tonhöhen, Zeiten und Lautstärken und lässt sich
z. B. in MuseScore öffnen. Sie wird bei Bedarf aus der Datenbank erzeugt
und nicht dort gespeichert. mpv spielt MIDI nicht ab; dafür braucht es
ein Programm wie fluidsynth oder timidity.

**Notenblatt.** `--sheet DATEI` zeichnet die angezeigten Noten mit
LilyPond als Notenblatt. Die Endung bestimmt das Format: `.pdf`, `.svg`
oder `.png`; mit `.ly` wird nur die LilyPond-Quelldatei geschrieben, die
du selbst weiterbearbeiten kannst. Das Blatt hat dieselbe Einteilung wie
die Textausgabe: eine Notenzeile je Phrase, darüber die Startzeit.

- Ohne weiteren Schalter werden nur Notenköpfe ohne Hälse gezeichnet.
  Der Rhythmus fehlt, weil die Erkennung Zeiten in Sekunden liefert und
  keine Notenwerte.
- Der Schlüssel ist der oktavierte Violinschlüssel (kleine 8 darunter),
  wie in Gitarrennoten üblich. Die Töne stehen also dort, wo du sie aus
  Gitarrennoten kennst.
- Vorzeichen stehen an jeder betroffenen Note und gelten nur für sie.
- Wie bei MIDI gilt die Schwelle `-m`, und in der Datenbank wird das
  Blatt nicht gespeichert.

**Notenblatt im Fenster.** `--show` (kurz `-w`) zeichnet dasselbe Blatt
als PDF und öffnet es im Standardbetrachter des Desktops, ohne dass du
eine Datei angeben musst. Das Terminal ist sofort wieder frei, das
Fenster bleibt offen. Das PDF liegt im Cache unter
`~/.cache/fretgrep/sheets/notes-ID.pdf` und wird beim nächsten `--show`
derselben Aufnahme überschrieben; zum Aufheben `--sheet DATEI` nehmen.
Beide Schalter gehen auch zusammen. Welcher Betrachter aufgeht, bestimmt
der Desktop (`xdg-mime query default application/pdf`). Über SSH ohne
grafische Oberfläche geht kein Fenster auf; dann `--sheet` benutzen.

**Ablage.** Der Ordner `archive/` im Projektordner ist von Git
ausgenommen. Dort kannst du erzeugte Notenblätter und MIDI-Dateien
ablegen, ohne dass sie im Repository landen:

```sh
mkdir -p archive
fretgrep notes 83 --sheet archive/wes.pdf --rhythm
```

**Notenwerte schätzen.** Mit `--rhythm` bekommt das Notenblatt Achtel,
Viertel, Sechzehntel und Pausen; Achtel und Sechzehntel einer Zählzeit
sind verbalkt. Über jeder Zeile steht das angenommene Tempo in Vierteln
pro Minute. Das ist eine Schätzung, kein Diktat:

- **Wie es geht:** fretgrep legt ein Raster aus Achteln über jede Phrase
  und folgt deinem Spiel Note für Note, sodass ein schwankendes Tempo
  nicht stört. Swing ist eingerechnet: Eine verzögerte Achtel auf „und“
  gilt als Achtel.
- **Zählzeiten:** Wo die Schläge liegen, ergibt sich aus dem Swing. Bei
  gerade gespielten Achteln ist das nicht erkennbar; dann stimmen die
  Notenwerte, aber die Balken können um eine Achtel verschoben sein.
- **Keine Takte:** Taktstriche und Taktart fehlen, weil eine
  Solo-Aufnahme nicht verrät, wo die Eins ist.
- **Kurze Phrasen** mit weniger als sechs Einsätzen bleiben Notenköpfe
  ohne Hälse.
- **Das Tempo ist die Schwachstelle.** Geswingte Achtel lassen sich auch
  als Viertel plus Achtel in schnellerem Tempo lesen, und beides passt
  rechnerisch ähnlich gut. Sieht ein Blatt danach aus oder wirkt es
  doppelt so schnell oder langsam wie gespielt, gib das Tempo mit
  `--tempo` vor. Jede Phrase darf davon um bis zu 8 % abweichen.
- Fehlnoten aus der Erkennung, etwa die Sprechstimme, stören den
  Rhythmus stärker als die reine Tonfolge. Eine höhere Schwelle `-m`
  kann helfen.

`--rhythm` und `--tempo` wirken nur zusammen mit `--sheet` oder `--show`; `--tempo`
allein schaltet die Notenwerte ebenfalls ein.

**Lautstärke-Schwelle.** Die Erkennung liefert zu jeder Note eine
Lautstärke zwischen 0 und 1. Leise Noten sind oft keine gespielten Töne,
sondern Obertöne oder die Sprechstimme, die als tiefe Töne um G2 und A2
erscheint. `-m` blendet alles unterhalb der Schwelle aus; gespeichert
bleibt immer alles. Die Stimme verschwindet damit nicht vollständig, und
leise gespielte Töne können mit ausgeblendet werden.

## Den Assistenten fragen

```sh
fretgrep chat was sind die Töne von G7HM5
fretgrep chat welche Skala passt über Dm7b5
fretgrep chat hab ich Aufnahmen mit alterierten Licks
fretgrep chat -c ja bitte, such mir Aufnahmen dazu   # an die letzte Antwort anknüpfen
fretgrep chat                  # Gespräch mit Rückfragen
fretgrep chat -c               # das letzte Gespräch als Gespräch fortsetzen
fretgrep chat --think warum klingt HM5 über V7 in Moll so gut
```

Ein Sprachmodell auf dem Ollama-Server beantwortet Fragen zu
Harmonielehre, Skalen, Akkorden und Improvisation. Es nutzt denselben
Server wie die Suche nach Bedeutung, das Modell legt
`FRETGREP_CHAT_MODEL` fest (Standard `qwen3.8:27b`).

**Töne werden berechnet, nicht geraten.** Sprachmodelle verrechnen sich
bei Skalentönen erstaunlich oft; ohne Hilfe nannte qwen3.8 für G7HM5
sechs Töne und vergaß das C. Deshalb rechnet fretgrep die Töne selbst
aus, und das Modell ruft diese Rechnung als Werkzeug auf. Ausgegeben wird
eine gedimmte Zeile wie `→ tones: G7HM5`, darunter die Antwort:

```
→ tones: G7HM5
Akkord G7: G B D F (1 3 5 b7)
Skala G HM5 (Mixolydisch b9 b13, Phrygisch-Dominant): G Ab B C D Eb F
Sie ist der 5. Modus von C harmonisch Moll.
```

- Bekannt sind Akkorde mit Erweiterungen und Alterationen (`G7`, `Dm7b5`,
  `Bø`, `CΔ7`, `C-7`, `G7b9#11`, `E7sus4`, `C6/9`, `G7alt` …) und Skalen:
  die Kirchentonarten, HM1 bis HM7, MM1 bis MM7, Pentatonik, Dur- und
  Moll-Blues (`Blues` allein ist Moll), Ganzton, HTGT, GTHT und Bebop,
  auch mit deutschen und englischen Namen (`C lydisch`, `F# alteriert`,
  `Db lydisch dominant`, `G Dur-Blues`).
- HM5 und MM7 meinen die Skala auf dem genannten Grundton: G HM5 ist der
  fünfte Modus von C harmonisch Moll.
- Akkord und Skala lassen sich verbinden: `G7HM5`, `Cmaj7 lydisch`.
- Notennamen sind englisch: B ist das deutsche H, Bb das deutsche B.
  Als Eingabe versteht fretgrep auch H.
- Geschrieben wird nach Stufen (Ab, nicht G#, als b9 von G). Die
  alterierte Skala steht so, wie Jazzbücher sie schreiben: G Ab Bb B Db
  Eb F.

**Deine Sammlung.** Fragst du nach Aufnahmen, durchsucht das Modell die
Datenbank (nach Bedeutung, wenn `FRETGREP_EMBED_MODEL` gesetzt ist, sonst
nach Stichwörtern) und nennt die IDs, etwa für `fretgrep play ID` oder
`fretgrep notes ID --show`. Die Abkürzungen aus dem Abschnitt
`[descriptions]` im Vokabular (z. B. `hm5`, `looper = mehrere Spuren übereinander`)
bekommt es ebenfalls mit.

**Gespräch.** Ohne Frage beginnt ein Gespräch, in dem Rückfragen wie „und
welche davon sind Spannungen?" möglich sind. Pfeiltasten bearbeiten die
Zeile, Strg+D oder `exit` beendet, Strg+C bricht eine laufende Antwort ab.

**Befehle im Gespräch.** Eine Zeile, die mit `!` beginnt, führt einen
fretgrep-Befehl aus, ohne das Gespräch zu verlassen: `!play 46` spielt
ab, `!playlist play "hm5 üben"` spielt eine Wiedergabeliste,
`!notes 46 --show` öffnet das Notenblatt, `!tones Dm7b5` zeigt Töne.
Nach dem Befehl (bei `play` also nach `q` in mpv) geht das Gespräch
weiter. Das Modell sieht diese Befehle und ihre Ausgabe nicht. Shell-Befehle
gehen auf diesem Weg nicht, nur fretgrep-Befehle.

**Gedächtnis.** Nach jeder Antwort speichert fretgrep das Gespräch unter
`~/.cache/fretgrep/chat.json`, auch nach einer einzelnen Frage. `-c`
(`--continue`) knüpft daran an: `fretgrep chat -c ja bitte` antwortet mit
dem Wissen um das vorige Gespräch, `fretgrep chat -c` ohne Frage setzt es
als Gespräch fort. Ohne `-c` beginnt jedes `fretgrep chat` neu und
überschreibt das gespeicherte Gespräch nach der ersten Antwort. Bei einer
einzelnen Frage antwortet das Modell gleich vollständig, statt
Rückfragen zu stellen, denn ohne `-c` könntest du nicht darauf antworten.

**Nur die Töne.** `fretgrep tones G7HM5` rechnet dasselbe wie das
Werkzeug des Assistenten, aber sofort und ohne Sprachmodell oder Server:

```
$ fretgrep tones G7HM5
Akkord G7: G B D F  [Intervalle 1 3 5 b7]
Skala G HM5 (Mixolydisch b9 b13, Phrygisch-Dominant): G Ab B C D Eb F  [Intervalle 1 b2 3 4 5 b6 b7]
  = 5. Modus von C harmonisch Moll
```

Was `tones` versteht, steht oben unter „Töne werden berechnet“ und bei
`fretgrep tones --help`.

**Dauer.** Eine Antwort von qwen3.8:27b braucht auf dem Host etwa eine
Minute; bis das erste Wort kommt, steht „… das Modell antwortet" da. Mit
`--think` überlegt das Modell erst (gedimmt sichtbar) und antwortet
gründlicher, braucht aber ein Mehrfaches. Ein anderes Modell wählt
`--model NAME`, etwa ein kleineres für schnellere Antworten.

## Ansehen, taggen, notieren

```sh
fretgrep list                  # alle Aufnahmen
fretgrep list --missing        # nur fehlende Dateien
fretgrep show 21               # alles zu Aufnahme 21
fretgrep tag 21 Favorit üben   # eigene Tags vergeben
fretgrep untag 21 üben         # eigene Tags entfernen
fretgrep note 21 langsam anfangen, Fingersatz prüfen
fretgrep note 21               # Notiz anzeigen
fretgrep note 21 --clear       # Notiz löschen
```

Die Nummer am Zeilenanfang von `list` und `search` ist die ID der Aufnahme.

fretgrep unterscheidet zwei Arten von Angaben:

- **Tag-Vorschläge** stammen aus dem Dateinamen und dem Ordner. Sie tragen
  eine Konfidenz zwischen 0 und 1 und werden bei jedem `scan` neu
  berechnet.
- **Eigene Tags und Notizen** stammen von dir. Kein Befehl außer `tag`,
  `untag` und `note` ändert sie. Dasselbe gilt für Wiedergabelisten und
  `playlist` bzw. `search --save`.

## Weitere Schalter

| Befehl | Schalter | Wirkung |
|---|---|---|
| `transcribe` | `21 22` | nur diese Aufnahmen |
| `transcribe` | `--limit 5` | höchstens so viele Aufnahmen |
| `transcribe` | `--redo` | vorhandene Transkripte neu erzeugen |
| `transcribe` | `--library ORDNER` | Ordner angeben statt `FRETGREP_LIBRARY` |
| `embed` | `--redo` | alle Vektoren neu berechnen |

`fretgrep --help` zeigt alle Befehle, den üblichen Ablauf und die
Einstellungen. `fretgrep BEFEHL --help` erklärt einen Befehl mit allen
Schaltern und Beispielen, etwa `fretgrep notes --help`.

## Blick in die Datenbank

Die Datenbank ist eine einzelne SQLite-Datei. Mit `-readonly` kann beim
Nachsehen nichts kaputtgehen:

```sh
sqlite3 -readonly ~/.local/share/fretgrep/fretgrep.db
```

Nützliche Eingaben in der SQLite-Konsole:

```sql
.tables
.schema auto_file
.mode column
.headers on

-- Aufnahmen mit Pfad
SELECT r.id, f.rel_path, f.duration_s
FROM recording r JOIN auto_file f ON f.recording_id = r.id
ORDER BY f.rel_path LIMIT 10;

-- Tag-Vorschläge einer Aufnahme
SELECT category, value, confidence, raw_token FROM auto_tag
WHERE recording_id = 21;

-- wie viele Vorschläge je Kategorie
SELECT category, count(*) FROM auto_tag GROUP BY category;

-- Transkripte mit Text
SELECT recording_id, language, text FROM auto_transcript WHERE text != '';

-- Vektoren: Modell und Länge
SELECT recording_id, model, length(vector) / 4 AS dimensionen
FROM auto_embedding LIMIT 5;

-- erkannte Noten: Anzahl je Aufnahme
SELECT recording_id, model, json_array_length(notes) AS noten FROM auto_notes;

-- eigene Tags, Notizen und Wiedergabelisten
SELECT * FROM user_tag;
SELECT * FROM user_note;
SELECT p.name, e.position, e.recording_id
FROM user_playlist p JOIN user_playlist_entry e ON e.playlist_id = p.id
ORDER BY p.name, e.position;
```

Mit `.quit` verlässt man die Konsole. Die Tabellen mit dem Namen
`search_index_...` gehören zum Suchindex und werden von SQLite verwaltet.
Was in welcher Tabelle steht, beschreibt die
[Architektur](architektur.md#datenmodell).

## Sichern

Alles, was sich nicht neu berechnen lässt, steht in der Datenbankdatei:
die eigenen Tags, Notizen und Wiedergabelisten. Eine Kopie dieser Datei
ist die Sicherung.
Die Aufnahmen selbst verändert fretgrep nie.

## Fehlermeldungen

| Meldung | Ursache und Abhilfe |
|---|---|
| „Datenbank … fehlt oder ist nicht aktuell“ | `fretgrep db upgrade` ausführen |
| „Kein Ordner angegeben und $FRETGREP_LIBRARY ist nicht gesetzt“ | Ordner angeben oder die Variable setzen; der Befehl hat nichts getan |
| „Bitte $FRETGREP_EMBED_MODEL setzen“ | die Variable setzen |
| „Kein Ollama-Server erreichbar (versucht: …)“ | Ollama läuft nicht oder lauscht an einer anderen Adresse, siehe Einstellungen |
| „Der Ollama-Server antwortet nicht richtig“ | meist fehlt dort das Modell (`ollama pull` auf dem Server) |
| „faster-whisper ist nicht installiert“ | `pip install -e ".[transcribe]"` |
| „mpv ist nicht installiert“ | `sudo apt install mpv` |
| „basic-pitch ist nicht installiert“ | die zwei Befehle aus dem Abschnitt Installation ausführen |
| „LilyPond ist nicht installiert“ | `sudo apt install lilypond` |
| „Kein Programm zum Öffnen gefunden (xdg-open)“ | `sudo apt install xdg-utils` oder `--sheet DATEI` benutzen |
| „Das Modell … gibt es auf dem Ollama-Server nicht“ | auf dem Server `ollama pull MODELL` ausführen oder `FRETGREP_CHAT_MODEL` ändern |
| „Die Suche enthält nur Füllwörter“ | andere Suchwörter wählen; die Suche nach Bedeutung kommt auch mit Füllwörtern zurecht |

## Hinweise, die keine Fehler sind

| Hinweis | Bedeutung |
|---|---|
| „Hinweis: … Gesucht wird nur nach Stichwörtern.“ bei `search` | Die Suche nach Bedeutung war nicht möglich, der Grund steht davor. Die Treffer stammen aus der Stichwortsuche. |
| „You are sending unauthenticated requests to the HF Hub“ bei `transcribe` | faster-whisper lädt beim ersten Lauf das Whisper-Modell herunter, ohne Anmeldung. Der Download läuft trotzdem; ein Token ist nicht nötig. |
| „Estimating duration from bitrate, this may be inaccurate“ bei `play` | Der Datei fehlt die Längenangabe im Kopf, mpv schätzt die Dauer. Die Wiedergabe ist davon nicht betroffen. |
| „mp3float: Header missing“ und „Error decoding audio“ bei `play` | Die Aufnahme enthält ein beschädigtes MP3-Stück von etwa 26 Millisekunden. mpv überspringt es und spielt weiter; hörbar ist höchstens ein winziger Aussetzer. Der Fehler steckt in der Datei, nicht in fretgrep. |
