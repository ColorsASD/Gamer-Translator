# Telepítési útmutató

Ellenőrzés dátuma: 2026. augusztus 30.

## Célkörnyezet és korlátok

A repository Python/PySide6 Windows asztali alkalmazást tartalmaz. A program Qt WebEngine ablakban nyitja meg a ChatGPT webes felületét, és helyi JavaScript automatizálást használ. Nincs saját webes backend, webhelyfeltöltési cél vagy OpenAI által biztosított staging hozzáférés a projektben.

A helyi staging ellenőrzés memóriaalapú DOM-mintával történt, letiltott webes kérésekkel. Emellett az elkülönített forrásprogramból egy bejelentkezés nélküli szöveges próba az élő ChatGPT-n is sikeres volt: „Hello gamer!” → „Szia, gamer!”. Ez nem az OpenAI belső tesztkörnyezete, és nem igazolja a bejelentkezett felület minden funkcióját. Az OpenAI infrastruktúrájába nem került kód; a saját, ideiglenes tesztbeszélgetésbe kizárólag a szintetikus próbaszöveg került. További élő beküldés külön jóváhagyás nélkül nem történik.

A dokumentált ChatGPT pluginút külön integrációt jelent. MCP-eszközökkel végzett integrációnál megfelelő kapcsolat, eszközsémák, az eszköz igénye szerinti hitelesítés és fiókjogosultság is szükséges. A jelenlegi asztali program nem ilyen plugin. Az aktuális integrációs tesztelési lehetőségeket az [OpenAI hivatalos dokumentációja](https://developers.openai.com/plugins/deploy/connect-chatgpt) írja le. Az átépítés külön feladat, nem végezhető egyszerű fájlfeltöltéssel.

## Elkülönített függőségtelepítés

A projekt gyökerében, PowerShellből:

```powershell
py -3.13 -m venv .venv313
.\.venv313\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv313\Scripts\python.exe -m pip check
```

Minden parancs sikeres kilépése után folytasd. A lockfájl a tesztelt Windows/Python 3.13.15 környezet 48 csomagverzióját rögzíti. A Windows OCR a Python 3.13-at támogató WinRT 3.2.1 csomagokra váltott. A Python/OpenSSL frissítés nem pusztán virtuális környezetcsere: a hivatalos, SHA-256 és Authenticode alapján ellenőrzött Python 3.13.15 telepítőből külön alapinterpreter is készült.

A jelenlegi gépen az új alapinterpreter helye `%LOCALAPPDATA%\Programs\Python\GamerTranslator-Python31315\python.exe`, OpenSSL-verziója 3.0.21. A korábbi Python 3.11.8 és `.venv` megmaradt. A PATH, a fájltársítások és a launcher binárisa nem módosult, de a `py` launcher felismeri az új telepítést, ezért implicit verzióválasztáskor már ezt is választhatja. A dokumentált parancsok explicit `.venv313` futtatót használnak. Az [installer ellenőrzése](evidence/python-runtime-installer.json) és a [környezet snapshotja](evidence/python-runtime-upgrade.json) megmaradt.

## Staging tesztek

```powershell
.\.venv313\Scripts\python.exe -m unittest discover -s tests -v
node --check gamer_translator\automation.js
node --test tests\test_automation.cjs
.\.venv313\Scripts\python.exe -m compileall -q main.py gamer_translator tests tools
git diff --check
```

A Python tesztek Qt offscreen környezetet használnak. A WebEngine teszt saját memóriaalapú profilt készít és blokkolja a nem helyi kéréseket. A natív műveleteket vizsgáló regressziók nem küldenek valódi billentyűleütéseket és nem nyitnak ChatGPT-beszélgetést. A staging ablak bezárását külön folyamatban, tényleges Qt eseményhurokkal is ellenőrzik.

A függőségellenőrzés reprodukálásához használj külön auditkörnyezetet, hogy az audit eszköze ne változtassa meg a csomagolandó környezetet:

```powershell
python -m venv "$env:TEMP\gamer-translator-audit"
& "$env:TEMP\gamer-translator-audit\Scripts\python.exe" -m pip install pip-audit==2.10.1 bandit==1.9.4
& "$env:TEMP\gamer-translator-audit\Scripts\python.exe" -m pip_audit -r requirements-lock.txt
& "$env:TEMP\gamer-translator-audit\Scripts\python.exe" -m bandit -r main.py gamer_translator
```

A későbbi audit eredménye eltérhet az újonnan közzétett sérülékenységek miatt. A lockfájl verziókat rögzít, csomagonkénti letöltési hash-eket nem.

## Tesztprogram készítése

```powershell
.\build.ps1 -PythonExecutable .\.venv313\Scripts\python.exe -OutputDirectory dist\staging\verified -SkipDependencyInstall
.\.venv313\Scripts\python.exe tools\verify_build.py '.\dist\staging\verified\Gamer Translator.exe'
Get-FileHash -LiteralPath 'dist\staging\verified\Gamer Translator.exe' -Algorithm SHA256
```

A `dist\staging\verified\Gamer Translator.exe` elkülönített kiadásjelölt. A korábbi `dist\Gamer Translator.exe` érintetlen marad. A build sikertelen függőségtelepítés vagy csomagolás esetén hibával leáll, és nem írja felül a meglévő célprogramot.

A frissítés első buildjén a csomagolás sikeres volt, de a Windows a korábbi `dist\staging\Gamer Translator.exe` cseréjét elutasította. A build emiatt hibát jelentett, és a korábbi fájl megmaradt. Az itt dokumentált új alkönyvtár ezt a fájlt sem írja felül. A sikertelen próbálkozás naplója `docs/evidence/build-python313-first-attempt.txt` néven megmaradt.

A build az interpretert még az eredeti környezetben feloldja, majd a saját futására a Windows és a kiválasztott interpreter könyvtáraira szűkíti a PATH-ot. Siker és hiba után is visszaállítja az eredeti értéket. Erre azért van szükség, mert egy köztes csomagba a PATH-on szereplő PDF-eszköz inkompatibilis ICU DLL-je került, és a tényleges EXE-indítás emiatt elbukott. A javított kis Qt-csomag az eredeti környezetben is sikeresen indult, a Windows saját ICU-könyvtárával. Rendszerfájl cseréje nem történt.

A `tools\verify_build.py` a becsomagolt Python-kódot és asseteket összeveti a munkafával, valamint a Python és OpenSSL DLL-ek bájtpontos egyezését is vizsgálja. A buildhez használt interpreterrel futtasd. A `dist\staging\verified\build-manifest.json` minden részellenőrzést tartalmaz. Ez statikus ellenőrzés; az EXE külön indítási próbája alább szerepel. Az elkészült kiadásjelölt mérete és SHA-256 értéke a [tesztjelentésben](test-report.md) található.

## A kész EXE offline próbája

```powershell
& '.\dist\staging\verified\Gamer Translator.exe' --self-test-report '.\dist\staging\verified\self-test.json' --self-test-duration 120
```

A jelentés `passed` mezőjének igaznak, a program kilépési kódjának nullának kell lennie. GUI EXE esetén a PowerShell interaktív meghívása nem feltétlenül várja meg a kilépést; automatizált futtatóban várd meg a saját elindított folyamat végét, és csak utána olvasd a jelentést. A jelentés hiánya nem siker. Az optimalizált Python-módot az önteszt elutasítja, így a kikapcsolt `assert` ellenőrzések nem adhatnak hamis sikerjelzést.

A teszt ideiglenes fájlprofilt, memóriavágólapot és nem tartós böngészőprofilt használ. Nem regisztrál gyorsbillentyűt, nem indít képkivágót és nem ír a Windows vágólapjára. Szöveget és képet helyi HTML-mintán küld, válaszmentést, overlayt, ablakváltásokat és kilépést vizsgál. A böngésző nem helyi kéréseit interceptor tiltja; ez nem teljes rendszerszintű csomagrögzítés.

A becsomagolt OCR-motorok tényleges futtatásához egészítsd ki a parancsot a `--self-test-model-dir` kapcsolóval és a három már ellenőrzött helyi ONNX modellt tartalmazó könyvtárral. A teszt másolatot készít az ideiglenes profilba, ellenőrzi a SHA-256 értékeket, és csak ezután futtatja a RapidOCR és a Windows OCR motorját egy generált „Hello gamer” képen. A modelleket nem tölti le automatikusan. Hiányzó vagy hibás modell hibát eredményez.

Az OCR minőségi mérését külön eszköz adja: `tools\benchmark_ocr.py`. A `--model-dir` és `--output` paraméterekkel 19 generált magyar, angol és gamer mintán mér, mintánként rögzíti a karakterhibákat. A benchmark sikeres lefutása nem jelenti minden minta hibátlan felismerését.

## Elkülönített élő felületi próba

```powershell
& '.\dist\staging\verified\Gamer Translator.exe' --staging
```

Ez az élő szolgáltatást nyitja meg, de a saját napi böngészőprofilt nem használja. A figyelés kezdetben ki van kapcsolva, a rendszervágólap, a globális gyorsbillentyűk és a rendszerébresztés tesztmódban nem működnek. A sütik memóriában maradnak; a helyi ideiglenes fájlprofil kilépéskor megszűnik. Az ablak bezárása a tesztprogramot is leállítja, nem tálcára rejti.

Csak jóváhagyott, személyes adatot nem tartalmazó mintát küldj. A bejelentkezést és az esetleges CAPTCHA-t a tesztelő végezze el, megkerülés nélkül. A jelenlegi ellenőrzés egyetlen bejelentkezés nélküli szövegpróbát igazolt; a bejelentkezett képfeltöltés és munkamenet-visszaállítás továbbra külön ellenőrzést igényel.

## Kiadás előtti kézi ellenőrzés

Külön Windows tesztfelhasználóval vagy tesztgépen, külön ChatGPT-tesztfiókkal végezd. A helyi staging és a tesztfiók sem biztosít hozzáférést az OpenAI belső staging környezetéhez.

1. Zárd be a régi alkalmazást, mielőtt ugyanazzal a helyi profillal új verziót indítasz. A régi és új egy-példányos zárolás eltér, ezért a két verzió ne használja egyszerre ugyanazt a böngészőtárolót.
2. Már a tesztprogram indítása előtt ellenőrizd, hogy nincs érzékeny kép a vágólapon. Első indításkor a figyelés alapból aktív, és az újonnan másolt képeket automatikusan küldi. Szükség esetén a tesztelés elején kapcsold ki.
3. Ellenőrizd a bejelentkezést, az eredetjelzést, a használt bejelentkezési szolgáltatót és a munkamenet újranyitását. Ne kerüld meg az oldal hozzáférési vagy botvédelmi ellenőrzéseit.
4. Küldd el a fordítási promptot egy új tesztbeszélgetésbe. Próbálj rövid magyar és angol szöveget, képet OCR-rel és OCR nélkül, majd az Alt+X gyors chatet.
5. Ellenőrizd a kész válasz vágólapra másolását, az overlayt, a tálcamódot, az Alt+C képkivágást és a begépelést egy üres szövegszerkesztőben. Terminálban ne teszteld a begépelést.
6. Ellenőrizd a hosszabb válaszokat, hálózati hibát, lejárt munkamenetet, párhuzamos művelet elutasítását, GPU-beállítás utáni újraindítást és hosszabb háttérfutást.
7. Futtasd újra az auditot minden új kiadáshoz. Az EXE nincs automatikusan digitálisan aláírva; terjesztés előtt a [kiadói tanúsítványhoz kötött aláírási útmutatót](followup-security.md) kövesd. A `tools\sign_release.ps1` a tesztelt bemeneti SHA-256 értéket, a pontos kiadót és a hiteles időbélyegzést is ellenőrzi. A Defender eredménye mindig csak a jelentésben rögzített fájlhashre érvényes.

## Kihelyezés és visszaállítás

Csak a staging és a fenti kézi ellenőrzések sikeres eredménye után cseréld a használt Windows programot. Őrizd meg a korábbi EXE-t, és zárt alkalmazás mellett készíts helyi biztonsági másolatot a `%LOCALAPPDATA%\Gamer Translator` könyvtárról. Ebben bejelentkezési munkamenet és fordításszöveg is lehet; ne kerüljön repositoryba vagy megosztott naplóba.

Hiba esetén zárd be az új programot és állítsd vissza a korábbi EXE-t. A böngészőprofil verziók közötti visszafelé kompatibilitása nem garantált; szükség esetén a helyi biztonsági másolatból állítsd vissza a teljes profilt.

Éles kihelyezés ebben az ellenőrzésben nem történt.
