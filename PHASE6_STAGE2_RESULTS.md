# Fáza 6 – etapa 2: herné meranie a oprava čerstvosti packetu

## Verdikt k 2. 10. 2026

**Integrita zberu: PASS. Aktivácia a rozjazd v zaznamenanom pokuse: PASS.
Neprerušené dokončenie jazdy: FAIL – strata autority pri stale packete.
Oprava čerstvosti po lokalizácii: PASS OFFLINE. Herné potvrdenie opravy:
NOT VERIFIED. Dokončený výjazd: NOT MEASURED.**

Ide o vyhodnotenie existujúcej jazdy, nie o nový herný test. Regulátor,
geometria, prevodovka, rozjazd, limit 500 ms a bezpečné zastavenie sa nemenili.
Nadchádzanie a odložené doladenie prirodzenosti zostávajú mimo rozsahu.
Používateľova celá pytest sada pre predchádzajúci stav prešla; tento nový
pracovný stav zatiaľ celou sadou neoveril. Agent celú sadu nespúšťal.

## Identita a pôvod dát

Východiskový HEAD: `ea63a747832524eb74883c641a3935bd05cfffac`. Sledovaný strom bol pred úpravou čistý.
Pravidlá: `PLUGIN_VERSIONS.md`, `DEFERRED_WORK.md`; metodika nadväzuje na
`PHASE6_STAGE1_RESULTS.md`. Časy v tabuľkách sú z jedného monotónneho základu,
ak nie je výslovne uvedený miestny čas UTC+2.

| Údaj | Hodnota |
| --- | --- |
| Kolekcia | `C:\Users\PC\AppData\Local\Programs\UltraPilot\evidence-diagnostics\phase6-stage2-20261002-164849` |
| Dense replay | `steering-replay-20261002T145055.396828Z-manual_disable.json` |
| Pasívne časovanie | `steering-timing-20261002T145423.439180Z-plugin_stop.json` |
| Session | `1` |
| Intent | `65aab0d92a394af5915df66908f6fd70` |
| Revision / build | `8` / `1d544f9b8ccb4fe18fa51e902c4df508` |
| Mapa / dataset | `promods-1.59` / `d6cc7936fce4e902761abb5d` |
| Backend / režim | `SCS_SDK` / jednoduchá automatická, vetva `g_trans=0` |
| Integrita | 1787 vzoriek, 75 súborov; 1 zahodená, 0 odmietnutých |
| Kvalifikácia | `READY_FOR_OFFLINE_REVIEW`, `atomic=false`, `confirmed=false`, `runtime_authorized=false` |

SHA-256 manifestu: `b1a598f64b630f6f83277a74f47aefdececb2b778b0e57e6ff16a787ed5d91d2`.
SHA-256 dense replaya: `5778168f1badae0fd3caa5303278a593a0dba8ffe2067ac28dbe8ffe79ae6d8a`.
SHA-256 pasívneho časovania: `c5088d53db1fe5cb29335c103a5a957a78980ac249b0058ad97cebb3e58d6258`.

Read-only porovnanie nainštalovaného Engine, Map, Autopilotu a collectora
potvrdilo zhodu obsahu s východiskovým HEAD po normalizácii LF/CRLF. Nejde
iba o dôveru v commit.txt ani o dôkaz všetkých historických súborov inštalácie.

| Nainštalovaný súbor | SHA-256 | Rozdiel oproti aktuálnej práci |
| --- | --- | --- |
| `core/engine.py` | `738e5a9315b6a97e8573a57dee046a5b08d61716807a473c5203f3a5713a57f8` | iba LF/CRLF alebo žiadny |
| `plugins/map/main.py` | `bb78d88cbebd0344f2a7dcac455cd5cbd24af967e7d1c699b8e1ab158f30d8b6` | nová lokálna oprava; zatiaľ nenasadená |
| `plugins/autopilot/main.py` | `fadad0fc5c30bc25508c3eb6b980424cd2bcf9e233e9c702916f8db1a84e61c3` | iba LF/CRLF alebo žiadny |
| `core/navigation/evidence_diagnostics.py` | `2997ee32cb432acf55ff179b3833552eb1828a01a6fbd2ce0bd6e693ee4c18eb` | iba LF/CRLF alebo žiadny |

Map bol 1.0.0; nová úzka oprava zvyšuje VERSION na 1.0.1. Autopilot aj ACC
zostávajú 1.0.0. Nastavenia ani inštalácia sa nemenili. Historická predkontrola
z 1. 10. týmto reportom nie je vydávaná za výsledok tejto novej opravy.

## Kauzálna rekonštrukcia incidentu

| Packet / udalosť | SDK frame | Pôvodné observation | Výpočet / publikovanie | Spotreba a dôsledok |
| --- | --- | --- | --- | --- |
| 2293 | 310020932 | 12195.4522926 | 12195.4652637 / dokončenie 12195.4667864 | Predchádzajúci platný cieľ; opakované čítanie je ten istý packet |
| 2294 | 310037598 | 12195.4701866 | 12195.9332124 / dokončenie 12195.9351766 | Vzorkované čítanie 12195.9369575, vek 466.771 ms |
| Prvé odmietnutie Engine | 310504246 je aktuálny vehicle frame, nie calculation frame | Vehicle observation 12195.9505774 | Engine 12195.9744901 | Packet 2294 má 504.304 ms; aktuálna telemetria vozidla len 23.913 ms |
| 2295 | 310504246 | 12195.9505774 | 12195.973455 / začiatok publikovania 12195.9748229 | Publikovanie začalo až po prvom odmietnutí Engine |

Packet 2294 nestál dlho v prenose: publikovanie trvalo 0.449 ms a prvé
**zaznamenané vzorkované** čítanie po jeho dokončení bolo o 1.781 ms neskôr.
Toto čítanie nie je dôkaz prvého doručenia. Nový packet 2295 ešte pri prvom
odmietnutí nebol publikovaný; záznam preto nepodporuje hypotézu, že Engine
ignoroval už dostupný nový packet. Identita zostala rovnaká.

| Fáza packetu 2294 | Trvanie |
| --- | ---: |
| Observation → koniec lane update | 5.787 ms |
| Koniec lane update → koniec road type | 0.648 ms |
| Koniec road type → pripravená referencia | 456.155 ms |
| Regulátor | 0.404 ms |
| Observation → vypočítaný packet | 463.026 ms |
| Observation → dokončenie publikovania | 464.990 ms |
| Výpočet → odmietnutie Engine | 41.278 ms |
| Observation → odmietnutie Engine | 504.304 ms |

**Preukázaná chyba v produkčnom toku:** `_refresh_steering_observation`
overil vek pred `LaneLocator.locate()` a súvisiacou publikáciou liveness,
ale po návrate už vek neoveril. Tým mohol začať výpočet nad pozorovaním,
ktorému príprava spotrebovala takmer celú lease. Overenie identity po
lokalizácii samotnú čerstvosť nedokazuje.

Vo vzorke zachytenej o 12195.9267567 už existuje novší SDK frame **310470914**,
rovnaká session/mapa/dataset a zhodná XYZ poloha v truck a vehicle observation.
Jeho pôvodný profile observation čas je **12195.8962868**. Neskorší transport
read timestamp 12195.9148699 ani opakovaný capture čas sa nepoužili na
obnovenie jeho čerstvosti. `atomic=false` zostáva; ide o uloženého kandidáta
s `stable_read` a potvrdenou väzbou frame, nie certifikovaný atómový ground frame.

**Presná historická podoperácia 456 ms zdržania nie je doložená.** Časové značky
rozlišujú referenčnú fázu, nie čas každého jej volania alebo preemptovanie OS.
Profilovanie reálnej cache a tých istých polôh ukázalo bežnú lokalizáciu
v jednotkách ms; 6500 opakovaní zaznamenalo aj automatickú GC pauzu približne
174 ms. To nedokazuje, že historických 456 ms spôsobilo GC. GC, export ani
evidence worker sa preto neoznačujú za preukázanú príčinu tej konkrétnej pauzy.

Collector beží vo worker threade Engine; Map má samostatný plugin proces.
Export kolekcie skončil až po incidente. Existujúci evidence worker má jednu
rozpracovanú úlohu bez rastúcej fronty; bez potvrdeného body profilu nebuduje
ťažký geometrický context. Tieto vetvy sa preverili meraním v offline záťaži; ich prítomnosť
sa nepovažuje za dôkaz nulovej ceny ani za dôkaz príčiny incidentu.

## Oprava a pred/po reprodukcia

Po lokalizácii sa znovu skontroluje skutočný vek. Ak nová snímka počas tejto
práce prekročila existujúci 100 ms preparation budget, prebehne **najviac jeden**
nový odber SDK a úplná lokalizácia novej polohy na tej istej platnej LanePath.
Opätovne sa kontroluje revision/intent/build/session/mapa/dataset, generation,
frame, výška a LaneMatch. Druhá pomalá lokalizácia, nezmenený starý frame,
strata SDK alebo identity vedú k odmietnutiu. Neexistuje nekonečná retry fronta.
Duplicitný už spotrebovaný frame nevytvorí nový packet ani nový timestamp.

Pred opravou regresný súbor s metódou priamo z HEAD: **4 failed, 2 passed**.
Po oprave všetkých šesť prípadov prešlo v cielenej sade. Celý produkčný test
vykonáva Map → PluginSDK/Autopilot → Engine a fyzické zápisy testovacieho
backendu vrátane jedného N, probe 0.12, handoffu, 456 ms lokalizácie a
oneskorenej spotreby. Následná skutočná strata dát stále potlačí pohon.

Offline benchmark používa 86 skutočných zaznamenaných polôh okolo incidentu,
13 segmentov platnej trasy rekonštruovaných existujúcim RoadNetwork z lokálnej
map-cache, pôvodný regulátor a metódu Map pred/po z HEAD. Pozície, heading,
rýchlosť, referenceGeometry a observation časy pochádzajú z existujúcich dát.
Zdržanie má deterministický monotónny model končiaci v pôvodnom reference
finish; prvá incidentová spotreba je v pôvodnom Engine čase. Bežné spotreby
majú explicitne modelovanú latenciu 30 ms. **Tieto veky nie sú novým herným
meraním ani meraním wall-clock IPC.** Skutočný CPU/wall náklad sa meria
samostatne pomocou perf_counter.

Súbežná varianta používa pôvodné zaznamenané VehicleProfile dataclassy a
existujúci bounded evidence worker plus skutočný delený export 250 úplných
syntetických trailer záznamov. Kolekcie vznikajú výhradne v ignorovanom audite.
Export v tom istom testovacom procese je záťažový test; v hre collector nie je
v Map procese. Počet prijatých evidence úloh závisí na plánovaní worker threadu,
pri všetkých variantoch však ostáva maximálne jedna rozpracovaná úloha.

| Metrika modelového end-to-end benchmarku | Pred | Po |
| --- | ---: | ---: |
| Interval nových packetov – medián / p95 / p99 / max [ms] | 34.947 / 53.305 / 136.135 / 480.484 | 34.947 / 53.305 / 136.135 / 480.484 |
| Vek pri spotrebe – medián / p95 / p99 / max [ms] | 30.000 / 30.000 / 101.146 / 504.303 | 30.000 / 30.000 / 37.230 / 78.203 |
| Prekročenia 500 ms / odmietnutia | 1 / 1 | 0 / 0 |
| Tie isté veky a odmietnutia pri súbežnom exporte | 1 prekročenie | 0 prekročení |
| Normálne referenčné steering výstupy mimo incidentovej novej polohy | baseline | numericky identické, max rozdiel 0 |

**Cadence sa v tejto reprodukcii nezrýchlila.** Oprava zabráni publikovaniu
už zostarnutého pozorovania po dlhej lokalizácii; neodstráni samotnú vynútenú
480 ms medzeru. Pri výpadku dlhšom než lease, chýbajúcom novom SDK frame alebo
druhom dlhom pokuse sa zachová bezpečné zastavenie. Žiadny starý povel sa
nepreznačuje ako nový. Nejde o prísľub odstránenia všetkých budúcich výpadkov.

| Skutočný wall čas Map ticku, oddelene od časového modelu [ms] | Medián | p95 | p99 | Max |
| --- | ---: | ---: | ---: | ---: |
| Pred | 4.063 | 6.411 | 17.544 | 31.225 |
| Po | 3.649 | 5.727 | 15.806 | 18.473 |
| Pred + súbežný export/evidence | 7.612 | 41.062 | 167.428 | 275.970 |
| Po + súbežný export/evidence | 3.999 | 19.493 | 36.216 | 40.893 |

Jednorazové wall časové rozdiely vrátane GC/scheduler variability nie sú dôkazom
zrýchlenia operácie ani hernej cadence. Controller benchmark má vo všetkých
16 prípadoch **numericky identické** výsledky pred/po; jeho zisky, kalibrácia,
limity, preview aj SteeringDynamics ostali nedotknuté.

## Herné meranie: použiteľná aktívna časť

Aktívne okno: handoff **12172.0858815** až prvá strata autority
**12195.9744901** (23.889 s). CTE/heading pochádzajú zo **737 jedinečných
immutable executor.source_packet**, ktorých execution bol v tomto okne;
dve skoršie observation snímky sa od aktívneho CTE oddelili. Zmeraný rozsah
pôvodných observation časov je **23.364 s / 156.154 m** pozdĺžneho progressu.
Neznámy koniec úseku ani chýbajúci výjazd sa neinterpolujú.

| Úsek podľa potvrdeného LaneId | n | Zmerané s / m | CTE RMS [m] | Časovo vážená RMS [m] | p95 / max abs CTE [m] |
| --- | ---: | ---: | ---: | ---: | ---: |
| Prístup/rozjazd po handoffe | 155 | 4.950 / 20.302 | 0.172 | 0.174 | 0.250 / 0.272 |
| Vjazd | 88 | 2.666 / 15.821 | 0.281 | 0.279 | 0.410 / 0.474 |
| Obiehanie | 425 | 13.606 / 103.063 | 0.186 | 0.181 | 0.374 / 0.555 |
| Dostupný začiatok výjazdu | 69 | 2.036 / 14.630 | 0.041 | 0.041 | 0.062 / 0.063 |
| Celá použiteľná aktívna časť | 737 | 23.364 / 156.154 | 0.189 | 0.187 | 0.368 / 0.555 |

Mean abs CTE **0.143 m**, p99 **0.485 m**.
Body tracking heading error RMS **0.01837 rad
(1.053°)**; maximum
**0.08420 rad (4.824°)**.
Pri týchto 737 zdrojoch nechýba CTE, heading ani calculation speed. Ide o
SDK chassis-origin CTE kabíny, nie o CTE nápravy návesu. Návesová presnosť:
**NOT VERIFIED** (`trailer_axle_replay_channels_observed=false`).

| Úsek | Rýchlosť pri calculation observation, medián / max [km/h] |
| --- | ---: |
| Prístup/rozjazd po handoffe | 17.129 / 24.273 |
| Vjazd | 18.486 / 30.882 |
| Obiehanie | 26.808 / 35.331 |
| Dostupný začiatok výjazdu | 27.199 / 28.187 |

Prístupové LaneId UID: 5337536178973708447 a 5337536093791584855.
Vjazd: 5337536180190062103, connector path (2,5,6), prefab dlc_blkw_46.
Obiehanie: 5337536095347671845, 5337536092906588896,
5337536180898893020 (dlc_blkw_47), 5337536096723407576.
Začiatok výjazdu: 5337536179565107919 (dlc_blkw_46, path (3,0,6))
a 5337536096979258520. Toto sú navigačné identity, nie fyzické okraje vozovky.

Státie a manuálne vzorky pred aktiváciou sa do aktívneho CTE nezapočítavajú.
Rozjazd pred handoffom je samostatne doložený Engine logom: jediné zaznamenané N
16:50:29.956, probe 0.12 o 16:50:29.983, čerstvý gear 4 o 16:50:30.184,
handoff s aktívnym plynom 0.185 o 16:50:30.237. N → handoff približne 281 ms.
Selector D sa neposielal. Pozorovaný následný dopredný pohyb potvrdzuje
funkčnú podporovanú vetvu; zber neobsahuje úplný surový manuálny vstup plynu,
preto sa nevydáva za experiment vylučujúci každý zásah vodiča.

Strata autority je jedna, prvý dôvod je stale observation 16:50:54.126;
kontrolované zastavenie 16:50:54.152 a nulové uvoľnenie výstupov po vypnutí
16:50:55.074. Neskorší názov exportu `manual_disable` tento prvý dôvod
neprepisuje. Koniec kolekcie približne 16:52:54 nie je príčinou incidentu.

## Packetové a časové metriky reálnej jazdy

| Signál | n | Medián [ms] | p95 [ms] | p99 [ms] | Max [ms] |
| --- | ---: | ---: | ---: | ---: | ---: |
| Interval nových immutable calculation packetov | 736 | 27.677 | 54.284 | 72.124 | 467.949 |
| SDK vek pri potvrdenom vzorkovanom zápise | 114 | 73.536 | 103.407 | 349.128 | 470.770 |
| Výpočet → potvrdený vzorkovaný zápis | 114 | 56.112 | 91.026 | 336.157 | 457.799 |
| SDK vek pri vzorkovanom čítaní Autopilotom | 47 | 31.801 | 54.569 | 283.405 | 466.771 |
| Lane update | 47 | 7.776 | 12.027 | 14.043 | 14.598 |
| Prezentácia | 47 | 0.125 | 0.445 | 0.699 | 0.846 |
| Road type | 47 | 0.483 | 0.883 | 1.196 | 1.417 |
| Referencia | 47 | 9.751 | 14.156 | 254.464 | 456.155 |
| Regulátor | 47 | 0.414 | 0.553 | 0.585 | 0.587 |
| IPC publikovanie | 22 | 0.383 | 1.194 | 1.446 | 1.507 |
| Publikovanie → vzorkované čítanie | 22 | 4.352 | 25.066 | 47.750 | 53.656 |

Intervaly dlhšie než 500 ms sa necenzurovali: medzi týmito 736 novými cieľmi
ich bolo 0. Napriek tomu jeden už takmer expirovaný cieľ dosiahol pri prvom
odmietnutí **504.304 ms**. Čerstvá cadence a vek konkrétneho zdroja sú rozdielne
veličiny. Potvrdené vzorkované zápisy obsahujú 0 prekročení 500 ms; to nie je
popretie incidentu, ktorý je zachytený odmietnutím v logu, nie platným zápisom.

Pre fyzické steering metriky prijatých **114 vzorkovaných backendových zápisov**
sa vyžaduje backend_sent, command_binding_proven, rovnosť output/engine_steer,
úplná identita a pôvodné source časy. 103 aktívnych kandidátov nemá takú väzbu;
1570 ostatných záznamov je mimo aktívneho okna alebo aktívnej autority.
Chýbajúci zápis sa nenahrádza nulou. Riadková SDK odozva nepredstavuje odozvu
na práve zapísaný povel; userSteer nie je meraný raw joy.x ani hodnota callbacku.

| Fyzický steering v doložených vzorkovaných úsekoch | p95 | Max | Jednotka |
| --- | ---: | ---: | --- |
| Absolútny krok (n=107) | 0.033408 | 0.094587 | normalizovaný input |
| Absolútna rýchlosť (n=107) | 0.178556 | 0.327738 | input/s |
| Absolútne zrýchlenie (n=100) | 0.801492 | 0.937883 | input/s² |

Ide o 7 oddelených vzorkovaných úsekov, 19.253 s. Tieto derivácie nie sú úplné
maximá 60 Hz vykonávača; medzi vzorkami môžu zostať nezaznamenané kroky.
Zaznamenaných zmien znamienka pri prahu 0.02: 0; nie je to úplný dôkaz absencie
oscilácií. Čas fyzickej saturácie je NOT VERIFIED.

## Metodika, reprodukcia a kontroly

RMS = sqrt(mean(CTE²)). Časovo vážená RMS používa ľavostranné držanie poslednej
platnej hodnoty s váhou dt do nasledujúcej snímky; bez poslednej terminálnej
váhy a bez mosta cez medzeru >500 ms, inú identitu alebo fázu. Percentily sú
lineárne interpolované. Rate je delta steer/dt; acceleration z rozdielu rate
na stredoch susedných intervalov. Neplatné/chýbajúce údaje sa neprenášajú ako 0.
Immutable calculation packet sa deduplikuje podľa celej identity a sequence;
meraná application frame sa nezamieňa za calculation SDK frame. Úplný výjazd,
clearance pri prekážkach a stopa nápravy návesu zostávajú nezmerané.

Analytický nástroj `tools/analyze_phase6_stage2.py` najprv overí celú integritu,
neprijme konfliktný immutable packet ani miešanie aktívnych session.
Výstupy, profily, benchmark JSON a veľké surové dáta zostávajú mimo Gitu.
Reprodukcia v tomto pracovnom strome:

```powershell
$env:PYTHONCASEOK='1'
python tools/analyze_phase6_stage2.py --collection 'C:\Users\PC\AppData\Local\Programs\UltraPilot\evidence-diagnostics\phase6-stage2-20261002-164849' --replay 'C:\Users\PC\AppData\Local\Programs\UltraPilot\route-diagnostics\steering-replay-20261002T145055.396828Z-manual_disable.json' --timing 'C:\Users\PC\AppData\Local\Programs\UltraPilot\route-diagnostics\steering-timing-20261002T145423.439180Z-plugin_stop.json' --build 1d544f9b8ccb4fe18fa51e902c4df508 --handoff-at 12172.0858815 --fault-at 12195.9744901 --output docs/steering-audit/phase6-stage2-20261002-results.json
python docs/steering-audit/stage2_head_reproduction.py
python docs/steering-audit/benchmark_stage2_real_route.py
python tools/run_steering_bench.py --ref HEAD --quiet --output docs/steering-audit/stage2-controller-before.json
python tools/run_steering_bench.py --quiet --output docs/steering-audit/stage2-controller-after.json
```

`stage2_head_reproduction.py` úmyselne očakáva neúspech pôvodnej metódy;
aktuálne súbory nevracia ani neprepisuje. Benchmark reálnej trasy používa
existujúcu map-cache bez novej extrakcie. Testovacie MapSDK je pamäťový adapter,
preto tento benchmark nemeria živý Manager IPC ani historické doručenie.

| Kontrola | Výsledok |
| --- | --- |
| Cielená produkčná/safety/Map/rozjazd/evidence/matematická sada | 226 passed |
| Nový analytický nástroj + existujúci delený export | 25 passed |
| Controller benchmark, oba smery/roviny/objazd/S/rýchlosti | 16 prípadov, výsledky pred/po presne identické |
| compileall | PASS |
| git diff --check a whitespace nových súborov | PASS |
| Celá pytest sada tohto nového stavu | používateľ spustí; agent ju nespúšťal |

Prvý cielený beh narazil na Windows filesystem sandbox PermissionError v
pytest basetemp. Rovnaká cielená sada mimo tohto obmedzenia prešla; nešlo o
chybu aplikácie a žiadny limit sa kvôli tomu neuvoľnil.

## Zmenené súbory a zostávajúce overenie

- `plugins/map/main.py`: kontrola veku po lokalizácii, jedna ohraničená nová
  snímka/lokalizácia alebo odmietnutie; VERSION 1.0.1.
- `tests/test_post_localization_freshness.py`: reprodukcia pred/po a celý
  produkčný tok, nová snímka, strata SDK/identity, bez nového frame, druhý timeout.
- `tools/analyze_phase6_stage2.py`: read-only vyhodnotenie konkrétnej etapy.
- `tests/test_phase6_stage2_analysis.py`: integrita, identity, manuálne vzorky,
  chýbajúci binding, deduplikácia a necenzurovanie dlhých intervalov.
- `PHASE6_STAGE2_RESULTS.md`: tento report.

Oprava konkrétnej chyby prijatia starého pozorovania je offline preukázaná.
Presné vnútorné volanie alebo scheduler pauza historickej 456 ms fázy zostáva
nedoložená; nesľubuje sa jej odstránenie ani nepretržitá dostupnosť pri každej
záťaži. Chýbajúci historický stack nemožno spätne vytvoriť z tejto kolekcie.
Ďalší krok je používateľova celá sada, následne osobitne schválené nasadenie
a kontrolované herné potvrdenie tej istej trasy. Nová jazda ani zber sa teraz
nevyžadujú a nearmujú. Nič sa necommitovalo, nepushovalo, nekopírovalo do
inštalácie; ETS2 sa neovládalo. Pôvodná kolekcia a log zostali zachované.

Príkaz používateľa na celú sadu:

```powershell
cd 'C:\Users\PC\Documents\GitHub\ets2la'
$env:PYTHONCASEOK='1'
python -m pytest tests -q
```
