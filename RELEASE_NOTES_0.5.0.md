# UltraPilot v0.5.0

Prepared: 2026-10-04. App and installer application version: 0.5.0.
No tag, GitHub release, commit, push or deployment is created by preparing these files.

## Source range and date provenance

Previous version: 0.4.2, introduced by commit
[`0755c0d375e65ad8918bb6a8e4ef0548d71416f2`](https://github.com/matule123/Ultrapilot/commit/0755c0d375e65ad8918bb6a8e4ef0548d71416f2).
The GitHub commit API and local Git agree on **2026-08-01 11:30:04 UTC / 13:30:04 Europe/Bratislava**.
This is the commit timestamp, **not a verified push timestamp**. The GitHub releases API returned an empty list on 2026-10-04; no published 0.4.2 release timestamp is available.

The reviewed range is `0755c0d..02dbdd2`: **115 commits**. The announcement consolidates their final effects rather than presenting superseded intermediate fixes as separate currently supported behaviors.

## What the application displays

The Slovak welcome begins with **v0.5.0 je tu!** and an opening paragraph.
`assets/app_release_notes.json` is the authoritative UI text, with 21 application-update bullets, a separate scope/compatibility section and plugin snapshots. It covers lateral control, packet performance/freshness, route building/topology, activation, transmissions, paired pedals, speed control, curve preview, ACC traffic, service-brake wait and signal restart, the new 1.59 traffic DLL, HUD/AR/map, settings/sounds, diagnostics/export, vehicle-profile and maneuver foundations, filtered updater, plugin versions and validation reports.

The lower plugin section uses `PLUGIN_CHANGELOG.md` to show **every documented intermediate release**, including the initial 1.0.0 tracking baseline. Version 0.4.2 predates independent plugin versions; no retroactive plugin version is invented. Older unversioned changes are covered in the app bullets and the inventory below.

The application version is synchronized across `core/update_check.py`, `installer.py` and the README badge. Plugin versions are not bumped simply because the app release number changes. The installer tool's own version is unchanged.

## Verification boundaries

Release notes distinguish implementation and offline regressions from live-game certification. Automatic restart needs the new compatible signal DLL, fresh relevant green acquisitions, uninterrupted service-brake evidence and valid authority. The geometric signal selector is a heuristic; physical hill hold, every intersection and complete traffic coverage are not certified. Predictive roundabout yielding, general stop-and-go, full trailer guidance and universally natural steering remain limited or deferred.

First launch can show the welcome even without an old announcement-state file, using the explicit published predecessor. Dismissal is persisted per installation. Same-version commit updates do not replay the announcement or move the app-release plugin baseline.

## Complete reviewed commit inventory

- `609e4af` — 2026-08-01 — vylepšené live map zobrazenie
- `c81febe` — 2026-08-01 — opravené chyby v hude a iné chyby
- `6c776c0` — 2026-08-01 — opravené chyby riadenia a ostatné chyby
- `6c3f3a0` — 2026-08-07 — Opravené držanie stredu pruhu
- `ec7035f` — 2026-08-07 — opravené chyby vykreslovania čiar v hude
- `656e2a9` — 2026-08-07 — Stabilizácia riadenia a autority pruhu
- `0867132` — 2026-08-08 — fáza 3:Spevnenie topológie a geometrie navigačných trás
- `3950125` — 2026-08-08 — fáza3:Bezpečné plánovanie zmien pruhov pred križovatkami
- `92cd6e0` — 2026-08-08 — zmeny v UI aplikácie a inštalátora
- `d8b7554` — 2026-08-08 — úpravy logu
- `123433f` — 2026-08-08 — Update logger.py
- `c28e8f1` — 2026-08-08 — upravy 3 guličiek
- `9bbe2bb` — 2026-08-08 — upravená karta nastavení a iné zmeny
- `d1fc7cb` — 2026-08-08 — upravene nastavania karta a rozloženie
- `f24b468` — 2026-08-08 — upravy logu
- `5e29092` — 2026-08-08 — opravené chyby v aplikácii
- `5b3508a` — 2026-08-08 — opravená pozícia 3 guličiek
- `f841751` — 2026-08-08 — opravené vypnutie v strede križovatky a zobrazovanie vypočítanej cesty v hude
- `0805ae5` — 2026-08-08 — pokus o opravu nestability riadenia
- `430c819` — 2026-08-08 — opravené niektoré chyby
- `7c58905` — 2026-08-08 — opravené chyby hudu a ostatných veci
- `dead539` — 2026-08-08 — opravené niektoré chyby
- `fc18894` — 2026-08-09 — Oprava stability riadenia, lokalizácie pruhov a HUD navigácie
- `ea46981` — 2026-08-09 — opravené pretáčanie v zákrute opravený hud a vylepšená live mapa
- `b67a1d0` — 2026-08-09 — vylepšený systém brzdenia v zákrutách  a stabilizácia riadenia v náročných podmienkach
- `e5afe2b` — 2026-08-09 — opravený plugin smeroviek a ich fungovanie
- `5b0b09b` — 2026-08-09 — opravená chyba pretáčania v tažkých podmienkach
- `06111a0` — 2026-08-10 — prerobený systém riadenia
- `0977170` — 2026-08-10 — opravené chyby nadídania v naročných zákrutách a dalšie opravy
- `d0b7952` — 2026-08-10 — opravené chyby brzdenia a AR čiary
- `3dc2454` — 2026-08-10 — prerobený systém renderovania AR čiary
- `aa33849` — 2026-08-10 — Plynulé a fyzikálne obmedzené riadenie volantu
- `b561b3b` — 2026-08-10 — Oprava kmitania riadenia po výjazde zo zákruty
- `704a404` — 2026-08-11 — Oprava nestabilného riadenia a kompenzácie návesu
- `a417091` — 2026-08-11 — opravené chyby zatáčania
- `0dd8d68` — 2026-08-12 — velká oprava kmitania a chýb v zatačaní a nový regulátor
- `0d82596` — 2026-08-15 — Prepracovanie riadenia na stabilný preview-pursuit regulátor
- `e8d5c57` — 2026-08-16 — doladenie chýb riadenia
- `df90c18` — 2026-09-05 — Prepracovanie a bezpečnostný audit riadenia autopilota
- `be7f6d0` — 2026-09-06 — opravy kmitania riadenia
- `f922893` — 2026-09-06 — pridana diagnostika na riadenie
- `556b9c5` — 2026-09-07 — Oprava plynulosti a kontinuity riadenia v zákrutách
- `77857fd` — 2026-09-09 — Spoľahlivá frame-bound diagnostika riadenia
- `64a10d9` — 2026-09-09 — Stabilizácia geometrie LanePath na hraniciach LaneId
- `67e3a5f` — 2026-09-09 — Oddelenie referencie kabíny od diagnostiky návesu a dočasne odstránenie trailer ofset pre blízke pridanie swept enviroper
- `089cd0c` — 2026-09-09 — Oprava predikcie CTE a stabilizácia priečneho riadenia
- `e53ee18` — 2026-09-10 — Oprava referenčného bodu kabíny v priečnom riadení
- `7f3d365` — 2026-09-10 — `Kalibrácia riadiaceho aktuátora a časovania`
- `d2e4453` — 2026-09-11 — tabilizácia geometrickej projekcie riadenia v zákrutách
- `0a75bf1` — 2026-09-11 — Synchronizácia telemetrie, výpočtu trasy a 60 Hz vykonávania riadenia
- `221cc90` — 2026-09-11 — opravené časovanie odosielania povelov
- `d92de66` — 2026-09-12 — Pridanie swept-envelope modelu a pridané získavanie viacero udajov z SDK
- `07d56e8` — 2026-09-12 — Pridanie bezpečného 3D kontraktu prejazdnej plochy pre swept-envelope plánovanie
- `8568c55` — 2026-09-12 — Pridanie fyzikálne validovaného plánovača lokálnych manévrov pre celú súpravu
- `839bd1a` — 2026-09-13 — Integrácia lokálneho manévru s autoritatívnou trasou a prefabovou topológiou
- `d10829a` — 2026-09-13 — Bezpečná runtime integrácia lokálnych manévrov s premávkou a atómovou referenciou
- `933f4ed` — 2026-09-14 — Produkčné dôkazové zdroje pre bezpečné manévre a kvalifikáciu celej súpravy
- `05d4f76` — 2026-09-14 — Odstránenie omylom sledovaných pytest artefaktov
- `da508ea` — 2026-09-14 — Bezpečný diagnostický zber reálnych dôkazov pre lokálne manévre
- `0308f0a` — 2026-09-14 — Oddelenie diagnostických evidence výstupov od diagnostiky navigačných trás
- `0e53c90` — 2026-09-14 — Odstránenie sledovaných pytest fixture výstupov
- `08a91fb` — 2026-09-15 — opravené a pridané niake veci
- `20f6f08` — 2026-09-22 — Automatický resolver assetov a kompilátor profilov vozidiel
- `107527a` — 2026-09-23 — Pridať overovanie vozidlových assetov a kalibrované dekódovanie PMC
- `33ec57c` — 2026-09-24 — Fix trailer diagnostics preflight without requiring stationary autopilot commands
- `7e5d20d` — 2026-09-24 — Fix large trailer diagnostic exports with verified chunked files
- `89b6248` — 2026-09-26 — Add passive steering command-to-game boundary diagnostics
- `93af709` — 2026-09-27 — Keep unbound steering response monitor offline
- `0ebf3fa` — 2026-09-27 — Mark lane width provenance and inactive trailer guidance
- `10f549e` — 2026-09-27 — Add offline trailer guidance experiment - still not implemented
- `166fb0f` — 2026-09-27 — Fix route confidence decay across validated prefab corridors
- `1c4c2d1` — 2026-09-27 — Fix route start localization on connected prefab branches
- `6d6f2ab` — 2026-09-27 — Fix prefab-entry route builds and reject stale steering on activation
- `848b49c` — 2026-09-27 — Show precise route-build failure reasons in logs and Dynamic Island
- `eec165c` — 2026-09-27 — Guard autopilot drive commands against neutral, reverse and stale packets
- `ea8e521` — 2026-09-27 — Require confirmed forward gear and remove automatic Drive pulses
- `0acdcdf` — 2026-09-28 — Add guarded one-press Drive engagement with SDK gear confirmation
- `78dc485` — 2026-09-28 — Allow one-press Drive engagement without parking brake
- `9f179cb` — 2026-09-28 — Fix autopilot launch for ETS2 simple automatic transmission and added automatic detector for transmition mode
- `d9cc769` — 2026-09-28 — Improve transmission mode UI and some UI changes, detection and notification sounds
- `53ab8e6` — 2026-09-28 — fixed bugs vyth seting SDK card
- `932f691` — 2026-09-28 — Add phase timing diagnostics for stale steering packets
- `ce7bd41` — 2026-09-29 — Capture passive steering timing without autopilot engagement
- `67f8661` — 2026-09-29 — Fix stale steering packets and optimize navigation handoff and added new system of calculating geometry from game
- `cce61a4` — 2026-09-29 — Fix simple automatic gear-zero transitions across Autopilot and Engine
- `78cadea` — 2026-09-30 — Fix activation telemetry snapshot consistency and freshness checks
- `c248acd` — 2026-09-30 — Fix simple automatic launch throttle handoff
- `90f3a6c` — 2026-09-30 — Publish steering revision with active GPS control packet
- `c5d63ef` — 2026-09-30 — Stabilize autopilot activation and Map control timing
- `2b6306f` — 2026-09-30 — Guard final steering writes and controlled stops
- `da108d2` — 2026-10-01 — Validate steering packets and stabilize safety handoff
- `cbcfd8a` — 2026-10-01 — Restore steering packet cadence by skipping unnecessary route validation
- `e989fc9` — 2026-10-01 — Fix duplicate SDK frame rejection and preserve steering failure reasons
- `e16e2a5` — 2026-10-01 — Add independent plugin versions and document deferred work
- `77736d3` — 2026-10-01 — Add phase 6 offline validation report and reproducible metrics
- `daa57f5` — 2026-10-01 — Clarify runtime source parity in phase 6 report
- `58d4669` — 2026-10-02 — Fix duplicate diagnostic frames and export rejected collections
- `2798aa3` — 2026-10-02 — Handle paused SDK frames and fix diagnostic capture timing
- `ea63a74` — 2026-10-02 — opravené niektoré chyby
- `3ef65c7` — 2026-10-02 — fix(map): revalidate SDK freshness after localization
- `c5cedbb` — 2026-10-02 — feat(plugins): show plugin versions and add release changelog
- `0ed71aa` — 2026-10-02 — fix(diagnostics): decouple collection identity from GPS route validity
- `1f592ce` — 2026-10-02 — docs: close phase 6 with scoped verification results
- `7adf8c8` — 2026-10-03 — Improve pedal coordination and bump affected plugin versions
- `9ffd5ac` — 2026-10-03 — Improve speed-control smoothness and bump ACC and Autopilot to 1.0.2
- `8400637` — 2026-10-03 — Improve route-aware ACC following and bump affected plugin versions
- `2126aab` — 2026-10-03 — Complete offline Phase 7 integration checks and document results
- `0107430` — 2026-10-03 — fix(updater): install only runtime files and protect user data
- `826cc86` — 2026-10-03 — feat(diagnostics): record longitudinal commands and ACC decisions
- `99c4ff7` — 2026-10-03 — fix(engine): resolve longitudinal freshness and activation token races
- `b9fb484` — 2026-10-03 — fix(longitudinal): preserve authority during GPS window advances
- `8885bd9` — 2026-10-03 — fix(longitudinal): refresh commands before writes and anticipate curve braking
- `3f11cb7` — 2026-10-03 — fix(safety): reject stale planner braking and preserve intervention reasons
- `fe0a992` — 2026-10-04 — feat(autopilot): add continuous brake holding and automatic traffic-light resume
- `02dbdd2` — 2026-10-04 — feat: add app release announcements and plugin version history
