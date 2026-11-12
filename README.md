# DroidBridge

Телефон как пульт для домашнего Windows-ПК — и экран телефона на компьютере. Работает в общей локальной сети, без облачного сервиса.

**[Windows и Android — релиз 1.0.4](https://github.com/alexfduch231-prog/DroidBridge/releases/tag/v1.0.4)** · [English](#english)

Версия 1.0.4 включает Windows-установщик со встроенными FFmpeg и ffplay и Android-приложение 1.15. Обновление Windows поверх прежней установки проверено: настройки сохранены, сервер и комплектные инструменты запускаются. Новые сценарии на реальном телефоне пока не проверены. В предыдущих slim-установщиках инструменты видео и звука нужно было выбирать отдельно.

## Что можно делать

- Смотреть экран ПК с телефона, нажимать, прокручивать и вводить текст.
- Смотреть экран Android на ПК; отдельно разрешить управление телефоном. Звук доступен на Android 10+ там, где приложение разрешает захват.
- Отправлять файлы с телефона в выбранную папку на ПК.
- Блокировать, выключать и перезагружать ПК, управлять музыкой, запускать выбранные тобой программы. Wake-on-LAN может разбудить ПК, если настроен на самом компьютере.

## Начать

1. Скачай установщик Windows. При запуске на ПК нажми **«Установить на телефон»** и отсканируй QR для скачивания APK. Уже установил? Нажми **«Уже установлено → подключить к ПК»**. APK также есть на странице релиза; архивы **Source code** для установки не нужны.
2. Установи приложения и подключи устройства к одной доверенной домашней сети. Windows 10/11 x64, Android 5+; жесты управления телефоном — Android 7+.
3. На ПК нажми **«Запустить сервер»**, затем **«Приложение на телефон / подключить» → «Уже установлено → подключить к ПК»**. Выбери домашний сетевой адаптер и нажми **«Создать новый QR»**.
4. Открой QR телефоном или вставь скопированную ссылку в **«Добавить ПК»**. Сравни код на двух устройствах, нажми **«Разрешить»** на ПК и **«Сохранить ПК»** на телефоне.
5. Попробуй **«Заблокировать»** или **«Смотреть экран ПК»**. В обычной установке 1.0.4 **FFmpeg и ffplay входят в комплект и выбираются автоматически**: отдельно скачивать их, менять PATH или устанавливать Python не нужно. **«Настроить видео и звук»** оставлено для ручного выбора другой сборки, если это действительно нужно.

**[Подробная инструкция, FFmpeg и помощь с подключением](docs/GETTING_STARTED.md)** · [Что меняется в 1.0.4](CHANGELOG.md)

## Обновления

В версии 1.0.4 добавлена проверка обновлений при запуске Windows- и Android-приложения с простым выбором **«Позже» / «Обновить»**: ничего устанавливать без твоего согласия не нужно. Первую версию с этой функцией придётся установить вручную со страницы релиза. Затем на Windows приложение скачает и проверит установщик, закроет свои сервер и просмотр и снова откроет главное окно только после успешной установки, сохранив настройки. На Android всё равно нужно подтвердить системную установку APK; повторное открытие приложения или уведомление зависит от ограничений системы и не гарантируется. [Подробности](docs/GETTING_STARTED.md#обновления).

## Важно знать

**Только доверенная локальная сеть.** Сопряжение защищено TLS, но основной транспорт команд, видео и файлов **не зашифрован**. Не открывай порты роутера в Интернет. Подключения через облако нет.

Защищённые экраны Android и UAC Windows не обходятся. Передача файлов — до 50 ГиБ. В версии 1.0.4 реализованы пауза и продолжение после обрыва Wi-Fi или перезапуска приложения: исходный файл должен остаться доступным и неизменным. Для продолжения нужна папка приёма на NTFS или другом диске с поддержкой жёстких ссылок; FAT/exFAT не поддерживаются. Незавершённые передачи хранятся до 7 дней и не считаются готовыми файлами. Подготовка большого файла перед отправкой может занять время; во время передачи держи Android-приложение на экране. Проверка этой функции на реальном телефоне пока не подтверждена. Совместимость с каждым устройством не гарантируется. Текущий режим H.264 экрана ПК использует NVIDIA NVENC: нужна поддерживаемая видеокарта NVIDIA и подходящий драйвер. Наличие FFmpeg само по себе не гарантирует работу этого режима на любом Windows-ПК.

## Как выглядит

Ниже **иллюстрации интерфейса, не скриншоты**. Они показывают расположение элементов, а не точный вид на твоём устройстве.

<p>
  <img src="docs/images/android-demo.svg" alt="Иллюстрация интерфейса Android, не скриншот" width="360">
  <img src="docs/images/windows-demo.svg" alt="Иллюстрация интерфейса Windows, не скриншот" width="460">
</p>

## О проекте

DroidBridge сделан с помощью ИИ изначально для себя — чтобы управлять домашним компьютером с телефона. Это экспериментальный личный проект, которым автор делится с другими. ИИ участвовал в написании кода; это не обещание безошибочной работы или профессиональной поддержки. Пользуйся только на своих устройствах или с разрешения их владельца.

Нашёл ошибку или есть идея — [создай Issue](https://github.com/alexfduch231-prog/DroidBridge/issues). Для разработки: [инструкция](docs/DEVELOPMENT.md), [участие](CONTRIBUTING.md), [безопасность](SECURITY.md). Оригинальный код — [MIT](LICENSE).

---

# English

Use your phone as a remote for your Windows PC, or view your phone on the computer. DroidBridge works on the same local network, without a cloud service.

**[Windows and Android — release 1.0.4](https://github.com/alexfduch231-prog/DroidBridge/releases/tag/v1.0.4)**

Version 1.0.4 includes the Windows installer with bundled FFmpeg/ffplay and Android app 1.15. An in-place Windows upgrade was verified: settings were preserved, and the server and bundled tools run. New scenarios have not yet been tested on a real phone. Earlier slim installers required a separate media-tool selection.

## What you can do

- View and control the PC screen from your phone: click, scroll and enter text.
- View Android on your PC, with optional phone control. Audio requires Android 10+ and an app that allows playback capture.
- Send files from your phone to a folder you choose on the PC.
- Lock, shut down or restart the PC, control media and launch programs you select. Wake-on-LAN can wake the PC if enabled in its hardware settings.

## Get started

1. Download the Windows installer. On the PC, choose **Install on phone** and scan the QR to download the APK. Choose **Already installed → connect to PC** to skip downloading. The APK is also on the release page; you do not need the **Source code** archives.
2. Install both apps and connect the devices to the same trusted home network. Requires Windows 10/11 x64 and Android 5+; phone-control gestures require Android 7+.
3. On the PC, click **«Запустить сервер»** (Start server), then **«Приложение на телефон / подключить» → «Уже установлено → подключить к ПК»** (Phone app / connect → Already installed). Choose your home network adapter and **Create new QR**. The main Windows panel currently uses Russian labels.
4. Open the QR link on Android, or paste the copied link into **Add PC**. Compare the code on both devices, click **Allow** on the PC, then **Save PC** on the phone.
5. Try **Lock** or **View PC screen**. The standard 1.0.4 installer **includes FFmpeg and ffplay and selects them automatically**: no separate download, PATH editing or Python installation is needed. **«Настроить видео и звук»** (Set up video and audio) remains available as an optional manual override.

**[Full setup guide, FFmpeg and troubleshooting](docs/GETTING_STARTED.md#english)** · [1.0.4 changes](CHANGELOG.md#english--104--2026-11-12)

## Updates

Version 1.0.4 adds startup update checks for both Windows and Android with a simple prompt: **Later / Update**; installation requires your consent. Install the first version that supports this feature manually from the release page. Afterwards, Windows will download and verify the installer, close its server and viewer, and reopen the main window only after a successful installation while keeping settings. Android still requires system APK-installation approval; reopening or a notification is best-effort and subject to system restrictions. [Details](docs/GETTING_STARTED.md#updates).

## Limitations

**Trusted LAN only.** TLS protects pairing, but the main command, video and file transport is **not encrypted**. Do not forward router ports to the Internet. There is no cloud connection.

Android protected screens and Windows UAC restrictions are not bypassed. Uploads are limited to 50 GiB. Version 1.0.4 implements pause and resume after Wi-Fi loss or an app restart; the source file must remain accessible and unchanged. Resuming needs a destination on NTFS or another hard-link-capable disk; FAT/exFAT is unsupported. Incomplete transfers are kept for up to 7 days and are not finished files. Preparing a large file before sending may take time; keep the Android app in the foreground during transfer. Real-phone verification of this feature is not yet confirmed. Compatibility with every device is not guaranteed. Current PC-screen H.264 encoding uses NVIDIA NVENC and requires a supported NVIDIA GPU and driver; bundling FFmpeg does not make this mode work on every Windows PC. The images above are **interface illustrations, not screenshots**.

## About

DroidBridge was built with AI, originally for the author's own home setup, and is shared as an experimental personal project. AI helped write the code; that is not a promise of bug-free operation or professional support. Use it only on your own devices or with their owner's permission.

Bugs and ideas: [Issues](https://github.com/alexfduch231-prog/DroidBridge/issues). For developers: [development guide](docs/DEVELOPMENT.md), [contributing](CONTRIBUTING.md), [security](SECURITY.md). Original code: [MIT](LICENSE).
