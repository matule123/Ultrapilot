# Odložená a nedokončená práca

Stav k 2. 10. 2026. Toto je plán ďalšej práce, nie prísľub termínu.

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

## Navrhovaná ďalšia samostatná úloha – plyn, brzda a ACC

Zdokumentovať arbitráž existujúcich pohonných a brzdových intentov a offline
reprodukovať súbeh bezpečnostného zastavenia, ACC, neplatnej premávky a manuálneho
zásahu. Kritériá stanoviť pred ladením; zachovať nulový pohon pri strate autority
alebo spiatočke a ochranu jednoduchej automatiky pred brzdením do R.
Fáza 6 túto úlohu neimplementuje; rozsah a obmedzenia sú v záverečnom reporte.
