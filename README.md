<p align="center">
  <img src="gamer_translator/assets/icon-1024.png" alt="Gamer Translator ikon" width="160" height="160">
</p>

# Gamer Translator

A Gamer Translator egy önálló Windows asztali alkalmazás, amely a `chatgpt.com` oldalt saját ablakban nyitja meg, és a képkivágásos fordítási munkafolyamatot közvetlenül ebből az ablakból kezeli.

## Fő képességek

- saját ablakos `chatgpt.com` felület
- kézi promptküldés a felső `Prompt elküldése` gombbal
- Windows képkivágó indítása gyorsgombbal
- a saját képkivágási gyorsgombbal készített képek automatikus beküldése a ChatGPT-be
- választható OCR mód, amely képről szöveget olvas ki és azt küldi a ChatGPT-nek
- az OCR mód alapértelmezetten bekapcsolt
- a kész fordítás automatikus visszamásolása a vágólapra
- a mentett fordítás karakterenkénti begépelése gyorsgombbal
- gyors chat overlay kézi szövegküldéshez
- szerkeszthető gyorsgombok lenyomásos rögzítéssel
- külön AltGr-kezelés, kiosztáshelyes írásjelek és Mouse 4–5 egérgombok gyorsgombként
- tálcaikon dupla kattintásos elrejtéssel és visszahozással
- háttérben tovább futó ChatGPT oldal lekicsinyítés vagy eltüntetés után is
- képernyő tetején megjelenő fordítási overlay `Betöltés...` állapottal
- egy példányos indítás, ahol a második megnyitás a meglévő ablakot aktiválja
- állítható overlay láthatóság és megjelenési idő
- a GPU gyorsítás módosítása mentés után automatikus újraindítással lép érvénybe

## Alap gyorsgombok

- `Alt + C`: Windows képkivágó megnyitása és a kivágott kép fordítása
- `Alt + V`: az utolsó mentett fordítás begépelése
- `Alt + X`: gyors chat overlay megnyitása

## Gyorsgombok beállítása

- Kattints a kívánt gyorsbillentyű mezőjére, majd nyomd le a kombinációt. A módosítás után mentsd el a beállításokat.
- Az `AltGr` külön módosítóként jelenik meg, nem keveredik a külön lenyomott `Ctrl + Alt` kombinációval. Magyar kiosztáson például az `AltGr + -` az alapgombot rögzíti, nem a begépelt `*` karaktert.
- A `Mouse 4` és `Mouse 5` az egér két oldalsó gombja. Önmagukban és módosítókkal, például `Ctrl + Mouse 4` kombinációként is használhatók mindhárom művelethez.
- A gyorsgomb rögzítése közben a meglévő gyorsgomb nem indít műveletet. A hozzárendelt oldalsó egérgomb használatakor a program elnyeli a vissza/előre eseményt; a többi egérgomb működése változatlan.
- A bekapcsolt, elmentett gyorsgombok főgombjának lenyomását, ismétlését és felengedését a program elnyeli, így a szokásos Windows-billentyűüzeneteket használó aktív alkalmazás nem kapja meg ugyanazt a parancsot. Ez a Mouse 4–5 gombokra és a külső makróprogram által előállított kombinációkra is vonatkozik; a program saját szövegbegépelése kivétel.
- Az elnyelt Alt/Win kombináció után a program maszkolja a menü/Start véletlen megnyitását. Az önálló módosítógombokat és a nem hozzárendelt kombinációkat nem tiltja le. Átkötés vagy kikapcsolás közben a már elnyelt főgomb a felengedéséig elnyelt marad.
- A gyorsgombok nem garantálhatnak minden programmal szemben elsőbbséget. Egy korábban értesített globális hook, a Windows védett billentyűparancsa, illetve a hookot megkerülő közvetlen játék-/illesztőprogram-bemenet nem zárható ki ezzel a módszerrel. Más program jogosultságait és gyorsgomb-beállításait az alkalmazás nem módosítja. A Windows működését a [hookok leírása](https://learn.microsoft.com/en-us/windows/win32/winmsg/about-hooks) és a [billentyűhook dokumentációja](https://learn.microsoft.com/en-us/windows/win32/winmsg/lowlevelkeyboardproc) részletezi.
- Az írásjelek natív Windows-gombazonosítóval kerülnek mentésre; a mezőben az aktuális kiosztás szerinti alapgomb neve látszik. A korábban hibásan rögzített kombinációt újra kell rögzíteni.
- Az `Fn` önálló felismerése billentyűzetfüggő. Ha a billentyűzet nem továbbítja a Windowsnak, általános gyorsgombként nem rögzíthető. Ha a gyártói szoftver támogatja, például `F13`–`F24` gombra átkötve használható. Az `Fn`-nel előállított, Windows által felismert normál billentyű rögzíthető.
- Ha az egér gyártói szoftvere a Mouse 4–5 gombot billentyűkombinációvá alakítja, az alkalmazás azt a kombinációt látja. A közvetlen egérgombos használathoz a gomb küldjön hagyományos vissza/előre oldalgomb-eseményt.

## Projektstruktúra

- `main.py`: a program belépési pontja
- `build.ps1`: `.exe` build PowerShellből
- `requirements.txt`: Python függőségek
- `gamer_translator/`: az alkalmazás forráskódja és assetjei

## Futtatás fejlesztés közben

1. Hozz létre külön környezetet a frissített Python 3.13 futtatóval:
   `py -3.13 -m venv .venv313`
2. Telepítsd az ellenőrzött függőségeket:
   `.\.venv313\Scripts\python.exe -m pip install -r requirements-lock.txt`
3. Indítsd el a programot:
   `.\.venv313\Scripts\python.exe main.py`

A `requirements.txt` a függőségek általános követelményeit, a `requirements-lock.txt` a Windows/Python 3.13.15 környezetben ellenőrzött pontos verziókat tartalmazza. A Windows OCR a karbantartott WinRT csomagokat használja. Verziófrissítés után a teszteket és a biztonsági auditot újra kell futtatni. A korábbi `.venv` környezet megmaradt; az új kiadás a `.venv313` környezetből készül.

## Exe készítése

PowerShellből a projekt gyökérmappájában:

```powershell
.\build.ps1 -PythonExecutable .\.venv313\Scripts\python.exe
```

Az elkészült egyfájlos program a `dist\Gamer Translator.exe` fájlba kerül.

Elkülönített tesztbuild a korábbi program felülírása nélkül:

```powershell
.\build.ps1 -PythonExecutable .\.venv313\Scripts\python.exe -OutputDirectory dist\staging\verified -SkipDependencyInstall
```

A `-SkipDependencyInstall` kapcsolót csak előzetesen telepített és ellenőrzött környezettel használd. Sikertelen build nem írja felül a korábbi programot.

## Használat

1. Indítsd el a programot.
2. Jelentkezz be a ChatGPT-be a megnyíló saját ablakban.
3. A `Prompt elküldése` gombbal küldd el a kézi promptot az aktuális beszélgetésbe.
4. Nyomd meg a beállított képkivágási gyorsbillentyűt (alapból `Alt + C`), majd jelöld ki a fordítandó területet. A `Win + Shift + S` billentyűvel készített vagy más módon vágólapra másolt kép nem indul el automatikus fordításra.
5. Várd meg a fordítást.
6. Ha az app le van kicsinyítve vagy el van tüntetve, a fordítás felül egy overlay blokkban is megjelenik.
7. A `Szöveg kiolvasása képről` beállítás alapértelmezetten be van kapcsolva. Ilyenkor a program előbb OCR-rel kiolvassa a képen lévő szöveget, és ezt küldi el a ChatGPT-nek.
8. A kész szöveget illeszd be vágólapról, vagy használd a begépelési gyorsgombot.
9. Az `Alt + X` gyorsgombbal bármikor megnyitható a gyors chat overlay kézi szövegküldéshez.

## Fontos beállítások

- a `Szöveg kiolvasása képről` beállítás alapból aktív
- az automatikus képfordítás csak a saját képkivágási gyorsbillentyűhöz tartozik; az `Esc` megszakítja a várakozást, a következő kivágásra legfeljebb 45 másodperc áll rendelkezésre
- ha a GPU gyorsítás állapota megváltozik és elmented a beállításokat, a program automatikusan újraindul

## Tálca és háttérmód

- az `X` gomb tálcára rejti az alkalmazást
- a tálcaikon dupla kattintásra elrejti vagy visszahozza az ablakot
- jobb kattintással `Eltüntetés` és `Kilépés` menü érhető el
- eltüntetve vagy lekicsinyítve is tovább fut a fordítási folyamat
- a programból egyszerre csak egy példány futtatható

## Megjegyzés

- A projekt nem az OpenAI API-t használja, hanem a webes ChatGPT felületet.
- A működés a `chatgpt.com` oldal felépítésére épül, ezért egy nagyobb felületi változás után a DOM-kezelést frissíteni kellhet.
- Az automatizálás csak a `https://chatgpt.com` és a `https://chat.openai.com` főoldali eredeten használható. Külső oldalon leáll, az aktuális eredet az ablak felső részén látható.
- Aktív programnál a saját képkivágási gyorsbillentyű után érkező első vágólapkép vagy a belőle kiolvasott szöveg automatikusan az aktuális ChatGPT-beszélgetésbe kerül. A kivágásra várakozás közben ne másolj más képet a vágólapra; az `Esc` vagy a külön megnyomott `Win + Shift + S` törli ezt az egyszeri küldési engedélyt.
- A program a legutóbbi fordítást és a böngésző munkamenetét helyben megőrzi. A begépelési gyorsgomb az aktív ablakba ír; sortörést és tabulátort is küldhet, ezért terminálban ne használd.
- A vágólap képkorlátja 40 millió képpont és 20 MiB PNG-adat. Az OCR modelleket a program SHA-256 ellenőrzés után tölti be.

## Ellenőrzés és telepítés

```powershell
.\.venv313\Scripts\python.exe -m unittest discover -s tests -v
node --test tests\test_automation.cjs
```

A tesztek helyi DOM-mintával és elkülönített adatokkal futnak; nem küldenek ChatGPT-üzenetet. A JavaScript tesztekhez Node.js szükséges, az elkészült program futtatásához nem.

A kész EXE külön offline önteszttel is ellenőrizhető:

```powershell
& '.\dist\staging\verified\Gamer Translator.exe' --self-test-report '.\dist\staging\verified\self-test.json' --self-test-duration 120
```

A jelentésben a `passed: true` és a sikeres kilépési kód jelzi a lefutást. Az önteszt nem nyitja meg a normál profilt, nem használja a rendszer vágólapját, nem regisztrál globális gyorsbillentyűt, és a mintalap külső hálózati kéréseit blokkolja. Az offline képpróba a csatolást ellenőrzi, az OCR minőségét külön mérjük.

A `--staging` kapcsoló ideiglenes profillal nyitja meg az élő ChatGPT-t, kikapcsolt figyeléssel és rendszerintegrációk nélkül. A sütik csak a memóriában maradnak. Ez a helyi alkalmazás tesztmódja, nem az OpenAI belső tesztkörnyezete; a kézzel elküldött szöveg az élő szolgáltatáshoz kerül.

- [Változtatások leírása](docs/changes.md)
- [Telepítési útmutató](docs/deployment.md)
- [Tesztelési jelentés](docs/test-report.md)
- [Biztonsági audit](docs/security-audit.md)
- [Kódaláírás és Windows biztonsági ellenőrzés](docs/followup-security.md)

## Licenc

Ez a projekt saját tulajdonú, minden jog fenntartva.

A forráskód, a dokumentáció és a kapcsolódó állományok használata, másolása, módosítása, terjesztése vagy továbbadása kizárólag előzetes írásos engedéllyel lehetséges. A részletek a `LICENSE.txt` fájlban találhatók.
