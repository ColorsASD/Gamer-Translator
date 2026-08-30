<p align="center">
  <img src="gamer_translator/assets/icon-1024.png" alt="Gamer Translator ikon" width="160" height="160">
</p>

# Gamer Translator

A Gamer Translator egy önálló Windows asztali alkalmazás, amely a `chatgpt.com` oldalt saját ablakban nyitja meg, és a képkivágásos fordítási munkafolyamatot közvetlenül ebből az ablakból kezeli.

## Fő képességek

- saját ablakos `chatgpt.com` felület
- kézi promptküldés a felső `Prompt elküldése` gombbal
- Windows képkivágó indítása gyorsgombbal
- vágólapról érkező képek automatikus beküldése a ChatGPT-be
- választható OCR mód, amely képről szöveget olvas ki és azt küldi a ChatGPT-nek
- az OCR mód alapértelmezetten bekapcsolt
- a kész fordítás automatikus visszamásolása a vágólapra
- a mentett fordítás karakterenkénti begépelése gyorsgombbal
- gyors chat overlay kézi szövegküldéshez
- szerkeszthető gyorsgombok lenyomásos rögzítéssel
- tálcaikon dupla kattintásos elrejtéssel és visszahozással
- háttérben tovább futó ChatGPT oldal lekicsinyítés vagy eltüntetés után is
- képernyő tetején megjelenő fordítási overlay `Betöltés...` állapottal
- egy példányos indítás, ahol a második megnyitás a meglévő ablakot aktiválja
- állítható overlay láthatóság és megjelenési idő
- a GPU gyorsítás módosítása mentés után automatikus újraindítással lép érvénybe

## Alap gyorsgombok

- `Alt + C`: Windows képkivágó megnyitása
- `Alt + V`: az utolsó mentett fordítás begépelése
- `Alt + X`: gyors chat overlay megnyitása

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
4. Használd a képkivágást, vagy illessz be képet a vágólapra.
5. Várd meg a fordítást.
6. Ha az app le van kicsinyítve vagy el van tüntetve, a fordítás felül egy overlay blokkban is megjelenik.
7. A `Szöveg kiolvasása képről` beállítás alapértelmezetten be van kapcsolva. Ilyenkor a program előbb OCR-rel kiolvassa a képen lévő szöveget, és ezt küldi el a ChatGPT-nek.
8. A kész szöveget illeszd be vágólapról, vagy használd a begépelési gyorsgombot.
9. Az `Alt + X` gyorsgombbal bármikor megnyitható a gyors chat overlay kézi szövegküldéshez.

## Fontos beállítások

- a `Szöveg kiolvasása képről` beállítás alapból aktív
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
- Aktív vágólapfigyelésnél a másolt képek vagy a belőlük kiolvasott szöveg automatikusan az aktuális ChatGPT-beszélgetésbe kerül. Érzékeny adatok másolása előtt kapcsold ki a figyelést.
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
