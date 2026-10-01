# Fáza 6 — etapa 1/3: offline overenie UltraPilotu

Dátum: 1. 10. 2026. **Verdikt: PASS pre vykonané offline regresie; NOT VERIFIED pre úplné herné overenie aktuálneho HEAD.** Historická jazda o 18:22 obsahuje automatické vypnutie, preto jej celý manéver nie je PASS. Nebol nájdený dôvod na preventívnu zmenu produkčného kódu. Regulátor, geometria, rozjazd, limity a pluginy zostali nezmenené.

## Rozsah a identita

- Overovaný commit: `e16e2a5eee6eb25b8c7d3d2227b6c28f83bb0116`. Pred prácou bol pracovný strom čistý. Nevykonal sa commit, push, nasadenie, spustenie hry ani ovládanie vozidla.
- Prečítané pravidlá: `PLUGIN_VERSIONS.md`, `DEFERRED_WORK.md`, kontext projektu a ignore pravidlá. V repozitári ani overenom rodičovskom reťazci nebol AGENTS.md. Odložené doladenie preview 0,200 s a nadchádzanie neboli otvorené; aktuálne preview zostáva 0,134 s.
- Všetkých 12 pluginov má VERSION **1.0.0**: acc, autopilot, collision, discord, drivepolicy, ecodrive, hud, lanecontrol, map, toll, tts, turnsignals. Žiadny plugin nebol zmenený, verzia sa nezvyšuje.
- SDK freshness limit zostáva **500 ms**. Repozitárová konfigurácia: target_speed=80, fps=60, autopilot steering_lock_rad=0,78; koreňový transmission_mode_preference=`0`. SHA-256 settings: `52e339d1996fe5d4f8f1f4991e19eb4990a1240607ffcfae477fce0ebd6992a8`. Benchmark používa svoje explicitné nezávislé parametre, nie tieto hodnoty automaticky.
- Súčasná nainštalovaná konfigurácia: transmission_mode_preference=`auto`, settings SHA-256 `382700250496677f028c82e4840032a3428435b4ba448b295908630fb43b93c1`. Tento stav nedokazuje nastavenie pri historickej jazde.

### Zdroj verzus inštalácia

Read-only kontrola z 2026-10-01T19:53:06.339722. Marker inštalácie `e16e2a5` sám nepotvrdzuje zhodu zostavy. Overené sú len nasledujúce súbory; nepredpokladá sa zhoda celej inštalácie ani historicky načítaných modulov.

| Runtime súbor | SHA-256 zdroja | SHA-256 inštalácie | zhoda |
| --- | --- | --- | --- |
| core/navigation/route.py | 4654f6fc8360295534208056d440f38af539ba66901f2bb4ab0d81273d79d4ee | 4654f6fc8360295534208056d440f38af539ba66901f2bb4ab0d81273d79d4ee | áno |
| core/lateral_controller.py | 39ab6a2cd3594b9b8d603dd816d76c92bcc69105981aceb99c4e22176eff05b8 | 39ab6a2cd3594b9b8d603dd816d76c92bcc69105981aceb99c4e22176eff05b8 | áno |
| core/engine.py | 6d73153af988b7569774c5faeaf87d9e68d5bd5aab80f5a685ea31a8b454b919 | 9987863812a7f468bec6da4496d770dfa82f737367a2ab4a79f730cedb900a94 | **NIE** |
| core/steering_dynamics.py | 155838c3fbefe57d7994b461550f05d39432799442ec8687465c18a60f7ad730 | 155838c3fbefe57d7994b461550f05d39432799442ec8687465c18a60f7ad730 | áno |
| plugins/map/main.py | bd3c7813eb2e6a19cf484fbb96ad9e74375360713b6dda94572843e680eb3116 | bb78d88cbebd0344f2a7dcac455cd5cbd24af967e7d1c699b8e1ab158f30d8b6 | **NIE** |
| plugins/autopilot/main.py | 6564918f4a771b9a8ab0012bc56ae0d7b106d214a0c2f29fbd4dbfeba4c226db | fadad0fc5c30bc25508c3eb6b980424cd2bcf9e233e9c702916f8db1a84e61c3 | **NIE** |

## Scenáre a výsledok

| Oblasť | Existujúci dôkaz / scenáre | Verdikt |
| --- | --- | --- |
| Riadenie | 16 referenčných + 2 analytické 90° + 198 variantov; všetky dokončené, žiadna strata pruhu podľa existujúceho indikátora 2,4 m | PASS offline |
| Šum, jitter, odozva | CTE šum 0,04 sin(7t)+0,015 sin(31t) m; heading 0,25° sin(9t); dt ~43–57 ms, každých 53 krokov 110 ms; transport 100 ms; response 0,25–0,60 s | PASS v rozsahu modelu |
| Výpadok / opakovaný SDK frame | test_steering_fresh_handoff, test_passive_steering_timing, test_map_control_packet_cadence, test_stage4d_control_timing; výpadok a expirácia medzi validáciou a zápisom | PASS offline |
| Krátka / dlhá GPS | test_lane_route_builder: dlhý potvrdený rolling LanePath 141 segmentov / 42 prefabov, lokálny horizont ~8,1 km; test_navigation_intent: posun prefixu a opakované UID | PASS offline; nie celá geometria 118 km |
| Road / prefab / kruhový objazd | test_lane_trajectory (vrátane 3 real-map testov), test_prefab_geometry_reuse, test_lane_audit_regressions; analytický objazd má jednu úplnú slučku | PASS offline |
| Smer / výška / lokalizácia | test_lane_locator, test_stage2_lane_geometry: nesprávny smer, most / cesta pod ním, teleport, príchod na koniec prvého pruhu; neplatný spoj odmietnutý | PASS fail-closed |
| Identita | navigation_intent / lane_authority / activation_observation: revision, intent, build, session, dataset; oneskorený worker a rolling prefix | PASS fail-closed |
| Jedno N, jednoduchá automatika | Engine + Plugin: launch .12 bez selectoru, oneskorený prvý Plugin tick, handoff, prechod gear>0 → 0 → gear>0, obmedzený deadline | PASS offline |
| Jedno N, reálna automatika | Engine + Plugin: jeden ohraničený D selector; čakanie bez plynu; potvrdenie iba čerstvým SDK gear>0; testy odmietnutia R / timeoutu | PASS offline; herný výsledok NOT VERIFIED |
| Pohyb / parkovacia brzda / vypnutie | dopredná jazda, brzdenie do R v simple auto, parkovacia brzda, manuálne vypnutie a nulové výstupy, opakované N, backend failure | PASS offline |
| Strata autority | neúplný/stale packet, heartbeat, strata lokalizácie, kontrolované zastavenie, prvý dôvod, výstražné svetlá a obnova iba čerstvým packetom | PASS offline |
| Presný aktuálny HEAD v ETS2 | nový replay nemá immutable source; 3 runtime súbory inštalácie sa nezhodujú so zdrojom | NOT VERIFIED |
| Fyzické hranice / nadchádzanie | odložené, mimo tejto etapy; navigačný model nedokazuje voľný priestor ani odstup od obrubníka | NOT VERIFIED |

Cielená sada: **506 passed, 1188 subtests passed, 42,07 s**, 28 vybraných testových súborov; zahŕňa aj zdedené fixture testy, nejde o 506 nezávislých fyzických experimentov. Po dokončení nástroja samostatne **9 passed** pre metodiku analýzy; tento počet sa nepripočítava ako ďalšia nezávislá validačná sada. Celá `tests/` sada nebola spustená.

Prvý beh zasiahol Windows filesystem sandbox (`PermissionError` a chyba cleanup dočasného adresára). Rovnaký výber s novým basetemp mimo tohto obmedzenia prešiel. Environmentálna chyba nie je zlyhanie aplikácie. Výsledky sú v ignorovanom `docs/steering-audit/phase6-stage1-targeted.xml`.

## Metodika metrík

`tools/analyze_phase6_stage1.py` je read-only analytický nástroj: neotvára riadiaci backend, nearmuje collector a neovláda hru. Chýbajúce/neplatné/NaN/inf/bool čísla sa nenahrádzajú nulou. JSON obsahuje počet platných aj vyradených vzoriek každej veličiny; `null` znamená NOT VERIFIED.

CTE RMS = sqrt(mean(CTE²)). Priemer, p95, p99 a maximum používajú |CTE|. Percentily sú lineárne interpolované na indexe (n−1)·p. Časová RMS používa sum(CTE_i²·dt_i)/sum(dt_i) a odmocninu, s ľavým držaním medzi susednými platnými vzorkami; posledná vzorka nemá umelo pridanú váhu. Váha sa neprenáša cez chýbajúce CTE, zmenu identity/stavu/referenčného bodu, spätný čas či dátovú medzeru.

Poloha a fyzický zápis sú samostatné časové rady. Heading sa uvádza v **radiánoch**; pre hernú referenciu je to `body_tracking_error_rad`, nie zamenená LaneLocator heading hodnota. Volant je normalizovaný input, nie radian kolesa. Step je |u_b−u_a|; rate používa skutočné dt medzi časmi zápisu alebo simulovaných krokov. Acceleration je rozdiel podpísaných rates vydelený vzdialenosťou ich časových stredov. Nepoužíva sa nominálne 1/60 s namiesto zaznamenaného dt.

CTE a execution rady sa delia pri medzere >500 ms. Pasívny časovací zber má v produkcii periódu najmenej 500 ms (`plugins/autopilot/main.py`), preto sa pri jeho analýze medzera delí pri >1 s; tento analytický cutoff **nemení** bezpečnostný freshness limit 500 ms. Žiadna derivácia ani časová váha nespája samostatné úseky. Metriky v tabuľke stresovej matice sú najhoršie výsledky samostatných scenárov, nie zlepená CTE séria.

Saturácia v simulácii znamená čas |steer_raw|≥1, nie fyzické dosiahnutie dorazu pneumatík. Herná source flag `saturated` tiež nepreukazuje mechanický doraz. Nežiaduce obrátenia používa existujúca benchmarková definícia: rovnaké znamienko lokálneho k>0,003/m, output nad 0,004, potom obrátenie; na S-zákrute sa úmyselná zmena smeru nezapočíta. Ďalší JSON údaj sign_changes_at_002 obsahuje aj úmyselné nábehy/návraty a nie je sám dôkaz oscilácie. Ustálenie: po konci zákruty posledný výskyt |CTE|>0,25 m alebo |heading|>1°; nedokončené ustálenie zostáva null.

### Model a jeho obmedzenia

Použitý existujúci `tests/steering_bench.py` + `tools/run_steering_bench.py`: nelineárny model, krok fyziky ≤5 ms, wheelbase 3,8 m, transport 100 ms, základný actuator gain 0,78 rad/input a response 0,32 s. Stresová matica mení gain 0,60 / 0,78 / 0,95 a response 0,25 / 0,425 / 0,60 s; kontrolér má explicitnú predbežnú kalibráciu 0,78. Rozdiel gainov je úmyselná neistota modelu, nie online ladenie. Analytické rampy zakrivenia majú 8 m a krok geometrie 0,5 m. R18/R35 sú test sledovania analytickej strednice, **nie fyzické povolenie prejazdu skutočnou križovatkou**.

Hlavné simulované CTE patrí bodu modelovej zadnej nápravy (`observation_ahead_m=0`), nie SDK originu kabíny. Modelový náves je bod kinematiky s 8 m ramenom; nie je potvrdeným reálnym podvozkom alebo swept clearance. Jeho metriky sú oddelené. CTE je skutočná modelová hodnota pred pridaním vstupného šumu; heading obsahuje označený merací šum. Povel Dynamics je simulovaným výstupom na časovej osi logu `t`; benchmark používa svoj integračný `dt`, preto jeho pôvodné derivatives majú inú definíciu než nový výpočet z časových značiek. Pôvodné limity a benchmark sa nemenia.

## Základné simulácie — CTE

Každý riadok je jeden oddelený úsek. Dĺžka je dĺžka zadanej referencie; vozidlo končí podľa pôvodného benchmarku asi 5 m pred jej koncom. Presný prejdený progress a počet platných veličín sú v JSON. Celkom **216 scenárov, 148464 vzoriek, 7578.54 s** súčtu oddelených simulovaných úsekov.

| Scenár | n / čas s / dĺžka m | RMS / časová RMS m | mean abs m | p95 / p99 abs m | max abs m |
| --- | --- | --- | --- | --- | --- |
| R18_-1 | 677 / 34.54 / 191.55 | 0.0497 / 0.0497 | 0.0274 | 0.1400 / 0.1625 | 0.1640 |
| R35_-1 | 636 / 32.43 / 244.96 | 0.0273 / 0.0274 | 0.0130 | 0.0827 / 0.1035 | 0.1058 |
| R83_-1 | 638 / 32.58 / 395.75 | 0.0170 / 0.0175 | 0.0077 | 0.0473 / 0.0770 | 0.0804 |
| R250_-1 | 718 / 36.65 / 920.40 | 0.0194 / 0.0197 | 0.0104 | 0.0510 / 0.0808 | 0.0889 |
| R18_1 | 677 / 34.54 / 191.55 | 0.0496 / 0.0497 | 0.0275 | 0.1399 / 0.1617 | 0.1633 |
| R35_1 | 636 / 32.43 / 244.96 | 0.0289 / 0.0289 | 0.0143 | 0.0854 / 0.1073 | 0.1099 |
| R83_1 | 638 / 32.58 / 395.75 | 0.0172 / 0.0177 | 0.0079 | 0.0471 / 0.0765 | 0.0807 |
| R250_1 | 718 / 36.65 / 920.40 | 0.0194 / 0.0196 | 0.0106 | 0.0510 / 0.0784 | 0.0857 |
| S35 | 742 / 37.86 / 285.00 | 0.0447 / 0.0450 | 0.0215 | 0.1047 / 0.2039 | 0.2158 |
| roundabout | 937 / 47.84 / 292.08 | 0.0312 / 0.0312 | 0.0145 | 0.0930 / 0.1248 | 0.1272 |
| straight_10 | 2078 / 106.22 / 300.00 | 0.1025 / 0.1023 | 0.0355 | 0.2692 / 0.4888 | 0.5000 |
| straight_30 | 694 / 35.45 / 300.00 | 0.1046 / 0.1040 | 0.0362 | 0.2545 / 0.4979 | 0.5000 |
| straight_60 | 348 / 17.75 / 300.00 | 0.1248 / 0.1243 | 0.0502 | 0.3824 / 0.4998 | 0.5000 |
| straight_90 | 232 / 11.83 / 300.00 | 0.1440 / 0.1436 | 0.0665 | 0.4504 / 0.5000 | 0.5000 |
| log_speed_R22_lag0.32 | 576 / 29.35 / 225.00 | 0.0501 / 0.0508 | 0.0269 | 0.1421 / 0.1756 | 0.1838 |
| log_speed_R22_lag0.5 | 577 / 29.40 / 225.00 | 0.0563 / 0.0558 | 0.0315 | 0.1182 / 0.2189 | 0.2246 |
| turn90_-1 | 451 / 22.99 / 174.98 | 0.0330 / 0.0330 | 0.0182 | 0.0941 / 0.1041 | 0.1066 |
| turn90_1 | 451 / 22.99 / 174.98 | 0.0326 / 0.0326 | 0.0184 | 0.0924 / 0.1037 | 0.1066 |

## Základné simulácie — riadenie a samostatný náves

Heading má rovnaké n a čas ako CTE tabuľka. Step/rate majú n−1 párov a acceleration n−2 trojíc; všetky základné rady sú spojité. Náves absentuje, keď simulácia nemá `trailer=True`; nevypĺňa sa nulou.

| Scenár | heading RMS / max rad | max step / rate input/s / accel input/s² | saturácia s | nežiaduce zmeny znamienka / ustálenie s | náves RMS / max m |
| --- | --- | --- | --- | --- | --- |
| R18_-1 | 0.0091 / 0.0332 | 0.0136 / 0.3170 / 4.1183 | 0.0000 | 0 / 2.5691 | 0.9356 / 1.8639 |
| R35_-1 | 0.0060 / 0.0219 | 0.0094 / 0.1808 / 2.5177 | 0.0000 | 0 / 0.5403 | 0.5966 / 0.9209 |
| R83_-1 | 0.0046 / 0.0157 | 0.0059 / 0.1097 / 1.4223 | 0.0000 | 0 / 0.0000 | 0.3059 / 0.3853 |
| R250_-1 | 0.0040 / 0.0125 | 0.0034 / 0.0750 / 0.8389 | 0.0000 | 0 / 0.0000 | 0.1145 / 0.1511 |
| R18_1 | 0.0089 / 0.0329 | 0.0123 / 0.2850 / 3.3881 | 0.0000 | 0 / 2.3034 | 0.9362 / 1.8654 |
| R35_1 | 0.0060 / 0.0219 | 0.0082 / 0.1658 / 1.6719 | 0.0000 | 0 / 0.3985 | 0.5971 / 0.9228 |
| R83_1 | 0.0045 / 0.0161 | 0.0063 / 0.1111 / 1.3955 | 0.0000 | 0 / 0.0000 | 0.3057 / 0.3869 |
| R250_1 | 0.0041 / 0.0127 | 0.0043 / 0.0842 / 0.9964 | 0.0000 | 0 / 0.0000 | 0.1150 / 0.1599 |
| S35 | 0.0082 / 0.0363 | 0.0123 / 0.2383 / 2.5177 | 0.0000 | 1 / 0.3932 | 0.6117 / 0.9226 |
| roundabout | 0.0070 / 0.0275 | 0.0105 / 0.2095 / 1.8551 | 0.0000 | 0 / 1.9038 | 0.9381 / 1.3096 |
| straight_10 | 0.0056 / 0.0258 | 0.0183 / 0.3661 / 3.9725 | 0.0000 | 0 / 0.0000 | neprítomný |
| straight_30 | 0.0062 / 0.0322 | 0.0177 / 0.3543 / 4.1220 | 0.0000 | 0 / 0.0000 | neprítomný |
| straight_60 | 0.0060 / 0.0257 | 0.0101 / 0.2025 / 1.9892 | 0.0000 | 0 / 0.0000 | neprítomný |
| straight_90 | 0.0058 / 0.0201 | 0.0061 / 0.1221 / 1.3774 | 0.0000 | 0 / 0.0000 | neprítomný |
| log_speed_R22_lag0.32 | 0.0093 / 0.0385 | 0.0127 / 0.2220 / 2.0448 | 0.0000 | 0 / 2.0216 | 0.9666 / 1.4802 |
| log_speed_R22_lag0.5 | 0.0119 / 0.0508 | 0.0137 / 0.2413 / 2.1221 | 0.0000 | 1 / 2.1111 | 0.9485 / 1.4771 |
| turn90_-1 | 0.0065 / 0.0228 | 0.0090 / 0.1662 / 2.1714 | 0.0000 | 0 / 0.3140 | neprítomný |
| turn90_1 | 0.0064 / 0.0216 | 0.0137 / 0.2930 / 2.7754 | 0.0000 | 0 / 0.6164 | neprítomný |

## Stresová matica

198 variantov = 11 geometrií × 3 gainy × 3 response × 2 konfigurácie. Základná tabuľka samostatne pokrýva oba smery. Matica používa pevný deklarovaný smer jednotlivých geometrií. Všetky dokončili úsek; žiadna neprekročila existujúci indikátor |CTE|>2,4 m; všetky platné analytické geometrie mali 0 control_rejected_samples. Maximálne |CTE| celej matice a základných scenárov: **1.304862 m**. Testy odmietnutia geometrie prebehli samostatne, nevkladajú sa do tohto počtu. Najhorší prípad je R18_gain0.60_response0.250_trailer: rozdiel medzi gainom modelu 0,60 a deklarovanou kalibráciou kontroléra 0,78 zväčšuje CTE. Je to reprodukovaná citlivosť, nie dôkaz regresie konkrétneho herného kamióna. Existujúca inkluzívna metrika nežiaducich zmien znamienka počíta 70 obrátení v 64 scenároch (maximum 2/scenár); zahŕňa aj prechodové nábehy a výjazdy. Po geometrickom obmedzení na monotónny oblúk s celým preview footprintom je monotone_opposite_samples=0 vo všetkých scenároch. Počty nie sú potlačené ani vydávané za nulu všetkých oscilácií. Najhoršie modelové CTE návesového bodu je 2,653024 m v R18_gain0.95_response0.250_trailer — nesmie sa zameniť s CTE hlavného bodu ani s bezpečnou clearance.

| Geometria | varianty / n / súčet úsekov s | najhoršie RMS / p95 / p99 / max CTE m | najhoršie heading RMS / max rad | max step / rate / accel |
| --- | --- | --- | --- | --- |
| R250 | 18 / 6078 / 310.18 | 0.3087 / 0.5359 / 0.6369 / 0.6414 | 0.0122 / 0.0305 | 0.0056 / 0.1113 / 1.0710 |
| R83 | 18 / 7504 / 382.31 | 0.2641 / 0.4608 / 0.5350 / 0.5395 | 0.0137 / 0.0433 | 0.0064 / 0.1267 / 1.6480 |
| R35 | 18 / 9224 / 470.16 | 0.3499 / 0.6575 / 0.6956 / 0.6986 | 0.0197 / 0.0713 | 0.0133 / 0.2750 / 2.6290 |
| S35 | 18 / 13366 / 682.25 | 0.4447 / 0.6842 / 0.7636 / 0.7768 | 0.0280 / 0.1274 | 0.0169 / 0.3385 / 5.6355 |
| roundabout_R25 | 18 / 16916 / 863.69 | 0.6443 / 0.8931 / 0.9674 / 0.9756 | 0.0187 / 0.0843 | 0.0120 / 0.2396 / 2.7526 |
| R18 | 18 / 12222 / 623.58 | 0.6258 / 1.2145 / 1.2999 / 1.3049 | 0.0294 / 0.1071 | 0.0189 / 0.4382 / 4.6604 |
| log_speed_R22 | 18 / 10394 / 530.06 | 0.6890 / 1.0455 / 1.1838 / 1.1923 | 0.0285 / 0.1117 | 0.0164 / 0.3522 / 4.2333 |
| straight_10 | 18 / 37404 / 1911.87 | 0.1052 / 0.2852 / 0.4940 / 0.5000 | 0.0057 / 0.0289 | 0.0183 / 0.3661 / 3.9725 |
| straight_30 | 18 / 12492 / 638.06 | 0.1096 / 0.3144 / 0.4991 / 0.5000 | 0.0069 / 0.0353 | 0.0177 / 0.3543 / 4.1221 |
| straight_60 | 18 / 6264 / 319.46 | 0.1355 / 0.4367 / 0.4999 / 0.5000 | 0.0089 / 0.0294 | 0.0101 / 0.2025 / 1.9892 |
| straight_90 | 18 / 4176 / 212.87 | 0.1730 / 0.4763 / 0.5000 / 0.5000 | 0.0113 / 0.0239 | 0.0061 / 0.1221 / 1.6865 |

Kompletné samostatné RMS, časové RMS, mean/p95/p99/max, heading, step/rate/accel, návrat, saturované časy a modelové návesy všetkých 216 prípadov sú v ignorovanom výsledkovom JSON; dajú sa znovu vytvoriť nástrojom nižšie. Matica nie je certifikát pre každú reálnu súpravu, zaťaženie či rýchlosť v R18.

## Herné meranie

### Zber 18:20–18:22 — platné source väzby

Kolekcia: `C:/Users/PC/AppData/Local/Programs/UltraPilot/evidence-diagnostics/roundabout-step2-20261001-182004`. Manifest SHA-256 `d1dc12bd64bba4e5a2df785456bca911621c218da1cfd09134deacab22d4eb3c`; overených **71 súborov**, **1585 vzoriek**, **4 zahodené**. `confirmed=false`, `runtime_authorized=false`; ide o kandidáta na offline posúdenie, nie udelenie manévrovacej autority ani atómový SDK snapshot.

Identita: session 1, map `promods-1.59`, dataset `d6cc7936fce4e902761abb5d`, intent `d01f08cda86e44f3b5fcb13b0ff3d3eb`, revision 9, build `78ee9cd8c6704060a106caed49813c40`. Aktívnych collector riadkov 442; inactive_unclassified 1143. Bez immutable source bolo 1109; ďalších 344 nemalo potvrdenú fyzickú source väzbu. Tieto vyradenia sú nedostatkom merania, nie automaticky poruchou riadenia.

370 jedinečných aktívnych source packetov: **32,0928 s**, progress **218,9354 m**. CTE je meraný **SDK chassis-origin LaneMatch**, nezamieňa sa za nápravu ani náves:

| n | RMS m | časová RMS m | mean abs m | p95 m | p99 m | max m | heading RMS / max rad |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 370 | 0,133874 | 0,133625 | 0,096536 | 0,277660 | 0,419299 | 0,460025 | 0,013295 / 0,064226 |

Heading zodpovedá približne 0,762° RMS / 3,680° max. Žiadne chýbajúce CTE ani heading v tomto aktívnom source úseku. Jediný neaktívny source packet zostal v samostatnom úseku; nepridáva sa do CTE štatistiky.

**132** fyzických zápisov má `backend_sent`, `command_binding_proven`, návratový čas zápisu a výstup zhodný s immutable source/executor. Je to **16** samostatných riedkych úsekov, súčet platných časov v nich ~19,4684 s. Ich max step 0,065527, max rate 0,244422 input/s, max accel 1,864685 input/s² sú iba zo zachytených párov; nepreukazujú maximá úplného 60 Hz priebehu. Fyzický doraz, trailer CTE, počet strát LaneMatch v celom prejazde a úplný bezpečnostný stop: **NOT VERIFIED**.

| Metrika ms | n | medián | p95 | p99 | maximum |
| --- | --- | --- | --- | --- | --- |
| Nové predložené packety, starý dense replay | 608 | 46.2134 | 92.4734 | 245.0144 | 264.6676 |
| SDK vek pri potvrdenom backend zápise | 132 | 120.3233 | 258.6734 | 311.3275 | 326.4722 |
| Výpočet → potvrdený backend zápis | 132 | 92.7081 | 239.5383 | 285.6073 | 306.9296 |
| Nové packety vzorkované combined zberom | 369 | 87.3603 | 188.2782 | 289.4137 | 313.6681 |

Cadence z combined zberu je podvzorkovaná a nesmie sa vydávať za úplnú frekvenciu produkcie. Starý dense replay má 3573 execution riadkov: 1854 aktívnych s platným immutable source, 3 s explicitne odmietnutým source sa vyradili; zvyšok nemá použiteľnú aktívnu source väzbu. Jeden source sequence sa pri odmietnutí objaví s `authority_valid=false`; neprepisuje platný source. Táto zmena je dôvod oddeleného vyradenia, nie nulovania CTE. Platné execution rady sa navyše rozdelili cez tri odmietnuté riadky: 1807 vzoriek / 32,3132 s a 47 vzoriek / 0,8062 s. Ich step/rate/acceleration sa nepočítajú cez túto medzeru. Maximum v prvom úseku je step **0,015402**, rate **0,589532 input/s**, accel **13,911600 input/s²**; presné p95/p99 a druhý úsek sú samostatne v JSON. Sú to outputy vykonávača, **nie ďalší dôkaz fyzických zápisov**.

Dense replay SHA-256 `0c84a79a07d42443498df726cea831141bbb7643f7d03fb516f6242630dda88d`. Jeden automatic_disable artefakt; konkrétny dôvod `GPS steering packet is incomplete` o 18:22:00. Logový ohraničený úsek a predchádzajúci ROUNDABOUT_PACKET_REJECTION report zachytávajú odmietnutý opakovaný SDK frame. Historické úplné dokončenie objazdu: **FAIL**; tento historický výsledok nesmie byť vydávaný za výsledok aktuálneho HEAD.

V tomto logovom okne je jedno N o 18:21:26,612. Probe .12 / brake 0 / steer 0 / bez selectoru: SDK frame 237623828, monotonic 17162,4761307; čerstvý gear 8: frame 237890484, 17162,7524019; handoff: frame 237957148, 17162,833995, throttle 0,183917 / brake 0. Potvrdenie prevodu po probe **276,271 ms**, handoff po probe **357,864 ms**; N→handoff približne **378 ms** podľa wall logu. **1 úspešný handoff z 1 zaznamenanej požiadavky v tomto okne**, nie globálna úspešnosť prvého N. Rýchlosť 9,233 m/s je nameraná v neskoršom frame 241407010 o 18:21:30,428. Presný okamih rozjazdu a vylúčenie ručného pedálu **NOT VERIFIED**: manuálny throttle v tomto zbere chýba. Log SHA-256 pri čítaní `93bf1824c6efda2af4a3834fa020d718383b2ebef9f483001b501db84e399c0f`; prehľad obsahuje len zvolený čas/build a potrebné ovládacie údaje.

### Nová jazda 19:23–19:25 — obmedzená schéma

Najnovší nájdený dense replay `steering-replay-20261001T172516.620019Z-manual_disable.json`, SHA-256 `166002a8c28c308d8433fcfb2195f4e70c9d9c6aa3cf9b255c0722621f962ef0`: 2040 vzoriek / 7293 execution riadkov. `source_packet` je vo execution riadkoch null. Nepoužijú sa nespoľahlivé mutable replay hlavičky na priradenie fyzického povelu, CTE alebo SDK odozvy. **Počet použiteľných source-bound fyzických povelov z tohto replaya: 0**; herné metriky celého reťazca aktuálneho HEAD preto **NOT VERIFIED**. Manual_disable artefakt sám nedokazuje úspešnú bezpečnostnú jazdu.

Časový záznam `steering-timing-20261001T172524.583977Z-plugin_stop.json`, SHA-256 `e707d4109046d716d75481e33b38b1714a611c01f3e91139002d26897ec42212`: **286** vzoriek, **264** identity-matched dostupných packetov, **201** active riadkov. Zvyšných 22 sa vylučuje z packetových metrík; nevyvodzuje sa z nich 22 produkčných chýb. Riadky sa delia medzi build `4f943fd4196f46079c04af4c3f28682f` / rev 7 / intent `47cd612155ff49c3a4d2cb01844f37bb` a build `2912d6dda01f4fb3b1b84771daf1f313` / rev 9 / intent `4cbbe02b439647e18ca2c5672ad831e2`; neaktívne dáta po zmene cieľa sa nespájajú s jazdou. Session/map/dataset sú uvedené priamo v JSON, bez predpokladu rovnakej fyzickej jazdy ako o 18:21.

Nasledujúca tabuľka je najdlhší aktívny súvislý časový úsek po delení pri 1 s: **201 vzoriek / 89.1507 s**, build `4f943fd4196f46079c04af4c3f28682f`. Dĺžka v metroch nie je v tejto schéme zaznamenaná. Hodnoty reference_ms pomenúvajú zaznamenaný interval prípravy, nie profiler jednotlivých funkcií; vysoký čas nedokazuje jednu konkrétnu funkciu. Publikovanie a read sa párujú len tam, kde sú obe časové značky.

| Fáza / metrika ms | n | medián | p95 | p99 | maximum |
| --- | --- | --- | --- | --- | --- |
| lane_update_ms | 201 | 20.1597 | 26.5244 | 56.0765 | 66.3736 |
| presentation_ms | 201 | 0.1813 | 3.8687 | 20.3164 | 50.4827 |
| road_type_ms | 201 | 0.5096 | 0.9570 | 1.7517 | 14.7314 |
| reference_ms | 201 | 27.7913 | 261.7376 | 296.9955 | 341.2431 |
| calculation_ms | 201 | 0.3615 | 0.5606 | 0.7001 | 0.8111 |
| IPC_publish_ms | 114 | 0.3549 | 0.8108 | 1.2479 | 1.2671 |
| publish_to_read_ms | 114 | 23.5146 | 230.9066 | 237.4147 | 238.4246 |
| compute_to_read_ms | 201 | 38.6244 | 224.6693 | 239.0187 | 258.1802 |
| observation_age_at_read_ms | 201 | 65.9466 | 253.6779 | 278.2547 | 307.6526 |

Žiadna použiteľná aktívna timing vzorka nemala age_at_read >500 ms; nejde o dôkaz každého ticku ani veku pri fyzickom zápise. Neaktívne vzorky po ukončení čítajú aj starý packet — nezamieňajú sa za aplikované riadenie. Presné rozdelenia všetkých segmentov sú v JSON. Bez source-bound zápisov a hashovo doloženej skutočne používanej zostavy sa nedá uzavrieť herný PASS aktuálneho HEAD.

## Kontroly a otvorené body

| Kontrola | Výsledok |
| --- | --- |
| Cielené navigačné, aktivačné, timing, controller a fail-closed regresie | PASS — 506 passed / 1188 subtests |
| Analytická metodika (RMS, váhy, gaps, missing, derivative, log/privacy, odmietnutý source, rôzne timing identity) | PASS — 9 passed |
| Controller benchmark | PASS — všetkých 16 case slovníkov presne zhodných s `steering-controller-bound-roundabout-20261001.json` |
| compileall core/plugins/ui/tools/tests | PASS |
| git diff --check a whitespace nových súborov | PASS; kontrolované aj untracked súbory |
| Celá pytest sada | NOT VERIFIED v tejto etape; spúšťa používateľ |
| Reálna automatika, každý bezpečnostný prechod v hre, úplný aktuálny HEAD | NOT VERIFIED |

Produkčný kód sa nezmenil. Nové súbory určené na sledovanie: `PHASE6_STAGE1_RESULTS.md`, `tools/analyze_phase6_stage1.py`, `tests/test_phase6_metrics.py`. Report je neignorovaný nový súbor pripravený na sledovanie v Git tree, zatiaľ nepridaný do indexu. Veľké surové vstupy sa nekopírovali a všetky auditné JSON/XML zostávajú ignorované. Existujúce súbory, swept-envelope a trailer_guidance zostali zachované.

Zostáva doplniť používateľovu celú pytest sadu a herné meranie presnej hashovo zhodnej zostavy s immutable source + potvrdenými zápismi. Novšia jazda bola nájdená a zhodnotená v rámci svojej obmedzenej schémy; nežiada sa automaticky ďalšia jazda. Neprirodzenosť, obraz AR, fyzické hranice, clearance a nadchádzanie nie sú uzavreté týmto reportom. Nemenia sa timeouty, bezpečnostné limity ani kalibrácia, aby výsledok vyzeral lepšie.

## Reprodukcia

Výpočty všetkých scenárov a existujúcich zberov (výstup zostáva ignorovaný):

```powershell
cd 'C:\Users\PC\Documents\GitHub\ets2la'
$env:PYTHONCASEOK='1'
python tools/analyze_phase6_stage1.py --simulate --matrix --collection 'C:\Users\PC\AppData\Local\Programs\UltraPilot\evidence-diagnostics\roundabout-step2-20261001-182004' --replay 'C:\Users\PC\AppData\Local\Programs\UltraPilot\route-diagnostics\steering-replay-20261001T162200.444168Z-automatic_disable.json' --replay 'C:\Users\PC\AppData\Local\Programs\UltraPilot\route-diagnostics\steering-replay-20261001T172516.620019Z-manual_disable.json' --replay 'C:\Users\PC\AppData\Local\Programs\UltraPilot\route-diagnostics\steering-timing-20261001T172524.583977Z-plugin_stop.json' --log 'C:\Users\PC\AppData\Local\Programs\UltraPilot\ultrapilot.log' --log-start 2026-10-01T18:21:14 --log-end 2026-10-01T18:22:01 --log-build 78ee9cd8c6704060a106caed49813c40 --output docs/steering-audit/phase6-stage1-metrics.json
python tools/run_steering_bench.py --output docs/steering-audit/phase6-stage1-controller-benchmark.json --quiet
python -m pytest tests/test_phase6_metrics.py -q -p no:cacheprovider --basetemp docs/steering-audit/pytest-phase6-metrics-user
python -m compileall -q core plugins ui tools tests
git diff --check
```

Kompletný výber 28 cielených súborov je zaznamenaný v `phase6-stage1-targeted.xml`; nebol nahradený celou sadou.

Presný cielený výber (po doplnení troch metodických testov bude ich počet o tri vyšší než prvý XML beh):

```powershell
$phase6Tests = @(
    'tests/test_phase6_metrics.py'
    'tests/test_activation_tick_stability.py'
    'tests/test_activation_observation_binding.py'
    'tests/test_activation_brake_and_stop.py'
    'tests/test_drive_engagement_safety.py'
    'tests/test_transmission_mode_activation.py'
    'tests/test_simple_auto_launch_handoff.py'
    'tests/test_simple_auto_ratio_transition.py'
    'tests/test_steering_fresh_handoff.py'
    'tests/test_map_control_packet_cadence.py'
    'tests/test_passive_steering_timing.py'
    'tests/test_lane_locator.py'
    'tests/test_lane_route_builder.py'
    'tests/test_lane_trajectory.py'
    'tests/test_lane_snapshot_transport.py'
    'tests/test_lane_authority_integration.py'
    'tests/test_navigation_intent.py'
    'tests/test_prefab_geometry_reuse.py'
    'tests/test_lane_audit_regressions.py'
    'tests/test_phase1_steering.py'
    'tests/test_stage2_lane_geometry.py'
    'tests/test_stage4d_control_timing.py'
    'tests/test_phase4c_steering_composition.py'
    'tests/test_phase4d_curve_coherence.py'
    'tests/test_phase4e_closed_loop_controller.py'
    'tests/test_phase4_steering_dynamics.py'
    'tests/test_steering_boundary_diagnostics.py'
    'tests/test_steering_replay.py'
)
python -m pytest $phase6Tests -q -p no:cacheprovider --basetemp docs/steering-audit/pytest-phase6-stage1-user
```
 Pri environmentálnom PermissionError použite nový jednoznačný basetemp v ignorovanom auditnom priečinku alebo rovnaký výber mimo filesystem sandboxu, nie zmenu tolerancií aplikácie.

Celá sada, ktorú spustí používateľ:

```powershell
cd 'C:\Users\PC\Documents\GitHub\ets2la'
$env:PYTHONCASEOK='1'
python -m pytest tests -q
```
