# OCR teljesítmény és bemenetkezelés

Ellenőrzés dátuma: 2026. szeptember 20. Kiinduló commit: `72835b8`.

## Javított működés

- Az OCR-re és a háttérfeladat leállására várakozás közben a GUI-szál a Qt eseményhurkát futtatja. A korábbi 40 ms-os alvás a GUI-szálon telepített billentyűzet- és egérhook továbbítását is késleltethette. A 40 ms most az eredmény ellenőrzésének időköze, közben a bemenet feldolgozható.
- A RapidOCR ONNX Runtime motorjai egy számítási szálat használnak, és az OpenCV párhuzamos feldolgozása is egy szálra korlátozott. Az OCR továbbra is alacsony prioritású háttérfeladat. A Windows OCR saját működésére és a böngészőfolyamatokra ez nem jelent egymagos korlátot.
- A globális egérhook csak Mouse 4–5 gyorsgombhoz, aktív gyorsgomb-rögzítőhöz vagy már elnyelt egérgomb felengedésének kezeléséhez marad telepítve.
- Az újrabelépő háttérfeladat nem írhatja felül a már futó feladat állapotát.

A Windows a low-level egérhookot a telepítő szál üzenetkezelésén keresztül hívja meg; ezért azon a szálon a várakozás módja az alkalmazáson kívüli egérhasználatot is érintheti. [Microsoft dokumentáció](https://learn.microsoft.com/en-us/windows/win32/winmsg/lowlevelmouseproc)

Az ONNX Runtime alapértelmezése magonként további számítási szálakat hozhat létre. A beállított egyetlen szál megszünteti ezt a motoronkénti párhuzamosságot. [ONNX Runtime dokumentáció](https://onnxruntime.ai/docs/performance/tune-performance/threading.html)

## Előtte–utána mérés

A mérés Windows alatt, Python 3.13.15, RapidOCR 3.9.2 és ONNX Runtime 1.29.0 környezetben, 12 logikai processzoron történt. A korábbi és a módosított forrás külön folyamatban, egymás után futott ugyanazon 19 generált magyar és angol képen. Mindkét futás legfeljebb öt különböző olvasatot kért, ugyanazokat a hash-ellenőrzött helyi modelleket és a magyar/angol Windows OCR-t használva.

| Mért érték | Korábbi változat | Javított változat |
| --- | ---: | ---: |
| Átlagosan igénybe vett logikai processzor | 4,448 | 0,928 |
| A mérőfolyamat átlagos CPU-terhelése a gép kapacitásához képest | 37,067% | 7,732% |
| A mérőfolyamat összes CPU-ideje | 443,344 s | 115,484 s |
| A 19 kép teljes mérési ideje | 99,671 s | 124,463 s |
| Karakterpontos első olvasat | 15/19 | 15/19 |
| Karakterhiba a 628 forráskarakterben | 5 | 5 |

A folyamat átlagos CPU-terhelése körülbelül 79%-kal, az elvégzett munkához felhasznált CPU-idő körülbelül 74%-kal csökkent. A teljes futási idő körülbelül 25%-kal nőtt. Mind a 19 képnél a teljes kiválasztott szöveglista és annak sorrendje is azonos maradt.

A [géppel feldolgozható mérési eredmény](evidence/ocr-performance.json) tartalmazza a források hashét, a csomagverziókat, az összesített és képenkénti méréseket. A `process_cpu_seconds` a folyamat minden szálának CPU-idejét összegzi, az `average_process_cpu_cores` ennek és az eltelt időnek a hányadosa. A százalék ezt osztja a gép logikai processzorainak számával.

## Ellenőrzés és korlátok

Az automatizált ellenőrzésben 198 Python- és 13 JavaScript-teszt sikeres. A Python/JavaScript szintaxisellenőrzés, a `pip check` és a `git diff --check` is sikeres. A valóban betöltött detektáló, osztályozó és felismerő ONNX-munkamenet külön ellenőrzése mindhárom esetben 1/1 szálbeállítást, soros végrehajtást és CPU-motort igazolt; az OpenCV egy szálat jelzett.

Az elkülönített EXE a `dist/staging/ocr-performance/Gamer Translator.exe` fájlban készült el. A 33 csomagellenőrzés sikeres; a csomagolt program offline öntesztje 8/8 ellenőrzést és 7 ismétlési ciklust teljesített. A RapidOCR és a Windows OCR is pontosan a `Hello gamer` mintaszöveget adta vissza. Az EXE SHA-256 értéke: `728c0ab42ac9bf5e33639069037f0324e6db05c39b762e424c12d192db28a2da`.

A regressziók valódi Qt-időzítőkkel és háttérszállal ellenőrzik, hogy a GUI a feladat befejezése előtt kiszolgálja az eseményeket. Lefedik a háttérhiba továbbítását, az újrabelépés elutasítását, a normál és GUI-eseményből kért leállást. Az egértesztek a hook szükségességét, a gyorsgomb-rögzítést és az elnyelt gombok felengedését vizsgálják. Az OCR-kompatibilitási teszt a telepített RapidOCR valódi konfigurációfeldolgozóján és ONNX-beállításain keresztül ellenőrzi a szálkorlátot.

- A mérés egyetlen gépen, szintetikus képeken történt. A futási időt a gép egyéb terhelése is befolyásolja.
- A CPU-adatok az OCR mérőfolyamatára vonatkoznak, nem a teljes gépre vagy az alkalmazás összes böngészőfolyamatára.
- A benchmark közvetlenül az OCR-szolgáltatást hívja. A GUI várakozásának javítását külön regressziók ellenőrzik.
- Valódi játékbeli FPS- és fizikai egérkésleltetés-mérés nem történt.
- A vágólapképből PNG, hash és base64 készítése még a GUI-szálon történik; nagyon nagy kivágásnál ez a kezdeti lépés továbbra is okozhat rövid megakadást.
