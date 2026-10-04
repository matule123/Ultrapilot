# Odložená a nedokončená práca

## Lease a nájazd na objazd 35 km/h – 4. 10. 2026

[PHASE7_LEASE_AND_ROUNDABOUT_20261004.md](PHASE7_LEASE_AND_ROUNDABOUT_20261004.md)
dokladá opravu zbytočnej závislosti čerstvého povelu od vyššieho neúčinného
mapového limitu a anticipačný horný cieľ 35 km/h na identifikovanom objazde.
Nižšie limity a dynamické dôkazy zachovávajú pôvodné lease. Modelové nájazdy
a dlhé cykly prešli offline; herný účinok nie je overený. Incident 19:51:22
neobsahuje pôvodný zoznam spotrebovaných lease, takže konkrétny historický vstup
nemožno jednoznačne určiť. Inštalovaný Engine a Map zodpovedajú staršiemu
cf25a975, nie vstupnému HEAD e0be9ea. Nič sa nenasadilo. Pred spoločným overením
treba celú sadu používateľa a osobitné schválenie konzistentného nasadenia.
Blokátor samostatného držania zo státia ostáva.

## Spoločná spoľahlivosť a zapnutie pred červenou – 4. 10. 2026

[PHASE7_JOINT_LIFECYCLE_RELIABILITY_20261004.md](PHASE7_JOINT_LIFECYCLE_RELIABILITY_20261004.md)
dokladá opravu starého mapového lease prenášaného do čerstvých pozdĺžnych
povelov a odovzdania rozjazdu plánovanému súvislému brzdeniu. Aktívne čakanie
po brzdení z jazdy a potvrdená zelená s rozjazdom bez ďalšieho N prešli offline.

Požiadavka „jedno N pri už stojacom kamióne → aktívne Čakám na zelenú so
samostatným držaním vozidla“ zostáva **BLOCKED** pre jednoduchú automatiku.
Chýba overený spôsob prevádzkového držania zo státia, ktorý novou SDK brzdovou
hranou nevyvolá R. Controller nemá oddelený potvrdený povel pre také držanie;
zmiešaný SDK brzdový údaj nedokazuje vlastníctvo neprerušenej brzdy vodiča.
Parkovaciu brzdu nepoužívame. Nový čakajúci požiadavkový stav s nulovými SDK
pedálmi výslovne vyžaduje držanie vodičom a **nie je** splnením tejto požiadavky.
Jeho pokračovanie po zelenej nie je dôkazom samostatného držania.

Nové runtime zmeny nie sú nasadené. Herná spotreba SDK brzdy, držanie na svahu
a úplný výsledok najnovšej opravy zostávajú neoverené. Ďalšia jazda sa teraz
nežiada; najprv celá sada používateľa a samostatné schválenie prípadného nasadenia.

## Rozjazd po semaforovom čakaní – 4. 10. 2026

[PHASE7_SIGNAL_STOP_RESUME_20261004.md](PHASE7_SIGNAL_STOP_RESUME_20261004.md)
opisuje dokončený offline tok uzamknutého semafora s producentovým časom,
generáciou a životným cyklom. Dve nové relevantné zelené snímky umožnia
riadené uvoľnenie súvislej brzdy a existujúci ohraničený rozjazd bez ďalšieho N.
Parkovacia brzda sa neovláda. Výber je geometrická heuristika, nie dokázaná
väzba na LaneId. Nejednoznačnosť, legacy zdroj a ďalší nevyjasnený dôvod
zastavenia rozjazd blokujú. Pripravený DLL kandidát nie je nasadený; spotreba
SDK vstupu, držanie na svahu a výsledok v ETS2 zostávajú neoverené.
Pred prípadným nasadením je potrebná celá sada používateľa a osobitný súhlas.
Nižšie uvedené BLOCKED závery opisujú starší kontrakt bez sidecaru.

## Súvislá prevádzková brzda – 3. 10. 2026

[PHASE7_CONTINUOUS_SERVICE_STOP_20261003.md](PHASE7_CONTINUOUS_SERVICE_STOP_20261003.md)
nahrádza nižšie uvedený paušálny predpoklad o brzde pri státí. Súvislý doložený
reťazec softvérových zápisov začatý pri doprednej jazde povoľuje plánované čakanie
bez ručnej brzdy. Spotreba DLL/ETS2 a držanie na skutočnom svahu nie sú herne
potvrdené. Automatický rozjazd po čakaní zostáva nepovolený: chýba pôvodný čas,
generácia a úplné potvrdenie zániku všetkých dôvodov zastavenia. Neznáma zelená
ani zmiznutie auta neznamenajú voľnú cestu. Existujúci rozjazd po N sa nemení.

Cielené overenie producenta našlo verejný MIT zdroj pre 1.59, ale nie dekódovanú
väzbu semaforu na smerovaný priechod. `traffic_item_rule_link_t` a polia
`N00007A8F`/`N00007AA3` nemajú doložený význam potrebný na potvrdenie zelenej.
Zdrojový timestamp/generácia samy nestačia. Presný dôkaz, hash nainštalovanej DLL
a reprodukcia legacy zelenej až po backend sú v doplnení vyššie uvedeného reportu.
Automatické pokračovanie zostáva BLOCKED; nová jazda sa nežiada.

## Držanie pri zastavení a tichý log – 3. 10. 2026

[PHASE7_SAFE_STOP_AND_LOGGING_20261003.md](PHASE7_SAFE_STOP_AND_LOGGING_20261003.md)
opisuje explicitné odovzdanie brzdy vodičovi pri jednoduchom automate,
uchovanie spotrebovanej brzdovej požiadavky a prvého dôvodu cez release/export
a presun bežných diagnostických výpisov na DEBUG. Rozjazd a riadenie nemení.
Automatické držanie na svahu a rozjazd po čakaní zostávajú nepodporované:
Controller nemá overený stavový povel pre držaciu brzdu s potvrdením vykonania
a vlastníctvom. Samotné tlačidlové pole `parkingbrake` ani SDK príznak
`parkBrake` tieto schopnosti nedokazujú. Brzdu zatiahnutú vodičom neuvoľňujeme.
Chýbajúci semafor alebo zmiznutý ACC kandidát neudeľujú autoritu na rozjazd.
Vodič musí pri odovzdaní prevziať brzdu; nulové výstupy nezaručujú státie na svahu.
Nové zmeny nie sú nasadené ani potvrdené v hre. Nová jazda sa nežiada.

## Zastavenie pred objazdom a prvý dôvod – 3. 10. 2026

[PHASE7_ROUNDABOUT_INTERVENTION_20261003.md](PHASE7_ROUNDABOUT_INTERVENTION_20261003.md)
uvádza offline opravu neviazanej brzdovej autority starého stavu planneru,
prvého dôvodu v Engine/UI/exporte a chybného označenia automatického vypnutia
ako manuálneho. Pri incidente 18:40:40 chýba skutočne vybraný pedálový povel,
preto nemožno dokázať premávku verzus expiráciu/identitu. Nové logovanie
neobnovuje historické údaje a herné potvrdenie zostáva otvorené.

Predvídavé dávanie prednosti, automatické čakanie a opätovný rozjazd na objazde
nie sú podporované. Chýba pôvodný čas/generácia traffic producenta,
potvrdená smerovaná dráha aktéra, miesto prednosti/konfliktu a pokrytie.
Reaktívny kandidát ani prázdny buffer nedokazujú bezpečnú medzeru.
Ochrana jednoduchej automatiky pred brzdením do R zostáva zapnutá;
pri bezpečnostnom zastavení odovzdá riadenie vodičovi. Nová jazda sa nežiada.

## Pozdĺžne povely a spomaľovanie pred objazdom – 3. 10. 2026

[PHASE7_COMMIT_AND_CURVE_REGRESSIONS_20261003.md](PHASE7_COMMIT_AND_CURVE_REGRESSIONS_20261003.md)
opisuje lokálnu opravu výberu pedálového povelu až po príprave Engine,
zjednotenie existujúceho zákrutového rýchlostného profilu a dostatočný horizont
nad dostupnou geometriou. Reprodukcie, fyzické testovacie zápisy a uzavretý model
prešli; herný výsledok nie je potvrdený. Presná odmietnutá historická snímka
nebola uložená, preto nemožno spätne určiť expiráciu verzus zmenu identity.
Oprava nezvyšuje timeout ani neobnovuje vek povelu. Ďalšia brána je celá sada
používateľa; nasadenie vyžaduje samostatný súhlas. ACC vstupné obmedzenia,
neznáma historická dĺžka čakania na zámok a komfort v ETS2 zostávajú evidované.

Stav k 3. 10. 2026. Toto je plán ďalšej práce, nie prísľub termínu.

## Fáza 6 – administratívne uzavretá v overenom rozsahu

[PHASE6_FINAL_RESULTS.md](PHASE6_FINAL_RESULTS.md) rozlišuje offline dôkazy,
poslednú meranú jazdu, historické zlyhania a neoverené vlastnosti aktuálneho HEAD.
Uzavretie nie je univerzálne herné potvrdenie ani povolenie nadchádzania.
Posledná jazda obsahuje celý navigovaný výjazd z objazdu a nasledujúcu cestu;
neidentifikovaný úsek „po mýto“ zostáva neoverený.

## Prirodzenosť riadenia – fáza 2 (odložené)

Riadenie používa existujúci regulátor a pôvodný preview 0,134 s.
Nevznikol nový systém „ľudského“ tvarovania volantu. Kandidát preview 0,200 s
bol zamietnutý pre zhoršenie držania pruhu. Doladenie nábehu a návratu
volantu na kruhovom objazde nie je hotové; doplní sa v budúcnosti.
Posledný analyzovaný zber už obsahuje celý navigovaný výjazd, ale riedke
potvrdené zápisy a chýbajúce kritérium prirodzenosti nepotvrdzujú plynulosť
každého fyzického 60 Hz výstupu. Meranie výjazdu nie je potvrdenie nového ladenia.

## AR čiara (otvorené)

Preblikávanie AR čiary je nahlásené, ale jeho konkrétna príčina ani oprava
nie sú potvrdené. Oprava steering packetu sama nedokazuje opravu vykresľovania.

## Nadchádzanie s návesom (odložené)

Nie je hotový univerzálny aktívny systém nadchádzania. Existujúce offline
plánovače a diagnostika nie sú dôkazom zapojeného a overeného živého systému.
Automatické získavanie potvrdených prejazdných hraníc a prekážok bez obrazu
nie je vyriešené. Vývoj sa obnoví v budúcnosti; bežné riadenie nesmie byť
označované za aktívne nadchádzanie.

## Zostávajúce overenie packetov a diagnostiky

Používateľova celá pytest sada prešla pre skorší zdokumentovaný stav;
nie je tým doložený výsledok pre najnovší commit 0ed71aa. Posledná jazda má
0 prekročení 500 ms v 246 potvrdených zápisoch. Úzka oprava kontroly čerstvosti
po lokalizácii prešla offline reprodukciou; presná príčina dlhých prestávok
stále nie je dokázaná a nemôže sa sľúbiť odstránenie všetkých budúcich výpadkov.

Oprava identity collectora 0ed71aa je overená offline, ale nainštalovaný zberač
ju zatiaľ neobsahuje. Herné potvrdenie jej dokončenia zostáva otvorené.
Samostatne zostáva herné overenie reálnej automatiky, úplnej zastavovacej dráhy
a vylúčenia ručného plynu chýbajúcim raw kanálom. Nová jazda sa teraz nežiada.

## Fáza 7.1 – jednotná arbitráž plynu a brzdy

Implementácia a cielené offline overenie sú v
[PHASE7_STAGE1_RESULTS.md](PHASE7_STAGE1_RESULTS.md). Jeden identitou a časom
viazaný povel prechádza poslednou bránou Engine; EcoDrive neobnoví plyn počas
brzdenia. Núdzová požiadavka zostáva nad bežným pohonom. Nasadenie ani herné
potvrdenie nového toku neprebehli; celú pytest sadu spustí používateľ.

## Fáza 7.2 – stabilita rýchlosti a pedálov (implementované offline)

[PHASE7_STAGE2_RESULTS.md](PHASE7_STAGE2_RESULTS.md) uvádza reprodukcie,
kritériá a porovnanie rovnakých uzavretých scenárov. Jediný existujúci ACC PID
rieši aj bežnú brzdu; integrál sa nenabíja pri vypnutí alebo vonkajšom brzdení.
Komfort v ETS2 zostáva neoverený. Pedálová rampa nie je záruka fyzického jerk.
Celú pytest sadu spustí používateľ; nasadenie v tejto úlohe neprebehlo.

## Fáza 7.3 – ACC (implementované ochranné zlepšenia, neúplný vstupný dôkaz)

[PHASE7_STAGE3_RESULTS.md](PHASE7_STAGE3_RESULTS.md) opisuje výber kandidáta
pozdĺž LanePath, odstupové obmedzenie pre existujúci PID a odmietnutie obnovenia
plynu po strate cieľa. Dvojité čítanie legacy bufferu nepotvrdzuje čerstvosť
producenta; chýba jeho timestamp/generácia, LaneId a úplnosť pokrytia.
Spoľahlivé živé ACC preto nie je potvrdené. Prázdny buffer po sledovaní vyžaduje
odovzdanie vodičovi; nevzniklo automatické stop-and-go ani nový dopravný senzor.
Spoločné offline overenie Fázy 7.4 je v záverečnom reporte nižšie a výslovne
oddeľuje tieto obmedzenia od držania rýchlosti a bezpečnostných zásahov.

## Fáza 7.4 – spoločné offline overenie uzavreté

[PHASE7_FINAL_RESULTS.md](PHASE7_FINAL_RESULTS.md) viaže výsledky 7.1–7.3
na commity a uzatvára spoločné offline kontrakty. Nové testy overili celý tok
producentov cez arbitráž až po fyzické volania Engine, oba automatické režimy,
poradie aktualizácií, okamžitú núdzovú brzdu a povel zo zrušenej aktivácie.
Riadenie ani runtime sa v 7.4 nemenili. Komfort v ETS2 a spoľahlivé živé ACC
zostávajú neoverené; simulácia ani prítomné súbory inštalácie to nepotvrdzujú.

Existujúci combined export má platnú integritu, ale neukladá cieľové rýchlosti,
paired longitudinal_command, skutočné longitudinal_applied s časom/identitou,
ACC kandidáta a prvý dôvod zásahu. Zber pre komfort preto zatiaľ nie je
pripravený. Najmenšia ďalšia úloha je explicitné doplnenie iba týchto malých
immutable diagnostických kanálov a izolované overenie väzby/exportu; nevzniklo
v tejto úlohe a nová jazda sa nežiada. Spätná SDK odozva sa musí párovať až
s následnými frame, nie automaticky s riadkom zápisu.

Táto medzera zodpovedá pôvodnej zostave 7.4. Následné zdrojové doplnenie je v
[PHASE7_LONGITUDINAL_DIAGNOSTICS.md](PHASE7_LONGITUDINAL_DIAGNOSTICS.md): bounded
nemenný zdroj rozhodnutia, skutočné SCS mapping zápisy, ciele a dostupný ACC
kandidát sa ukladajú do existujúceho combined zberu. Export, integrita a analýza
sú overené offline; zmena zatiaľ nie je nasadená ani herne potvrdená. Ďalší krok
je používateľova celá sada a samostatné schválenie spoločného nasadenia core
súborov. Chýbajúce SDK pedálové kanály ostávajú null; návrat zápisu nie je
dôkazom spotreby hrou. Komfort a spoľahlivosť traffic zdroja ostávajú backlog.

Samostatný blokátor ACC zostáva timestamp/generácia traffic producenta,
nepreukázaná príslušnosť k pruhu/pokrytie a neznámy rozdiel referenčných bodov
od nárazníkov. Diagnostické doplnenie tieto údaje nevytvorí. Nový senzor, DLL,
stop-and-go ani nadchádzanie nie sú súčasťou uzavretia Fázy 7.

## Zastavenie a semaforový rozjazd – oprava incidentu 4. 10.

[PHASE7_SIGNAL_LIFECYCLE_REGRESSION_20261004.md](PHASE7_SIGNAL_LIFECYCLE_REGRESSION_20261004.md)
dokumentuje úzke opravy core: strata dôvodu plánovaného zastavenia cez limit
diagnostickej kópie, prvá brzda pri potvrdenom prechodnom nulovom prevode a
export skutočných párov pedálových zápisov. Opakované cykly červená–čakanie–zelená
prešli offline cez oboch skutočných producentov, Autopilot, Engine a Controller.
Samotný incident nemá záznam pôvodného zdroja brzdy; ten sa spätne nevymýšľa.

Herná spotreba súvislej SDK brzdy pri státí a následný rozjazd na relevantnú
zelenú zostávajú neoverené. Po celej sade používateľa a schválenom spoločnom
nasadení core stačí overiť podporovaný jeden semaforový cyklus. Výber hlavy je
geometrická heuristika; chýbajúca alebo nejednoznačná zelená ani zmiznuté auto
nesmú povoliť pokračovanie. Parkovacia brzda vodiča zostáva mimo autority.
