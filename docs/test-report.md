# Tesztelési jelentés

Dátum: 2026. augusztus 30. Kiinduló commit: `13d6dce`.

## Környezet és hatókör

A végső ellenőrzés Windows alatt, külön `.venv313` környezetben történt: Python 3.13.15, OpenSSL 3.0.21, PySide6 6.11.2, Pillow 12.3.0, RapidOCR 3.9.2, ONNX Runtime 1.29.0, WinRT 3.2.1 és PyInstaller 6.22.2. A lockfájl 48 csomag pontos verzióját rögzíti. A korábbi `.venv` / Python 3.11.8 környezet megmaradt; annak régebbi bizonyítékai történeti eredmények.

A regressziók valódi Qt/Chromium motort használnak, saját memóriába töltött DOM-mintán. A `https://chatgpt.com/` base URL ezekben csak az eredetellenőrzést szimulálja. Az interceptor blokkolja a nem helyi webes kéréseket. A normál alkalmazásprofil, személyes beszélgetés és Windows-vágólap nem része a tesztadatnak. Az ettől különálló, egyetlen élő, bejelentkezés nélküli szövegpróba alább szerepel.

## Sikeres automatizált ellenőrzések

| Ellenőrzés | Eredmény | Lefedettség |
| --- | --- | --- |
| Python regressziók | 70/70 sikeres, 10,626 s | Beállítások, OCR, IPC, build, natív ablak, WebEngine, tesztmód |
| JavaScript regressziók | 13/13 sikeres | Origin, payload, kép, prompt, konkurencia, válaszszöveg, helyreállítás |
| Qt WebEngine integráció | 5/5, a Python sor része | Szöveg, kép, streaming válasz, ApplicationWorld, hálózati tiltás |
| Új OCR-minőségi regressziók | 11/11, a Python sor része | Átfedések, koordináták, motorállapot, rangsor és legitim karakterek |
| Tesztmód és életciklus | 7/7, a Python sor része | Profil/vágólap elkülönítése, argumentumok, tényleges folyamatkilépés |
| JavaScript/Python szintaxis | Sikeres | `node --check`, `compileall` |
| Függőségek összhangja | Sikeres | `pip check` |
| Git whitespace | Sikeres | `git diff --check`; CRLF figyelmeztetés nem hiba |
| Friss függőségaudit | 48 csomag, 0 ismert találat | Python csomagadvisoryk az audit időpontjában |
| Bandit statikus vizsgálat | 34 alacsony, 0 közepes, 0 magas | 4466 sor, 0 kihagyott vizsgálat; minden figyelmeztetés értékelve |
| Optimalizált önteszt elutasítása | Sikeres negatív próba | `python -O`: kilépési kód 1, `passed: false`, 0 ciklus |

Összesen **83 automatizált regressziós teszt sikeres**; az alcsoportok nem további tesztek. A Bandit 1-es kilépési kódját a dokumentált figyelmeztetések okozzák, nem lett csendben sikernek átminősítve. Az új `self_test.py` 17 explicit ellenőrzési assertje is szerepel a listában.

Futtatási parancsok:

```powershell
.\.venv313\Scripts\python.exe -m unittest discover -s tests -v
node --check gamer_translator\automation.js
node --test tests\test_automation.cjs
.\.venv313\Scripts\python.exe -m compileall -q main.py gamer_translator tests tools
.\.venv313\Scripts\python.exe -m pip check
git diff --check
```

Nyers eredmények: [Python](evidence/unittest-python313.txt), [JavaScript](evidence/javascript-tests-final.txt), [csomagaudit](evidence/pip-audit-python313.json), [Bandit](evidence/bandit.json), [optimalizált mód elutasítása](evidence/optimized-self-test-rejected.json).

## Sikeres tesztesetek

A tesztfájlok minden konkrét esetet külön névvel tartalmaznak. Az ellenőrzések az alábbi viselkedéseket igazolták:

- Sérült JSON, hibás UTF-8 és nem objektum beállítások nem okoznak indulási hibát; a régi promptmigráció megmarad, az egyedi prompt nem íródik át.
- A szöveges `false` nem kapcsolja be a figyelést; az időzítők határértékei érvényesülnek.
- Hibás fájlcsere esetén az előző beállításfájl és cache megmarad; az ékezetes szöveg és a többi adatszekció megőrződik.
- Hiányzó SHA, hibás letöltés, HTTP-modellcím és nem helyi fájlnév elutasítva; a jó modell atomikusan kerül a célhelyére, a már ellenőrzött modell nem igényel új letöltést.
- Túl nagy kép a dekódolás előtt elutasítva; az átlátszó háttér nem nyeli el a fekete szöveget; öt feletti OCR-jelölt számítása helyes.
- Az IPC külön folyamatban, ideiglenes profillal megakadályozza a második elsődleges példányt.
- Hibás pip-parancs, sikertelen build és hiányzó EXE esetén a korábbi program megmarad. Sikeres build csak a kijelölt alkalmazást cseréli.
- Idegen origin, HTTP, hamis aldomain, más port és felhasználói adatos URL nem automatizálható.
- Az ApplicationWorld automatizálás működik akkor is, ha a mintalap MainWorldje azonos nevű hibás függvényt állít be.
- A memóriaalapú mintalapon a textarea és a többsoros contenteditable szöveg, a PNG-csatolás és a fokozatosan elkészülő válasz feldolgozása sikeres.
- A weboldal általános vágólap- és helyifájl-hozzáférése tiltott; a képfeltöltési út így is működik.
- A részlegesen beillesztett prompt nem kerül elküldésre; a párhuzamos küldés nem írja felül a folyamatban lévőt; a HTML-szerű szöveg nem válik HTML-elemmé.
- Az inline szöveg, a `thinking` szót tartalmazó fordítás és a kézi helyreállítás időzítője a javított működést követi.
- Az eredetjelzés nem tartalmaz bejelentkezési tokent vagy jelszót; az overlay egyszerű szövegként kezeli a választ.
- A begépelés megáll ablakváltáskor, nem indul lenyomva maradt módosítóbillentyűvel, és hibát jelez Windows-beviteli elutasításkor. A teszt nem küld valódi billentyűket.
- A szóközös/idézőjeles újraindítási argumentumok megőrződnek; hibás válaszfigyelési JSON és idézőjeles azonosító nem okoz kódbefecskendezést.

- A staging indítás még a normál beállításprofil és singleton előtt elágazik; a rendszer vágólapját nem olvassa. A reset gomb tesztmódban nem indíthat normál programpéldányt.
- A staging ablak bezárása külön alfolyamatban, tényleges Qt eseményhurokból kilép, és felszabadítja a saját ideiglenes könyvtárát. A korábbi változat ablak nélküli háttérfolyamatát ezzel sikerült reprodukálni és javítani.

## Valódi OCR-próba

A korábbi kétmintás próba után az OCR 19 generált magyar, angol és gamer képen lett összehasonlítva. A javítás előtti rangsorolás és az új változat ugyanabban a Python 3.13.15 / WinRT környezetben, azonos modellekkel futott. A baseline a régi felismerési/rangsorolási függvényeket rekonstruálja; a működéshez szükséges modellútvonal- és SHA-javítás mindkettőben megmaradt. A hat külön ellenőrző minta eredményének ismeretében már nem változott a javítás.

| Mérőszám | Korábban | Javítás után |
| --- | --- | --- |
| Karakterpontos képek | 7/19 | 15/19 |
| Karakterhibák | 32/628 | 5/628 |
| Karakterhibaarány | 5,10% | 0,80% |
| Hat külön ellenőrző minta | 3/6 pontos, 7 karakterhiba | 4/6 pontos, 3 karakterhiba |

Mind a hét korábban pontos minta pontos maradt. A teljes mintakészletben a karakterhibák száma 84,4%-kal csökkent; ez nem általános pontossági ígéret. A képek Arial/Consolas betűvel, világos és sötét háttérrel készültek; nem fedik le az összes játékot vagy betűtípust.

Négy képen maradt eltérés: az `Árvíztűrő` szóban `ű → ú`, egy önálló `Ő → Ó`, valamint két parancsos mintában felesleges szóköz. Az eredeti diagnosztikai mondat aktuális kimenete `Árvíztúrő tükörfúrógép`: a hibás plusz `ti` megszűnt, egy ékezethiba megmaradt. Ezek sikertelen karakterpontossági esetek, nem sikeresként elszámolt eredmények. Mintaszövegre írt cserét és modellcserét nem alkalmaztunk.

A [mintánkénti mérés](evidence/ocr-quality-benchmark.json) forráshasheket és eltéréseket is tartalmaz. A `tools/benchmark_ocr.py` megismételhető mérőeszköz; alapértelmezés szerint kizárólag meglévő, hash-ellenőrzött helyi modellekkel dolgozik. Nem küld képet vagy szöveget ChatGPT-be.

## Elkészült és ténylegesen futtatott Windows tesztprogram

A `dist/staging/verified/Gamer Translator.exe` egyfájlos Windows x64 GUI kiadásjelölt mérete **381 500 794 bájt**. SHA-256:

```text
465a14948960d4e4d836068462993ad97dc4f3859a0fe069b357775d184c8867
```

A statikus csomagellenőrzés **32/32 sikeres**; 6 saját Python-modul egyezik a munkafával. A JavaScript, az ikon, valamint a Python és OpenSSL natív könyvtárai is a megfelelő ellenőrzött változatot tartalmazzák. A csomag 3315 archívumbejegyzést és 1053 Python-modult tartalmaz. Részletek: [manifest](evidence/build-manifest.json), [buildfigyelmeztetések](evidence/build-warnings.txt).

**A kész EXE el lett indítva és végigfutott**, nem csak a forrás. Az offline önteszt `frozen: true`, Python 3.13.15, OpenSSL 3.0.21 mellett **109 szöveges ciklust**, egy PNG-csatolást és a két natív OCR-motor tényleges felismerését vizsgálta. A mérés belső ideje 122.365 másodperc; ehhez a PyInstaller kibontásának ideje hozzáadódhat. A RapidOCR és a Windows OCR eredménye egyaránt `Hello gamer`. A kilépés sikeres, a jelentésben minden ellenőrzés igaz.

A próba a teljes ablakot offscreen környezetben építi fel; memóriavágólapot, ideiglenes profilt és helyi HTML-oldalt használ. A valódi Windows-vágólap, a globális gyorsbillentyűk és a képkivágó helyettesítettek. Ezért a sikeres önteszt nem állítja, hogy a felhasználó játékában az összes natív integrációt interaktívan teszteltük. Bizonyíték: [becsomagolt alkalmazás öntesztje](evidence/frozen-self-test.json). A kétperces forráspróba külön 106 szöveges ciklust teljesített: [forrásönteszt](evidence/source-self-test-python313.json).

A tényleges EXE-indítás az egyik köztes csomagon `QtCore` DLL-hibát mutatott ki. A csomagoló a PATH-on található Poppler PDF-eszköz ICU DLL-jét emelte be, amelyből a Qt által igényelt 20 export hiányzott. A Windows saját ICU-könyvtára ezeket tartalmazza. A buildkörnyezet elkülönítése ezt az idegen függőséget kizárja; rendszer-DLL cseréje nem történt. A sikertelen futás [nyers hibája](evidence/frozen-dll-failure.txt) és a [DLL-elemzés](evidence/frozen-dll-analysis.json) megmaradt. A fenti sikeres önteszt már a javított csomagra vonatkozik.

A végleges csomag [független DLL-ellenőrzése](evidence/frozen-path-contamination-verified.json) 360 natív fájlt dolgozott fel hiba nélkül. A korábban azonosított 48 idegen DLL egyike sem szerepel benne; a vizsgált Poppler- és MinGW-könyvtárakkal nincs fájlhash-egyezés. Ez az ellenőrzés az archívum tartalmát vizsgálja, a sikeres működést a külön EXE-próba igazolja.

A nem használt OCR-backendekhez tartozó feltételes importfigyelmeztetések megmaradtak a naplóban. Az EXE Authenticode-állapota **NotSigned**; kiadói tanúsítvány nélkül nem tekinthető hitelesen aláírt kiadásnak. A konkrét fájl Defender-vizsgálatát és az aláírás előfeltételeit a [kiegészítő audit](followup-security.md) rögzíti.

Az offscreen futás Chromium-naplójában GLES-környezet létrehozási hibák is szerepelnek. A fent jelzett alkalmazás-, DOM- és OCR-ellenőrzések ezek mellett sikeresen lefutottak; a naplót nem szűrtük. Ebből a GPU-gyorsítás működésére nem vonható le sikeres teszteredmény, az külön interaktív ellenőrzés marad.

## Élő ChatGPT-felület egyszeri próbája

Az új interpreterrel, forrásból indított `--staging` ablakban a `https://chatgpt.com/` oldal betöltődött. Friss, nem tartós profil, bejelentkezés és személyes adatok nélkül az alkalmazás saját „Prompt elküldése” gombja ezt a mintát továbbította:

> Gamer Translator kompatibilitási teszt. Fordítsd magyarra ezt az angol mondatot, és csak a fordítást add vissza: Hello gamer!

Az alkalmazás „A prompt elküldve.” állapotot jelzett; a beszélgetésben a tényleges felhasználói üzenet és a **„Szia, gamer!”** válasz is megfigyelhető volt. A bizonyíték [külön JSON-ban](evidence/live-chatgpt-smoke.json) szerepel. Ez egy bejelentkezés nélküli szöveges minta, nem a végleges EXE teljes online tesztje. További élő beküldést a Computer Use biztonsági kapuja explicit engedélyhez kötött, ezért nem folytattuk. OpenAI szerveroldali telepítés nem történt.

## Kiadás előtti nyitott ellenőrzések

- Kiadói tanúsítvány és hiteles SignTool hiányában digitális aláírás nem történt. Az aláíró eszköz előkészítve és negatív ágakon tesztelve van; valódi aláírás nélkül annak sikeres ágát nem állítjuk teszteltnek.
- A bejelentkezett felület, SSO, munkamenet-visszaállítás és élő képfeltöltés külön jóváhagyott tesztfiókos ellenőrzést igényel. CAPTCHA- vagy hozzáférési korlátozás nem lett megkerülve.
- A valós képkivágó, tálcaikon, globális gyorsbillentyűk, játékba begépelés, GPU-váltásos újraindítás és többórás háttérfutás nem része a kétperces offline próbának.
- Az OCR négy dokumentált mintán nem karakterpontos. Valódi képeken további minőségi ellenőrzés szükséges.
- A hivatalos Python telepítő OpenSSL 3.0.21-et tartalmaz; az upstream 3.0.22 öt további javítását és a 3.0 ág közeli támogatási határát a biztonsági audit értékeli. A program normál HTTPS-útvonalán konkrét elérhetőséget nem azonosítottunk, de a pip-audit nulla találata nem natív CVE-mentességi állítás. Gyártói javított futtatókörnyezetre frissítés szükséges, amint megfelelő csomag rendelkezésre áll.
- A kilépési hiba reprodukálására indított korábbi, már ablak nélküli saját staging folyamatok célzott leállítását eszközpolicy blokkolta; külön felhasználói jóváhagyást kértünk. Az új forrás életciklustesztje sikeres. A [záró állapotellenőrzéskor](evidence/pending-staging-cleanup.json) a régi, saját 4148 → 17380 → 18576 folyamatlánc és az ideiglenes könyvtára még létezett. Takarításkor újra ellenőrizni kell a folyamatok azonosságát; személyes alkalmazás vagy profil nem módosítható.
- OpenAI belső staging hozzáférés és szerveroldali kihelyezés nem áll rendelkezésre. A helyi audit nem igazolja a szolgáltatás belső architektúrájának biztonságát, és nem garantál sérülékenységmentességet.

## Kért végrehajtási ellenőrzőlista

- [x] Kód áttekintése és hibák azonosítása.
- [x] Igazolt hibák javítása a forráskódban.
- [x] Telepítési folyamat dokumentálása.
- [x] Helyi staging build elkészítése, becsomagolt EXE futtatása.
- [ ] Kód telepítése az OpenAI belső chatgpt.com tesztkörnyezetébe: nincs ilyen célkörnyezet és hozzáférés.
- [x] Helyi funkcionális és OCR-tesztek rögzítése; az egyszeri élő szövegpróba külön dokumentálva.
- [x] Biztonsági audit a jelentésben meghatározott helyi hatókörben.
- [x] Auditjelentés és kiadói aláírási útmutató elkészítése.

A nyitott tételek nem sikeresként elszámolt ellenőrzések. A [telepítési útmutató](deployment.md) és a [biztonsági audit](security-audit.md) a következő kiadási lépéseket és korlátokat is tartalmazza.
