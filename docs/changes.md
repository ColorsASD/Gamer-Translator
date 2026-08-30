# Változtatások leírása

Ellenőrzés dátuma: 2026. augusztus 30. Kiinduló commit: `13d6dce`.

A Gamer Translator meglévő Windows alkalmazása lett javítva. A módosítás nem alakítja át a programot webalkalmazássá, API-klienssé vagy ChatGPT pluginná. A licenc és a szerzői jogi szövegek változatlanok.

## Böngésző és automatizálás

- A natív kód és az oldaloldali JavaScript ellenőrzi az engedélyezett HTTPS eredetet. A Python oldal a portot és a felhasználói adatokat is vizsgálja; megtévesztő hostnév és nem HTTPS cím elutasítva.
- Az automatizálás Qt `ApplicationWorld` környezetben fut, így az oldal saját azonos nevű JavaScript függvényei nem írják felül a natív kézbesítést.
- A weboldalak általános JavaScript vágólapolvasási és -írási engedélye megszűnt. A program natív vágólapkezelése és a DOM-eseményen keresztüli képfeltöltés megmaradt.
- Az aktuális webes eredet a felső eszközsáv alatt látható. Az URL jelszava, lekérdezési paraméterei és töredéke nem jelenik meg.
- A párhuzamos küldések nem írhatják felül egymás beviteli mezőjét. A kézi művelet közben érkező vágólapellenőrzés későbbre kerül.
- A prompt csak teljes, normalizált egyezés után küldhető el; részleges vagy visszaállított bevitelnél hiba jelzi a sikertelen beillesztést.
- A kép adatURL típusa, base64 tartalma és mérete ellenőrzött. A vágólap képére kódolás előtti pixelkorlát is érvényes.
- A `thinking` szót tartalmazó rendes fordítás nem vész el állapotjelzésként. Az inline formázás nem szúr szóközt a szó vagy parancs közepébe.
- A kézi küldés helyreállítása DOM-változás nélkül is felébred az időzítő lejártakor; saját automatizált esemény nem indít új kézi helyreállítást.

## Natív működés és tárolás

- A fordítási overlay és a futási állapotok egyszerű szövegként jelennek meg; a külső tartalom nem értelmeződik HTML-ként.
- A hibás JSON-szerkezet és UTF-8 nem állítja le az indulást. A logikai beállítások kezelik a szöveges `false` értéket, az időzítők és overlayértékek korlátozott tartományban maradnak.
- A beállítások ideiglenes fájlon keresztül, atomikus cserével íródnak ki, így a megszakadt mentés megőrzi az előző fájlt.
- A programszintű zárolás profilonként történik. A Windows helyi IPC ugyanahhoz a felhasználóhoz korlátozott, az importálás nem nyitja meg a normál alkalmazásprofilt.
- A begépelés nem indul el, ha a módosítóbillentyű nem lett felengedve; aktív ablak váltásakor megáll. A Windows által elutasított bevitel nem kap sikerjelzést.
- A Windows billentyűzetfüggvények megfelelő natív típusokat kapnak. Az újraindítás megőrzi a szóközös és idézőjeles argumentumokat.
- Részlegesen elfogadott begépelés után a program megkísérli a szintetikus billentyűk felengedését, így a módosítóbillentyűk elengedése sem marad ki a hibakezelésből.
- A begépelés célablaka már a gyorsbillentyű aktiválásakor rögzül. Ha a felengedésre várakozás alatt másik ablak kerül előtérbe, a program nem kezd el oda írni. A Windows előtér-ellenőrzése és a billentyűbevitel nem atomi művelet, ezért ez kockázatcsökkentés, nem abszolút célablak-garancia.

## OCR és build

- A frissen letöltött OCR modell ellenőrzőösszegét a program maga is ellenőrzi. Hiányzó vagy hibás SHA-256 esetén a modell nem kerül betöltésre; sikeres ellenőrzés után atomikus csere történik.
- Az OCR a kép teljes dekódolása előtt méretkorlátot alkalmaz. Az átlátszó hátteret fehérre helyezi, így nem tűnik el a fekete szöveg.
- Az öt feletti OCR-jelölt igényét a gyors feldolgozási ág helyesen számolja.
- A RapidOCR 3.9.2 kompatibilitási hibája javítva: a motor a csomag metaadatai alapján letöltött tényleges modellfájlokat és az ONNX modell saját karakterkészletét használja a megszűnt szótárútvonal helyett.
- A build külön ideiglenes könyvtárban készül, ellenőrzi a külső parancsok kilépési kódját és a létrejött fájlt. Csak siker után cseréli a célprogramot, más EXE-t nem töröl.
- A Python futtató és a kimeneti könyvtár paraméterezhető; a tesztelt függőségek pontos verzióját külön lockfájl rögzíti.
- Külön Python 3.13.15 / OpenSSL 3.0.21 futtatókörnyezet készült. A korábbi Python és `.venv` megmaradt; az új build a `.venv313` környezetet használja. A Windows OCR a Python 3.13-mal kompatibilis WinRT csomagokra váltott.
- Az OCR rangsorában a RapidOCR indokolatlan fix előnye megszűnt; több felismerő egyezése számít, ugyanannak a motornak több képszűrője nem ad sokszoros támogatást.
- Az átfedő szövegdobozok közös képrésze korlátozott számú újraolvasást kap. A program nem töröl találomra szavakat, és nem alkalmaz mintaszövegre írt ékezetjavítást.
- Az üres OCR-elemek kiszűrése megőrzi a koordináták és szövegek párosítását. Az angol aposztróf és az önálló, értelmes betű nem számít automatikusan zajnak.
- A 19 generált mintából 7 helyett 15 lett karakterpontos; 32 helyett 5 karakterhiba maradt. A külön ellenőrző minták eredménye és a megmaradt hibák a [mérési jelentésben](evidence/ocr-quality-benchmark.json) szerepelnek.

## Elkülönített tesztelés

- A `--self-test-report` kapcsoló a kész EXE-n belül is futtatható offline alkalmazáspróbát indít, külön ideiglenes fájlprofillal, memóriavágólappal és nem tartós böngészőprofillal. A külső rendszerintegrációk nem futnak.
- A `--self-test-model-dir` kapcsolóval helyi, hash-ellenőrzött modellekből a becsomagolt RapidOCR és Windows OCR motor tényleges felismerése is ellenőrizhető, modellletöltés nélkül.
- Az önteszt optimalizált Python-módban hibával leáll; kikapcsolt ellenőrzésekkel nem adhat sikeres jelentést.
- A `--staging` kapcsoló külön, ideiglenes profillal nyitja meg az élő ChatGPT-t. A figyelés kezdetben kikapcsolt, a rendszer vágólapja és a globális gyorsbillentyűk nem használhatók. A tesztmód nem jelent OpenAI staging-hozzáférést.
- A staging ablak eseményhurokban mért kilépési hibája javítva lett: az utolsó ablak bezárása explicit kilépést kér, így nem marad láthatatlanul futó új tesztpéldány. Ezt külön folyamatban, a temp profil felszabadulásával együtt teszteljük.
- A `tools/verify_build.py` minden saját Python-modul forrásegyezését, az asseteket és a natív futtatókönyvtárakat is ellenőrzi. A build figyelmeztetései az ideiglenes könyvtár takarítása után is megmaradnak.
- Az EXE-ben igazolt QtCore/ICU indulási hiba javításához a build PATH-ja elkülönül a többi fejlesztőeszköztől. A csomag nem a PDF-eszköz idegen ICU DLL-jét használja; az eredeti PATH a build után siker és hiba esetén is helyreáll. A javítást külön, ténylegesen futtatott Qt-próba is ellenőrzi.
- Kiadói tanúsítványhoz kötött aláíró segédprogram készült. Az aláírás és az időbélyegzés csak érvényes tanúsítvány és hiteles SignTool meglétekor fut; az eredeti staging EXE megmarad.

A biztonsági döntések okát a módosított kódrészletek rövid magyar megjegyzései és a [biztonsági audit](security-audit.md) részletezik.
