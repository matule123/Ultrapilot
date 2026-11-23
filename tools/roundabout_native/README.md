# UltraPilot a C++ výber kandidátskych priesečníkov

**Stav k 21. novembru 2026 je BLOCKED.** Prototyp je dostupný iba cez
offline nástroj. Pri pôvodnej prekrývajúcej sa záťaži prekročil celý cyklus
limit p99 50 ms v oboch režimoch. Overenie v hre zostáva otvorené.

## Rozsah

C++ dostáva už vypočítané polohy karosérií pre existujúce vetvy a pôvodné
úseky trasy. V jednej dávke za cyklus s mapovými hypotézami vyberie rovnaké
dvojice úsekov ako Python v perf21. Používa rovnaké hranice obdĺžnikov,
rovnaký test rovnobežnosti a rovnaké intervaly parametrov priesečníka.
Python vypočíta vetvy a polohy, vyhodnotí výšku a čas príchodu, zvolí
konflikt, vykoná predikciu kontaktu karosérií a rozhodne o pedáloch.

Adaptér v procese offline prehrávania overí hash zmrazeného perf21 a nahradí
jediné miesto výberu dvojíc v metóde `crossing`. Pôvodný aplikačný import
stále používa Python. Dávka pokrýva najviac 80 aktérov, 4 karosérie, 8 vetiev,
33 polôh na vetvu a 512 úsekov trasy. Výsledok obsahuje usporiadané indexy
segmentov a bitové masky úsekov. Chybný stav, chýbajúce potvrdenie spracovania
vstupov alebo poškodený výstup prerušia offline beh. Režim `--audit` porovná
aj všetky kandidátske dvojice každého natívne spracovaného aktéra.

## Prekrývajúci sa model 40 + 40

Tri prehratia po 32 cyklov na každý režim. Rovnaké vzorky, geometria, horizont,
záznamové hodiny a limity ako v perf21. Hodnoty sú v ms a p99 je pri 96
vzorkách zároveň maximum. Meranie cyklu prebehlo bez profilovacích obalov.
Model naďalej vyvolá technické odpojenie pre chýbajúcu kontinuitu vlastníka
obmedzenia v rovnakom snímku ako release11.

| Variant | Režim | Celý cyklus p50 / p95 / p99 / max | Engine flush p99 |
| --- | --- | --- | --- |
| release11 Python | jednoduchý automat | 75,16 / 173,61 / 200,43 / 200,43 | 48,84 |
| release11 Python | reálny automat | 67,36 / 154,59 / 163,46 / 163,46 | 32,20 |
| perf21 Python | jednoduchý automat | 46,21 / 83,19 / 125,69 / 125,69 | 33,09 |
| perf21 Python | reálny automat | 46,24 / 85,73 / 123,98 / 123,98 | 22,33 |
| perf21 + C++ | jednoduchý automat | 33,20 / 55,88 / 97,77 / 97,77 | 18,48 |
| perf21 + C++ | reálny automat | 33,77 / 69,78 / 79,77 / 79,77 | 24,66 |

Prototyp splnil maximum cyklu pod 100 ms a maximum zápisu pod 50 ms v tomto
súbore meraní. P99 cyklu prekročil hranicu 50 ms a p99 zápisu hranicu 16,67 ms.
Táto krátka séria má pozorovateľnú variabilitu medzi behmi. Výsledky udávajú
pozorované časy na tomto hostiteľovi.

Samostatný profil s rovnakým modelom. Časy v rámci jedného cyklu sa môžu
prekrývať. Výber dvojíc má 81 aktívnych cyklov na režim, príprava grafu a
referencie má 6 studených volaní na režim.

| Fáza | Jednoduchý automat p50 / p95 / p99 / max | Reálny automat p50 / p95 / p99 / max |
| --- | --- | --- |
| Výber dvojíc, perf21 Python | 7,04 / 13,22 / 70,44 / 70,44 | 6,92 / 12,32 / 50,77 / 50,77 |
| Celé rozhranie C++ | 1,35 / 2,32 / 3,27 / 3,27 | 1,26 / 3,03 / 3,76 / 3,76 |
| Balenie a kópie | 0,52 / 0,73 / 1,78 / 1,78 | 0,48 / 0,86 / 1,76 / 1,76 |
| Volanie DLL | 0,79 / 1,52 / 1,69 / 1,69 | 0,72 / 1,62 / 2,22 / 2,22 |
| Rozbalenie a kontrola | 0,02 / 0,41 / 0,69 / 0,69 | 0,02 / 0,46 / 0,72 / 0,72 |
| Celé vyhodnotenie križovania s C++ | 13,36 / 25,27 / 51,70 / 51,70 | 13,50 / 40,26 / 52,75 / 52,75 |
| Príprava polôh karosérií | 4,16 / 8,07 / 35,40 / 35,40 | 4,26 / 11,12 / 35,62 / 35,62 |
| Výber a predikcia vetiev | 6,27 / 12,60 / 27,43 / 27,43 | 6,34 / 13,08 / 31,64 / 31,64 |
| Predikcia kontaktu karosérií | 5,10 / 10,64 / 12,88 / 12,88 | 5,14 / 13,17 / 15,76 / 15,76 |
| Studená príprava selektora | 3,36 / 3,70 / 3,70 / 3,70 | 3,28 / 4,13 / 4,13 / 4,13 |
| Kópie modelovanej IPC počas projekcie | 0,12 / 1,67 / 3,22 / 3,22 | 0,12 / 2,15 / 3,01 / 3,01 |

Najpomalší profilovaný jednoduchý cyklus trval 78,81 ms. Príprava polôh
karosérií zabrala 33,32 ms, výber vetiev 10,67 ms, zápis Engine 13,26 ms a
celé rozhranie C++ 2,22 ms. GC na tomto cykle trvalo 0,01 ms. Najpomalší
profilovaný cyklus reálneho automatu trval 86,55 ms. Zápis Engine zabral
46,34 ms a GC počas cyklu 30,69 ms. Na najpomalšom neprofilovanom cykle
reálneho automatu mala projekcia 62,54 ms nástenného času, 15,63 ms CPU
času vlákna a 0,01 ms GC za celý cyklus. Windows vykazoval CPU čas v krokoch
15,625 ms. Meranie CPU nevysvetľuje celý rozdiel. Benchmark s
kopírujúcou IPC náhradou priamo nemeria čakanie na skutočnú medziprocesovú
komunikáciu ani cestu plánovača OS.

Zadržané objekty selektora dosiahli 2 548 774 B pre release11 a 3 370 716 B
pre perf21 Python aj C++, v oboch režimoch. Polia jednej natívnej dávky mali
medián 696 960 B a maximum 1 393 920 B, v oboch režimoch. Meranie zahŕňa
polia polôh, dĺžok, limitov a masiek s indexmi. Meranie RSS exportérov má
samostatný rozsah.

## Zhoda s release11

Číselná tolerancia bola nula. Pre obe prevodovky sa zhodovalo všetkých 32
cyklov pôvodnej vstupnej sady aj 32 prekrývajúcich sa cyklov. Porovnaných bolo
4 846 záznamov vetiev podľa ID aktéra pri pôvodných vstupoch a 5 120 v modeli.
Zhodovali sa identity, poradie a priradenie konfliktov, vlastníci obmedzení,
platnosť ACC, limit rýchlosti, rozhodnutia a chronologické zápisy Controlleru.
V každom režime bolo 78 zápisov pri pôvodných vstupoch a 79 pri modeli.
Priebežná kontrola natívnych kandidátskych dvojíc skontrolovala 162 aktérov
v pôvodnej vstupnej sade a 2 126 v prekrývajúcom sa modeli.

Prešlo 274 cielených regresií vrátane nebezpečného križovania, kontaktov
kabíny a prívesu, nejednoznačných a chýbajúcich aktérov, zápornej rýchlosti
tesne pri zastavení, skutočnej spiatočky a neúplného natívneho výstupu.

Časované prehratie pôvodného aktéra 61 ponechalo autopilota aktívneho a malo
nula neplatných vstupov ACC v oboch režimoch. Maximum celého cyklu bolo
35,83 ms a 42,49 ms. Referenčný prípad 11926 má stále chýbajúci pôvodný
záznam Autopilota.

## Samostatný skutočný export 40 + 40

V každom režime prebehlo 1 400 cyklov so zberom vypnutým a 1 400 cyklov so
zberom zapnutým. Pôvodné kritériá exportu prešli v oboch režimoch. Zhodovali
sa aj hashe vstupov, rozhodnutí a zápisov s archivovaným perf21. Pri zapnutom
zbere obsahoval každý export 1 927 presných zápisov pedálov, overené časti
Engine a Autopilota, 30,00 s pred udalosťou a 15,55 s po nej, pri nulovej
strate vzoriek. Scéna nemá použiteľné mapové vetvy, takže počet volaní C++
bol nula. Súbeh C++ a exportu na prekrývajúcich sa prístupoch ostáva otvorený.

| Režim | Celý cyklus bez zberu p50 / p95 / p99 / max | Celý cyklus so zberom p50 / p95 / p99 / max | Počas exportu p99 / max | Engine flush so zberom p99 / max |
| --- | --- | --- | --- | --- |
| Jednoduchý automat | 12,59 / 16,92 / 19,01 / 29,85 | 15,83 / 20,51 / 23,41 / 41,53 | 23,92 / 25,69 | 7,71 / 25,56 |
| Reálny automat | 12,95 / 17,26 / 20,05 / 30,64 | 16,49 / 22,67 / 27,50 / 50,84 | 28,31 / 29,49 | 8,42 / 35,15 |

| Režim | Maximum RSS exportéra | Horný odhad RSS procesu a brokera | Horný odhad RSS celej skupiny | Obsadenie Engine / AP |
| --- | ---: | ---: | ---: | ---: |
| Jednoduchý automat | 1 154 375 680 B | 365 395 968 B | 1 519 771 648 B | 39 474 040 / 7 653 370 B |
| Reálny automat | 1 139 814 400 B | 377 352 192 B | 1 517 166 592 B | 38 953 573 / 7 500 355 B |

P99 čakania na zámok zberu bolo 0,0017 ms v oboch režimoch. Maximum bolo
0,1622 ms v jednoduchom a 0,1349 ms v reálnom automate.

## Identita vstupov a zostavenia

Deväť evidovaných SHA-256 sa zhodovalo pre release11 aj perf21. SHA-256
prehrávanej vstupnej sady `nov2-roundabout-native.json` je
`d61453d95ae293ce302357bff5b3999c298889fc5d8fe009a669101996505a06`.
SHA-256 meranej knižnice `crossing_pairs_final.dll` je
`92dc1c1f35746b6815cabeda8ec7843fb53fc62e5f575c7a48aacb823d06f891`.
Samostatnou prekážkou nasadenia je nainštalovaná `ets2la_plugin.dll` so
SHA-256 `41335023cc84487d3c38d9f497d06f54cb501e142267ff51d5ff1ea714849811`.
Overený manifest požaduje
`330c37eb5540cd23c84dba9a7b7824c1f791cd5aac7cd7c9bb5341db8ad5715c`.

Súhrn meraní je v `build/roundabout-native/summary-final.json`. Surové
prehratia sú v `timed-*.json`, profilované prehratia a ich doplnkové záznamy
v `profile-*.json`, porovnania v `exact-*.json` a posúdenie exportu v
`export-final/assessment.json` v tom istom adresári.

## Reprodukcia

Spustené z koreňa repozitára cez CPython 3.14.4 x64, NumPy 2.4.6 a MSVC
19.44.35229 x64. Pôvodný beh exportu vyžaduje prostredie s prístupom k
lokálnym Windows named pipes. Kombinácia príkazov uchová výstupy do nového
adresára. `--audit` pridáva porovnania, preto sa používa mimo merania cyklu.

```powershell
$env:PYTHONCASEOK='1'
$env:PYTHONDONTWRITEBYTECODE='1'
$python='C:/Users/PC/AppData/Local/Python/pythoncore-3.14-64/python.exe'
$vcvars='C:/DevTools/VS2022BuildTools/VC/Auxiliary/Build/vcvars64.bat'
$out='build\roundabout-native-repro'
New-Item -ItemType Directory $out | Out-Null
$dll="$out\crossing_pairs_final.dll"
cmd.exe /d /c ('"' + $vcvars + '" >nul && cl.exe /nologo /LD /O2 /fp:strict /W4 /WX /std:c++17 /Fo:' + $out + '\crossing_pairs_final.obj tools\roundabout_native\crossing_pairs.cpp /link /OUT:' + $dll + ' /IMPLIB:' + $out + '\crossing_pairs_final.lib')

foreach($stage in 'release11','perf21-offline','native') {
    $runtime=@($stage)
    if($stage -eq 'native') { $runtime=@('perf21-offline','--library',$dll) }
    & $python -m tools.roundabout_native.run @runtime replay --overlap --repeat 3 --out "$out/timed-$stage.json"
    & $python -m tools.roundabout_native.run @runtime replay --overlap --repeat 3 --profile --out "$out/profile-$stage.json"
    & $python -m tools.roundabout_native.run @runtime replay --audit --out "$out/audit-$stage-original.json"
    & $python -m tools.roundabout_native.run @runtime replay --audit --overlap --out "$out/audit-$stage-overlap.json"
    & $python -m tools.roundabout_native.compare timings "$out/timed-$stage.json"
    & $python -m tools.roundabout_native.compare phases "$out/profile-$stage.json"
}
foreach($scene in 'original','overlap') {
    & $python -m tools.roundabout_native.compare exact "$out/audit-release11-$scene.json" "$out/audit-native-$scene.json"
}
& $python -m tools.roundabout_native.run perf21-offline --library $dll replay --wall-clock --out "$out/actor61-paced.json"
& $python -m tools.roundabout_native.run perf21-offline --library $dll test -- -q -x --tb=short `
    tests/traffic/test_roundabout_motion.py tests/traffic/test_actor_motion_contract.py `
    tests/traffic/test_signed_stop_prediction.py tests/traffic/test_motion_broadphase.py `
    tests/traffic/test_native_owner_contract.py tests/traffic/test_roundabout_incident.py `
    tests/test_acc_following.py tests/lifecycle/test_joint_regressions.py `
    tests/lifecycle/test_longitudinal_completion.py tests/signals/test_signal_lifecycle.py `
    tests/signals/test_green_restart.py tools/test_nov3_motion_equivalence.py `
    tools/roundabout_native/test_bridge.py --basetemp "$out/pytest"
& $python -m tools.roundabout_native.run perf21-offline --library $dll export --out "$out/export"
```
