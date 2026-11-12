# Android voluntary startup updater

Scope: native Java, Android API 21 minimum / target 34, no AndroidX or Gradle. Release metadata is versionCode 25 / versionName 1.15. Existing build/signing inputs and settings storage are unchanged.

## Trust and consent

Only MainActivity ordinary foreground startup initiates the process-once background feed check. The feed is fixed in UpdateManifest. Offline and invalid-feed failures are silent. Both Windows and Android signed metadata must pass strict schema validation before Android compares versionCode; a Windows-only version change cannot create an Android prompt loop. Accepted sequence floors are persisted separately from settings. Sequence acceptance never downloads or executes an artifact.

RSA-3072 / SHA256withRSA verifies the domain-separated raw payload bytes against a pinned SPKI public key. Duplicate JSON keys (including escaped aliases), invalid UTF-8/Base64, fractional numbers, unsupported fields, expiry, rollback, wrong repository/channel, arbitrary asset paths, and oversized metadata are rejected. No private publisher key is included or accessed by Android code.

An explicit Update action downloads into the private application cache. Redirects are manually bounded to five and the exact HTTPS GitHub host allowlist. Normal platform TLS/hostname checks remain enabled. Response length and the actual byte count/hash must match signed metadata. APK identity, versionCode, versionName, minSdk and current/pinned signing certificate must match before staging the read-only APK. API 21-23 uses a bounded binary XML reader for minSdkVersion because the public PackageManager property is available only from API 24.

The nonexported provider serves only content://ru.alexv.pcmote.updates/update.apk, read-only, after revalidating the signed metadata, hash, and APK identity on every open/query. Only display name and size metadata are queryable. Android source-install settings and the standard package installer always retain the user's confirmation; no Accessibility service or mirroring is started.

Workers are serialized and process-wide generation tokens invalidate callbacks and work after lifecycle changes. Pausing cancels network work and dismisses dialogs; partial files are removed. A pending update offer can be reattached after rotation; an interrupted transfer is not resumed automatically. A verified file remains available while the user visits system permission/installer UI.

## Offline verification

Run from the project root:

```
python -m unittest discover -s app -v
```

The tests execute the real pure-Java verifier against the synthetic signed fixture and 24 separately signed adversarial metadata vectors, exercise strict JSON/URL/version/expiry/sequence rejection, and execute a synthetic binary Android manifest minSdk read. A compile-only test compiles all Android Java sources with `-source 8 -target 8 -bootclasspath android-34/android.jar` and a temporary generated resource-symbol stub. No APK is created. Tests also assert manifest/provider/lifecycle/localization integration and run the existing app regression suite.

Synthetic fixtures have deliberately fake asset sizes/hashes; they are not real release artifacts and must never be published as an installable release.

## Limits / device acceptance still required

No emulator, device, ADB, network transfer, package installation, or real APK build is exercised by these host tests. Static integration tests do not establish real lifecycle behavior. A real signed release must additionally be tested on API 21-23 (binary XML extraction), API 24-27, API 28+ signing APIs, and API 33-34 notification/source-install policies. Exercise rotation and backgrounding during check/download, cancel/timeout/truncated transfer, source permission grant/deny/back, installer accept/cancel, provider grant access, real same-signer APK replacement, settings retention, and no automatic mirroring/accessibility startup.

Android cannot guarantee automatic reopening after update. Below API 29 the replacement receiver attempts a normal launch best-effort. API 29+ uses a user-openable notification only when notification permission/settings permit. If notifications are unavailable the user must reopen the launcher manually. No permission is solicited by the replacement receiver and no background launch restriction is bypassed.
