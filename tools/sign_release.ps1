[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = 'High')]
param(
  [Parameter(Mandatory)]
  [ValidatePattern('^[0-9a-fA-F]{40}$')]
  [string]$CertificateThumbprint,

  [Parameter(Mandatory)]
  [ValidateNotNullOrEmpty()]
  [string]$ExpectedPublisherSubject,

  [Parameter(Mandatory)]
  [ValidatePattern('^[0-9a-fA-F]{64}$')]
  [string]$ExpectedUnsignedSha256,

  [Parameter(Mandatory)]
  [uri]$TimestampUrl,

  [Parameter(Mandatory)]
  [ValidateNotNullOrEmpty()]
  [string]$SignToolPath,

  [ValidateSet('CurrentUser', 'LocalMachine')]
  [string]$CertificateStore = 'CurrentUser',

  [string]$InputPath = 'dist\staging\verified\Gamer Translator.exe',
  [string]$OutputPath = 'dist\release-signed\Gamer Translator.exe'
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$codeSigningOid = '1.3.6.1.5.5.7.3.3'

function Resolve-ReleasePath {
  param([string]$Path)

  $fullPath = if ([IO.Path]::IsPathRooted($Path)) {
    [IO.Path]::GetFullPath($Path)
  } else {
    [IO.Path]::GetFullPath((Join-Path $projectRoot $Path))
  }

  $releaseRoots = @((Join-Path $projectRoot 'dist'), (Join-Path $projectRoot 'release'))
  $insideRelease = $false

  foreach ($releaseRoot in $releaseRoots) {
    if ($fullPath.StartsWith($releaseRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
      $insideRelease = $true
    }
  }

  if (-not $insideRelease) {
    throw 'Az aláírandó és az elkészülő fájl csak a projekt dist vagy release könyvtárában lehet.'
  }

  # Könyvtárhivatkozáson keresztül sem írunk a kijelölt kiadási területen kívülre.
  $currentPath = $fullPath
  while ($currentPath.Length -gt $projectRoot.Length) {
    if (Test-Path -LiteralPath $currentPath) {
      $item = Get-Item -LiteralPath $currentPath -Force
      if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
        throw "Az aláírás útvonala nem tartalmazhat könyvtárhivatkozást: $currentPath"
      }
    }
    $currentPath = Split-Path -Parent $currentPath
  }

  return $fullPath
}

if (-not $TimestampUrl.IsAbsoluteUri -or $TimestampUrl.Scheme -ne 'https' -or
    -not $TimestampUrl.Host -or $TimestampUrl.UserInfo -or $TimestampUrl.Fragment) {
  throw 'A tanúsítványkiadó által megadott RFC 3161 HTTPS időbélyegző-végpont szükséges, felhasználói adat és fragment nélkül.'
}

$sourcePath = Resolve-ReleasePath -Path $InputPath
$destinationPath = Resolve-ReleasePath -Path $OutputPath
if (-not (Test-Path -LiteralPath $sourcePath -PathType Leaf) -or [IO.Path]::GetExtension($sourcePath) -ne '.exe') {
  throw 'A kiindulási EXE fájl nem található vagy a kiterjesztése hibás.'
}
if ([IO.Path]::GetExtension($destinationPath) -ne '.exe' -or
    $sourcePath.Equals($destinationPath, [StringComparison]::OrdinalIgnoreCase) -or
    (Test-Path -LiteralPath $destinationPath)) {
  throw 'Az aláírt kiadásnak új EXE fájlba kell kerülnie; a meglévő fájlt nem írjuk felül.'
}

$unsignedSha256 = (Get-FileHash -LiteralPath $sourcePath -Algorithm SHA256).Hash
if ($unsignedSha256 -ne $ExpectedUnsignedSha256) {
  throw 'Az EXE SHA256 értéke eltér a jóváhagyott és tesztelt kiadásétól.'
}
if ((Get-AuthenticodeSignature -LiteralPath $sourcePath).Status -ne 'NotSigned') {
  throw 'A kiindulási fájl már aláírt vagy az aláírási állapota nem egyértelmű; előbb külön ellenőrizni kell.'
}

$normalizedThumbprint = $CertificateThumbprint.ToUpperInvariant()
$certificatePath = "Cert:\$CertificateStore\My\$normalizedThumbprint"
if (-not (Test-Path -LiteralPath $certificatePath)) {
  throw 'A megadott tanúsítvány nem található a kiválasztott személyes tanúsítványtárban.'
}
$certificate = Get-Item -LiteralPath $certificatePath
if ($certificate.Subject -cne $ExpectedPublisherSubject) {
  throw 'A tanúsítvány Subject mezője nem egyezik a jóváhagyott kiadó pontos azonosítójával.'
}
if (-not $certificate.HasPrivateKey -or $certificate.EnhancedKeyUsageList.ObjectId -notcontains $codeSigningOid) {
  throw 'Elérhető privát kulccsal rendelkező Code Signing tanúsítvány szükséges.'
}
$now = Get-Date
if ($now -lt $certificate.NotBefore -or $now -gt $certificate.NotAfter -or $certificate.Subject -eq $certificate.Issuer) {
  throw 'A tanúsítvány még nem érvényes, lejárt vagy önaláírt; kiadáshoz nem használható.'
}

$chain = [Security.Cryptography.X509Certificates.X509Chain]::new()
try {
  $chain.ChainPolicy.RevocationMode = [Security.Cryptography.X509Certificates.X509RevocationMode]::Online
  $chain.ChainPolicy.RevocationFlag = [Security.Cryptography.X509Certificates.X509RevocationFlag]::ExcludeRoot
  $chain.ChainPolicy.VerificationFlags = [Security.Cryptography.X509Certificates.X509VerificationFlags]::NoFlag
  $chain.ChainPolicy.UrlRetrievalTimeout = [TimeSpan]::FromSeconds(20)
  [void]$chain.ChainPolicy.ApplicationPolicy.Add([Security.Cryptography.Oid]::new($codeSigningOid))
  if (-not $chain.Build($certificate)) {
    $chainErrors = ($chain.ChainStatus | ForEach-Object { $_.Status.ToString() }) -join ', '
    throw "A tanúsítvány Windows bizalmi vagy visszavonási ellenőrzése sikertelen: $chainErrors"
  }
} finally {
  $chain.Dispose()
}

if (-not [IO.Path]::IsPathRooted($SignToolPath) -or -not (Test-Path -LiteralPath $SignToolPath -PathType Leaf)) {
  throw 'A Windows SDK signtool.exe fájljának teljes, létező útvonalát kell megadni.'
}
$resolvedSignTool = (Resolve-Path -LiteralPath $SignToolPath).Path
$toolSignature = Get-AuthenticodeSignature -LiteralPath $resolvedSignTool
if ([IO.Path]::GetFileName($resolvedSignTool) -ine 'signtool.exe' -or
    $toolSignature.Status -ne 'Valid' -or
    $toolSignature.SignerCertificate.Subject -notmatch '(^|,\s*)O=Microsoft Corporation(,|$)') {
  throw 'Csak érvényes Microsoft-aláírással rendelkező Windows SDK SignTool használható.'
}

$action = "Aláírás és RFC 3161 időbélyegzés: $ExpectedPublisherSubject; $normalizedThumbprint; bemeneti SHA256: $unsignedSha256"
if (-not $PSCmdlet.ShouldProcess($destinationPath, $action)) {
  return
}

$destinationDirectory = Split-Path -Parent $destinationPath
New-Item -ItemType Directory -Path $destinationDirectory -Force | Out-Null
$temporaryDirectory = Join-Path $destinationDirectory ('.sign-' + [guid]::NewGuid().ToString('N'))
$temporaryPath = Join-Path $temporaryDirectory 'Gamer Translator.exe'
Resolve-ReleasePath -Path $temporaryPath | Out-Null
New-Item -ItemType Directory -Path $temporaryDirectory | Out-Null

try {
  Copy-Item -LiteralPath $sourcePath -Destination $temporaryPath
  if ((Get-FileHash -LiteralPath $temporaryPath -Algorithm SHA256).Hash -ne $unsignedSha256) {
    throw 'A kiindulási fájl időközben megváltozott; az aláírás megszakadt.'
  }

  $signArguments = @('sign', '/sha1', $normalizedThumbprint, '/s', 'My', '/fd', 'SHA256',
    '/tr', $TimestampUrl.AbsoluteUri, '/td', 'SHA256', '/d', 'Gamer Translator', '/v')
  if ($CertificateStore -eq 'LocalMachine') {
    $signArguments += '/sm'
  }
  $signArguments += $temporaryPath
  & $resolvedSignTool @signArguments
  if ($LASTEXITCODE -ne 0) {
    throw "Az aláírás vagy az időbélyegzés nem sikerült figyelmeztetés nélkül (kilépési kód: $LASTEXITCODE)."
  }

  & $resolvedSignTool verify /pa /all /tw /v $temporaryPath
  if ($LASTEXITCODE -ne 0) {
    throw "Az aláírt kiadás ellenőrzése sikertelen (kilépési kód: $LASTEXITCODE)."
  }
  $signedSignature = Get-AuthenticodeSignature -LiteralPath $temporaryPath
  if ($signedSignature.Status -ne 'Valid' -or
      $signedSignature.SignerCertificate.Thumbprint -ne $normalizedThumbprint -or
      $null -eq $signedSignature.TimeStamperCertificate) {
    throw 'A kiadói aláírás vagy a hiteles időbélyeg nem igazolható.'
  }

  # Csak teljesen ellenőrzött másolatot helyezünk ki; az eredeti staging EXE változatlan.
  Resolve-ReleasePath -Path $destinationPath | Out-Null
  if (Test-Path -LiteralPath $destinationPath) {
    throw 'A célfájl időközben létrejött; nem írjuk felül.'
  }
  Move-Item -LiteralPath $temporaryPath -Destination $destinationPath
  [pscustomobject]@{
    OutputPath = $destinationPath
    UnsignedSha256 = $unsignedSha256
    SignedSha256 = (Get-FileHash -LiteralPath $destinationPath -Algorithm SHA256).Hash
    PublisherSubject = $certificate.Subject
    PublisherThumbprint = $normalizedThumbprint
    TimestampSubject = $signedSignature.TimeStamperCertificate.Subject
    AuthenticodeStatus = $signedSignature.Status.ToString()
  }
} finally {
  # Egyetlen saját ideiglenes fájl és az üres könyvtára törlődik, rekurzív törlés nincs.
  Resolve-ReleasePath -Path $temporaryPath | Out-Null
  if (Test-Path -LiteralPath $temporaryPath -PathType Leaf) {
    Remove-Item -LiteralPath $temporaryPath -Force
  }
  if (Test-Path -LiteralPath $temporaryDirectory -PathType Container) {
    [IO.Directory]::Delete($temporaryDirectory, $false)
  }
}
