# Fáza 6 – etapa 2: kontrolované herné overenie

## Stav

**Príprava zberu: PASS. Herné meranie: NOT VERIFIED – čaká sa na používateľov zber.**

Kontrola 1. 10. 2026 nad HEAD `daa57f507b04f1e5fc8a403cda7efdea2e57e526`.
Pracovný strom bol pri začatí čistý; upozornenie na neprístupnú `.pytest_cache`
nie je zmena zdrojov. Používateľ potvrdil úspech celej pytest sady v etape 1;
počty nedodal. Agent celú sadu neopakoval. Pravidlá verzovania sú v
`PLUGIN_VERSIONS.md`, metodika a baseline v `PHASE6_STAGE1_RESULTS.md`.
Odložená prirodzenosť riadenia a nadchádzanie zostávajú mimo tejto etapy.

Produkčný kód, regulátor, geometria, limity ani timestampy sa nemenili.
Verzie pluginov sa preto nezvyšujú. Živý zber nebol armovaný a do inštalácie
sa nezapisovalo. Izolovaná predkontrola pracovala iba so syntetickými dátami
v ignorovanom `docs/steering-audit`.

## Kompatibilita inštalácie

Inštalácia: `C:\Users\PC\AppData\Local\Programs\UltraPilot`.
Read-only kontrola 1. 10. 2026 o 20:29:44 miestneho času:

| Súbor | SHA-256 inštalácie | Zhoda so zdrojom |
| --- | --- | --- |
| core/navigation/evidence_diagnostics.py | dd9f6ca5603056dbfff320d54680ff8c145dcfefac7cd9f66b3abb2c75e89150 | bajtová |
| core/steering_executor.py | 5741b3fa9f9f4b02a7e95cd1dcfec93377ba7b6936feca26b0d2e8cef2dc6a80 | bajtová |
| core/steering_replay.py | 4aa79898d2d886987b0eb63a4e9e376e833169c003015268b4a6dc388bf08f4a | bajtová |
| tools/manage_maneuver_diagnostics.py | 1ec5d751eeb9309b5741b9b2e49d9ebf498bbc6d6dfe5db252f4d3e769094c67 | bajtová |
| core/engine.py | 9987863812a7f468bec6da4496d770dfa82f737367a2ab4a79f730cedb900a94 | obsahová; rozdiel iba CRLF/LF |
| plugins/autopilot/main.py | fadad0fc5c30bc25508c3eb6b980424cd2bcf9e233e9c702916f8db1a84e61c3 | obsahová; rozdiel iba CRLF/LF |

Map, Engine a Autopilot boli obsahovo porovnané aj v etape 1. Zhoda súborov
nepotvrdzuje verziu modulov už načítaných v bežiacom procese; postup preto
vyžaduje úplné vypnutie UltraPilotu pred armovaním a jeho následné spustenie.

Diagnostika je aktuálne DISABLED, nastavenie `enabled=false`,
`confirmed=false`, `runtime_authorized=false`. Štyri pôvodné kolekcie zostali
zachované. Limit ôsmich kolekcií zatiaľ umožňuje nový zber bez mazania.

## Izolovaná predkontrola

Existujúca schéma 1 a combined export postačujú; nový zberač netreba.

| Kontrola | Výsledok |
| --- | --- |
| 3 000 syntetických vzoriek, 300 s / 0,1 s, kapacita 3 600 | export READY_FOR_OFFLINE_REVIEW, 0 zahodených |
| Manifest a všetky chunky | inspect: integrity_valid=true, 80 súborov, 3 000 vzoriek |
| Státie bez povelu | 3 vzorky bez falošného command binding |
| Immutable capture zdrojového packetu | 2 997 naviazaných syntetických povelov; neskoršia zmena zdrojového dict nemení export |
| Calculation sequence, submission sequence, calculation/application SDK frame, pôvodné časy a identita | zachované a overené po exporte |
| CTE, body tracking heading error, rýchlosť, gameSteer a tyre angles | presné názvy kanálov overené po exporte |
| Skutočné volanie Engine backendu pred ponukou collectoru; stale odmietnutie | existujúce produkčné hraničné testy PASS s izolovaným backendovým dvojníkom |
| Pozorovateľská vetva Autopilotu, manuálny zber, prerušený export, kolízia ID, poškodený manifest, CLI a absencia JSON práce na výstupnej hranici | 9 cielených testov PASS, 13 deselected |
| Existujúci tools/analyze_phase6_stage1.py | izolovaný export načítaný a vyhodnotený |
| compileall pre použitý zberač, executor, replay, CLI, analytický nástroj a izolovaný skript | PASS |
| git diff --check a whitespace kontrola nového reportu | PASS |

Prvý export v filesystem sandboxe skončil DIAGNOSTIC_EXPORT_WRITE_FAILED;
čítanie úspešného exportu v sandboxe následne explicitne vyvolalo PermissionError.
Rovnaká predkontrola mimo tohto obmedzenia prešla. Produkčný export sa kvôli
environmentálnemu obmedzeniu nemenil. Izolované SDK hodnoty sú syntetické;
nejde o meranie v ETS2 ani o dôkaz spotreby DLL.

Reprodukčné podklady zostávajú ignorované:
`docs/steering-audit/preflight_phase6_stage2_20261001.py`,
`phase6-stage2-collection-preflight-20261001.json`,
`phase6-stage2-installation-preflight.json` a
`phase6-stage2-isolated-analysis-20261001.json` v tom istom priečinku.

## Kanály a pravidlá párovania

| Kanál | Umiestnenie / význam |
| --- | --- |
| Immutable cieľ | automatic-observations: executor.source_packet |
| Výpočet | source_packet.calculation_sequence, sdk_frame_us, computed_at, observation_timestamp |
| Identita | navigation_intent_id, route_build_id, authority_revision/revision, source_game_session_id, source_map_key, source_dataset_fingerprint a lane_match_snapshot.active_lane_id |
| CTE kabíny | source_packet.lane_match_snapshot.lateral_error_m, metre; SDK chassis-origin LaneMatch, nie náprava návesu |
| Heading | source_packet.body_tracking_error_rad; LaneMatch heading_error_rad vykazovať osobitne, nemiešať referencie |
| Rýchlosť pri výpočte | source_packet.observation_speed_ms, m/s; truck.speed je iné, capture-time pozorovanie |
| Vykonávač | executor.submission_sequence, execution_monotonic_s, output |
| Backendový zápis | backend_sent, engine_steer, command_binding_proven, steering_boundary.steering_write_returned_at_s, application_sdk_frame_us |
| SDK odozva | truck.sdkFrameTimeUs, gameSteer, roadWheelAnglesRad, yawRateRadS, pose a captured_at_s |

Zápis a SDK údaje z rovnakého riadku nie sú automaticky kauzálne súčasné.
Odozvu hodnotiť až z neskorších jedinečných SDK frame v rovnakej identite,
so zachovaným intervalom neistoty času SDK pozorovania. Readback nie je dôkaz
spotreby DLL; raw joy.x nie je merané. Zber má **atomic=false** a poskytuje
iba kandidátov na offline posúdenie, nie potvrdený fyzický profil.

Combined vzorkuje potvrdené backendové zápisy približne 10 Hz. Dense replay
pri zapnutej diagnostike uchová aj source-bound priebeh vykonávača približne
60 Hz; nie každý jeho riadok dokazuje fyzický backendový zápis. Maximá
step/rate/acceleration preto uviesť oddelene pre vzorkované fyzické zápisy
a vykonávač. Riedke vzorky nesmú certifikovať maximum všetkých fyzických tickov.

## Jeden používateľský zber – presný postup

### 1. Príprava pri úplne vypnutom UltraPilote

ETS2 môže byť pripravené na bezpečnom mieste. Vyber krátky okruh: voľná rovina,
široká ľavá/pravá zákruta a jeden celý kruhový objazd vrátane výjazdu. Žiadne
vyvolávanie porúch. Nastavenia riadenia ani prevodovky počas zberu nemeň.
UltraPilot úplne ukonči aj v systémovej lište. Potom v jednom PowerShell okne:

```powershell
cd 'C:\Users\PC\Documents\GitHub\ets2la'
$env:PYTHONCASEOK='1'
$tool = 'tools/manage_maneuver_diagnostics.py'
$out = 'C:\Users\PC\AppData\Local\Programs\UltraPilot\evidence-diagnostics'
$settings = 'C:\Users\PC\AppData\Local\Programs\UltraPilot\settings.json'
$id = 'phase6-stage2-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
if (Test-Path (Join-Path $out $id)) { throw 'STOP: collection-id už existuje.' }
python $tool arm --settings $settings --output $out --collection-id $id --purpose combined --duration 300 --sample-period 0.1 --capacity 3600 --max-sessions 8
if ($LASTEXITCODE -ne 0) { throw 'STOP: arm zlyhal, nezačínať jazdu.' }
$budget = [System.Diagnostics.Stopwatch]::StartNew()
$id
```

Päťminútový limit beží od prijatia arm príkazu workerom pri spustení aplikácie.
Časovač vyššie je konzervatívnejší, od zadania príkazu. Približne 3 000 vzoriek
sa zmestí do kapacity 3 600 bez očakávaného prepisovania. Nie je potrebná nová
inštalácia. STOP pri chybe príkazu, existujúcom ID alebo limite kolekcií;
nič staré nemaž. V tomto dokumente sú príkazy pripravené pre používateľa,
agent ich proti inštalácii nevykonal.

### 2. Spustenie aplikácie a stojaca predkontrola

Spusti UltraPilot s vypnutým autopilotom. Súprava stojí, parkovacia brzda
zatiahnutá, platná GPS trasa. Počkaj na hru, Map a zber; príprava má rezervu
približne 60–120 s. V stojacom stave skontroluj:

```powershell
$a = python $tool status --output $out | ConvertFrom-Json
Start-Sleep -Seconds 2
$b = python $tool status --output $out | ConvertFrom-Json
$b | ConvertTo-Json -Depth 6
if ($a.collection_id -ne $id -or $b.collection_id -ne $id -or $b.purpose -ne 'combined' -or $b.state -ne 'COLLECTING' -or -not $b.accepting_samples) { throw 'STOP: zber nie je pripravený.' }
if ($b.sample_count -lt 3 -or $b.sample_count -le $a.sample_count -or $b.trailer_preflight.latest_sdk_frame_us -le $a.trailer_preflight.latest_sdk_frame_us -or -not $b.trailer_preflight.vehicle_stationary) { throw 'STOP: nerastú vzorky/SDK frame alebo vozidlo nestojí.' }
if ($b.confirmed -ne $false -or $b.runtime_authorized -ne $false) { throw 'STOP: nesprávny diagnostický stav.' }
if ($budget.Elapsed.TotalSeconds -gt 150) { throw 'STOP: málo času na celý manéver; nerozbiehať sa, dokončiť zber.' }
```

Zber nevyžaduje pripojený náves. Trailer-specific preflight môže byť pri kabíne
bez návesu false; nie je to odmietnutie merania kabíny. Rast frame nie je dôkaz
atómového snapshotu ani stojaceho command binding. Pri predkontrole sa povel
autopilota úmyselne nevyžaduje. STOP tiež pri neplatnej trase, nepripojenej hre,
nerastúcej telemetrii, REJECTED_STALE či rastúcom výpadku zberu.

### 3. Jeden prejazd

Až po predkontrole a pri pripravenosti vodiča uvoľni parkovaciu brzdu a raz
stlač N. Bez ručného plynu pri overovaní automatického rozjazdu. Ak aktivácia
zlyhá, N neopakuj kvôli získaniu úspechu; bezpečne zostaň stáť a exportuj dôvod.
Prejdi krátku rovinu, ľavú a pravú zákrutu a celý kruhový objazd s výjazdom
na rovinu pri primeranej rýchlosti. Bez nastavovania počas jazdy a bez
sledovania PowerShellu za jazdy. Poznač čas prvého N a začiatok/koniec manévrov
a to, či bol ručný zásah. Nevynucuj dokončenie okruhu kvôli časovému limitu.

**Okamžitý STOP a prevzatie vodičom:** cúvanie/R, neočakávaný plyn či radenie,
odchádzanie z pruhu, prudký/oscilačný volant, stale/strata lokalizácie, výstražné
svetlá alebo kontrolované zastavenie, nejasný stav autority či bezpečnostné
odmietnutie. Neskúšať za jazdy vyvolať stale stav alebo zmeniť trasu/režim.

### 4. Bezpečné ukončenie, finish a inspect – aplikáciu ešte nevypínať

Pri normálne aktívnom autopilote ho vypni jedným N a manuálne bezpečne zastav.
Ak už bol automaticky vypnutý, ďalšie N nestláčaj, aby si ho znovu nezapol.
Vozidlo zabezpeč parkovacou brzdou. UltraPilot nechaj otvorený až do úspešného
inspect; jeho predčasné vypnutie zruší nedokončený ring buffer.

```powershell
$s = python $tool status --output $out | ConvertFrom-Json
if ($s.collection_id -ne $id) { throw 'STOP: nesprávna kolekcia.' }
if ($s.state -in @('ARMED','COLLECTING')) {
    python $tool finish --output $out --collection-id $id
    if ($LASTEXITCODE -ne 0) { throw 'STOP: finish zlyhal, aplikáciu ponechať otvorenú.' }
}
# SAMPLE_COMPLETE znamená prípravu exportu, nie dokončený manifest.
# Ak už uplynul limit a stav je READY_FOR_OFFLINE_REVIEW, finish neposielať znovu.
$deadline = (Get-Date).AddMinutes(3)
do {
    Start-Sleep -Seconds 2
    $s = python $tool status --output $out | ConvertFrom-Json
    $s | Select-Object state, reason, collection_id, sample_count, dropped_samples
} while ($s.collection_id -eq $id -and $s.state -in @('ARMED','COLLECTING','SAMPLE_COMPLETE') -and (Get-Date) -lt $deadline)
if ($s.collection_id -ne $id -or $s.state -ne 'READY_FOR_OFFLINE_REVIEW') { throw 'STOP: export nie je hotový/platný. Nezačínať ďalší zber; ponechať aplikáciu otvorenú a poslať status.' }
$collection = Join-Path $out $id
python $tool inspect $collection
if ($LASTEXITCODE -ne 0) { throw 'STOP: integrita exportu neprešla.' }
```

Export nie je garantovaný do dvoch sekúnd; poll čaká až tri minúty. Pri
prekročení čakania nezačínať nový zber ani vypínať aplikáciu počas zápisu;
poslať presný status. Úspešný inspect musí uviesť integrity_valid=true,
sample_count aspoň 30, confirmed=false a runtime_authorized=false. To potvrdí
integritu, nie dostatočnosť každého riadiaceho kanálu alebo úspech jazdy.

### 5. Vypnutie aplikácie a následné disable

Po úspešnom inspect UltraPilot normálne ukonči, potom v tom istom PowerShelli:

```powershell
python $tool disable --settings $settings --output $out
if ($LASTEXITCODE -ne 0) { throw 'STOP: disable zlyhal.' }
if ((Get-Content $settings -Raw | ConvertFrom-Json).maneuver_evidence_diagnostics.enabled -ne $false) { throw 'STOP: diagnostika zostala povolená.' }
```

Kolekcia zostáva zachovaná. Status pri vypnutom workeri môže ešte ukazovať
READY_FOR_OFFLINE_REVIEW; disable nastavuje config/control, neprepisuje úspešný
manifest. Pošli `$id`, výstup posledného status a inspect, informáciu o prvom N
a ručnom zásahu. Dáta na vyhodnotenie: celý priečinok kolekcie vrátane manifestu
a všetkých chunkov, log príslušného časového okna a najnovší manual_disable alebo
automatic_disable dense replay / plugin_stop timing z tej istej session.
Samostatný manifest bez chunkov nestačí. Video sa nevyžaduje.

## Vyhodnotenie po dodaní dát

Použiť existujúci `tools/analyze_phase6_stage1.py --collection <priečinok>
--output docs/steering-audit/phase6-stage2-game-metrics.json`; pripojiť správny
`--replay` a log iba s explicitným `--log-start`, `--log-end`, `--log-build`.
Výsledky následne doplniť do tohto sledovaného reportu. Surové dáta zostávajú
mimo Gitu. Dĺžka/sample count musia byť uvedené pre každý segment zvlášť.

Existujúci nástroj rozlišuje active a inactive_unclassified. Rozjazd, manuálny
úsek a bezpečnostné zastavenie oddeliť navyše podľa logovaných prechodov
probe/handoff/disable a platnej časovej väzby, nie podľa domnienky z gear=0.
Ak chýba jednoznačný prechod, daný úsek zostáva neklasifikovaný / NOT VERIFIED.
Nespojovať segmenty cez zmenu session/intent/revision/build/mapy/datasetu,
neplatné údaje ani medzeru nad 500 ms. Opakované frame deduplikovať a vykázať.

CTE RMS = sqrt(mean(CTE²)); časovo váženú RMS počítať s trapézovými váhami
medzi platnými susednými vzorkami rovnakého segmentu. Heading v rad aj °;
steering normalizovaný input, rate input/s a acceleration input/s² podľa
skutočných Δt. Chýbajúce údaje nezamieňať za nulu. Klasifikáciu referenčného
bodu zachovať; žiadny záver o náprave návesu ani odstupe od prekážok.

| Herná metrika etapy 2 | Aktuálny stav |
| --- | --- |
| Počet vzoriek, trvanie a vzdialenosť aktívnych segmentov | NOT VERIFIED |
| CTE RMS / časovo vážená RMS / mean abs / p95 / p99 / max abs | NOT VERIFIED |
| Heading RMS / maximum | NOT VERIFIED |
| Steering step / rate / acceleration, saturácia a oscilácie | NOT VERIFIED |
| Intervaly nových packetov: median / p95 / p99 / max | NOT VERIFIED |
| SDK vek pri potvrdenom zápise a compute → write latencia | NOT VERIFIED |
| Odmietnutia, stale/neúplné packety, lokalizačné straty, vypnutia a dôvody | NOT VERIFIED |
| Prvé N, čas aktivácie a automatického rozjazdu bez ručného plynu | NOT VERIFIED |

Absencia hlášky v riedkom replayi nedokazuje absenciu udalosti. Zoznam udalostí
porovnať s logom; riedke potvrdené zápisy a plný executor trace vykázať oddelene.
NOT VERIFIED nie je FAIL; PASS jazdy možno vyhlásiť až po integritnom,
časovom a bezpečnostnom vyhodnotení skutočného zberu.
