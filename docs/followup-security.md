# Kiegészítő kiadásbiztonsági ellenőrzés

Ellenőrzés dátuma: 2026. augusztus 30. A tanúsítványtár és a Windows állapotának vizsgálata csak metadata-olvasást végzett. Privát kulcsot nem exportáltam, tanúsítványt vagy megbízható gyökeret nem telepítettem, Defender-beállítást és kizárást nem módosítottam.

## Az elkülönített buildkörnyezetből készült kiadásjelölt ellenőrzése

A PATH-szennyezés javítása után elkészült `verified` kiadásjelölt egyéni Defender-vizsgálata **befejeződött, fenyegetést nem talált**, és az EXE változatlan maradt. Az új fájl vizsgálata külön futás volt; a korábbi, indítási hibás EXE eredményét nem vittük át rá.

| Adat | Eredmény |
| --- | --- |
| Fájl | `dist/staging/verified/Gamer Translator.exe` |
| Méret | 381 500 794 bájt |
| SHA256 előtte/utána és a build-manifestben | `465a14948960d4e4d836068462993ad97dc4f3859a0fe069b357775d184c8867` |
| Indítás | 2026-08-30 17:41:19.4909023 UTC |
| Befejezés | 2026-08-30 17:41:19.5579046 UTC |
| Kilépési kód | `0` |
| Szöveges eredmény | `Scan finished.` és `found no threats.` |
| Mód | Egyéni fájlvizsgálat, `-DisableRemediation` |
| Authenticode | `NotSigned` |
| Statikus buildellenőrzés | 32/32 sikeres |
| Valódi EXE-önteszt | Sikeres, `frozen=true`, 109 szövegciklus és egy PNG-útvonal, 122,365 s belső tesztidő |
| Natív OCR és kilépés | RapidOCR és Windows OCR: pontos „Hello gamer”; 7/7 ellenőrzés, sikeres takarítás, folyamat kilépési kódja 0 |

Tartós bizonyíték: [defender-final.json](evidence/defender-final.json), [teljes konzolkimenet](evidence/defender-final.txt) és [build-manifest.json](evidence/build-manifest.json). A statikus ellenőrzés most a Python ABI-stubot, a Python/OpenSSL és Qt natív fájlok egyezését, az idegen ICU hiányát és a Qt által igényelt rendszer-ICU exportokat is vizsgálja. A build PATH-korlátozását és az indítási hiba okát a [biztonsági audit SEC-08 megállapítása](security-audit.md) részletezi.

A teljes, valóban becsomagolt EXE offline próbája is **sikeres**: [frozen-self-test.json](evidence/frozen-self-test.json). Ideiglenes profil, memóriavágólap, letiltott natív gyorsbillentyűk és helyi szintetikus tartalom mellett futott; személyes profilt vagy új élő promptot nem használt. A külön natív összevetés 360 becsomagolt PE-fájlon 0 értelmezési hibát és a vizsgált Poppler/MinGW könyvtárakkal 0 hash-egyezést talált; a korábbi 48 idegen bejegyzés nincs a csomagban: [frozen-path-contamination-verified.json](evidence/frozen-path-contamination-verified.json). Ez meghatározott forráskönyvtárakra végzett összevetés, nem minden futás közbeni DLL-betöltés teljes bizonyítása.

```powershell
& 'C:\ProgramData\Microsoft\Windows Defender\Platform\4.18.26070.9-0\MpCmdRun.exe' `
  -Scan -ScanType 3 `
  -File 'C:\Saját\Asztal\MineWild - Magyar Minecraft Szerver Közösség\Projectek\Gamer Translator\dist\staging\verified\Gamer Translator.exe' `
  -DisableRemediation
```

A Defender-vizsgálat nem igazolja önmagában a teljes EXE működését, az aláírást vagy az összes natív sebezhetőség hiányát. A rövid futási időből nem következtettem a belső cache-re vagy a vizsgálat mélységére. Javító művelet nem volt engedélyezve; házirend/kizárás nem változott, külső online fájlszkennerre kézi feltöltés nem történt. A Windows meglévő Defender-felhőházirendje változatlan. A `-DisableRemediation` jelentését a [Microsoft dokumentációja](https://learn.microsoft.com/en-us/defender-endpoint/command-line-arguments-microsoft-defender-antivirus) rögzíti.

## A QtCore-indítási hibával érintett köztes kiadásjelölt Defender-ellenőrzése

A Python 3.13.15-alapú köztes kiadásjelölt egyéni Defender-vizsgálata **befejeződött, fenyegetést nem talált**, az EXE változatlan maradt. A parancs előtti hash-ellenőrzés biztosította, hogy a statikus buildellenőrzéssel azonos fájlt vizsgálja. **Ennek a fájlnak a tényleges indítása QtCore DLL-betöltési hibával sikertelen volt; a Defender-eredmény nem kiadási vagy futási PASS.** Az újracsomagolt `verified` változat külön vizsgálata és sikeres indítási tesztje a fenti szakaszban szerepel.

| Adat | Eredmény |
| --- | --- |
| Fájl | `dist/staging/python313-final/Gamer Translator.exe` |
| Méret | 398 996 348 bájt |
| SHA256 előtte és utána | `6c93262a971096a829c3741d3c17c8b7ee4cc245e5eaca9da6da0f38da7216ca` |
| Indítás | 2026-08-30 17:27:47.0683027 UTC |
| Befejezés | 2026-08-30 17:27:47.1350425 UTC |
| Kilépési kód | `0` |
| Szöveges eredmény | `Scan finished.` és `found no threats.` |
| Mód | Egyéni fájlvizsgálat, `-DisableRemediation` |
| Authenticode | `NotSigned` |
| Statikus buildellenőrzés | 24/24 sikeres; a natív Python/OpenSSL fájlok egyezése is ellenőrizve |

Tartós történeti bizonyíték: [defender-qtcore-failed.json](evidence/defender-qtcore-failed.json), [teljes konzolkimenet](evidence/defender-qtcore-failed.txt) és [build-manifest-qtcore-failed.json](evidence/build-manifest-qtcore-failed.json). A JSON a teljes parancsot, előtte/utána hash-t, fájlméretet és a használt Defender motor-, platform- és szignatúraverziót is rögzíti.

```powershell
& 'C:\ProgramData\Microsoft\Windows Defender\Platform\4.18.26070.9-0\MpCmdRun.exe' `
  -Scan -ScanType 3 `
  -File 'C:\Saját\Asztal\MineWild - Magyar Minecraft Szerver Közösség\Projectek\Gamer Translator\dist\staging\python313-final\Gamer Translator.exe' `
  -DisableRemediation
```

A kimenet befejezett vizsgálatot igazol, de a rövid futási időből nem következtettem a belső cache működésére vagy a vizsgálat mélységére. Nem jelent teljes sérülékenységmentességet, és nem zárja le az aláírási és natív runtime-frissítési feltételt. Javító művelet nem volt engedélyezve; Defender-házirendet/kizárást nem változtattam, külső online fájlszkennerre nem töltöttem fel az EXE-t. A Windows meglévő Defender-felhőházirendje változatlan maradt. A kapcsoló jelentését a [Microsoft dokumentációja](https://learn.microsoft.com/en-us/defender-endpoint/command-line-arguments-microsoft-defender-antivirus) rögzíti.

## A korábbi kiadásjelölt Defender-ellenőrzése

Az alábbi korábbi, Python 3.11-alapú fájl vizsgálata **befejeződött**, nem csak az indítás történt meg. Ez történeti eredmény: a Python 3.13.15-re áttérés és a forrásmódosítások utáni új buildre nem vihető át.

| Adat | Eredmény |
| --- | --- |
| Fájl | `dist/staging/Gamer Translator.exe` |
| Méret | 410 114 495 bájt |
| SHA256 előtte és utána | `E5A9C1833D32CA46EE8280AAB8B77F11D92C341102080B1E3E4E4FAD05599A0B` |
| Indítás | 2026-08-30 16:56:44.4069213 UTC |
| Befejezés | 2026-08-30 16:56:44.9886100 UTC |
| Kilépési kód | `0` |
| Szöveges eredmény | `Scan finished.` és `found no threats.` |
| Helyreállítás/karantén | A `-DisableRemediation` kapcsoló miatt a vizsgálat nem alkalmaz javító műveletet |

A futtatott parancs:

```powershell
& 'C:\ProgramData\Microsoft\Windows Defender\Platform\4.18.26070.9-0\MpCmdRun.exe' `
  -Scan -ScanType 3 `
  -File 'C:\Saját\Asztal\MineWild - Magyar Minecraft Szerver Közösség\Projectek\Gamer Translator\dist\staging\Gamer Translator.exe' `
  -DisableRemediation
```

Egyértelmű, befejezett „nem talált fenyegetést” eredmény érkezett, és a fájl hash-e nem változott. Ez nem bizonyít teljes sérülékenységmentességet, és nem helyettesíti a funkcionális teszteket vagy a kiadói aláírást. Új build vagy aláírás után a hash változik: arra az új fájlra ismételt vizsgálat szükséges.

A kapcsoló egyéni vizsgálatnál mellőzi a javító műveleteket, és a találatokat a konzolkimeneten jelzi. A használt verzió súgóját és a [Microsoft hivatalos MpCmdRun-dokumentációját](https://learn.microsoft.com/en-us/defender-endpoint/command-line-arguments-microsoft-defender-antivirus) ellenőriztem. Külső online fájlszkennerre nem töltöttem fel az EXE-t; a Windows meglévő Defender-felhőházirendjét nem változtattam meg.

A nyers, időbélyegzett eredmények helye:

```text
C:\Users\juher\AppData\Local\Temp\gamer-translator-defender-ceab4f7839e24f2b9ba23de2e061c160\before.json
C:\Users\juher\AppData\Local\Temp\gamer-translator-defender-ceab4f7839e24f2b9ba23de2e061c160\scan.txt
C:\Users\juher\AppData\Local\Temp\gamer-translator-defender-ceab4f7839e24f2b9ba23de2e061c160\after.json
```

## Digitális aláírás lehetőségei

Mindkét személyes tanúsítványtár olvasása sikeres volt:

| Vizsgált tár | Code Signing EKU tanúsítvány |
| --- | --- |
| `Cert:\CurrentUser\My` | 0 |
| `Cert:\LocalMachine\My` | 0 |

A szűrés a `1.3.6.1.5.5.7.3.3` Code Signing EKU-ra vonatkozott. Találat esetén csak a nyilvános Subject, Issuer, thumbprint, érvényességi idő és `HasPrivateKey` metadata került volna olvasásra. A vizsgálat nem állapítja meg egy külön külső HSM vagy felhős aláíró szolgáltatás elérhetőségét.

A `signtool.exe` nem volt elérhető a PATH-on vagy a `C:\Program Files (x86)\Windows Kits\10\bin` alatt. A kiadásjelölt Authenticode-állapota **`NotSigned`**. Aláírás nem történt; ehhez a kiadóhoz tartozó, jóváhagyott Code Signing tanúsítvány és az ahhoz használható aláíró környezet még hiányzik. Saját készítésű gyökértanúsítvánnyal vagy önaláírt tanúsítvánnyal nem helyettesítettem a kiadó hitelesítését.

### Elkészített aláíró segédprogram

A [tools/sign_release.ps1](../tools/sign_release.ps1) Windows PowerShell/PowerShell alatt használható, Windows tanúsítványtárban elérhető Code Signing tanúsítvánnyal. Külön aláírt másolatot készít, az eredeti staging EXE-t nem változtatja meg.

A segédprogram:

- kötelezővé teszi a tanúsítvány pontos thumbprintjét és a jóváhagyott kiadó teljes, egyező Subject mezőjét;
- megköveteli a tesztelt bemeneti EXE jóváhagyott SHA256 hash-ét;
- ellenőrzi a Code Signing EKU-t, a privát kulcs jelenlétét és az érvényességi időt; önaláírt tanúsítványt elutasít;
- ellenőrzi a Windows bizalmi láncát, online visszavonási ellenőrzéssel; ellenőrzési hibánál nem ír alá;
- teljes útvonalon megadott, érvényes Microsoft-aláírású Windows SDK SignToolt fogad el;
- SHA256 fájlaláírást és RFC 3161 SHA256 időbélyeget kér a megadott HTTPS végponton;
- minden SignTool-hibát és figyelmeztetést sikertelenségként kezel;
- utólag `verify /pa /all /tw` ellenőrzést, kiadói thumbprint-egyezést és időbélyeg-tanúsítványt követel meg;
- csak a projekt `dist` vagy `release` mappájába írhat; könyvtárhivatkozást és meglévő kimeneti fájl felülírását elutasítja;
- nem exportál kulcsot, nem kér PFX-jelszót parancssorban, nem választ automatikusan másik tanúsítványt, és nem telepít bizalmi gyökeret.

A `/sha1` itt kizárólag a tanúsítvány thumbprint szerinti kiválasztására szolgál. A fájl és az időbélyeg lenyomata külön `/fd SHA256` és `/td SHA256` értékkel készül. A kapcsolókat és a figyelmeztetési kilépési kódot a [Microsoft SignTool dokumentációja](https://learn.microsoft.com/en-us/windows/win32/seccrypto/signtool) határozza meg.

### Használat a hiányzó előfeltételek biztosítása után

1. A kiadó jóváhagyott tanúsítványa legyen elérhető a kiválasztott `My` tanúsítványtárban, a megfelelő privát kulccsal. A kiadói azonosságot előbb ellenőrizni kell; más szervezet tanúsítványa nem használható csak azért, mert technikailag elérhető.
2. Telepítsd az eredeti Microsoft Windows SDK SignTool összetevőjét, és add meg a `signtool.exe` teljes útvonalát. A tanúsítványkiadótól származó, RFC 3161-et támogató HTTPS időbélyegző-végpont szükséges. A tokenhez tartozó szoftver vagy PIN megadása külön szolgáltatói követelmény lehet.
3. Készítsd el és sikeres statikus, funkcionális és Defender-teszttel fogadd el a `dist/staging/verified/Gamer Translator.exe` fájlt. Futtasd a buildellenőrzést, amely a `dist/staging/verified/build-manifest.json` fájlt létrehozza. Csak az ott rögzített és elfogadott hash-t használd. Az aláíró segédprogram alapértelmezett bemenete ez a fájl; a korábbi `python313-final` build QtCore-indítási hibája miatt nem fogadható el aláírásra.
4. A projekt gyökerében állítsd össze az ellenőrizhető paramétereket:

```powershell
$releaseManifest = Get-Content -LiteralPath 'dist\staging\verified\build-manifest.json' -Raw | ConvertFrom-Json
$signArguments = @{
  CertificateThumbprint = Read-Host 'A jóváhagyott Code Signing tanúsítvány 40 hex karakteres thumbprintje'
  ExpectedPublisherSubject = Read-Host 'A jóváhagyott kiadó pontos teljes Subject mezője'
  ExpectedUnsignedSha256 = $releaseManifest.sha256
  CertificateStore = 'CurrentUser'
  SignToolPath = Read-Host 'A Microsoft Windows SDK signtool.exe teljes útvonala'
  TimestampUrl = Read-Host 'A tanúsítványkiadó RFC 3161 HTTPS időbélyegző URL-je'
}

.\tools\sign_release.ps1 @signArguments -WhatIf
```

A `-WhatIf` elvégzi a bemenetek, a tanúsítvány és a SignTool ellenőrzését, de nem ír alá és nem hoz létre kimeneti fájlt. A lánc ellenőrzése hálózati visszavonási lekérdezést igényelhet. Ha nincs tanúsítvány vagy nem igazolható a lánc, már ez a lépés is hibával leáll.

5. Ellenőrizd a megjelenített kiadót, thumbprintet, bemeneti SHA256 hash-t és kimeneti útvonalat. A jóváhagyás után:

```powershell
.\tools\sign_release.ps1 @signArguments -Confirm
Get-AuthenticodeSignature -LiteralPath 'dist\release-signed\Gamer Translator.exe'
Get-FileHash -LiteralPath 'dist\release-signed\Gamer Translator.exe' -Algorithm SHA256
```

6. Az aláírt fájlon is futtass Defender-ellenőrzést és elkülönített indítási tesztet. Külön, tiszta Windows tesztgépen is ellenőrizd a kiadó bizalmi láncát. A helyi `Valid` állapot önmagában nem bizonyítja, hogy minden célgép ugyanazzal a gyökértanúsítvány-készlettel rendelkezik.

Az aláíró segédprogram PowerShell-szintaxisa hibamentes. Hat negatív ellenőrzés sikeres: hibás thumbprint, hibás SHA256-formátum, HTTP-időbélyegző, kiadási mappán kívüli bemenet, eltérő EXE-hash, hiányzó tanúsítvány. Ezek egyikénél sem történt aláírás vagy kihelyezés. **Sikeres tényleges aláírás és RFC 3161-kérés nem volt tesztelhető tanúsítvány és SignTool nélkül.**

## A helyi Windows frissítettségi pillanatfelvétele

| Adat | Mért állapot |
| --- | --- |
| Windows build | `26200.9278` |
| DisplayVersion | `25H2` |
| Legújabb látható frissítések | `KB5120998`, `KB5120997`, telepítve: 2026-08-29 |
| További látható frissítés | `KB5120708`, telepítve: 2026-08-12 |
| Defender platform | `4.18.26070.9` |
| Defender motor | `1.1.26070.7` |
| Biztonsági intelligencia | `1.457.407.0`, frissítve: 2026-08-30 02:40:13 +02:00 |
| Legutóbbi gyorsteszt metadata szerinti befejezése | 2026-08-30 17:03:34 +02:00 |
| Vírusvédelem, valós idejű védelem, Defender szolgáltatás | Aktív |
| Tűzfal Domain / Private / Public profil | Mindhárom aktív |
| Windows Update reboot-required jelző | Nincs |
| Component Based Servicing reboot-pending jelző | Nincs |
| PendingFileRenameOperations | Van |

A `PendingFileRenameOperations` jelző önmagában nem bizonyít hiányzó biztonsági frissítést; egy program frissítése is létrehozhatja. A gépet nem indítottam újra. A jelzett állapotot a következő tervezett újraindítás után érdemes újra ellenőrizni.

A frissítéslista helyi metadata, nem online Windows Update megfelelőségi igazolás. Nem indítottam teljes rendszer- vagy hálózati sérülékenységvizsgálatot, külső behatolási tesztet, Windows-frissítésletöltést vagy automatikus Windows-frissítéstelepítést. A fenti Defender-eredmény mindig a megadott hash-ű fájlra vonatkozik.

## Az alkalmazás futtatókörnyezetének frissítése

A runtime-agent az eredeti Python mellett külön projektinterpretert telepített: **Python 3.13.15 / OpenSSL 3.0.21**. A `.venv313` ezt használja; a korábbi `.venv` továbbra Python 3.11.8 / OpenSSL 3.0.13, ezért a végső kiadáshoz nem azt kell kiválasztani. A hivatalos telepítő SHA256-ellenőrzése sikeres, Authenticode-állapota `Valid`, aláírója Python Software Foundation (`evidence/python-runtime-installer.json`). Nem állítottuk át a rendszer összes Python-telepítését.

A `.venv313` tényleges verzióit függetlenül ellenőriztem. A `python-runtime-upgrade.json` 48 csomag teljes listáját és a natív Python/OpenSSL fájlok hash-ét tartalmazza; a `pip-audit-python313.json` mind a 48 csomagon 0 ismert sérülékenységet jelez. Ez Python-csomagaudit, nem teljes Windows- vagy natív DLL-audit. A WinRT 3.2.1 csomagokra váltott Windows OCR és a RapidOCR natív motor külön szintetikus tesztben is a várt „Hello gamer” szöveget adta.

**Nyitott natív frissítési feltétel:** a hitelesített Python-csomag OpenSSL 3.0.21 verziója után 2026-08-25-én megjelent a 3.0.22 biztonsági kiadás. A részletes, öt advisoryra kiterjedő elérhetőségi triázst a [biztonsági audit](security-audit.md) tartalmazza. A vizsgált normál HTTPS-útvonalon nem azonosítottam konkrét kihasználható hívásláncot, de nem állítok 0 natív sérülékenységet. Az OpenSSL 3.0 upstream támogatása 2026-09-07-én lezárul. Következő lépés a Python szállítójának támogatott, javított, aláírt runtime-jával új build és ismételt ellenőrzés; tetszőleges DLL-cserét nem végeztünk. [OpenSSL kiadási jegyzetek](https://openssl-library.org/news/openssl-3.0-notes/index.html), [támogatási stratégia](https://openssl-library.org/policies/releasestrat/).

A forrásból indított offline önteszt 106 cikluson, 120,496 másodpercen át sikeresen futott, ideiglenes profillal, memóriavágólappal és letiltott natív gyorsbillentyűkkel. Ezt a végső `verified` EXE 109 ciklusos, 122,365 másodperces sikeres futása és két natív OCR-motorpróbája követte. Az optimalizált Python-módot a teszt explicit elutasítja, így az `assert` utasítások nem maradhatnak ki észrevétlenül. A bejelentkezés nélküli élő próba kizárólag egy szintetikus szöveget küldött a friss tesztprofilból; „Szia, gamer!” választ kapott. Ez nem személyes profil használata és nem OpenAI-infrastruktúra-audit. A konkrét hash-hez kötött tesztjelentés a részletes hatókört is rögzíti; a bejelentkezett és további kézi funkciópróbák ettől még nem tekinthetők elvégzettnek.

A korábbi, a kilépésjavítás előtti staging próbából megmaradt folyamat takarítása külön helyi művelet: az eszköz biztonsági korlátozása miatt nem kényszerítettük a leállítást. A fő tesztfolyamat végső, olvasó ellenőrzése szerint a `4148 → 17380 → 18576` folyamatsor és a `gamer-translator-live-staging-7i777wi2` ideiglenes könyvtár még jelen volt. Ez a példány a normál személyes profilt nem használta. Az új forrás kilépési javítását külön folyamatban futó regresszió és a végső EXE tiszta kilépése igazolja; ezek nem szüntetik meg a korábban elindított példányt. A régi saját tesztablak bezárása vagy a folyamatok jóváhagyott leállítása még helyi takarítási feladat.
