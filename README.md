# CodexPi

Ein zentraler Codex-Worker auf dem Raspberry Pi, eine persistente Projektqueue
und ein Windows-Worker für ausdrücklich erforderliche native Windows-Jobs.
Dashboard, Discord und Scheduler teilen sich einen schlanken Python-Prozess.

## Alltag

Im Windows-Terminal:

```text
codexpi
/rename Mein Projekt
/goal Die vollständige Aufgabe
```

`codexpi` verbindet per SSH mit dem Pi. Einen vorhandenen Projektnamen erneut
anzugeben öffnet dessen gespeicherte native Session; es entsteht kein neues Goal.
Das Terminal kann geschlossen werden, die Pi-Arbeit läuft in tmux weiter.

Dashboard: **http://192.168.2.105:8787/**, nur im privaten LAN, mit Passwort.
Neue Projekte werden ausschließlich über `codexpi` angelegt, nicht im Browser
oder über Discord.

- **Resume** setzt fort oder reiht ein, ohne ein anderes laufendes Projekt zu
  verdrängen. Ohne ursprüngliches `/goal` wird nur die richtige Session geöffnet.
- **Pause** bleibt nach Neustarts wirksam. **Pause all** sperrt automatische Arbeit.
- **Run now** erscheint nur für eine tatsächliche Änderung der Queue-Reihenfolge.
- **Details** zeigt Session, Pfad, Repo, Commit-/CI- und Worker-Informationen.
- **Delete** verlangt den exakten Namen, beendet die Zuordnung, archiviert die
  Session und entfernt den Discord-Channel. Privates GitHub-Repo und lokales
  Recovery-Backup bleiben erhalten; Windows-Checkouts werden nicht gelöscht.
- **Usage / Limits** zeigt verbleibende Nutzung: 100% verfügbar, 0% aufgebraucht.
  Weekly ist Standard; die History enthält ausschließlich gespeicherte Messwerte.

Ein Resume gilt erst nach Controller-Bestätigung als erfolgreich. Bei einem
Timeout nicht wiederholt klicken oder `/goal resume` in weitere Sessions tippen;
den konkreten Fehler und die gespeicherte Session prüfen.

## Installation und Betrieb

Installationspfad Pi: `/home/raspberry/CodexPi`. Windows: `C:\CodexPi`.
Die benutzerspezifischen systemd-Dienste laufen als `raspberry` mit aktiviertem
Linger: `codexpi`, `codexpi-native`, `codexpi-unsnooze`.

```sh
systemctl --user status codexpi codexpi-native codexpi-unsnooze
/home/raspberry/CodexPi/bin/codexpi-tool windows-status
```

Die vorhandenen `Setup/`-Skripte dokumentieren die geprüfte Installation; sie sind
**kein ungeprüfter One-click-Installer für einen anderen Rechner**. Sie enthalten
die festen Pfade, ARM64-/Versionsannahmen und bestehende Benutzerzuordnungen.
Vor Neuinstallation oder Updates Versionen und lokale Konfiguration prüfen,
Backups erstellen und keine laufenden Goals unterbrechen. Secrets nicht in
Argumente, Screenshots, Logs oder Git übernehmen.

## Dokumentation

- [Architektur, Module und Datenmodell](docs/architecture.md)
- [Recovery, Backup/Restore und sichere Diagnose](docs/recovery.md)
- [Windows-Worker, Autostart und Protokoll](docs/windows-worker.md)
- [Queue-Pause und Freigaben](docs/manual-pause.md)
- [Rename/Delete](docs/lifecycle.md), [24/7-Pi-Deployment](docs/deployment.md)
- [Unsnooze und native Resume-Grenzen](docs/unsnooze.md)
- [Usage-History und Favicon](docs/usage-history.md)
- [Installations-/Prüfstand](docs/progress.md), [Requirement-Audit](docs/requirement-audit.json)

## Entwicklung und Prüfung

```powershell
cd C:\CodexPi
.venv\Scripts\python.exe -m unittest discover -s tests
.venv\Scripts\python.exe Setup\verify-secrets.py
py -3.11 Setup\verify-controller-recovery.py
py -3.11 Setup\verify-usage-ui.py --live
```

Der Recovery-Aufruf ohne `--crash` ist ein lesender Vorabcheck. Mit `--crash`
beendet er bewusst ausschließlich den inaktiven Controller-Prozess; vorher die
Beschreibung in `docs/recovery.md` lesen. UI-Prüfungen verwenden die vorhandene
isolierte Edge/Playwright-Testumgebung, keine neue Laufzeitabhängigkeit des Pi.

Der Gesamtauftrag ist noch **nicht abgeschlossen**. Einzelne bestandene Tests
ersetzen keinen vollständigen Audit. Reale Reboot-/Active-Goal-Recovery,
automatisches Unsnooze nach Provider-Reset und ausgewählte Windows-Migration
haben jeweils eigene Nachweispflichten; die Migration findet erst am Ende statt.
