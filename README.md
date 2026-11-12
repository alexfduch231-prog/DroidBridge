# DroidBridge

Телефон как пульт для домашнего Windows-ПК — и экран телефона на компьютере. Работает в общей локальной сети, без облачного сервиса.

**[Скачать для Windows и Android — релиз 1.0.3](https://github.com/alexfduch231-prog/DroidBridge/releases/tag/v1.0.3)** · [English](#english)

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
5. Попробуй **«Заблокировать»** или **«Смотреть экран ПК»**. Для H.264 и звука отдельно скачай и распакуй **FFmpeg с ffplay**, затем укажи папку через **«Настроить видео и звук» → «Выбрать папку…»**. Менять PATH не нужно; после настройки заново запусти сервер и окно просмотра. Python отдельно не нужен.

**[Подробная инструкция, FFmpeg и помощь с подключением](docs/GETTING_STARTED.md)**

## Важно знать

**Только доверенная локальная сеть.** Сопряжение защищено TLS, но основной транспорт команд, видео и файлов **не зашифрован**. Не открывай порты роутера в Интернет. Подключения через облако нет.

Защищённые экраны Android и UAC Windows не обходятся. Передача файлов — до 50 ГиБ, без возобновления после обрыва; Android-приложение нужно держать открытым. Совместимость с каждым устройством не гарантируется.

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

**[Download for Windows and Android — release 1.0.3](https://github.com/alexfduch231-prog/DroidBridge/releases/tag/v1.0.3)**

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
5. Try **Lock** or **View PC screen**. For H.264 and audio, separately download and extract **FFmpeg with ffplay**, then select its folder via **«Настроить видео и звук» → «Выбрать папку…»** (Set up video and audio → Choose folder). No PATH change is needed; restart the server and viewer after setup. A separate Python installation is not required.

**[Full setup guide, FFmpeg and troubleshooting](docs/GETTING_STARTED.md#english)**

## Limitations

**Trusted LAN only.** TLS protects pairing, but the main command, video and file transport is **not encrypted**. Do not forward router ports to the Internet. There is no cloud connection.

Android protected screens and Windows UAC restrictions are not bypassed. File uploads are limited to 50 GiB, cannot resume after interruption and require the Android app to stay open. Compatibility with every device is not guaranteed. The images above are **interface illustrations, not screenshots**.

## About

DroidBridge was built with AI, originally for the author's own home setup, and is shared as an experimental personal project. AI helped write the code; that is not a promise of bug-free operation or professional support. Use it only on your own devices or with their owner's permission.

Bugs and ideas: [Issues](https://github.com/alexfduch231-prog/DroidBridge/issues). For developers: [development guide](docs/DEVELOPMENT.md), [contributing](CONTRIBUTING.md), [security](SECURITY.md). Original code: [MIT](LICENSE).
