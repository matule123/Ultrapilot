# Obnova spoľahlivosti: dôkazy a tri oddelené fázy opráv

## Čo je hotové teraz — nie ďalšia verzia ACC

Z jazdy 24. 10. 2026 sú zachované kópie logov, nainštalovaného kódu a replayov.
Každý zo štyroch doložených bezpečnostných zásahov má vlastný JSON a krátky
prehľad v `docs/steering-audit/oct24-driving-incidents/`. Párový export Engine
a Autopilot je jeden incident, nie dve chyby. Všetkých 13 replayov prešlo
kontrolou integrity a 53 položiek deployment receipt sedí s inštaláciou.

Samotná integrita neznamená úplnosť záznamu, správnosť rozhodnutia ani to, že
hra skutočne spotrebovala zapísaný pedálový povel. Originály sa nemenili,
neodstránili; zber na novú jazdu nie je aktivovaný. Runtime a verzie sa nemenili.

| Spis | Čas | Doložený zásah | Čo zatiaľ nie je potvrdené |
| --- | --- | --- | --- |
| `01-201154-gps` | 20:11:54 | GPS bol označený ako odstránený, revízia sa zmenila 12 → 13; odmietnutý starý steering packet. V okamihu následného boundary záznamu rýchlosť približne 50,3 km/h. | Prečo zmizol cieľ: príchod, zrušenie alebo nekonzistentný vstup. Nie je to doložené zlyhanie ACC. |
| `02-201351-acc42` | 20:13:51 | ACC pôvodný cieľ 42, typ `lead`; `no_candidate_unproven_coverage` → `following_required` → neplatné longitudinal observation → technický stop. | Či actor skutočne odbočil mimo kolíznej trajektórie a či bol pôvodne správne vybraný. |
| `03-201435-hold` | 20:14:35 | Pohyb 0,054094 m/s (~0,195 km/h), zaradený stupeň 4, pri continuous service brake hold → technický stop. Vybraný vstup bol platný; brake demand 0,277307, zdroj `traffic_light`. | Príčina skorého/nestabilného hold prechodu, pohybu a súvis s farbou semafora. Nejde o dôkaz potreby iba zvýšiť toleranciu. |
| `04-201522-acc39` | 20:15:22 | ACC cieľ 39, typ `crossing`, následne `no_candidate_unproven_coverage` a rovnaká vetva invalid observation. | Časové ukončenie konfliktu, geometria križovania a dôvod pretrvávajúceho vlastníctva cieľa. |

Pri incidente 02 mal odmietnutý vstup vek ~35,8 ms a do expirácie zostávalo
~464 ms; pri incidente 04 vek ~42,1 ms a zostávalo ~458 ms. Tieto dve
odmietnutia sa preto nesmú prezentovať ako vypršaný lease ani riešiť zvýšením
timeoutu. Sú to doložené dôvody odmietnutia, ešte nie úplné prvotné príčiny.

Pri incidente 02 obsahuje zachovaná história červenú/žltú/zelenú; pri incidente
03 sú zachované nenulové hodnoty `signal_color` zelené. To je dôvod preveriť
väzbu signal ID/frame/stop cieľa a hold vlastníka. Samotná zelená v jednom
stĺpci ešte nedokazuje, že patrila presne tomu zdroju brzdy v okamihu zásahu.

Používateľov opis „červená → zelená → rozjazd → auto prechádzajúce popred
kamión → zastavenie“ je samostatné svedectvo. Log navyše hlási o 20:13:48
`Moving planned stop released: source signal, ID 1, generation 10729`.
Priradenie presného fyzického auta a všetkých okamihov k jednotlivým zásahom
sa nesmie domyslieť z poradia hlášok.

## Podstatné medzery a identita zostavy

- Tri zápisy udalostí zlyhali na `SIGNIFICANT_EVENT_EXPORT_DISK_QUOTA`
  (20:13:04, 20:13:34, 20:14:34). Archívna kópia sama kvótu pôvodného zberača
  neuvoľnila; zdrojové súbory zostali na mieste.
- Sú zachované približne 30-sekundové rozhodovacie histórie, ale detailné
  pedálové žurnály sú ohraničené a označené ako neúplné. Napríklad pri zásahu
  02 zostalo osem detailných volaní s rozsahom ~0,21 s a `dropped_events=2786`.
  Agregovaná história nie je náhradou detailného call-by-call toku.
- Nie je potvrdená úplná historická scéna: všetky pôvodné actor polia,
  geometrie a predikcie pred znížením detailu. Aktuálny snapshot nedokáže
  spätne doplniť chýbajúci minulý packet. ID 42/39 nie je trvalá identita auta
  mimo konkrétneho lifecycle/slotu/source/acquisition.
- Nainštalované `core/engine.py`, `core/longitudinal.py`,
  `core/transmission_mode.py`, `plugins/autopilot/main.py` sa líšia od dnešného
  pracovného stromu. To nie je dôkaz, že pracovný strom problém už opravuje.
  Fázy musia porovnať presný nasadený kód s kandidátom; PASS sady na pracovnom
  strome sa nesmie vydávať za otestovanie celej inej nainštalovanej zostavy.
  Rozdiely versioned game DLL oproti legacy root assets sú zámerné a nie sú
  v tomto zozname označené za chybu nasadenia.
- `TOPOLOGY_AMBIGUOUS` pri dlhších trasách je ďalšia, oddelená vetva navigácie.
  Z nej sa nesmie bez časovej a dátovej väzby vyrobiť príčina neskoršieho ACC stopu.

## Fáza 1 — uzavrieť zber pred ďalšou opravou riadenia

Táto fáza má najprv dokončiť existujúci incidentový zber, nie vytvoriť druhý
paralelný systém a nie meniť jazdné rozhodnutia.

1. Uzamknúť presný deployment manifest a archivovať rozdiely oproti kandidátovi.
2. Jeden trvalý incidentový identifikátor pre súvisiaci Engine/Autopilot/HUD
   zásah; jedno hlavné JSON dossier + ľudský prehľad. Pred/po rozsah sa uvedie
   ako skutočne zachovaný, nie sľúbený. Oddeliť:
   plánované státie, ochranné spomalenie, AEB, technický stop, zásah vodiča.
3. Zachovať aspoň konfigurovateľné 30 s pred a 10 s po udalosti, ak sa dá bez
   narušenia riadiaceho ticku; chýbajúcu časť výslovne označiť. Dočasné zastavenie
   alebo opätovná aktivácia nesmú vymazať pôvodný prvý dôvod. Po vypnutí aktívneho
   riadenia môže pokračovať iba pasívny zber, nie povely vozidlu.
4. Pred stratením/kompaktovaním uložiť **skutočne spotrebovanú** akvizíciu:
   lifecycle, generation, zdrojový frame a čas; pôvodné moving/parked záznamy,
   ID/source/slot, pozície, rýchlosti, rozmery, orientácie, relevantné flags.
   Pripojiť ego obálku, lane/route revíziu, bod konfliktu a výpočet predikcie.
   Vizuálnu farbu/typ auta uvádzať len ak ich zdroj poskytuje. HUD farba rizika
   musí byť odlíšená od fyzickej farby auta.
5. Uchovať semaforové ID/passage, nameranú farbu a čas, osobitne odhad fázy,
   stop cieľ a jeho zdroj; každý kandidát obmedzenia s dôvodom prijatia/odmietnutia,
   vybraného vlastníka, požadované pedále, skutočné volania backendu a SDK odozvu.
   Pripojiť rýchlosť/zrýchlenie, prevodovku, otáčky, vstupy vodiča, hold/launch
   stav; nedostupné polia zostanú `unavailable`, nikdy odhadom doplnené.
6. Kvóta: overená recoverable archivácia uzavretých prípadov, explicitná
   predkontrola miesta a limitu, žiadne tiché prepisovanie/mazanie. Diagnostická
   chyba musí byť jasne viditeľná, nesmie blokovať riadenie. Nedvíhať limit
   bez ohraničeného diskového a pamäťového rozpočtu.
7. Opakovateľné testy pre quota full, export exception, burst dvoch zásahov,
   opätovné zapnutie, lifecycle reset, zmiešané frame, výpadok po prvom dôvode,
   rotáciu archívu a prípady bez actor dát. Zmerať dopad na tick/IPC/pamäť.

**Výstupná brána:** na vopred definovaných testoch každý zásah vytvorí
validovateľný spis alebo jednoznačný záznam zlyhania zberu; žiadne vymyslené
okolnosti, zmena rozhodnutí ani nové latencie vedúce k stopom. Až potom nová
krátka jazda. Dnešné štyri dossiers sú zachované, ale táto brána ešte splnená nie je.

## Opravná fáza A — semafor, brzdenie, hold a rozjazd

Reprodukovať konkrétny prechod červená → zelená počas brzdenia a pri skoro
nulovej rýchlosti cez Map/Policy/ACC/Engine/skutočný Controller. Najprv porovnať
nasadený stav a pracovný kandidát. Vysvetliť kto mení brzdu/plyn a kto vlastní
hold. Oddeliť dojazd, potvrdené státie, hold, uvoľnenie a rozjazd.

**Brána:** pôvodný reprodukčný prípad pred opravou zlyhá; po oprave bez
brzda–plyn oscilácií, predčasného hold ani falošného technického vypnutia.
Zelená neprebije skutočný konflikt s autom; státie na červenej neprejde do
samovoľného plazenia. Kvantifikovať chybu rýchlosti, stop odstup, jerk a zmeny
vlastníka/pedálov pred → po; zachovať núdzové vetvy a preveriť pomalé fyziky.

## Opravná fáza B — ACC/krížiace autá/prednosť na objazde

Spoločné prípady 02 a 04, ale odlíšiť `lead` od `crossing`/yield konfliktu.
Zrekonštruovať pôvodný výber, kontinuitu a dôkaz uvoľnenia. Nesmie sa riešiť
tým, že zmiznuté auto automaticky znamená voľnú cestu, ani tým, že ľubovoľné
auto pri križovatke navždy zostane vlastníkom ACC.

**Brána:** odbočujúce a potvrdene odchádzajúce auto uvoľní obmedzenie;
naozaj neviditeľná/stratená prekážka sa nevydá za bezpečne odídenú. Cut-in,
stojace auto, vozidlo priamo pred vjazdom, prechádzajúce auto na objazde,
actor mimo nášho koridoru, zmena slotu/ID/lifecycle a dve súčasné hrozby majú
samostatné negatívne aj pozitívne testy. AEB a prednosť nesmú byť vypnuté.
Historický actor sa neidentifikuje iba číselným ID.

## Opravná fáza C — GPS/aktivácia/trasy a spoločné overenie

Riešiť incident 01 osobitne od ACC: stratu cieľa, zmenu revízie a bezpečné
odovzdanie, potvrdený príchod verzus ručné zrušenie, opätovnú aktiváciu bez
reštartu. Nevydávať GPS nulu automaticky za dôkaz príchodu. Nejednoznačné
prefab prepojenie porovnať s natívnym zdrojom → exportom → lane výberom;
nevypnúť validátor a nevyberať ľubovoľnú vetvu.

**Spoločná brána nasadenia:** konzistentný testovaný payload a hashe, celé
regresie plus reprodukcie z A/B/C, kontrola výkonu. Potom jedna vopred určená
jazda cez predtým zlyhávajúce miesta: červená–zelená pri dobrzďovaní, auto
odbočujúce popred kamión, obsadený/prázdny objazd, zmena/zrušenie cieľa a
opätovné zapnutie. Po každom probléme jeden overený spis. PASS pytest sa
neoznačuje za GAME VERIFIED; nenašiel sa nový problém ≠ vysvetlená stará príčina.

## Aktuálny handoff

Začať fázou 1 na existujúcich rozhraniach. Ďalšiu testovaciu jazdu ani ďalšiu
verziu ACC teraz nevyžadovať. Necommitovať/nepushovať/nenasadzovať opravy
riadenia iba preto, že sú pripravené. Návrhy A/B/C sú oddelené pracovné bloky,
nie tvrdenie, že už boli implementované alebo že všetky historické chyby sú známe.
