# Alt+V vizsgálati jelentés

Ellenőrzés dátuma: 2026. október 1. Javított alkalmazásverzió: `5.13`. Kiinduló commit: `513f2ea` (`v5.12`).

## A hiba oka

A helyi alkalmazásnaplóban az Alt+V felismerése sikeres volt, de a gyors chat beküldése után a válaszfigyelő három percen át nulla felhasználói és nulla assistant üzenetet talált. Ezért a begépelés `no_current_translation` okkal elutasítva lett. A kérdéses időszakban a napló 0–1 ms eseményhurok-késést és 21–26 GiB szabad rendszermemóriát mutatott. Ezek az adatok nem támasztják alá az erőforráshiányt ennél a konkrét hibánál; GPU-terhelést és játékbeli FPS-t a napló nem mér.

A csak olvasó, helyi profilmásolattal végzett vizsgálat igazolta, hogy a betöltődő ChatGPT üzenetfelülete megváltozott. Az oldalon meglévő üzenetek egyikén sem szerepelt a korábban keresett `data-message-author-role`, `data-message-id` vagy `article` szerkezet. A felhasználói szöveg `data-user-message-bubble` elemben, a válasz `data-conversation-role="assistant"` fejléc után, `data-chatgpt-selection-message-id` és `data-markdown-text-style` elemekben volt megtalálható.

A javított felismerés ugyanazon élő beszélgetésben három felhasználói üzenetet és három választ talált. A legutóbbi válasz és felhasználói üzenet stabil azonosítót kapott, és a válasz a megfelelő felhasználói üzenethez tartozott. A szerkezeti jelentés csak elemszámokat, attribútumneveket, ismert szerepjelöléseket és szöveghosszt tárolt; beszélgetésszöveg, cookie és üzenetazonosító nem került bele. Új élő ChatGPT-üzenet nem lett elküldve.

## Javított működés

- Az üzenetfelismerés a korábbi és az igazolt új ChatGPT felületet is támogatja. A közös `data-turn-key` nem használható külön üzenetazonosítóként, mert ugyanahhoz a körhöz felhasználói és assistant üzenet is tartozik.
- A közvetlen és tartalék keresési módok eredménye egyesül, DOM-sorrendben és duplikáció nélkül. A szemantikailag elrejtett másolatok kimaradnak; a képernyőn kívüli vagy háttérben megjelenített üzenetek nincsenek emiatt kizárva.
- A válasz a teljes markdown törzsből származik. A szerzőfejléc, kezelőgomb és rejtett törzsrész nem része a fordításnak.
- A vágólapmásolás kikapcsolása mellett is megmarad a kész fordítás az Alt+V számára. A folyamatban levő és időtúllépéskor még részleges válasz nem kerül a kész fordítások közé.
- Azonos szövegű, egymás utáni válaszok is külön üzenetként kezelhetők. Az azonos szöveg részlegesből kész állapotba váltása is külön előrehaladási jelzést ad.
- A beküldés előtti üzenetállapot a beviteli mező és a csatolmány készségi várakozása után rögzül. Az előkészítés közben betöltődő régi beszélgetési előzmény így nem köthető az új kéréshez.
- A késői válaszfigyelés lezárás előtt egyszer még kiolvassa a végső eredményt. Új kérés után a régi kérés válasza nem írhatja felül az új fordítást.
- A begépelés célablaka, szövege és kérésazonosítója már a gyorsgomb felismerésekor rögzül. Fókuszváltás, új kérés vagy megváltozott fordítás megszakítja a műveletet.
- Kilépés és a gyorsgombok újraregisztrálása megszakítja a már elindult begépelést is. Leállítás után további karakter és sikeres befejezési jelzés nem kerül továbbításra.
- A módosítóbillentyű felengedésére váró útvonal időtúllépése látható magyar státuszt és `typing.rejected` naplóeseményt ad.
- A karakterek billentyűkiosztása a célablak szálának kiosztásából származik. A saját Qt célablak billentyűeseményei begépelés közben is feldolgozódnak; ez javítja a nagybetűk, AltGr-jelek és emojik saját alkalmazáson belüli torzulását.
- Bekapcsolt Caps Lock mellett a betűk Unicode-bevitelként kerülnek továbbításra, így megmarad a fordítás kis- és nagybetűs alakja. Az alkalmazás nem kapcsolgatja a Caps Lockot. A billentyűállapot forrását a napló jelzi; a helyi Windows-próba a bekapcsolt és kikapcsolt esetet is ellenőrzi.
- A Windows által elutasított vagy részlegesen befogadott bevitel számlálókat és Windows-hibakódot kap. A sikertelen szintetikus billentyűfelengedés is naplózva lesz, legfeljebb egy újrapróbálással.
- A böngészőbetöltés a navigáció elindításakor már várakozó állapotba kerül. Kilépéskor a folyamatban levő böngészőműveletek megszakításként zárulnak; nem indul új navigáció és nem keletkezik emiatt hamis JavaScript-időtúllépési hiba.

## Ellenőrzés

A végső forráson és az abból készített EXE-n végzett ellenőrzések:

| Ellenőrzés | Eredmény |
| --- | --- |
| Teljes Python regresszió | 294/294 sikeres, nulla kihagyott teszt és nulla váratlan natív rendszerhívás |
| JavaScript regresszió | 38/38 sikeres |
| Böngészőbetöltés és kilépés | 6/6 sikeres; a teljes Python-csomag része |
| Új ChatGPT DOM valódi Qt/Chromium motorral | 4/4 sikeres; a teljes Python-csomag része; a késői előzményteszt három beküldési változatot ellenőriz |
| Külön folyamatban futó Windows fogadóablak | 5/5 sikeres: kész fordítás ismételten és két Caps Lock állapotban, részleges válasz, új kérés után érvénytelen régi fordítás |
| Caps Lock be- és kikapcsolva, külön Windows fogadóablakban | 2/2 teljes szöveg pontosan megérkezett; a fenti öt próba része |
| Saját Qt célablak és GUI szál | 1/1 teljes szöveg pontosan megérkezett |
| Végső EXE forrás- és futtatókörnyezet-egyezése | 34/34 sikeres |
| Végső EXE offline önteszt | 8/8 sikeres, 54 egymás utáni fordítási ciklus; PNG-csatolás és képkivágáshoz kötött vágólapkezelés sikeres |
| Csomagolt RapidOCR és Windows OCR | Mindkettő pontosan a szintetikus `Hello gamer` szöveget ismerte fel |
| Függőség- és szintaxisellenőrzés | `pip check`, Python-fordítás, JavaScript-szintaxis és `git diff --check` sikeres |
| Friss Python-csomagaudit | 48 csomag, nulla ismert sérülékenység és nulla kihagyott csomag |
| Windows Defender célzott EXE-vizsgálat | Sikeresen befejeződött, a vizsgált EXE-hez nulla észlelés |

A natív próbák a valódi Windows hookon és `SendInput` útvonalon mentek végig. A hookok a próbák végén eltávolítva lettek, külső hálózati kérés nem történt. A magyar ékezetek, kis- és nagybetűk, ASCII-jelek, írásjelek, sortörés, tabulátor és emojik egyezését a fogadómező tényleges szövege igazolta. A Caps Lockot a próba a kezdeti kikapcsolt állapotba visszaállította.

A közzétett EXE mérete `381561175` bájt, SHA-256 ellenőrzőösszege: `d4d6a41f875c1f5957daeb68e88345f886845ae505a34638dc09ed4f70285c65`. A forrás- és csomagegyezés összesítése az [ellenőrzési állományban](evidence/alt-v-checks.json) található.

## Az ellenőrzés határai

A Python és JavaScript regressziók elkülönített adatokat és helyi DOM-mintákat használnak. A modern felület képes és szöveges próbái valódi Qt/Chromium motorral futnak, külső hálózat nélkül. A natív Alt+V próbák szintetikus magyar, ASCII-, írásjel-, sortörés-, tabulátor- és emojiszöveget küldenek saját szövegfogadó ablakba, ideiglenes profillal és memóriavágólappal. A saját és a külön folyamatban futó fogadóablak külön ellenőrzés.

A korábbi EXE-önteszt nem regisztrált globális gyorsgombot és nem végzett natív begépelést. Ezt a hiányt a külön Windows-beviteli próbák pótolják. Az offline önteszt továbbra is rendszerintegrációk nélkül ellenőrzi a teljes fordítási folyamatot, képbeillesztést, ablakkezelést és OCR-felismerést.

A meg nem nevezett játék, a fizikai billentyűzet, eltérő adminisztrátori jogosultság, anti-cheat és többórás háttérfutás nem lett igazolt. A Windows alacsony szintű hookja nem garantál elsőbbséget minden közvetlen játék- vagy illesztőprogram-bemenettel szemben. A `typing.completed` esemény a bevitel Windows általi befogadását jelzi; külső programtól nincs általános szövegvisszaigazolás.

A részletes helyi bizonyítékok a `dist\staging\alt-v-audit` és `dist\staging\alt-v-repair` könyvtárban találhatók. Személyes profil, beszélgetésszöveg és futásidejű napló nem kerül a Git-repository-ba vagy a release-be.
