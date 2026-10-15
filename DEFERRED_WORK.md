# Odložená a nedokončená práca

## Traffic lease handoff — 15 October 2026

See [PHASE7_TRAFFIC_LEASE_HANDOFF_20261015.md](PHASE7_TRAFFIC_LEASE_HANDOFF_20261015.md).
Core selection now preserves the validated envelope required by bounded final
write recovery; actual consumed inputs/vehicle pairing survive a prewrite
fault separately from safety output. No plugin/DLL or regulator release change.
Historical traffic publication/first delivery and the initiating scheduling gap
are not retained. They are not inferred from a later SDK frame or an older
significant receipt. New behavior is GAME NOT VERIFIED. Performance outliers
(including a 134.4 ms modeled recovery flush) remain explicitly reported,
without claiming an identified GC/IPC cause. Existing significant-event quota
is still full; no originals are archived or deleted, and automatic fault export
retains its priority receipt. No new drive is requested in this task.

## October 14 final stop-completion continuation

The final continuation in
[PHASE7_DESTINATION_STOP_AND_ACC_COMPLETION_20261014.md](PHASE7_DESTINATION_STOP_AND_ACC_COMPLETION_20261014.md)
reproduces and fixes the shared positive-moving-constraint/terminal-hold conflict.
Qualified ordinary protective caps now feed the existing speed PID instead of a
separate legacy distance brake; acquired-source loss and terminal conflicts remain
protected. ACC 1.3.1 is an actual consumer change; DrivePolicy stays 1.1.4. The
initial held-brake-decrease-only experiment failed the closed model and is rejected.

Positive-GPS planning standstill now retains continuous service brake and explicit
driver takeover instead of silently releasing it and claiming native completion.
Automatic GPS disappearance/arrival remains BLOCKED by the undefined native
private target and completion/cancellation lifecycle interface. A local Map tail,
zero remainder or receiver timestamp cannot supply that authority. The historical
turn's original actor and original 93 ms sample spans are absent; their exact causes
remain unproved. New same-input CPU-cycle/wall/GC/export measurements are separate
offline observations, not retroactive explanation or game verification.

The earlier v1/v2 candidate ZIPs are superseded by the final continuation. No
installation or original data is changed, and no new ordinary ride is requested
to obtain missing native semantics. The complete two-problem request stays OPEN
at the precisely named GPS producer/handover dependency.

## October 14 independent completion and exact blockers

October 14 follow-up reviewed the calculated LanePath endpoint: a full current
UID window can produce the same final centerline point for distinct live GPS
remainders. Computed endpoints are acceptable only with independent whole-goal
identity/completeness; native coordinates alone are not the sole possible design.
Arrival/cancellation semantics remain unresolved. The review fixes actual-box
AEB omissions (parked bodies and already-observed overlap on a short horizon)
and sticky incomplete crossing ownership. Same-image SDK pedal/load fields and
an offline passive response estimator are implemented; existing old data lack
those channels, and no automatic calibrated mapper is enabled or certified.

[PHASE7_DESTINATION_STOP_AND_ACC_COMPLETION_20261014.md](PHASE7_DESTINATION_STOP_AND_ACC_COMPLETION_20261014.md)
adds a real acquisition-timed native Traffic v1 candidate, qualified negative
leader anticipation, original-body crossing-clearance ownership/restart and
protective observed tractor/trailer contact prediction. The one existing PID
estimates its measurement derivative and retains anti-windup and immediate
safety priority. No installation changed. These are model/ABI/production-test
results, not game acceptance or complete traffic coverage.

Arrival after automatic GPS removal remains BLOCKED: the available native
route task exposes nodes/remainders and partly unknown waypoint/target structs,
not an authenticated final world goal and completion-versus-cancellation event.
No receiver-side disappearance heuristic or unknown native flags are used.
The initiating actor of the historical October 13 hold is still absent, so the
new clearance reproduction does not prove that historical stop was spurious.
Legacy/unqualified actor stops remain conservative. Calibrated load-adaptive
acceleration mapping and certified full swept AEB remain separate blockers;
actual boxes/source time do not provide road-load identification, dimension
error bounds, traffic coverage or future articulation accuracy.

## October 13 arrival / retry / stop ownership follow-up

[PHASE7_ARRIVAL_RETRY_AND_ACC_ACCELERATION_20261013.md](PHASE7_ARRIVAL_RETRY_AND_ACC_ACCELERATION_20261013.md)
fixes the historically recorded DrivePolicy startup `KeyError: 'speed'` and
separates an additional reproduced reactivation defect from missing historical
producer evidence. Unexpected traffic-stop release is not solved: the original
actor/conflict is absent; skipping hold by heuristic type failed a preserved
native-crossing safety regression and was rejected. The first compact stop cause
is now retained by the existing receipt. GPS disappearance while moving is not safely identifiable as
arrival: a stable producer-owned destination position and completion/cancellation
lifecycle are missing. The nominal signed acceleration representation is not
measured load-adaptive regulation. Additional recovery-slew candidates were
rejected; producer-timed leader acceleration and verified complete ego/trailer
swept AEB remain blocked. No new drive, deployment or broad sensor rewrite is
requested. The complete user request remains open in those explicit scopes.

## Oct 13 ACC departure and plugin lifecycle

[PHASE7_ACC_DEPARTURE_AND_PLUGIN_LIFECYCLE_20261013.md](PHASE7_ACC_DEPARTURE_AND_PLUGIN_LIFECYCLE_20261013.md)
fixes reproduced oriented-body departure and validated-geometry dependency
reset defects, plus silent KeyError exit/restart storms and shutdown spawning.
Historical actor boxes/source slot and DrivePolicy exception were not retained;
these exact historical branches are not declared proved. ACC 1.2.0 preserves
the approved 5 m stop and signal lifecycle. A MonoCruise-inspired relative-speed
candidate was rejected after cut-in/steady-state regressions. Producer freshness,
coverage, calibrated physical acceleration/jerk and verified stop-and-go remain
open. No deployment or new drive is requested; game confirmation remains separate.

## Authorized five-metre planning reference — 13 October

[PHASE7_FIVE_METRE_STOP_REFERENCE_20261013.md](PHASE7_FIVE_METRE_STOP_REFERENCE_20261013.md)
implements the user's explicit 8 -> 5 m SDK-reference policy after paired
production-path offline verification. No new controller, line calibration,
parking operation or ACC version is introduced. The historical 6+2 m baselines
below remain historical evidence; their reserve is superseded for new prepared
signal passages. Exact painted-line/bumper clearance remains unmeasured and
the existing stationary +2.3377 m calibration is not activated. Conservative
body clearance is not certified for all trucks by copying ETS2LA's heuristic.
Full user pytest PASS and separate deployment approval remain gates; no game
verification is claimed.

## ETS2LA stop-target source comparison

[PHASE7_ETS2LA_STOP_REFERENCE_COMPARISON_20261012.md](PHASE7_ETS2LA_STOP_REFERENCE_COMPARISON_20261012.md)
verifies a concrete same-entry target difference: local ETS2LA Python subtracts
5 m; UltraPilot subtracts 6+2 m, placing its reference target 3 m earlier.
This is separate from regulator residual and does not measure bumper/painted-line
clearance. No blind global reserve reduction, new acceleration controller or
runtime change was made; a scoped equivalent target remains an implementation
candidate requiring the unchanged directed/safety contracts.

## Oct 12 moving-green and non-signal brake lifecycle

[PHASE7_GREEN_APPROACH_AND_TRAFFIC_HOLD_20261012.md](PHASE7_GREEN_APPROACH_AND_TRAFFIC_HOLD_20261012.md)
corrects the reproduced moving-green ratio-zero deadlock and missing physical
hold ownership for forward-started Traffic braking without a semaphore. Existing
bounded launch, actual brake chain, first-fault evidence and safety gates remain.
ACC stays 1.1.9; no new plugin version, DLL, controller or geometry change.
Actual obstacle clearance remains unavailable, so disappearance cannot restart
a stopped vehicle. The early crossing actor poses needed to adjudicate abrupt
braking and the bound bumper/painted-line geometry remain missing. Exact stop
distance and the legitimacy of that crossing prediction are not closed; no
candidate deployment or GAME VERIFIED claim is made.

## Terminal approach to the unchanged planning target

[PHASE7_STOP_AND_MANEUVER_INDICATORS_20261012.md](PHASE7_STOP_AND_MANEUVER_INDICATORS_20261012.md)
adds the reproduced positive-envelope Traffic/ACC ownership and premature hold
correction, with unused positive integral discarded only for qualified signal
coast. Final targeted checks pass; the final full suite belongs to the user.
Default/delayed model residuals improve, but idle-drive sensitivity does not meet
the relative no-regression criterion. Exact convergence and painted-line/front
geometry are still open; no candidate deployment or game PASS is claimed.
Selected-exit indicator metadata is also offline checked on actual placed topology.

The full-suite first-brake regression was corrected on 12 October: preserve
the calculated first positive slow-terminal brake and stationary request while
retaining Engine ownership. All 2,401 tests and 1,592 subtests passed; no deployment
or physical stop-line calibration is implied by that result.

[PHASE7_TERMINAL_APPROACH_20261012.md](PHASE7_TERMINAL_APPROACH_20261012.md)
removes a reproduced premature full-brake discontinuity at low speed while
the qualified stop envelope remains positive. Continuous acknowledged holding,
green restart and 6 m + 2 m margins remain. The closed model still has a stopping
residual; exact convergence and the unretained cause of the historical 2.5514 m
gap are not closed. Broader candidate changes were discarded for pedal/jerk or
standstill regressions. Physical painted-line/front geometry remains a separate
limitation; the stationary +2.3377 m calibration is not activated. No game
acceptance or candidate deployment is claimed.

## Oct 11 traffic, indicators and unresolved physical geometry

[PHASE7_JOINT_TRAFFIC_AND_INDICATORS_20261011.md](PHASE7_JOINT_TRAFFIC_AND_INDICATORS_20261011.md)
records the receipt-matched destination deployment and the separate current
candidate ACC 1.1.8 / TurnSignals 1.0.1. Supported witnessed lead departure,
between-producer-tick coasting, omitted native trailers and live indicator
enable/ownership have production-flow offline reproductions. Missing, stale,
duplicate or reassigned actor observations still cannot clear an acquired loss;
no traffic coverage or safe-gap proof is invented. No candidate deployment or
game acceptance has occurred.

Still blocking complete roundabout collision resolution: original collision
actor trajectories and reliable producer-timed coverage/motion/ego truck-trailer
body envelopes for the richer existing maneuver contract. Still blocking exact
semaphore front-to-line adjustment: reference-to-front geometry and physical
stop-line position. Recorded 2.5514 m is SDK reference to a derived target;
existing 6 m + 2 m allowances occur once. No arbitrary shortening was made.

[PHASE7_STOP_LINE_GEOMETRY_20261011.md](PHASE7_STOP_LINE_GEOMETRY_20261011.md)
exhausts the current SDK, full active prefab cache, external body catalog and
pinned native source. The catalog is empty, ego boxes are not transported and
no painted-line coordinates are available. Straight/curved production-path
models preserve hold/restart; they do not fix or verify a 1–2 m bumper gap.
The exact remaining prerequisite is a metric front-bumper/painted-line geometry
record bound to truck configuration, SDK pose and placed dataset/passage.
The conservative fallback is unchanged; this is not a completed stopping-gap
repair or a reason to deploy the unrelated pending traffic candidate.

Eight old significant-event files fill the existing quota; the originals and
log are preserved. Future event capture requires separately authorized archival,
not silent deletion. The detailed incident has only 0.264 s and the 30-second
summary is explicitly incomplete. User full pytest and separately authorized
consistent runtime deployment remain prerequisites to game confirmation. No
new drive or MonoCruise implementation is requested in this task.

## Oct 11 GPS completion / unresolved approach evidence

[PHASE7_DESTINATION_AND_APPROACH_REVIEW_20261011.md](PHASE7_DESTINATION_AND_APPROACH_REVIEW_20261011.md)
records the positive-distance route retention/common-stop correction and normal
physical release in both automatic modes. Zero/removal is not inferred arrival.
The photographed front/painted-line relation and second-roundabout winning brake
are not retained; no reserve/geometry/steering adjustment is guessed. The existing
eight-file significant-event quota is full, blocking new event capture until
separately authorized archival. No originals, installation or game are changed.
Current candidate ACC 1.1.7 / DrivePolicy 1.1.3 / Autopilot 1.3.4 is offline only;
full pytest, authorized deployment and game acceptance remain separate gates.
MonoCruise is not implemented here.

## Dojazd na semafor a uvoľnenie počas pohybu – 10. 10. 2026

[PHASE7_SIGNAL_APPROACH_TIMING_20261010.md](PHASE7_SIGNAL_APPROACH_TIMING_20261010.md)
dokladá zotrvanie súvislej brzdy aj po zelenej pri približne 3,3 km/h. Engine
uvoľňoval semaforový dôvod iba pri státí; kandidát ho po potvrdených nových
zelených snímkach uvoľňuje aj za pohybu a obnovuje aktuálny platný povel.
Pôvodný odpočet a oba žlté stavy sa zachovávajú. Končiaca kvalifikovaná zelená
používa spoločný zastavovací profil, bez nového regulátora alebo novej DLL.

Offline model na reálnom prefabe: 48 behov, oba automatické režimy, 20/35/50 km/h,
žiadny súbeh kladných fyzických pedálov ani prejdenie vstupu na červenú. Nejde
o herné potvrdenie. Časť jerk metrík sa nezlepšila a report to uvádza.
Otvorené: chýbajúci začiatok historického skorého dojazdu/odpočet, fyzická spotreba
SDK brzdy a stop čiara/rozmery. Samostatný pretek starej traffic aktivácie po
manuálnom vypnutí a novom N je teraz opravený offline v
[PHASE7_REACTIVATION_TRAFFIC_20261010.md](PHASE7_REACTIVATION_TRAFFIC_20261010.md):
rovnaká autorita okrem aktivácie čaká v pôvodnom pevnom limite bez plynu,
starý packet sa nevykoná, nové údaje pokračujú bez ďalšieho N. Historicky
odmietnutý epoch bol 8145579392300; presné IPC poradie ani herný účinok novej
opravy nie sú potvrdené. Celý životný cyklus preto nie je označený GAME VERIFIED.
Pred nasadením zostáva celá sada používateľa a samostatný súhlas; teraz sa
ďalšia jazda nežiada.

## Natívny smer semafora na mieste incidentu – 10. 10. 2026

[PHASE7_SIGNAL_NATIVE_DIRECTION_20261010.md](PHASE7_SIGNAL_NATIVE_DIRECTION_20261010.md)
dokladá chybu dodatočného otočenia natívneho smeru o 180°. Pôvodný PPD objekt
skupiny 3 sa zhoduje s uloženou zelenou hlavou ID 3 na 0,01578 mm a reguluje
opačný prejazd; naša trasa používa skupinu 1. Opravené je scoped priradenie aj
hodnotenie neistého smeru, bez premapovania ID, novej DLL či vydania pluginu.
Vzdialenostná a packet-refresh oprava zostávajú. Produkčný offline model
v oboch režimoch dokončí opakované červená–držanie–zelená–rozjazd cykly.

Otvorené zostávajú historicky neuložené owner/kind údaje celej natívnej snímky,
živá prítomnosť vlastnej hlavy skupiny 1, účinok súvislej SDK brzdy v hre,
držanie na svahu a presná stop čiara. PPD objekty bez vehicle navCurve väzby
sa bez znalosti runtime druhu nevyhlasujú za cudzie. Legacy unscoped heuristika
nie je týmto overená. Celé herné miesto preto nie je označené GAME VERIFIED.
Ďalšia jazda sa teraz nežiada; pred nasadením zostáva používateľova celá sada
a samostatný súhlas s konzistentným balíkom.

## Dokončenie smerovaného semafora a traffic autority – 9. 10. 2026

[PHASE7_SIGNAL_AND_TRAFFIC_COMPLETION_20261009.md](PHASE7_SIGNAL_AND_TRAFFIC_COMPLETION_20261009.md)
uzatvára reprodukované softvérové chyby offline: natívne vlastníctvo lampy namiesto
zámeny jej výšky za vrstvu vozovky, neplatný display traffic používaný na brzdu,
brzdenie po predĺžení osi kabíny mimo skutočnej zakrivenej trasy a prudký nábeh
potvrdenej brzdy pri státí. Podporované opakované červená–držanie–zelená cykly
prešli na troch reálnych prefaboch v oboch režimoch. Kandidát Autopilot 1.3.3,
Map 1.1.1 a DLL 1.59.3-up-signal-scope sa nenasadili; inštalácia stále 1.3.1.

Existujúci PedalJournal automaticky zapečatí významnú udalosť aj pred vypnutím,
s jedným čakajúcim slotom, štyrmi exportmi za minútu a diskovou kvótou 8 súborov /
16 MiB. Zaznamenáva straty a neúplnosť; staré dáta nemaže. Nevyžaduje armovanie.
Steering a všeobecné komfortné benchmarky zostávajú numericky nezmenené.

Presná historická hlava a pôvodný skorší actor/TTC stále chýbajú: report
neprisudzuje týmto incidentom syntetické vstupy. Neoverené zostávajú živé
prefab UID/node/origin/group priradenie, úplné pokrytie križovatiek, spotreba
súvislej SDK brzdy, držanie na svahu a geometria predku/stop čiary. Nový scoped
kontrakt umožňuje podporovaný tok, ale nenahrádza tieto herné dôkazy.
Starší report BLOCKED sa tým dopĺňa o hotové offline opravy, nie o tvrdenie
vyriešenej historickej jazdy. Ďalšia jazda sa teraz nežiada; najbližšia brána je
celá pytest sada používateľa, potom samostatne schválené konzistentné nasadenie.

## Prehliadnutá červená a brzdenie pred druhým objazdom – 9. 10. 2026

[PHASE7_SIGNAL_COVERAGE_AND_BRAKE_REVIEW_20261009.md](PHASE7_SIGNAL_COVERAGE_AND_BRAKE_REVIEW_20261009.md)
oddeľuje nové dve aktivácie zostavy 1.3.1 od starších jázd. Opravené offline:
tiché pokračovanie pri nepriradenej živej hlave, potlačenie jej čerstvej farby
v HUD a zachovanie silnejšieho núdzového zásahu pri odovzdaní. Kandidát 1.3.2
sa nenasadil. Nepriradená hlava vyžaduje prevzatie, nie vymyslenú červenú či
potvrdený voľný prejazd. Známy uzamknutý semafor a súvislá brzda zostávajú.

Celé vyriešenie incidentov zostáva BLOCKED: historická surová hlava a
spotrebovaná selekcia pri prehliadnutej červenej nie sú uložené; skorší brzdný
impulz je mimo zachovanej 30-sekundovej pedálovej histórie. Jeho pôvodný
traffic brake_basis/actor/TTC a SDK posted speed limit sa nedajú obnoviť.
Pôvodná pozorovaná geometria sa dala analyticky obnoviť; jej profil pri danom
úseku nepotvrdzuje skok na 20 km/h. Regulátor ani profil sa naslepo nemenili.
Herné pokrytie semaforov, presná stop čiara a HUD skok zostávajú neoverené.
Nová jazda sa v tejto úlohe nežiada a kandidát nie je označený za herne hotový.

## Kvalifikácia semafora, dojazd a observer – 8. 10. 2026 večer

[PHASE7_SIGNAL_APPROACH_CONSISTENCY_20261008.md](PHASE7_SIGNAL_APPROACH_CONSISTENCY_20261008.md)
dokladá reprodukcie na oboch skutočných prefabových umiestneniach večernej
jazdy, nesprávne naviazanie bežnej ACC brzdy na budúce zastavenie, zamknutie
slabej dojazdovej brzdy, pretek pri dopisovaní game.log a zastaraný súhrn
pripravenosti pri okamžitom ďalšom N. Opravy sú overené offline; nie sú nasadené.
Strata už kvalifikovanej hlavy naďalej vyžaduje bezpečné čakanie a rovnakú
čerstvú zelenú. Volant a všeobecný pozdĺžny benchmark sú numericky nezmenené.

Otvorené zostávajú namaľovaná stop čiara a geometria predku, účinok súvislého
SDK brzdenia a držania na svahu, presné historické bajty pri čítaní game.log,
pôvodný odmietnutý súhrn navigačnej pripravenosti a používateľom hlásený pád
bez aktuálneho tracebacku. Silnejšie držanie v modeli zvyšuje jerk tesne pri
státí; komfort v ETS2 sa preto nepovažuje za potvrdený. Samostatné bezpečné
držanie pri novej aktivácii už stojaceho vozidla v jednoduchej automatike
ostáva obmedzením. Ďalšia jazda sa v tejto úlohe nežiada.

## Spoločný semaforový tok – 8. 10. 2026

[PHASE7_SIGNAL_STOP_LIFECYCLE_20261008.md](PHASE7_SIGNAL_STOP_LIFECYCLE_20261008.md)
dokladá opravu prerušenia plánovanej brzdy bez živého signal locku a obnovu
väzby po návrate toho istého autorovaného semafora. Offline model znížil
prepnutia plyn/brzda z 13 na dve očakávané zmeny; normálna červená,
volant a pozdĺžny komfort sú numericky nezmenené. Nepotvrdené zostávajú
účinky SDK v hre, príčina pohybu pri držaní o 17:28:56 a pôvodný odmietnutý
ACC vstup o 17:29:00, ktorý export neuchoval. Chýbajúci živý semafor ani
zmiznutý aktér nepovoľujú rozjazd. Existujúce obmedzenie bezpečného držania
pri novej aktivácii zo státia ostáva; ďalšia jazda sa teraz nežiada.

## Spoločný brzdový tok a krížiaca premávka – 6. 10. 2026

[PHASE7_JOINT_STOP_TRAFFIC_20261006.md](PHASE7_JOINT_STOP_TRAFFIC_20261006.md)
dokladá reprodukovaný konflikt prvého plánovaného brzdenia pri čerstvom gear=0
so staršou potvrdenou históriou. Spoločný ohraničený stav povoľuje iba brzdu,
nie plyn; skutočný zápis vytvorí existujúce súvislé držanie. Aktuálny brzdový
reťazec sa preverí pred zastaraným deadline prechodnej nuly. Semafor sa uzamkne
aj pri začatí brzdenia na žltú. Tri cykly červená–čakanie–zelená–rozjazd prešli
cez produkčné komponenty offline bez ďalšieho N a bez ručnej brzdy.

Nový ochranný výpočet skúma všetkých zachytených aktérov na smerovanej trase
a nezabudne druhé auto po odstránení prvého. Nie je to potvrdenie voľného
priechodu: legacy traffic nemá producentov čas/generáciu, úplné pokrytie ani
doloženú históriu konfliktov. Kolízny problém preto zostáva NOT VERIFIED;
spoľahlivé autonómne prijatie medzery na objazde tým nie je hotové.

Opravené SDK čítanie odmieta čiastočný obraz a pri zistenom prekrývaní kópie
uchová poslednú prijatú snímku iba s pôvodným časom, najviac v existujúcom
500 ms limite. Pauza a skutočný výpadok naďalej bezpečne odoberú autoritu.
Historický výpadok 19:26:54 neobsahuje pôvodný pause/active/read-failure stav;
posledný Map tick trval 27,06 ms, takže blokovanie Mapu nie je preukázané.
Presný pôvod piatich historických prepnutí pedálov tiež nie je doložený.

Volant a pozdĺžny komfort sú v príslušných benchmarkoch numericky nezmenené.
Autopilot má 1.2.2; nezmenené pluginy nedostali nové verzie. Zmeny sa
nenasadili; celá sada používateľa a herná spotreba súvislej SDK brzdy zostávajú
otvorené. Samostatné bezpečné držanie pri novej aktivácii už stojaceho vozidla
na červenú ostáva predošlým blokátorom. Ďalšia jazda sa teraz nežiada.

## Prefabové priradenie semafora a odvodený cieľ – 6. 10. 2026

[PHASE7_PREFAB_SIGNAL_BINDING_20261006.md](PHASE7_PREFAB_SIGNAL_BINDING_20261006.md)
dokladá prenos autorovaného semaphoreId, smerovaný vstup do celého prejazdu,
priestorovo a výškovo ohraničené priradenie živého ID a včasný brzdný profil.
Chýbajúca väzba pri známom vstupe už nesmie byť nahradená nepotvrdenou zelenou.
Súvislá kladná brzda môže počas platného dojazdu klesať; čakanie ju nepreruší.
Prípustný tok pokračuje po potvrdenej zelenej bez ďalšieho N a bez ručnej brzdy.

Cieľ je odvodený, nie namaľovaná stop čiara. Rezerva predku 6 m nie je meraná
geometria ani záruka pre ľubovoľný mod. Modelové dostatočné nájazdy 20/35/50 km/h
prešli; krátky 30 m nájazd z 50 km/h v použitom modeli prekročil vstup a následný
automatický rozjazd ostal zablokovaný. Predošlý samostatný problém držania pri
aktivácii už stojaceho vozidla na červenú sa touto úlohou nerieši.

Nejednoznačné skupiny, chýbajúce údaje, živé priradenie PPD/DLL a spotreba SDK
brzdy zostávajú otvorenými hranicami podpory. Tri zaznamenané skutočné prefabové
reťazce boli rekonštruované bez zmeny geometrie; historické hlavy/farby a pedálové
väzby však v starej jazde chýbajú. Nové zmeny nie sú nasadené ani herne potvrdené.
Celú sadu spustí používateľ. Ďalšia jazda sa teraz nežiada.

## Kandidát ACC, nájazd a uzamknutý semafor – 5. 10. 2026

[PHASE7_TRAFFIC_APPROACH_AND_SIGNAL_20261005.md](PHASE7_TRAFFIC_APPROACH_AND_SIGNAL_20261005.md)
dokladá opravu získania pasívneho/neúčinného ACC kandidáta, výberu vzdialenej
ostrejšej zákruty namiesto bližšieho účinného obmedzenia a straty uzamknutého
semafora po prejdení SDK bodom aj pri odovzdaní rozjazdu. Offline reprodukcie
prešli; volant a ochranné ACC scenáre zostali numericky nezmenené.

Inštalácia pri audite obsahovo zodpovedala vstupnému 9350be7 po normalizácii
LF/CRLF. Nové zmeny sa nenasadili. Historické ID a účinnosť ACC kandidáta
20:29:05 neboli uložené; jeho vek a deadline dokazujú, že nešlo o expiráciu.
Presné fyzické vjazdy oboch používateľom označených objazdov nie sú samostatne
identifikované. Existujúci cieľ 35 km/h ostáva iba na identifikovaných objazdoch.

Zdroj semafora neposkytuje potvrdenú stop čiaru ani vzdialenosť predku vozidla
od SDK referencie. Zastavenie pred fyzickou čiarou preto zostáva neoverené;
poloha hlavy sa za čiaru nevydáva. Strata získaného ochranného cieľa stále
vyžaduje bezpečné odovzdanie, keď zdroj nevie potvrdiť voľnú cestu. Samostatné
držanie pri novej aktivácii zo státia ostáva predchádzajúcim blokátorom.

V modeli sa vjazd spomalil včas, ale jerk pri jitteri nie je všade lepší.
Komfort, živá spotreba SDK brzdy a úplný herný výsledok ostávajú otvorené.
Celú sadu spustí používateľ; ďalšia jazda sa teraz nežiada.

## Odovzdávanie pozdĺžnych rozhodnutí – 5. 10. 2026

[PHASE7_LONGITUDINAL_HANDOFF_20261005.md](PHASE7_LONGITUDINAL_HANDOFF_20261005.md)
dokladá spoločnú opravu skladania účinných lease, pôvod deadline a ohraničené
odovzdanie bez pohonu pri čakaní na nové rozhodnutie. Posledná kontrola ostáva
tesne pred fyzickým zápisom; starý povel ani čas sa neobnovujú. Existujúci
potvrdený brzdový reťazec sa nepreruší ani počas spomaľovania pred státím.
Šesť 75-sekundových offline behov s nezávislými cadence a modelovaným IPC
prešlo bez technickej straty autority; nejde o dôkaz živého časovania ETS2.
Inštalovaných osem kontrolovaných súborov obsahovo zodpovedalo vstupnému
b5a7aa3, takže aktuálny incident nevysvetľuje skorší nesúlad nasadenia.
Historický producent konkrétneho deadline 21:02:40 nebol uložený a nedá sa
jednoznačne určiť. Nové pôvodné lease údaje ostávajú v existujúcom zberači.

Celá sada používateľa a herný účinok novej opravy zostávajú otvorené; nič sa
nenasadilo. Blokátor samostatného držania pri zapnutí zo státia ostáva, rovnako
ako nepotvrdená spotreba SDK brzdy/hill hold a limity legacy traffic zdroja.
Staršie reporty nižšie dokladujú svoje zostavy, nie úplné vyriešenie neskorších
opakovaných expirácií. Ďalšia jazda sa teraz nežiada.

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

## Obnova packetov a technické vypnutia 9. 10.

[PHASE7_PACKET_REFRESH_RELIABILITY_20261010.md](PHASE7_PACKET_REFRESH_RELIABILITY_20261010.md)
oddeľuje opravené opakované rozbaľovanie geometrie, prefabovú enumeráciu a
pretek pri ohraničenom nulovom pozdĺžnom odovzdaní od zatiaľ nevysvetlenej
vnútornej pauzy Mapu 620/477 ms. Offline integračné scenáre a benchmarky sú
doložené, no pôvodný vnútorný krok nie je historicky preukázaný. Chýbajúce
časovanie jednotlivých operácií referencie sa teraz ukladá v existujúcom exporte;
nevznikol nový zberač ani požiadavka na ďalšiu jazdu. Limit 500 ms a skutočné
bezpečnostné zastavenie zostávajú. Žiadna zmena sa automaticky nenasadila.

Po používateľovej celej sade a osobitne schválenom nasadení zostáva akceptácia
aspoň 5 km kontrolovanej jazdy vrátane semaforového zastavenia a pokračovania.
Táto akceptácia zatiaľ neprešla; report nevyhlasuje problém úplne vyriešený.

Pokračovanie dokladá štvrtú opravu: Map už pri obsadenom evidence workeri
nečíta dva veľké vstupy, ktoré by worker zahodil. História od 221cc90 odlišuje
novšie evidence čítania a opakovanú lokalizáciu od staršieho prefabového DFS.
Tri párové merania so súbežnými exportmi zlepšili p95 obnovy packetov, ale
maximum veku pri zápise sa zhoršilo (179,8 → 192,4 ms); širšia spoľahlivosť
preto zostáva nepreukázaná. Historické vnútorné pauzy 620/477 ms nemajú
dostatočné pôvodné časové značky na jednoznačné pripísanie operácii či GC.

Úspešná jazda už vie v existujúcom combined, passive a dense exporte uchovať
časovanie referencie a presne sekvenovaný predchádzajúci dokončený Map tick,
vrátane práce po publikovaní a medzery pred ďalším tickom. Izolovaný export
cez skutočný vykonávač a Engine prešiel bez automatického vypnutia. OFFLINE
VERIFIED sa vzťahuje na štyri reprodukované chyby a kontrakt exportu;
GAME VERIFIED na aktuálnom kandidátovi zatiaľ chýba. Verzie sa nemenili,
inštalácia ani starý checkout neboli upravené.

## Traffic availability incident — 10 October

[PHASE7_TRAFFIC_AVAILABILITY_20261010.md](PHASE7_TRAFFIC_AVAILABILITY_20261010.md)
records the shared envelope/usability correction, explicit required-demand and
signal-coverage validation, bounded source-ID diagnostics and first-fault export
preservation. The actual first AP comparison is missing; the earlier optional
traffic packet accompanied a successful write and is not substituted for it.
Original actor rows/pointers/common generation were not retained, so the native
duplicate-ID cause is not historically established. No new drive is requested.
Core-only changes are offline verified; no plugin version or DLL changed and
nothing was deployed. Traffic publisher freshness, actor lane/coverage proof and
this correction's game result remain unverified. The earlier frozen packet-refresh
bundle does not include the new four-file core correction.

## Distance-aware unassigned signal incident — 10 October evening

[PHASE7_SIGNAL_DISTANCE_CONTRACT_20261010.md](PHASE7_SIGNAL_DISTANCE_CONTRACT_20261010.md)
documents the actual green ID 3 / 119.739 m directed-entry premature takeover.
The candidate uses bounded distance-aware uncertainty, the shared existing
stopping envelope and original signal lease. Four deployed-selector
counterexamples fail; qualified stop/hold/green/restart remains supported in
both automatics. ACC 1.1.5 and DrivePolicy 1.1.1 consume that same constraint;
Autopilot/Map/DLL versions are unchanged. No deployment or game result.

The original native owner fields and full head array were not retained; native
instance ID 3 is not proven to be authored control group 1 on the reconstructed
passage. Complete coverage at that place remains NOT VERIFIED. A later stop
before the conflict is still required if qualification cannot be established;
moving the early intervention is not completion of signal coverage. The
existing bounded incident receipt now retains owner, compared map input and
derived-target/reserve fields without arming or new SDK/IPC reads. No new drive
is requested, and unknown color/disappearance is never automatic clearance.

## Roundabout traffic incident — 14 October

[PHASE7_ROUNDABOUT_TRAFFIC_INCIDENT_20261014.md](PHASE7_ROUNDABOUT_TRAFFIC_INCIDENT_20261014.md)
records the acquisition-timed crossing/terminal-stop correction, current-frame
departure continuity, inactive planner/ACC speech lifecycle and priority first
evidence/quota preservation. Existing signals, 5 m offset, green restart,
indicators, geometry, regulators and native DLL are preserved. No deployment.
Historical initiating actor poses and the first emergency's decisive input were
not retained, so the whole historical classification remains NOT VERIFIED.
Normal significant-event storage is still full; originals require separately
approved archival, while the existing automatic fault export retains priority.
New game behavior is unverified. The cancelled GPS-arrival task is not reopened.
