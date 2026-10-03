# Egymás utáni képküldések vizsgálati jelentése

Ellenőrzés dátuma: 2026. október 3. Javított alkalmazásverzió: `5.15`. Kiinduló commit: `5551bfd` (`v5.14`).

A későbbi élő `5.15` hiba és a szerepattribútum nélküli képes üzenetek pontos DOM-változatának javítása a [szerepfejlécek vizsgálati jelentésében](heading-image-audit.md) szerepel. Az alábbi eredmények az előző helyi `5.15` ellenőrzést rögzítik.

## A hiba oka

A friss `5.14` naplóban az első kép 13:12:32-kor bekerült a feldolgozásba. A csatolás és a beküldés 13:12:36-kor visszaigazolást kapott, az új, 72 karakteres válasz pedig 13:12:41-kor már befejezett és stabil volt. A felismert felhasználói üzenetek száma közben egy maradt. A `request_user_unbound` elutasítás miatt a válasz nem lett kész fordításként mentve, és a háromperces válaszvárás 13:15:36-kor időtúllépéssel zárult.

A második kép 13:12:52-kor bekerült a sorba, majd 163,883 másodperc várakozás után indult el. A csatolása és beküldése 13:15:42-kor sikeres volt. A napló alapján a kivágás, a vágólapengedély és a kép átadása működött; a második kép késését az első kérés válaszvárása okozta. A második kérés új válasza 13:15:47-re 172 karakterig jutott, de ez sem kapcsolódott felismert új felhasználói üzenethez.

13:15:52-kor egy JavaScript-eredmény lekérdezése túllépte az öt másodperces callback-határt. A Python-oldali feldolgozás megszakadt, miközben a böngészőben futó küldés még élt. A következő két sorba tett kép 15 ms alatt hibára futott, és 13:17:29-kor egy új kivágás is azonnal elutasítást kapott. A forrásban az előző, tovább futó küldés zárja megakadályozta az új művelet indulását. Az eredményt és az előrehaladási adatot a lekérdezés már a JavaScriptben törölte, így egy későn visszaérkező callback adatvesztést is okozhatott.

A kattintható képes üzenet felismerési hibája külön helyi regresszióban reprodukálható: az explicit felhasználói szerepjel mellett a `button > img` tartalom kimaradt, ha nem volt szövegbuborék. A korábbi tesztminták közvetlenül konténerbe tett képet használtak. A hibás `v5.14` kód ebben a próbában egy felhasználói üzenetet és két assistant üzenetet talált, de a kész új választ elutasította.

A pontos élő DOM-változatot a csak olvasó profilmásolat ezúttal sem igazolta: nem töltött be beszélgetést. A naplóban látható felismerési hiány és a forrásban bizonyított kattinthatóképes hiányosság összhangban van, de a kettő azonossága további élő kérés nélkül nem bizonyítható.

## Javított működés

- Az explicit felhasználói szerephez tartozó kattintható képes üzenet szövegbuborék nélkül is felismerhető. A profilképek, kezelőelemek, rejtett tartalom és vegyes felhasználói-assistant konténerek kizárása megmarad.
- A callback-határt túllépő eredménylekérdezés a teljes küldési határidőn belül ismételhető. A kép csatolása és a beküldés nem indul újra emiatt.
- A lekérdezés nem fogyasztja el az eredményt, a naplót vagy az előrehaladási adatot. Az ismételt olvasás sorszám alapján nem ment vagy naplóz kétszer ugyanazt az eseményt.
- A véglegesen megszakadt művelet saját azonosítójával megszakítja a böngészőben futó küldést. A zár felszabadul, a következő kérés elindulhat. A késői indítás és a korábbi művelet késői lezárása nem érintheti az új kérést.
- Az aktív képküldés az eredménylekérdezések között is frissíti a működési időbélyegét. A watchdog nem minősíti elavultnak a még szabályosan futó válaszvárást.
- A várakozó képek számlálója a következő feldolgozásra kijelölt képet is beleszámolja.
- A válaszállapot naplója külön számlálja a látható felhasználói szerepjelölőket és a felhasználói körhöz tartozó kattintható képeket. Az ismételt lekérdezés, a helyreállt lekérdezés, a megszakítás és a foglalt küldés elutasítása saját eseményt kap.

## Ellenőrzés

| Ellenőrzés | Eredmény |
| --- | --- |
| Teljes Python regresszió | 317/317 sikeres |
| JavaScript regresszió | 51/51 sikeres |
| Modern DOM valódi Qt/Chromium motorral | 13/13 sikeres; a teljes Python-csomag része |
| Natív callback, poll és watchdog | 11/11 sikeres; a teljes Python-csomag része |
| Diagnosztikai háttéríró és naplóolvasó | 25/25 sikeres; a teljes Python-csomag része; az új számlálók megmaradnak, a beszélgetéstartalom és azonosító kimarad |
| Forrásból futó alkalmazásönteszt | 9/9 sikeres, három gyorsfordítási ciklus és két egymást követő kattintható képes kérés; OCR-modell nélkül |
| Végleges EXE forrás- és futtatókörnyezet-egyezése | 34/34 sikeres |
| Végleges EXE offline önteszt | 10/10 sikeres, 55 gyorsfordítási ciklus és két egymást követő kattintható képes kérés |
| Csomagolt RapidOCR és Windows OCR | Mindkettő pontosan a szintetikus `Hello gamer` szöveget ismerte fel |
| Függőség- és szintaxisellenőrzés | `pip check`, Python-fordítás, JavaScript-szintaxis és `git diff --check` sikeres |

A késői callback valódi Qt/Chromium-próbája 100 ms-mal késlelteti az első eredménylekérdezés natív visszahívását, 20 ms-os teszthatár mellett. Az ismételt lekérdezés ugyanazt a kész választ visszaadja; a kép egyetlen beküldést kap. A próba nem használ hálózatot, személyes profilt vagy natív gyorsbillentyűt.

A megszakítás valódi Chromium-próbája ellenőrzi a várakozó képkérés lezárását, a küldési zár és automatikus helyreállítás felfüggesztésének felszabadulását, a késői válaszfigyelés hiányát és a következő sikeres kézbesítést. A képnézegető `button` és `[role="button"]` alakja, az `aria-haspopup="dialog"` változat, valamint az avatar- és menükizárás is külön próbát kapott.

A teljes Python-csomag után hozzáadott utolsó JavaScript-menükizárás külön 51/51 JavaScript- és 13/13 modern Qt/Chromium-ismétlést kapott. A csomagolt automatizálás a végleges forrással bájtpontosan egyezik.

A végleges EXE mérete `381566888` bájt, SHA-256 ellenőrzőösszege: `2abb9aeeffc18897efc4b9e2843f0c81278403e034277a718719bb3a2855cfd8`. A helyi telepített fájl `C:\Saját\Alkalmazások\Gamer-Translator-v5.15.exe`, ugyanazzal az ellenőrzőösszeggel. A csomagolt önteszt 64,669 másodperc alatt zárult. A tartalommentes ellenőrzési adatok az [ellenőrzési állományban](evidence/second-image-checks.json) találhatók.

A telepített `5.15` normál profillal elindult. A böngészőbetöltés és az automatizálás beillesztése sikeres, az indulás alatt nulla `ERROR` vagy `CRITICAL` esemény keletkezett. Ez az indulást igazolja; új bejelentkezett képkérés sikerét nem.

## Az ellenőrzés határai

A regressziók szintetikus DOM-mintával, memóriavágólappal és elkülönített profillal futnak. A teljes képküldési út valódi Qt/Chromium motort használ. Új bejelentkezett ChatGPT-üzenet és játék közbeni fordítás nem része az automatikus ellenőrzésnek.

A hibák idején a napló 0–7 ms eseményhurok-késést és 75–93% rendszermemória-foglaltságot mért. A magas memóriaterhelés hozzájárulhatott egy késői böngészőcallbackhez; ezt a napló önmagában nem bizonyítja. A felhasználói üzenet felismerési hibája és a megszakítás után bennmaradó zár külön forráshiba. GPU-terhelés és játékbeli FPS nem lett mérve.

Személyes profil, beszélgetésszöveg és futásidejű napló nem kerül a Git-repository-ba.
