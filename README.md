<p align="center">
  <img src="gamer_translator/assets/icon-128.png" alt="Gamer Translator ikon" width="128" height="128">
</p>

# Gamer Translator

A Gamer Translator egy önálló Windows asztali alkalmazás, amely a `chatgpt.com` oldalt saját ablakban nyitja meg, és a képkivágásos fordítási munkafolyamatot közvetlenül ebből az ablakból kezeli.

## Fő képességek

- saját ablakos `chatgpt.com` felület
- kézi promptküldés a felső `Prompt elküldése` gombbal
- Windows képkivágó indítása gyorsgombbal
- vágólapról érkező képek automatikus beküldése a ChatGPT-be
- a kész fordítás automatikus visszamásolása a vágólapra
- a mentett fordítás karakterenkénti begépelése gyorsgombbal
- szerkeszthető gyorsgombok lenyomásos rögzítéssel
- tálcaikon dupla kattintásos elrejtéssel és visszahozással
- háttérben tovább futó ChatGPT oldal lekicsinyítés vagy eltüntetés után is
- képernyő tetején megjelenő fordítási overlay `Betöltés...` állapottal
- egy példányos indítás, ahol a második megnyitás a meglévő ablakot aktiválja
- állítható overlay láthatóság és megjelenési idő

## Alap gyorsgombok

- `Alt + C`: Windows képkivágó megnyitása
- `Alt + V`: az utolsó mentett fordítás begépelése

## Projektstruktúra

- `main.py`: a program belépési pontja
- `build.ps1`: `.exe` build PowerShellből
- `requirements.txt`: Python függőségek
- `gamer_translator/`: az alkalmazás forráskódja és assetjei

## Futtatás fejlesztés közben

1. Telepítsd a függőségeket:
   `python -m pip install -r requirements.txt`
2. Indítsd el a programot:
   `python main.py`

## Exe készítése

PowerShellből a projekt gyökérmappájában:

```powershell
.\build.ps1
```

Az elkészült egyfájlos program a `release\Gamer Translator.exe` fájlba kerül.

## Használat

1. Indítsd el a programot.
2. Jelentkezz be a ChatGPT-be a megnyíló saját ablakban.
3. A `Prompt elküldése` gombbal küldd el a kézi promptot az aktuális beszélgetésbe.
4. Használd a képkivágást, vagy illessz be képet a vágólapra.
5. Várd meg a fordítást.
6. Ha az app nincs előtérben, a fordítás felül egy overlay blokkban is megjelenik.
7. A kész szöveget illeszd be vágólapról, vagy használd a begépelési gyorsgombot.

## Tálca és háttérmód

- az `X` gomb tálcára rejti az alkalmazást
- a tálcaikon dupla kattintásra elrejti vagy visszahozza az ablakot
- jobb kattintással `Eltüntetés` és `Kilépés` menü érhető el
- eltüntetve vagy lekicsinyítve is tovább fut a fordítási folyamat
- a programból egyszerre csak egy példány futtatható

## Megjegyzés

- A projekt nem az OpenAI API-t használja, hanem a webes ChatGPT felületet.
- A működés a `chatgpt.com` oldal felépítésére épül, ezért egy nagyobb felületi változás után a DOM-kezelést frissíteni kellhet.

## Licenc

Ez a projekt saját tulajdonú, minden jog fenntartva.

A forráskód, a dokumentáció és a kapcsolódó állományok használata, másolása, módosítása, terjesztése vagy továbbadása kizárólag előzetes írásos engedéllyel lehetséges. A részletek a `LICENSE.txt` fájlban találhatók.
