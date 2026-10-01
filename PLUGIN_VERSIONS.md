# Verzie pluginov

Každý vstavaný plugin má vlastnú triednu konštantu `VERSION` vo svojom
`plugins/<plugin>/main.py`. Formát je `MAJOR.MINOR.PATCH`.

- PATCH: oprava bez nekompatibilnej zmeny rozhrania.
- MINOR: nová spätne kompatibilná funkcia.
- MAJOR: nekompatibilná zmena rozhrania alebo konfigurácie.

Úvodná verzia všetkých 12 vstavaných pluginov je 1.0.0: acc, autopilot,
collision, discord, drivepolicy, ecodrive, hud, lanecontrol, map, toll, tts,
turnsignals. Ide o začiatok samostatného verzovania, nie o certifikáciu
dokončenosti ani rekonštrukciu historických vydaní.

Pri zmene pluginu uprav jeho VERSION a popíš zmenu v commite. Číslo sa
nezvyšuje pri každom spustení ani automaticky podľa počtu commitov.
Správca kontroluje formát pri načítaní, zaznamená verziu do logu a publikuje
slovník `plugin_versions` pre načítané pluginy. Vypnuté pluginy sa nenačítajú.
Externý plugin bez vlastnej VERSION zdedí 0.0.0 (neversionovaný).

Tento systém neinštaluje samostatné aktualizácie pluginov a zatiaľ nekontroluje
kompatibilitu ich závislostí. Aktualizácie naďalej používa existujúci mechanizmus
UltraPilotu. Samostatné aktualizácie možno doplniť v budúcnosti.
