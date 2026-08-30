# Gamer Translator – független biztonsági ellenőrzés

Dátum: 2026-08-30. Kiindulási commit: 13d6dce49dc7eb81b3a2f884ec04914a60396e7a. A kezdő kódban két magas kockázatú bizalmi határ problémát, egy modellintegritási hibát és több kisebb megerősítési lehetőséget találtam. A javításokkal párhuzamosan független kódellenőrzés történt; az alábbi eredeti sorszámok a kiindulási commitra vonatkoznak. A korrigált forráson új statikus ellenőrzés, az elkülönített tesztmód kézi kódellenőrzése és négy független, hálózat nélküli modellintegritási teszt történt. A végső függőségaudit Python 3.13.15 alatt 48 csomagon 0 ismert találatot adott.

A végső `verified` EXE statikus ellenőrzése, 109 ciklusos offline futása, PNG-útvonala, mindkét natív OCR-motorja és külön Defender-vizsgálata sikeres. A kiadói aláírás hiánya, a natív OpenSSL frissítési feltétele és a még el nem végzett bejelentkezett/kézi szolgáltatástesztek megmaradnak; a sikeres staging eredmények nem jelentenek teljes biztonsági garanciát.

Ez helyi asztali alkalmazás, nem a chatgpt.com szerverének forráskódja. Az OpenAI infrastruktúráját, privát beszélgetéseket, munkamenetsütiket és a személyes böngészőprofilt nem vizsgáltam. A független audit nem olvasott valódi vágólaptartalmat és nem küldött online promptot. A fő tesztelési folyamat elkülönített Qt- és OCR-próbákat, valamint egyetlen, bejelentkezés nélküli élő szöveges próbát végzett; ezeket az alábbiak és a tesztelési jelentés külön azonosítják. A kért általános „ne hagyj ki semmilyen biztonsági ellenőrzést” nem jelent teljeskörű sérülékenységmentességi garanciát.

## Megállapítások

### SEC-01 – Magas: globális weboldali vágólaphozzáférés

Hely: gamer_translator/main_window.py:1187–1188, BrowserPage:437–446.

Bizonyíték: JavascriptCanAccessClipboard=True és JavascriptCanPaste=True minden megnyitott oldalra. Nincs származási helyhez kötött permission-kezelés vagy főkeret navigációs korlátozás. A Qt dokumentáció kifejezetten javasolja mindkét beállítás kikapcsolását a korlátlan vágólapelérés miatt.

Hatás: egy beágyazott böngészőben megnyitott rosszindulatú oldal a platform lehetőségei szerint a natív fordítási folyamattól független vágólap-hozzáférést kaphat. Ez különösen érzékeny lehet jelszókezelőből másolt szövegnél.

Biztonságos reprodukálás: elkülönített, szintetikus tesztprofilban ellenőrizni a két WebAttribute értékét, majd kizárólag mesterséges vágólapszöveggel tesztelni a helyi fixture oldal hozzáférését. Éles vágólappal nem reprodukáltam.

Javítás: mindkét attribútum False, a natív vágólapfunkció megtartásával. A módosított kódban ezt ellenőriztem.

Forrás: [Qt WebEngine beállítások](https://doc.qt.io/qt-6/qwebenginesettings.html).

### SEC-02 – Magas: automatizálás nem megbízható oldalon és írható MainWorld globálisokban

Hely: gamer_translator/main_window.py:2074–2089, 3293–3318, 3468–3505, 3569–3574; gamer_translator/automation.js:1, 462.

Bizonyíték: loadFinished után minden sikeres oldalbetöltés automatizálást kapott; runJavaScript előtt nem történt origin-ellenőrzés. Az _is_chatgpt_url csak hostname-t nézett, HTTPS-t/portot nem. A window.__gamerTranslatorDeliver függvény és eredménygyűjtők a weboldallal közös MainWorldben voltak.

Hatás: rossz időben történő navigáció vagy oldaloldali JS-manipuláció a képet/OCR-szöveget más oldalnak adhatja, illetve hamis fordítást másoltathat a natív vágólapra. Nincs QWebChannel/native QObject bridge; ebből közvetlen általános Python-kódfuttatás nem állapítható meg.

Biztonságos reprodukálás: stubbelt/elkülönített böngésző URL-ének cseréje az előkészítés és küldés között; ellenőrizni, hogy rossz HTTPS origin, HTTP, nem alapértelmezett port és felhasználói adatos URL ne kaphassa meg a payloadot. A MainWorldből felülírt __gamerTranslatorDeliver ne befolyásolja a natív küldést.

Javítás: pontos origin-ellenőrzés Pythonban és JS-ben, ellenőrzés navigáció után is, ApplicationWorld használata. A módosított kódban ezeket ellenőriztem. Az eredet mindig látható címkével megjelent, ami csökkenti a címsor nélküli idegen oldal megtévesztési kockázatát; a külső bejelentkezési oldalakat nem tiltották vaktában.

Forrás: [Qt WebEngine biztonsági szempontok](https://doc.qt.io/qt-6/qtwebengine-security.html).

### SEC-03 – Közepes: OCR-modell első letöltése után nem volt hash-ellenőrzés

Hely: gamer_translator/ocr_service.py:241–251.

Bizonyíték: a DownloadFile.run SHA256 paramétere félrevezető volt. A telepített RapidOCR 3.7.0 és az új 3.9.2 forrásában a hash csak a már létező fájl átugrásához volt ellenőrizve. _save_response_with_progress után a függvény visszatért ellenőrzés nélkül.

Hatás: sérült vagy a letöltési forrás oldalán lecserélt modell már az első letöltéskor ONNX-betöltésbe kerülhet. Tényleges kódfuttatást nem állapítottam meg.

Reprodukálás: DownloadFile.run helyettesítése olyan fixture-függvénnyel, amely a várt hashhez képest eltérő bájtokat ír. Az eredeti _ensure_assets nem utasította el ezeket a letöltés után. A javított kód elutasítja.

Javítás: kötelező, érvényes SHA256 metaadat, HTTPS, ellenőrzött fájlnév, külön ideiglenes letöltés, letöltés utáni hash és atomikus publikálás. Négy független teszt PASS: hiányzó hash tiltása; hibás friss modell tiltása célfájl nélkül; HTTP tiltása; helyes hashű modell publikálása. Az új RapidOCR mindhárom modelljéhez van SHA256 metaadat.

### SEC-04 – Közepes: régi környezet és nem rögzített függőségek

Hely: requirements.txt:1–7; build.ps1:37; helyi interpreter és csomagkészlet.

Kiindulási környezet: Python 3.11.8, OpenSSL 3.0.13, Qt/PySide6 6.11.0. A Qt Chromium alapverzió 140.0.7339.225 volt, de a biztonsági javítási szint 146.0.7680.80; csak az alapverzió alapján nem lehet hiányzó CVE-patchekre következtetni.

A pip-audit 2.10.1 a kezdeti 43 csomagon 46 advisory-bejegyzést adott 6 csomagban. Az adatbázis duplikációi miatt ez 32 különböző (csomag, advisory-azonosító) pár. Nem 46 függetlenül kihasználható alkalmazáshiba.

- idna 3.11 → javítás 3.15+
- msgpack 1.1.2 → javítás 1.2.1+
- Pillow 12.1.1 → az összes jelzett találat javítása 12.3.0+
- pip 24.0 → az összes jelzett találat javítása 26.2+
- setuptools 65.5.0 → az összes jelzett találat javítása 83.0.0+
- urllib3 2.6.3 → javítás 2.7.0+

Elérhetőségi korlátok: az alkalmazás a vágólapképet Qt-val PNG-re kódolja, ezért a Pillow PSD/font/PDF specifikus hibái a rendes vágólapútvonalon nem igazoltan elérhetők. A pip/setuptools találatok buildtelepítési lánchoz tartoznak; nincs ilyen natív hívás a fordítási útvonalon. Az urllib3 ismert problémái meghatározott streaming/dekódolási vagy low-level proxy feltételeket igényelnek. Ettől a komponensek frissítése indokolt.

Az első elkülönített `.venv` staging környezetben 41 frissen telepített csomag, pip 26.2.1 és setuptools 84.0.0 mellett 0 ismert pip-audit találat és sikeres `pip check` volt. Ez történeti köztes eredmény: a `.venv` alapja még Python 3.11.8 / OpenSSL 3.0.13. A globális csomagkészletet nem módosítottam.

A végső buildkörnyezet a külön `.venv313`: Python **3.13.15**, OpenSSL **3.0.21**, PySide6/Qt **6.11.2**. A Python telepítő SHA256 értéke egyezett a hivatalos forrással, Authenticode-aláírása `Valid`, kiadója Python Software Foundation. A runtime-agent a projekt számára külön alapinterpretert telepített; a korábbi Python és `.venv` megmaradt. A telepített interpreter verzióját és az audit JSON-t függetlenül összevetettem: **48 telepített és 48 auditált csomag, 0 ismert találat**, `pip check` sikeres. A Windows OCR a Python 3.13-kompatibilis `winrt-runtime` és WinRT-csomagok 3.2.1 verzióját használja; a forrásban a régi WinSDK import csak kompatibilitási tartalék maradt.

Az aktuális 48 verziót a `requirements-lock.txt` rögzíti; a `python-runtime-upgrade.json` tételes csomaglistát és a natív Python/OpenSSL fájlok hash-ét is tartalmazza. Qt 6.11.2 Chromium biztonsági javítási szintje 151.0.7922.71. A lockfájl letöltési hash-eket nem rögzít, ezért a telepítési lánc további megerősítési lehetősége a hash-ekkel rögzített csomagkészlet. A pip-audit nem auditálja magát az interpretert, a becsomagolt natív könyvtárak teljes CVE-készletét vagy a Windowst; 0 találatból ezek sérülékenységmentessége nem következik. Későbbi frissítéskor auditot és funkcionális tesztet kell ismételni.

Ellenőrzött elsődleges közlemények:

- [Pillow biztonsági közlemény](https://github.com/python-pillow/Pillow/security/advisories/GHSA-pwv6-vv43-88gr) – CVE-2026-42311, PSD memóriakorrupció, 12.2.0 javítja.
- [Setuptools biztonsági közlemény](https://github.com/pypa/setuptools/security/advisories/GHSA-5rjg-fvgr-3xxf) – CVE-2025-47273, PackageIndex útvonalbejárás, 78.1.1 javítja.
- [urllib3 biztonsági közlemény](https://github.com/urllib3/urllib3/security/advisories/GHSA-mf9v-mfxr-j63j) – CVE-2026-44432, streaming kitömörítési erőforrás-kimerítés, 2.7.0 javítja.
- [Python 3.11.14 biztonsági kiadás](https://www.python.org/downloads/release/python-31114/) – a korábbi 3.11.8 környezet után megjelent biztonsági javítások és a 3.11 ág source-only támogatási helyzete.
- [Python 3.13.15 kiadás](https://www.python.org/downloads/release/python-31315/) – az új, külön telepített futtatókörnyezet hivatalos forrása; telepítőellenőrzés: `evidence/python-runtime-installer.json`.
- [Qt WebEngine biztonsági verziózás](https://doc.qt.io/qt-6/qtwebengine-overview.html) – Chromium biztonsági patch-backport és külön lekérdezhető javítási szint.

#### Maradó natív OpenSSL-frissítési feltétel

A Python 3.13.15 hivatalos Windows-csomagja OpenSSL 3.0.21-et tartalmaz, de időközben megjelent a **3.0.22 biztonsági kiadás, 2026-08-25-én**. A 0 pip-audit találat ezért nem jelenti, hogy a natív runtime minden upstream javítást tartalmaz. A kiadás öt advisoryt javít a 3.0 ágon. [OpenSSL 3.0 kiadási jegyzetek](https://openssl-library.org/news/openssl-3.0-notes/index.html), [hivatalos biztonsági közlemény](https://openssl-library.org/news/secadv/20260825.txt).

| Azonosító | Upstream súlyosság / érintett felület | Alkalmazási elérhetőség |
| --- | --- | --- |
| CVE-2026-63072 | Moderate; CMS kulcskicsomagolás, heap-túlírás | CMS-dekódolás nincs a vizsgált alkalmazási útvonalon. |
| CVE-2026-63076 | Moderate; CMP védelmi paraméter, hibás pointer | Az alkalmazás nem CMP-kliens vagy -szerver. |
| CVE-2026-54874 | Low; DTLS rekordpuffer memóriaigénye | A Python modellletöltés TLS-alapú HTTPS, nem DTLS. |
| CVE-2026-63074 | Low; CMP extra tanúsítványok cache-növekedése | CMP-kiszolgáló és tartós CMP-környezet nincs. |
| CVE-2026-75803 | Low; üres AEAD ciphertext közvetlen EVP_Cipher() lezárásakor | Közvetlen ilyen hívás nincs; a szokásos TLS-rekordút elemzése alább. |

A vizsgált saját forrás, `requests` és `urllib3` nem használ CMS/CMP/DTLS vagy közvetlen EVP API-t. A RapidOCR letöltője `requests.get(..., stream=True, timeout=...)` hívást végez, alapértelmezett tanúsítványellenőrzéssel; a Python `ssl` modul a vizsgált környezetben TLS-protokollokat tesz elérhetővé. A saját `ctypes` hívások Windows ablak-, billentyű- és folyamatfunkciókat céloznak, nem OpenSSL-t. A beágyazott ChatGPT-oldal WebEngine-hálózata külön komponens, nem a Python modellletöltő `ssl` híváslánca.

Az AEAD-kérdésnél az API-nevek hiányán túl az upstream 3.0.21 TLS-rekordkezelését is ellenőriztem. A TLS 1.2 provider út `EVP_CipherUpdate`-et használ, és a nulla rekordhosszt előbb elutasítja; a TLS 1.3 tag és legalább egy tartalombájt meglétét követeli, majd `EVP_CipherUpdate` / `EVP_CipherFinal_ex` lépéseket alkalmaz. Ezek alapján a vizsgált normál HTTPS-használatban **nem azonosítottam konkrét kihasználható hívásláncot**; ez forrásalapú elérhetőségi következtetés, nem teljes natív bináris bizonyítás vagy aktív támadási teszt. [OpenSSL 3.0.21 TLS-rekordforrás](https://raw.githubusercontent.com/openssl/openssl/openssl-3.0.21/ssl/record/ssl3_record.c), [TLS 1.3-rekordforrás](https://raw.githubusercontent.com/openssl/openssl/openssl-3.0.21/ssl/record/ssl3_record_tls13.c).

A natív frissítés nyitott kiadási feltétel marad: a Python szállítójának ellenőrzött, aláírt, javított runtime-jára kell áttérni és újraépíteni, majd megismételni a teszteket. Tetszőleges forrásból származó DLL-lel nem cseréltük le a hitelesített Python-csomag részeit. Az OpenSSL 3.0 upstream támogatása **2026-09-07-ig** tart, ezért a támogatott runtime-ra váltás sürgős tervezési feladat. [OpenSSL támogatási stratégia](https://openssl-library.org/policies/releasestrat/).

### SEC-05 – Alacsony: explicit méretkorlát nélküli kép- és szövegfeldolgozás

Hely: gamer_translator/main_window.py:3515–3539; gamer_translator/ocr_service.py:306–309.

Bizonyíték: az eredeti kód a teljes QImage-t PNG-re és Base64-re másolta méretkorlát nélkül; az OCR előbb teljes RGB képet hozott létre és csak utána kicsinyített.

Hatás: túl nagy helyi vágólapkép az alkalmazást jelentős memória- és CPU-terhelésnek teszi ki. Távoli kódfuttatást nem állapítottam meg.

Javítás: képpont- és bájtkorlát a további másolás/feldolgozás előtt, támogatott formátum és hibás adat kezelése. A natív vágólapútvonal és a JavaScript képkorlátja 20 MiB, a natív pixelkorlát 40 millió. A külön is hívható OCR képbemeneti korlátja 64 MiB és 40 millió képpont.

### SEC-06 – Alacsony / megerősítés: helyi egyetlen példány kezelés

Hely: main.py:98–112.

Bizonyíték: fix globális QLocalServer név, nincs explicit UserAccessOption és nincs független fájlzár. A Qt platformalapértelmezett jogosultságára támaszkodott.

Hatás: más helyi példány/azonos nevű IPC-kiszolgáló összetévesztése és indítási versenyhelyzet. Igazolt másik felhasználós támadást nem végeztem; privilegizált kódvégrehajtás ebből nem következik, az üzenet csak ablakot aktivál.

Javítás: profilhoz kötött név, QLockFile és explicit UserAccessOption. A módosított forrásban szerepelnek.

Forrás: [QLocalServer jogosultságok](https://doc.qt.io/qt-6/qlocalserver.html).

### SEC-07 – Adatvédelmi maradó kockázat / meglévő szándékos működés

Hely: gamer_translator/defaults.py:166; gamer_translator/main_window.py:2195–2217, 1174; gamer_translator/settings_store.py:184–187.

Az aktív alkalmazás minden új vágólapképet feldolgoz, nem kizárólag a saját képkivágója által létrehozottat. OCR-módban a helyi képből kiolvasott szöveg, másik módban maga a kép a bejelentkezett ChatGPT-beszélgetésbe kerül. Az utolsó fordítás settings.json-ban olvasható szövegként, a böngésző munkamenete pedig tartós profilban marad meg.

Ezek README-ben jelzett alapfunkciók; az audit kedvéért nem kapcsoltam ki és nem változtattam meg őket. Dokumentálni kell az adatáramlást és a monitor kikapcsolását érzékeny vágólaptartalom előtt. A helyi profilhoz/adminisztrátori jogosultsághoz hozzáférő személy kockázatát a JS-origin védelme nem szünteti meg. Tényleges privát profil/adat tartalmát nem olvastam.

A globális begépelési gyorsbillentyű a Windows aktuális fókuszára támaszkodik. A végső audit még azonosított egy várakozási rést: a módosítóbillentyűk felengedése előtti ablakváltás az új ablakot választhatta ki. Ez is javítva lett: a célablak már a gyorsbillentyű aktiválásakor rögzül (`main_window.py:3136`), hiányzó ablaknál azonnal leáll, és a felengedés után, valamint minden karakter előtt ellenőrzés történik (`main_window.py:3197`). Három külön regresszió igazolja a várakozás alatti ablakváltás és hiányzó célablak elutasítását, valamint a változatlan célablak megtartását. Maradó platformkorlát, hogy a `GetForegroundWindow` ellenőrzés és a `SendInput` nem egyetlen atomi Windows-művelet: teljes célablak-garanciát a védelem nem jelent. A gyorsbillentyűtől a begépelés végéig maradjon a kívánt szövegmező aktív; érzékeny mezőnél a funkció kikapcsolandó. Valódi felhasználói ablakba nem gépeltem tesztadatot.

### SEC-08 – Közepes / buildbiztonság: az örökölt PATH idegen natív DLL-t adott a csomaghoz

Hely: `build.ps1` csomagolási környezete; a `6c93262a971096a829c3741d3c17c8b7ee4cc245e5eaca9da6da0f38da7216ca` SHA256 hash-ű köztes EXE `icuuc.dll` bejegyzése. Ez a követő ellenőrzésben feltárt csomagolási hiba, nem a kiindulási forrás sorszámaihoz kötött megállapítás.

Bizonyíték: a PyInstaller az örökölt PATH-on elérhető Poppler-környezet ICU 78.3 könyvtárát választotta. A becsomagolt `Qt6Core.dll` húsz verzióutótag nélküli ICU-exportot igényel, amelyet ez a DLL nem adott; a natív függőségi elemzés ezért egyetlen eltérő élt jelzett: `PySide6/Qt6Core.dll` → `icuuc.dll`. A tényleges EXE-indítás a QtCore importjánál „missing procedure” hibával állt le. A `frozen-dll-analysis.json` import/export-listáját és hash-eit az audit is áttekintette; a runtime-agent szerint a vizsgált MSVC-függőségek exportjai megfeleltek.

Hatás: a rögzített Python-csomaglista és a forrásazonosság ellenére a build az operátori környezet más termékének natív komponensét csomagolta. Ebben az esetben indítási hiba volt az igazolt következmény. Rosszindulatú DLL-t vagy kihasznált kódvégrehajtást nem állapítottunk meg; a tanulság a natív buildfüggőségek eredetének ellenőrzése.

Biztonságos reprodukálás: az EXE archívumából kinyert PE-importok/exportok statikus összevetése az alkalmazás elindítása nélkül. A valódi indítási próba elkülönített tesztmódot kért, és már az importnál sikertelen volt; nem jutott személyes profilhoz vagy online promptküldésig.

Javítás: a `build.ps1:60–65` előbb feloldja a kiválasztott interpreter útvonalát, majd a build folyamatában a rendszerkönyvtárra, Windows-gyökérre és az interpreter könyvtárára korlátozza a PATH-ot; a `build.ps1:116–117` `finally` ága az eredeti PATH-ot visszaállítja. Ezt az audit forrásban is ellenőrizte. Idegen Poppler ICU helyett a célrendszer rendszerfüggőségét használja; Windows-rendszerfájlt nem módosítottunk vagy csomagoltunk önkényesen a kiadásba.

A minimális fagyasztott Qt-próba sikeres, Python 3.13.15 / Qt 6.11.2 alatt valóban `C:\Windows\System32\icuuc.dll` töltődött be. Az örökölt PATH visszaállításával elindított próbánál is ez történt (`qt-probe-result.json`, `qt-probe-restored-path-result.json`). Az új `verified` alkalmazáscsomag 32 statikus ellenőrzése sikeres; a manifest külön igazolja az idegen ICU hiányát, a szükséges rendszerexportokat és a kritikus natív fájlok egyezését. A konkrét DLL-feloldási hiba javítása igazolt, és a teljes alkalmazáscsomag 109 ciklusos offline öntesztje is sikeres. A külön `frozen-path-contamination-verified.json` 360 natív fájl elemzésén 0 parse-hibát és 0 hash-egyezést jelez a vizsgált Poppler/MinGW forráskönyvtárakkal; a korábbi 48 idegen csomagbejegyzés eltűnt. A vizsgálat nem modellezi az összes dinamikus `LoadLibrary` hívást. A korábbi Defender „nem talált fenyegetést” eredmény a kompatibilitási hibát nem cáfolta.

## További ellenőrzések

- Titokminták: a kezdeti 11 követett fájl után a végső vizsgálat 42 követett vagy új, Git által nem kizárt Python/JavaScript/PowerShell/szöveges dokumentációs fájlra terjedt ki. Privátkulcs, OpenAI/GitHub/AWS token és hozzárendelt hardcoded secret minták: 0 találat. Ez mintaalapú ellenőrzés, nem történelmi teljes git secret audit; nem olvasta a személyes profil vagy vágólap tartalmát.
- Nincs QWebChannel, általános natív QObject bridge, közvetlen külső promptfeldolgozó HTTP-szerver, eval vagy pickle betöltés a saját forrásban.
- A JSON-ból JS payloadba továbbítás json.dumps-t használ, a JS DOM-kezelés nem épít felhasználói HTML-t innerHTML/eval útvonalon.
- A külső fordítás és státuszszöveg QLabel esetén PlainText lett; ezzel HTML-ként történő félreértelmezés nem marad a módosított megjelenítőkben.
- QTWEBENGINE_DISABLE_SANDBOX, QTWEBENGINE_REMOTE_DEBUGGING nincs beállítva az örökölt környezetben; veszélyes Chromium flag-minták nem szerepeltek. Sandbox vagy tanúsítványellenőrzés kikapcsolását nem kértem/nem végeztem.
- Windows build 26200.9278, DisplayVersion 25H2; folyamat nem rendszergazdai. Defender vírus- és valós idejű védelem aktív, szignatúra 2026-08-30 02:40:13 +02:00; Domain/Private/Public tűzfalprofil aktív. A részletes, kizárólag metadata alapú pillanatfelvételt és korlátait a [kiegészítő ellenőrzés](followup-security.md) rögzíti; ez nem teljes OS sérülékenységi vizsgálat.
- Bandit 1.9.4 végső újrafuttatás a `main.py` és `gamer_translator` forrásokra: **4466 sor, 34 LOW, 0 MEDIUM, 0 HIGH, 0 kihagyott teszt**. A 34 figyelmeztetés részletes kézi triázsa alább olvasható. A parancs 1-es kilépési kódját ezek a figyelmeztetések okozzák; az eredményt nem kezeltük figyelmeztetésmentes sikernek.
- Licencek/szerzői jogok módosítása nem történt. Az ellenőrzött staging EXE Authenticode-állapota `NotSigned`; kiadói tanúsítvány és SignTool nem volt elérhető. Az aláírás előfeltételeit és biztonságos segédprogramját a [kiegészítő ellenőrzés](followup-security.md) részletezi. A bináris futási bizonyítékot mindig a konkrét build hash-éhez kell kötni; a statikus audit önmagában nem EXE-indítási teszt.
- Az új `dist/staging/verified/Gamer Translator.exe` külön Defender-vizsgálata befejeződött, 0-s kilépéssel és explicit „found no threats.” kimenettel. A 381 500 794 bájtos fájl SHA256 hash-e előtte/utána és a manifestben azonos: `465a14948960d4e4d836068462993ad97dc4f3859a0fe069b357775d184c8867`. `-DisableRemediation` mellett nem kért javító műveletet. Tartós eredmény: `evidence/defender-final.json` és `.txt`. Ez nem helyettesíti a futási tesztet vagy a maradó natív advisoryk kezelését.
- A `dist/staging/python313-final/Gamer Translator.exe` köztes kiadásjelölt Defender-vizsgálata befejeződött, 0-s kilépéssel és explicit „found no threats.” kimenettel. A 398 996 348 bájtos fájl SHA256 hash-e előtte/utána változatlan: `6c93262a971096a829c3741d3c17c8b7ee4cc245e5eaca9da6da0f38da7216ca`. `-DisableRemediation` mellett nem kért javító műveletet. Történeti eredmény: `evidence/defender-qtcore-failed.json` és `.txt`. Ennek a fájlnak a tényleges indítása QtCore DLL-betöltési hibával sikertelen volt: a scan nem futási vagy kiadási PASS. A fenti `verified` változatot az újracsomagolás után külön ellenőriztük; a két fájl eredménye nem cserélhető fel.

### Bandit kézi triázs

| Jelzés | Darab és aktuális hely | Értékelés |
| --- | --- | --- |
| B404 / B603 | 3; `main_window.py:8`, `1952`, `2050` | Subprocess-import és újraindítás. Argumentumlista, nincs `shell=True`; az újraindítási PowerShellben a fájlnév és argumentumok külön, tesztelt idézést kapnak. Nem közvetlen webes vagy OCR-válaszból képződik parancs. |
| B606 / B607 | 2; `main_window.py:3155` | A konstans `ms-screenclip:` Windows-protokoll megnyitása. Nem tetszőleges, távoli adatból összeállított shellparancs. Elkülönített tesztmódban a gyorsbillentyűs útvonal tiltott. |
| B110 | 5; `main_window.py:2514`, `2587`, `2758`, `3466`, `3496` | Best-effort állapotfrissítés/takarítás hibáinak mellőzése; nem origin-, integritás- vagy jogosultságellenőrzés elnyelése. |
| B101 | 7; `ocr_service.py:615–619`, `894`, `904` | Windows OCR importok és belső listatípus invariánsai. Nem a modell hash-ét, HTTPS-t vagy a képméretet védő feltételek; ezek explicit kivételt dobnak. |
| B101 | 17; `self_test.py:185–247` | Szándékos, explicit tesztállítások; nem csendben kihagyott ellenőrzések. Az audit által jelzett optimalizálási rést a `sys.flags.optimize` explicit elutasítása javítja a teszt előtt. Valódi `python -O` futás 1-es kóddal, 0 ciklussal és `passed=false` jelentéssel állt le. |

Ezekből a végső forrásban nem azonosítottam új bizonyított sérülékenységet. A figyelmeztetések a nyers JSON-ban megmaradtak, nincs `nosec` elnyomás. Az optimalizált önteszt elutasítását az `evidence/optimized-self-test-rejected.json` bizonyítja.

### Az elkülönített tesztmód biztonsági határai

A `main.py:150` belépési pont a `--self-test-report` és `--staging` módot a normál profil, vágólap és egyetlen példány kezelése előtt választja le. A `MainWindow` ideiglenes `SettingsStore`-t és memóriában élő vágólapot kap; a Qt-profil off-the-record. A `self_test.py` letiltja a natív gyorsbillentyűt, tray-ikont, hangot, ébrentartást és normál újraindítást. Az alapérték-visszaállítás sem kapcsolhatja vissza véletlenül ezeket az illesztőket. A személyes profil tartalmát a teszt nem másolja át.

A `--self-test-report` felülírja a Qt platformot `offscreen` értékre, helyi HTML fixture-t használ, és az oldal `data:`, `blob:`, `about:` sémán kívüli kéréseit interceptor tiltja. A képútvonal szintetikus PNG-t kap a memóriavágólapról. A kéréslista ürességének ellenőrzése a WebEngine-oldal kéréseire vonatkozik, nem teljes rendszer- vagy folyamatszintű hálózati csomagrögzítés. Sandboxot, TLS- vagy tanúsítványellenőrzést a teszt nem kapcsol ki.

Az opcionális `--self-test-model-dir` a csomag által megadott három modell helyi példányát SHA256-ellenőrzés után másolja a teszt ideiglenes könyvtárába. A motorpróba szintetikus „Hello gamer” képet használ. Hiányzó vagy hibás modell esetén leáll; nem pótlólagos hálózati modellletöltésből kell sikeressé tennie a próbát. A `source-self-test-ocr.json` szerint az új interpreter alatt mindkét natív motor a várt szöveget adta, a takarítás is sikeres.

A `--staging` ezzel szemben szándékosan élő ChatGPT-oldalt nyit friss, memóriabeli profillal, automatikus vágólapfigyelés nélkül. Ez nem offline mód és nem a szolgáltató staging környezete. A tesztfőfolyamat egyetlen, bejelentkezés nélküli, szintetikus angol promptjára „Szia, gamer!” választ figyelt meg (`evidence/live-chatgpt-smoke.json`). Ez a forrásból futó szöveges útvonal egyszeri kompatibilitási bizonyítéka; nem igazolja az éles képbeküldést, a bejelentkezést vagy a teljes bináris működést. További élő promptot az audit nem küldött.

## Javított forrásban ellenőrzött pontok

Az alábbi sorszámok a jelentés készítésekor aktuális munkafára vonatkoznak; a fenti megállapítások kiindulási sorszámaitól eltérhetnek.

| Ellenőrzés | Aktuális hely | Állapot |
| --- | --- | --- |
| Natív vágólapkezelés, webes clipboard API tiltása | `gamer_translator/main_window.py:1202` | Forrásban ellenőrizve |
| Látható, tokenmentes origin címke | `gamer_translator/main_window.py:2117` | Forrásban ellenőrizve |
| Python és JavaScript origin-védelem, ApplicationWorld | `gamer_translator/main_window.py:3537`, `gamer_translator/automation.js:7` | Forrásban és offline Qt tesztben ellenőrizve |
| Fordítás PlainText megjelenítése | `gamer_translator/main_window.py:570` | Forrásban ellenőrizve |
| Begépelés leállítása a várakozás és begépelés közbeni fókuszváltáskor, SendInput eredmény ellenőrzése | `gamer_translator/main_window.py:3136`, `3197` | Forrásban és regresszióban ellenőrizve; platformkorlát: SEC-07 |
| Modifier felengedési timeout eredményének kezelése | `gamer_translator/main_window.py:3181` | Forrásban ellenőrizve |
| OCR-modell letöltés utáni hash-vizsgálata | `gamer_translator/ocr_service.py:264` | 4 független offline teszt és valódi modellletöltés sikeres |
| Kép erőforráskorlátja | `gamer_translator/main_window.py:3604`, `gamer_translator/ocr_service.py:350` | Forrásban és regresszióban ellenőrizve |
| Profilhoz kötött egyetlen példány és user-only IPC | `main.py:101` | Forrásban ellenőrizve |
| Atomikus beállításmentés | `gamer_translator/settings_store.py:205` | Forrásban ellenőrizve |
| Ideiglenes profil, memóriavágólap, letiltott natív mellékhatások | `gamer_translator/self_test.py:58`, `93` | Forrásban és elkülönített tesztben ellenőrizve |
| Optimalizált Python-mód elutasítása az öntesztben | `gamer_translator/self_test.py:175` | Explicit védelem, negatív futás sikeres |

A végső regressziós készletben 70 Python teszt sikeres 10,626 másodperc alatt (`unittest-python313.txt`), és 13 JavaScript teszt is sikeres (`javascript-tests-final.txt`), összesen 83 regresszió. A részleges Windows-begépelés utáni billentyűfelengedés, a módosítóbillentyűkre várás közbeni ablakváltás, az elkülönített folyamat valódi kilépése és a build PATH-jának sikeres/hibás build utáni pontos helyreállítása külön regressziót kapott. Ezen túl Python 3.13.15 alatt 120,496 másodperces, 106 ciklusos forrás-önteszt sikeres (`source-self-test-python313.json`), külön natív OCR-próbával és optimalizált módot elutasító negatív próbával. A teszt-EXE-ről, a pontos végső buildről és a chatgpt.com kompatibilitásának nyitott feltételeiről a [tesztelési jelentés](test-report.md) számol be; a statikus audit nem helyettesíti azokat.

A tényleges végső EXE-próba a `465a14948960d4e4d836068462993ad97dc4f3859a0fe069b357775d184c8867` SHA256 hash-ű, 381 500 794 bájtos `verified` fájlon is sikeres: `frozen=true`, 109 szövegciklus, egy PNG-útvonal, 122,365 másodperc belső tesztidő, 7/7 sikeres ellenőrzés és tiszta kilépés. RapidOCR és Windows OCR is pontosan „Hello gamer” eredményt adott. A fő tesztfolyamat 0-s kilépési kódot rögzített; a nyers alkalmazásjelentés a `frozen-self-test.json`. Ez offline, szintetikus tartalmú próba, nem a személyes profil vagy a bejelentkezett szolgáltatás teljes tesztje.

## Bizonyítékfájlok

Bizonyítékok helye: `C:\Users\juher\AppData\Local\Temp\gamer-translator-security-02616877c9f5415db9bba45538fdb505`. Ezek ideiglenes auditkimenetek, nem a forráscsomag részei.

- installed.txt: eredeti globális 43 csomag snapshotja.
- pip-audit.json: eredeti audit nyers kimenete, duplikált advisory rekordokkal.
- staging-installed.txt: az első staging .venv 41 csomagjának történeti verziólistája.
- staging-pip-audit.json: az első staging audit, 0 találat.
- bandit-final.json: a végső forrás statikus ellenőrzésének mind a 34 figyelmeztetése.

A végső ellenőrzések tartós másolatai a [docs/evidence](evidence/) könyvtárban szerepelnek: `pip-audit-python313.json`, `dependency-audit-python313.txt`, `python-runtime-upgrade.json`, `python-runtime-installer.json`, `bandit.json`, a Python/JavaScript tesztkimenetek, a `source-self-test-python313.json`, `source-self-test-ocr.json`, `optimized-self-test-rejected.json`, `live-chatgpt-smoke.json`, `build-manifest.json`, `frozen-self-test.json`, `frozen-path-contamination-verified.json`, `defender-final.json` és `defender-final.txt`. A korábbi, Python 3.11-alapú és a QtCore-indítási hibás fájlok köztes bizonyítékok maradnak, nem írják felül az új runtime eredményeit. A fájlok nem tartalmaznak beolvasott privát beszélgetést, sütit vagy vágólaptartalmat. Bejelentkezett chatgpt.com funkcionális teszt és szolgáltatói infrastruktúra-audit nem történt.
