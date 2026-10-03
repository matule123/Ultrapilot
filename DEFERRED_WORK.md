# Odložená a nedokončená práca

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
Fáza 7.4 má spoločne overiť aktuálny pozdĺžny tok a výslovne oddeliť tieto
obmedzenia od meraného držania rýchlosti a bezpečnostných zásahov.
