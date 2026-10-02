# Képes válaszfelismerés vizsgálati jelentés

Ellenőrzés dátuma: 2026. október 2. Javított alkalmazásverzió: `5.14`. Kiinduló commit: `a09db79` (`v5.13`).

## A hiba oka

A helyi `5.13` naplóban a 22:03-kor indított képkérés csatolása és beküldése visszaigazolást kapott. A beküldés után körülbelül hat másodperccel az assistant üzenetek száma egyről kettőre nőtt, és egy 29 karakteres válasz befejezett állapotba került. A felismert felhasználói üzenetek száma közben egy maradt. A válasz `pending=false`, `stable=true`, `fresh=false` állapota miatt az alkalmazás nem mentette el fordításként. A háromperces válaszvárás, majd a további kétperces figyelés eredmény nélkül ért véget.

A 00:01-kor indított képkérés ugyanígy hibázott: két felhasználói üzenet mellett az assistant üzenetek száma kettőről háromra nőtt, a válasz nyolc másodpercen belül kész lett, de frissként nem volt elfogadható. A későbbi eset alatt 94–96%, a korábbi eset alatt 29–30% volt a rendszermemória foglaltsága. A memóriahiány önmagában nem magyarázza a közös felismerési hibát. Az alkalmazásnapló GPU-terhelést és játékbeli FPS-t nem mér.

Az anonimizált napló nem tárolja a beszélgetés DOM-ját vagy az üzenetazonosítókat, ezért a pontos élő oldalszerkezeti változat ezekből az adatokból nem állapítható meg. A forrásban azonban reprodukálható hiányosság volt: a saját, explicit `data-conversation-role="user"` szerepjelöléssel rendelkező képes üzenet kimaradt, ha nem kapott szöveges `data-user-message-bubble` elemet vagy a korábban keresett üzenet- és keresőattribútumokat. A szerepjel mélyebb belső konténerben sem volt felismerhető.

A `v5.13` forrásával végzett, hálózat nélküli Qt/Chromium próba ugyanazt a hibát reprodukálta: egy korábbi felhasználói és assistant üzenet után az új képkérés válasza elkészült, az assistant számláló kettőre nőtt, a felhasználói számláló egy maradt, és időtúllépés következett. A korábbi képes tesztminta mindig létrehozott egy felhasználói szövegbuborékot; ezért ezt a változatot nem fedte le.

## Javított működés

- Az explicit felhasználói szerepjel és a saját üzenetkonténer alapján a szöveg nélküli képes kör is felismerhető, a korábbi szövegbuborék és keresőattribútumok nélkül.
- A fejléc mélyebb belső konténerben is felismerhető. A felhasználói és assistant szerepet egyaránt tartalmazó közös konténer nem számít külön felhasználói üzenetnek.
- Egy tetszőleges kép, profilkép vagy névrészlet nem igazol felhasználói kört. A rejtett szerepjel, rejtett tartalom és rejtett másolat nem helyettesítheti a tényleges üzenetet.
- A beküldés előtti kiinduló állapot, a felhasználói és assistant azonosítók, a DOM-sorrend, a kész állapot és az új kéréshez tartozás ellenőrzése megmarad. A közös `data-turn-key` nem válik külön üzenetazonosítóvá.
- A korábbi felhasználói üzenet megmaradt stabil azonosítója akkor is igazolhatja az utána érkező új képkérést, ha a régi üzenet DOM-eleme újrarajzolódott és az új képkérésnek nincs saját stabil azonosítója. Ha a régi stabil horgony eltűnik, egy új DOM-elem önmagában továbbra sem igazol új kérést.
- A válaszállapot naplója külön jelzi a kérés kötését, a legutolsó felhasználói üzenet és a válaszhoz tartozó felhasználói üzenet egyezését, az assistant azonosítójának újdonságát, a felhasználói szerep felismerésének módját és az elutasítás okát.
- Az új mezők az első válaszvárásnál és a késői figyelésnél is rendelkezésre állnak. Üzenetazonosító, fordítás, prompt, kép, cookie és webcím továbbra sem kerül a naplóba.

## Ellenőrzés

| Ellenőrzés | Eredmény |
| --- | --- |
| Teljes Python regresszió | 302/302 sikeres |
| JavaScript regresszió | 45/45 sikeres |
| Modern DOM valódi Qt/Chromium motorral | 10/10 sikeres; a teljes Python-csomag része |
| Diagnosztikai háttéríró és naplóolvasó | 25/25 sikeres; a teljes Python-csomag része; a bool- és enummezők megmaradnak, a beszélgetéstartalom és azonosító kimarad |
| Forrásból futó alkalmazásönteszt | 8/8 sikeres, három gyorsfordítási ciklus és két modern képes kérés; OCR-modell nélkül |
| Végleges EXE forrás- és futtatókörnyezet-egyezése | 34/34 sikeres |
| Végleges EXE offline önteszt | 9/9 sikeres, 53 gyorsfordítási ciklus, két modern képes kérés, sikeres képkivágási engedély- és gyorsítótár-ellenőrzés |
| Csomagolt RapidOCR és Windows OCR | Mindkettő pontosan a szintetikus `Hello gamer` szöveget ismerte fel |
| Függőség- és szintaxisellenőrzés | `pip check`, Python-fordítás, JavaScript-szintaxis és `git diff --check` sikeres |

A valódi Chromium-regressziók két egymást követő, azonos szövegű kész fordítást, a kép előkészítése közben betöltődő előzményt, a rejtett másolatokat, a közös user+assistant konténert és a régi assistant áthelyezését is ellenőrzik. Új felhasználói üzenet nélkül és korábbi assistantazonosítóval a válasz elutasítva marad. A JavaScript-csomag külön ellenőrzi a stabil korábbi horgony mellett érkező, csak DOM-azonosítós képkérést, valamint az eltűnt horgony és régi üzenet újrarajzolásának elutasítását.

A képes pozitív Chromium-próbák a meglévő tesztkeret 3000 ms-os válaszlimitjét használják. A minta 600 ms-os Stop-időzítője offscreen futásnál késhet; a rövidebb, 1000 ms-os pozitív teszt egyszeri hibát adott a teljes csomagban. A változatlan 1000 ms-os határral végzett 143 tesztes ismétlés sikeres volt, a Stop-időzítő 720 ms-nál zárult. A két elutasítási próba továbbra is 1000 ms-os keretet használ, majd a már befejezett válaszon is ellenőrzi a frissesség hiányát. A tesztidőkorlát változása az alkalmazás háromperces válaszlimitjét nem módosítja.

A végleges EXE mérete `381565279` bájt, SHA-256 ellenőrzőösszege: `370a149240ec0a5c3eaa8b4e981c26e8fd4b8fa2abc44d7040079b7fcd9167b2`. A helyi telepített fájl `C:\Saját\Alkalmazások\Gamer-Translator-v5.14.exe`, ugyanazzal az ellenőrzőösszeggel. A csomag- és regresszióellenőrzés tartalommentes adatai az [ellenőrzési állományban](evidence/image-response-checks.json) találhatók.

A telepített `5.14` normál profillal elindult. A böngészőbetöltés és az automatizálás beillesztése sikeres, az indulás alatt nulla `ERROR` vagy `CRITICAL` esemény keletkezett. Ez az indulást igazolja; új bejelentkezett képkérés sikerét nem.

## Az ellenőrzés határai

A regressziók helyi DOM-mintával, elkülönített adatokkal és valódi Qt/Chromium motorral futnak. A csak olvasó profilmásolat ezúttal nem töltött be beszélgetést; ebből nem származik igazolt élő DOM-szerkezet. Új bejelentkezett ChatGPT-üzenet és játék közbeni fordítás nem része az automatikus ellenőrzésnek. A javítás és a naplóbővítés további valós kérésnél ad pontosabb bizonyítékot.

Személyes profil, beszélgetésszöveg és futásidejű napló nem kerül a Git-repository-ba.
