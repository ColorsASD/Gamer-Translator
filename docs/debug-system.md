# Esemény- és hibanaplózás

Ellenőrzés dátuma: 2026. október 1. A naplórendszer első kiadása: `5.12`.

A `5.13` kiadásban javított Alt+V, új ChatGPT üzenetfelület és további megszakítási események részletei az [Alt+V vizsgálati jelentésében](alt-v-audit.md) szerepelnek. Az alábbi ellenőrzési eredmények az első, `5.12` kiadáshoz tartoznak.

A `5.14` képes válaszfelismerési javítása és a kéréshez kötés új diagnosztikai mezői a [képes válaszfelismerés vizsgálati jelentésében](image-response-audit.md) szerepelnek.

## Naplók helye és működése

A normál alkalmazás automatikusan JSONL eseménynaplót ír a `%LOCALAPPDATA%\Gamer Translator\logs` könyvtárba. A Beállítások `Naplómappa megnyitása` gombja ezt a könyvtárat nyitja meg. A napló nem kerül feltöltésre.

Az aktuális fájl `gamer-translator.jsonl`. Az 5 MiB-os korlát elérésekor az előző fájl `.1` végződést kap; összesen öt korábbi fájl marad meg. A lemezírás külön háttérszálon fut, legfeljebb 4096 várakozó eseménnyel. A megtelt sor és a helyreállt lemezírás saját eseményt kap. Naplózási hiba nem állíthatja le a fordítást.

Minden sor helyi időzónás időbélyeget, folyamatazonosítót, szálazonosítót, alkalmazásverziót, munkamenet-azonosítót, eseménytípust és súlyosságot tartalmaz. A fordítási események közös `request_id` mezője összeköti a kérés teljes útját. A számszerű időtartamok ezredmásodpercben szerepelnek.

## Rögzített események

- alkalmazásindulás, Qt-importhiba, példánykezelés, kilépés és kezeletlen Python-kivételek
- ablak és böngésző betöltése, aktív vagy pihentetett állapot, háttérmód, újratöltés és böngészőfolyamat-leállás
- gyorsgombok regisztrálása, műveletindítás, várakoztatás, elutasítás és Windows-hibakódok
- képkivágási engedély, lejárat, kép mérete, előkészítési idő, sorba állítás és sorbetelés
- OCR-modellintegritás, motorindítás, feldolgozási variánsok, jelöltek száma, futásidő és hibák
- képbeillesztési kísérlet, feltöltés visszaigazolása, várakozás, tartalmi állapotjelzők és küldési szakasz
- válaszfelismerés, időtúllépés, késői válaszfigyelés, elavult eredmény elutasítása és fordítás mentése
- begépelés indítása, befejezése, fókuszváltás vagy új kérés miatti megszakítása
- beállításmentés, hibás beállításfájl és mentési hiba

A `runtime.snapshot` esemény 15 másodpercenként az alkalmazás és a megjelenítő folyamat CPU-idejét, memóriahasználatát, a szabad rendszermemóriát és az eseményhurok késését méri. A CPU-százalék a folyamat két mintavétel közötti CPU-idejéből számított, a gép logikai processzorszámára normalizált érték. Ez nem játékbeli FPS- vagy fizikai bemeneti késleltetés-mérés, és GPU-terhelést nem mér.

## Tartalomvédelem

A napló csak engedélyezett számlálókat, állapotjelöléseket és időtartamokat fogad el. Fordítás, prompt, OCR-szöveg, kép, vágólaptartalom, cookie, token, jelszó, teljes webcím és helyi fájlút nem kerül bele. A böngésző és a Qt által kiírt üzenetekből a súlyosság és a hossz marad meg. Kivételnél a típus, ismert forrásmodul, függvénynév és sorszám szerepel, a nyers hibaüzenet és a forrássor nem.

A napló nem rögzíti az összes lenyomott billentyűt: kizárólag az alkalmazás saját gyorsgombjaihoz tartozó műveleteket követi. Az offline önteszt és a staging külön ideiglenes naplómappát használ, a normál profilt nem éri el. A PyInstaller Python előtti bootloaderhibája nem jut el ehhez a naplózóhoz; ilyen esetben a Windows alkalmazáseseményeit is meg kell nézni.

## Hibakeresés

Hibánál jegyezd meg az időpontot és a műveletet. A kérés `request_id` mezőjével látszik, hogy a folyamat a kivágás, a csatolás, a küldés, a válasz vagy a begépelés szakaszában állt meg. Az előző fájlokat is meg kell tartani, mert a kérés kezdete már forgatott naplóba kerülhetett.

```powershell
.\.venv313\Scripts\python.exe tools\read_diagnostics.py --last 200
.\.venv313\Scripts\python.exe tools\read_diagnostics.py --level ERROR --last 50
.\.venv313\Scripts\python.exe tools\read_diagnostics.py --request-id <request_id>
.\.venv313\Scripts\python.exe tools\read_diagnostics.py --summary
```

A naplóolvasó a forgatott fájlokat időrendben olvassa. A hibás vagy félbeszakadt sorokat kihagyja és jelzi; a napló tartalmát nem módosítja.

## Javított működés

- Új fordítási kéréskor a régi mentett szöveg érvénytelenné válik. Sikertelen kérés után a begépelési gyorsgomb nem gépelheti be a korábbi választ.
- A válasz az új beküldött felhasználói üzenethez kötődik. Egy korábbi válasz újrarajzolása önmagában nem jelent új fordítást.
- A fájlkiválasztó mező saját beállítása nem igazolja a kép feltöltését. A kész csatoláshoz tényleges látható kép-előnézet és befejezett feldolgozás kell.
- Sikertelen csatolás után a saját, vissza nem igazolt fájlkijelölés törlődik, így nem blokkolja a következő kivágást. A valós csatolmány és a folyamatban levő feltöltés megmarad.
- A késői válaszfigyelés legfeljebb 120 másodpercig marad aktív. Új kérés után a korábbi válasz nem írhatja felül a legújabb eredményt.
- A késői válaszfigyelés lezárása megőrzi az utolsó választ akkor is, ha a felület eseménykezelése a lezárás idején késik.
- A várakozó jogosított képek sorba kerülnek. Begépelés közben a képkivágási gyorsgomb várakoztatható, nem vész el némán.
- A kiadás előtti audit az urllib3 2.7.0 függőségben három ismert hibát jelzett. A rögzített és becsomagolt függőség a javított 2.8.0 verzióra frissült.

Az urllib3 frissítését az upstream [HTTPS proxy TLS közleménye](https://github.com/urllib3/urllib3/security/advisories/GHSA-8988-9cw3-xx77), [Deflate-feldolgozási közleménye](https://github.com/urllib3/urllib3/security/advisories/GHSA-gh4c-6fx4-qh6g) és [chunked válaszok memóriahasználatáról szóló közleménye](https://github.com/urllib3/urllib3/security/advisories/GHSA-vxq7-64xx-v4gw) indokolja. Ez önmagában nem bizonyítja, hogy a korábban jelzett játék közbeni hibát ezek okozták.

Az ellenőrzések helyi, elkülönített DOM-mintákat és tesztprofilokat használnak. Az élő ChatGPT felülete és a játék közbeni működés későbbi vizsgálatához az új eseménynapló ad bizonyítékot.

## Ellenőrzés

- Python tesztek: 243/243 sikeres.
- JavaScript tesztek: 27/27 sikeres, szintaxisellenőrzés sikeres.
- Függőség-, fordíthatósági és diff-ellenőrzés sikeres.
- Friss pip-audit: 45 ellenőrzött függőség, az urllib3 frissítése után nulla ismert sérülékenység és nulla kihagyott csomag.
- A végleges EXE csomagellenőrzése: 34/34 sikeres, a beépített forrás és assetek egyeznek a munkafával.
- A végleges EXE offline öntesztje: 8/8 sikeres, hét fordítási ciklussal. A RapidOCR és a Windows OCR a mintaképen egyaránt `Hello gamer` szöveget adott.
- Külön Qt-próbában 40 naplóesemény keletkezett; a fordítás útja közös kérésazonosítóval követhető volt, a mintaszöveg és a fordítás nem került a naplóba.

A helyi EXE: `dist\staging\debug-system\Gamer Translator.exe`. Mérete: 381 554 780 bájt. SHA-256: `a5c59eb00b5bc0b7207460c6aaa901026420e7acaf4906d0c60bbf9d7363eb62`.

Az ellenőrzési állományok a `dist\staging\debug-system` könyvtárban találhatók: `build-manifest.json`, `frozen-self-test-release.json`, `python-tests-final.txt`, `node-tests-final.txt`, `release-pip-audit-fixed.json`, `release-defender-final.txt`, `offline-diagnostics.jsonl` és `ui-preview.png`. A kiadási fájl neve `Gamer-Translator-v5.12.exe`; ugyanazt az ellenőrzött EXE-t tartalmazza. A [kiadás előtti összesítés](evidence/debug-system-checks.json) a tesztek, az audit és a csomag ellenőrzési adatait tartalmazza.
