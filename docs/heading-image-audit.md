# Szerepattribútum nélküli képes üzenetek vizsgálati jelentése

Ellenőrzés dátuma: 2026. október 3. Javított alkalmazásverzió: `5.16`. Kiinduló commit: `5551bfd` (`v5.14`). Az előző helyi `5.15` javítás és ellenőrzés az [egymás utáni képküldések jelentésében](second-image-audit.md) szerepel.

## A hiba oka

A friss `5.15` naplóban az első kép 13:44:32-kor indult el, a csatolás és a beküldés 13:44:36-kor sikeres volt. 13:44:42-kor a válasz már elkészült és stabil volt, de a felismert felhasználói üzenetek száma továbbra is egy maradt. A `request_user_unbound` elutasítás miatt a fordítás nem lett kész eredményként mentve. A 13:45:17-kor és 13:45:40-kor kivágott további képek az első válaszra váró művelet mögött sorban maradtak.

A normál böngészőprofilból végzett helyi, port nélküli Qt-vizsgálat egy már meglévő beszélgetés technikai DOM-szerkezetét olvasta ki. Az oldalon két képes felhasználói üzenet volt. Egyiknél sem szerepelt `data-conversation-role="user"` vagy `data-message-author-role="user"` attribútum. Az egyetlen régi szöveges buborék miatt az előző felismerő csak egy felhasználói üzenetet talált.

A képes üzenet külső konténere egy `h4.sr-only` elemet tartalmaz a teljes `You said:` felirattal. A kép a fejléc testvérágán álló, `data-chatgpt-search-unit-key` és `data-chatgpt-search-message-ids` attribútumokkal rendelkező belső konténerben található, egy `role="button"` képnézegető alatt. A szerep tehát a saját UI-fejlécből, az üzenet stabil azonosítója a belső keresőegységből olvasható ki.

Az élő szerkezetet utánzó új Qt/Chromium-regresszió a még eredeti `5.15` automatizálással elbukott: egy felhasználói üzenetet és két assistant üzenetet talált, miközben a kész új válasz nem kapcsolódott az elküldött képhez. Az előző javítás explicit felhasználói szerepjelhez tartozó kattintható képet tesztelt; az élő oldal szerepattribútum nélküli változatát akkor még nem igazolta.

## Javított működés

- A felismerő a saját üzenetkonténer `h1`–`h6`, `sr-only` fejlécének teljes, ismert UI-feliratát is szerepbizonyítékként kezeli. A stabil azonosító a saját belső üzenetegységből származik.
- A fejlécet csak a hozzá tartozó üzenetegység örökölheti. Közös user-assistant konténer, eltérő szerepjel, rejtett tartalom, idézet, markdown, kód, composer és kezelőelem nem adhat felhasználói szerepbizonyítékot.
- Az aktuális kéréshez kötés, a beküldés előtti válaszpillanatkép, a DOM-sorrend és a kész válasz ellenőrzése megmarad. Az egyező válaszszöveg önmagában nem igazol új eredményt.
- A tartalommentes válaszállapot-naplóban a fejlécből felismert szerep `user_role_source=heading_role` értékkel szerepel.
- Az alkalmazásönteszt három egymást követő, szövegbuborék és szerepattribútum nélküli képkérést, majd egy szöveges kérést futtat. Mindegyik azonos kész válaszszöveget kap, de külön kérésazonosítóval, új befejezési állapottal és aktuális mentett eredménnyel kell zárulnia.

## Élő szerkezeti összehasonlítás

A végleges automatizálást és az eredeti, csomagolt `5.15` JavaScript-assetet ugyanazon már betöltött, bejelentkezett DOM-on, új üzenet küldése nélkül is összehasonlítottuk. Az automatikus composer-helyreállító figyelő és DOM-pulzálás ebben az olvasópróbában ki volt kapcsolva. Az oldal két képes üzenetet tartalmazott.

| Technikai állapot | Korábbi `5.15` | Javított `5.16` |
| --- | --- | --- |
| Felismert felhasználói üzenetek | 1 | 3 |
| Felismert assistant üzenetek | 3 | 3 |
| Legutolsó felhasználói szerep forrása | `user_bubble` | `heading_role` |
| Legutolsó felhasználói üzenet stabil azonosítója rendelkezésre áll | Igen | Igen |

A régi olvasó az utolsó választ is az egyetlen felismert, korábbi szöveges userhez rendelte. A javított olvasó már a saját legutolsó képes usert találja meg. Ez a meglévő DOM felismerését igazolja; a kérés újdonságát és befejeződését külön, teljes kézbesítési regresszió ellenőrzi.

A csomagolt eredeti `5.15` asset külön Qt-reprodukciója az új élő mintán szintén a várt időtúllépést és `request_user_unbound` állapotot adta. A tesztharness miatt csak a JavaScript verziócímkéje kapott memóriabeli egyeztetést; a felismerő és kézbesítő kód nem változott. Az eredeti asset SHA-256 értéke `9567c36ff528641d812f75c0a84bebd16b4ef2e5f6bf561611dea031c314e05c`, a végleges javított asseté `9a9ba7e3f9e236a7426b1f0ad3381d027aff40f45a84b96dced4cf9431b80edd`.

## Ellenőrzés

| Ellenőrzés | Eredmény |
| --- | --- |
| Teljes Python regresszió | 321/321 sikeres, 86,841 másodperc |
| JavaScript regresszió | 55/55 sikeres |
| Modern DOM valódi Qt/Chromium motorral | 17/17 sikeres; a teljes Python-csomag része; 18 elutasítandó UI-fejléc-változat külön ellenőrizve |
| Natív callback, poll és watchdog | 11/11 sikeres; a teljes Python-csomag része |
| Diagnosztikai háttéríró és naplóolvasó | 25/25 sikeres; a teljes Python-csomag része; a `heading_role` érték az író, olvasó és formázó között is megmarad |
| Forrásból futó teljes alkalmazáspróba | 11/11 sikeres; a teljes Python-csomag része; három képes és egy szöveges kérés azonos válasszal, új kész eredményként mentve |
| Végleges EXE forrás- és futtatókörnyezet-egyezése | 34/34 sikeres |
| Végleges EXE offline önteszt | 12/12 sikeres, 55 gyorsfordítási ciklus, három modern képkérés és egy modern szöveges kérés |
| Csomagolt RapidOCR és Windows OCR | Mindkettő pontosan a szintetikus `Hello gamer` szöveget ismerte fel |
| Függőség- és szintaxisellenőrzés | `pip check`, Python-fordítás, JavaScript-szintaxis és `git diff --check` sikeres |

A negatív Qt-mátrix a nem valódi fejlécet, hiányzó `sr-only` osztályt, pontatlan feliratot, saját üzenethatár hiányát, üres azonosítót, kereshető tartalomba tett fejlécet, explicit assistant kört, vegyes szerepet, rejtett fejlécet és képet, rejtett szülőt, avatart, menüt, toolbart, idézetet, kódot és markdown tartalmat vizsgálja. A JavaScript-mátrix a több saját tartalomág miatti kétértelműséget és az üzenettartalomban idézett assistant fejlécet is kizárja. Külön regresszió ellenőrzi a közös külső message-ID melletti saját azonosságot és a régi assistant újrarajzolásának elutasítását.

A végleges EXE mérete `381569817` bájt, SHA-256 ellenőrzőösszege: `e603c8c1fab98651a086344beaf8f80d1fae04a2bef199275890411b37e7b84e`. A helyi telepített fájl `C:\Saját\Alkalmazások\Gamer-Translator-v5.16.exe`, ugyanazzal az ellenőrzőösszeggel. A csomagolt önteszt 65,344 másodperc alatt zárult. A tartalommentes ellenőrzési adatok az [ellenőrzési állományban](evidence/heading-image-checks.json) találhatók.

A telepített `5.16` normál profillal elindult. A böngészőbetöltés és az automatizálás beillesztése sikeres, az indulás alatt nulla `ERROR` vagy `CRITICAL` esemény keletkezett. Ez az indulást igazolja; új bejelentkezett képkérés sikerét nem.

## Az ellenőrzés határai

A bejelentkezett szerkezeti vizsgálat már meglévő beszélgetést olvasott, új ChatGPT-üzenetet nem küldött. A kiolvasott adatok kizárólag attribútumnevek, statikus szerepértékek, darabszámok és állapotjelzők; beszélgetésszöveg, üzenetazonosító, képtartalom, webcím és profiladat nem kerül az ellenőrzési állományba.

A teljes képküldési regressziók elkülönített profillal, szintetikus DOM-mintával, memóriavágólappal és valódi Qt/Chromium motorral futnak. Új bejelentkezett képkérés és játék közbeni gyorsbillentyűhasználat nem része az automatikus próbának.
