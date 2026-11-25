# Projekt: Woodshed (CLI-Befehl: fretgrep)

## Ziel
Privates, nicht kommerzielles Tool, das meine Gitarren-Lick-Aufnahmen
durchsuchbar macht, z. B. "Blues über 251" oder "Chet Baker moll".

## Umgebung
- Entwicklung in einer VM (Kali, libvirt-NAT), dort läuft Claude Code.
- Lokale LLMs laufen per Ollama auf dem Host (mehr Ressourcen), erreichbar
  aus der VM über http://192.168.122.1:11434. Endpoint und Modellname als
  Konfiguration (Umgebungsvariable oder Config-Datei), nie hartkodiert.
- Das Nachbarprojekt "cai_testing" nutzt diese Anbindung bereits und dient
  als Referenz. Nur lesen, nichts daran ändern.
- Netzwerk: keine Netzwerkkonfiguration von VM oder Host ändern, keine
  neuen Brücken oder Freigaben anlegen, keine Zugangsdaten zum Host im Repo.
- Whisper und basic-pitch laufen zunächst in der VM. Wenn zu langsam,
  Auslagerung auf den Host prüfen und vorschlagen, nicht eigenmächtig tun.

## Daten
- Aufnahmen: MP3, mono, 44,1 kHz, ca. 35 s, aktuell ca. 130+ Dateien,
  Handy-Diktiergerät, meist solo ohne Backing Track. Teils gesprochene
  Erklärungen in den Aufnahmen.
- Ordner: 251/{major,minor,unsortiert} sowie Ordner zu einzelnen Songs.
  Struktur teilweise durcheinander: Ordnernamen nur als schwachen
  Hinweis nutzen, nie als alleinige Wahrheit.
- Dateinamen: gemischt Deutsch/Englisch, Tippfehler, Leerzeichen am Ende,
  Umlaute, uneinheitliche Akkordschreibweise (Cj7 = cmaj7).
  Unicode NFC-normalisieren, robust parsen.
- Quelle der Dateien: lokaler Ordner. Ingest aus Filen.io (CLI/WebDAV/
  rclone) ist eine Idee mit niedriger Priorität, nicht Teil von Phase 1.

## Glossar
- 251 = ii-V-I, dur/moll; Lage = Gitarrenposition (v.lage = 5. Lage)
- HM5 = Harmonisch-Moll-5 (Mixolydisch b9 b13); alt = altered
- trit = Tritonus-Substitution; simp = simple (vereinfachte Variante)
- twnby/twnbay = "There Will Never Be Another You"
- CC = Charlie Christian; mit looper = mehrere Spuren übereinander
- Namen wie wes, joe pass, baker, raney, larsen, malone, benson,
  barry harris, mobley, cecil, gould = Vorbilder/Stilquellen

## Anforderungen
1. Intelligente Suche (Stichwort plus semantisch).
2. Nachträglich Tags und Notizen vergeben; getrennt von automatisch
   erzeugten Daten, werden nie überschrieben.
3. Wiedergabe mit Tempo-/Tonhöhenänderung wie mpv, A-B-Loop.
4. Notenerkennung der gespielten Gitarre, zunächst Test an ca. 5 Licks.

## Rahmenbedingungen
- Python, PEP8/Pylint-konform, gut lesbar. Open Source, lokal, kein Snap
  (apt oder pip). Nur das Gefragte bauen, keine Zusatzfeatures.
- Datenbank: SQLAlchemy plus Alembic für alle Schemaänderungen, kein
  create_all(). Migrationen versioniert im Repo, eine Revision pro
  Änderung. Bei SQLite render_as_batch=True. FTS5-Tabellen erkennt
  Autogenerate nicht: per op.execute() mit rohem SQL anlegen und prüfen.
- Datenmodell: auto_meta (neu berechenbar) strikt getrennt von user_meta
  (meine Tags/Notizen). Migrationen dürfen user_meta nie verwerfen.
- Stabile Datei-ID über Inhalts-Hash, nicht über Pfad.
- Technikvorschläge (faster-whisper, basic-pitch, SQLite+FTS5,
  mpv/rubberband) sind unverbindlich. UI-Wahl und Scope sind offen.

## Vorgehen
- Phase 1: Dateien einlesen, Dateinamen parsen (Tags mit Konfidenz, als
  Vorschlag markiert), in SQLite speichern, mit Tests.
- Bei Unklarheit nachfragen statt raten.