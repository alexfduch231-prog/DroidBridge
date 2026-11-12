# ASCII only. Build RU/alexv pcmote APK without Gradle.
# Continue: stderr ot javac/d8 - eto obichno warnings, oni ne dolzhny uryvat sborky.
# Realnye oshibki lovim po $LASTEXITCODE v Chk.
$ErrorActionPreference = "Continue"

$SDK = if ($env:ANDROID_HOME) { $env:ANDROID_HOME } else { Join-Path $env:LOCALAPPDATA "Android/SDK" }
$BT    = "$SDK\build-tools\34.0.0"
$AJAR  = "$SDK\platforms\android-34\android.jar"
if (-not $env:JAVA_HOME) { throw "Set JAVA_HOME to JDK 21" }; $JDK = Join-Path $env:JAVA_HOME "bin"
$ROOT = $PSScriptRoot
$APP   = "$ROOT\app"
$BUILD = "$ROOT\build"
$OUT   = "$ROOT\pc-remote.apk"

function Step($name) { Write-Host ("==> " + $name) }
function Chk($code, $name) {
    if ($code -ne 0) { throw ("FAILED: " + $name + " (exit " + $code + ")") }
}

if (Test-Path $BUILD) { Remove-Item $BUILD -Recurse -Force }
New-Item -ItemType Directory -Path $BUILD | Out-Null
New-Item -ItemType Directory -Path "$BUILD\classes" | Out-Null
New-Item -ItemType Directory -Path "$BUILD\gen" | Out-Null

Step "aapt2 compile"
& "$BT\aapt2.exe" compile --dir "$APP\res" -o "$BUILD\res.zip" 2>&1 | ForEach-Object { "$_" }
Chk $LASTEXITCODE "aapt2 compile"

Step "aapt2 link"
& "$BT\aapt2.exe" link -I "$AJAR" `
    --manifest "$APP\AndroidManifest.xml" `
    --min-sdk-version 21 --target-sdk-version 34 `
    --auto-add-overlay `
    --java "$BUILD\gen" `
    -o "$BUILD\unaligned.apk" `
    "$BUILD\res.zip" 2>&1 | ForEach-Object { "$_" }
Chk $LASTEXITCODE "aapt2 link"

Step "javac"
$srcs = @()
$srcs += (Get-ChildItem -Recurse "$BUILD\gen" -Filter *.java | ForEach-Object { $_.FullName })
$srcs += (Get-ChildItem -Recurse "$APP\src" -Filter *.java | ForEach-Object { $_.FullName })
# -parameters obyazatelen: bez nego javac 21 stavit na konstryuktory vnutrennix klassov
# atribut MethodParameters s pustym imenem (name_index=0), a D8 iz build-tools 34 na etom
# padayet s vnitrennim NullPointerException ("String.length() ... <parameter1> is null").
& "$JDK\javac.exe" -encoding UTF-8 -nowarn -parameters -source 8 -target 8 `
    -bootclasspath "$AJAR" -d "$BUILD\classes" $srcs 2>&1 | ForEach-Object { "$_" }
Chk $LASTEXITCODE "javac"

Step "d8 (class -> dex)"
# d8 v build-tools 34 padayet s vnitrennim NPE, kogda podaesh po odnomu .class s dollarom
# v imeni (MainActivity$1.class). Gradle vsegda peredayot jar - delaem tak zhe.
& "$JDK\jar.exe" -c -f "$BUILD\classes.jar" -C "$BUILD\classes" . 2>&1 | ForEach-Object { "$_" }
Chk $LASTEXITCODE "jar"
& "$BT\d8.bat" --min-api 21 --lib "$AJAR" --output "$BUILD" "$BUILD\classes.jar" 2>&1 | ForEach-Object { "$_" }
Chk $LASTEXITCODE "d8"

Step "aapt add classes.dex"
Push-Location $BUILD
& "$BT\aapt.exe" add "$BUILD\unaligned.apk" "classes.dex" 2>&1 | ForEach-Object { "$_" }
$rc = $LASTEXITCODE
Pop-Location
Chk $rc "aapt add"

Step "zipalign"
& "$BT\zipalign.exe" -f 4 "$BUILD\unaligned.apk" "$BUILD\aligned.apk" 2>&1 | ForEach-Object { "$_" }
Chk $LASTEXITCODE "zipalign"

Step "keystore"
$KS = "$ROOT\debug.keystore"
if (-not (Test-Path $KS)) {
    & "$JDK\keytool.exe" -genkeypair -v -keystore "$KS" `
        -storepass android -keypass android -alias pcmote `
        -keyalg RSA -keysize 2048 -validity 10000 `
        -dname "CN=pcmote, OU=home, O=home, L=home, S=home, C=RU" 2>&1 | ForEach-Object { "$_" }
    Chk $LASTEXITCODE "keytool"
} else {
    Write-Host "keystore exists, reuse"
}

Step "apksigner"
if (Test-Path $OUT) { Remove-Item $OUT -Force }
& "$BT\apksigner.bat" sign --ks "$KS" --ks-pass pass:android --key-pass pass:android `
    --out "$OUT" "$BUILD\aligned.apk" 2>&1 | ForEach-Object { "$_" }
Chk $LASTEXITCODE "apksigner sign"

Step "apksigner verify"
& "$BT\apksigner.bat" verify --print-certs "$OUT" 2>&1 | ForEach-Object { "$_" }
Chk $LASTEXITCODE "apksigner verify"

$fi = Get-Item $OUT
Step ("DONE: " + $OUT + " (" + [math]::Round($fi.Length/1024,1) + " KB)")
