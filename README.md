# DroidBridge

Управляй домашним компьютером с телефона — или телефоном с компьютера. Оба устройства должны быть в одной локальной сети. Аккаунты и облако не нужны.

**[Скачать для Windows и Android](https://github.com/alexfduch231-prog/DroidBridge/releases/latest)** · [English](#english)

## Что умеет

- Показывает экран ПК на телефоне: можно нажимать, прокручивать и печатать.
- Показывает экран телефона на ПК. Если разрешить управление на Android, можно пользоваться им мышью.
- Отправляет файлы с телефона в выбранную папку на компьютере. Прерванную передачу можно продолжить.
- Запускает твои программы, управляет музыкой, блокирует, перезагружает и выключает ПК.
- Может разбудить выключенный ПК, если компьютер и сеть поддерживают Wake-on-LAN.

## Как подключить

1. **Установи приложение на ПК и телефон.** Нужные файлы лежат на странице скачивания; архивы с исходниками не нужны. QR для скачивания Android-приложения есть и в разделе «Подключение» на ПК.
2. **Подключи устройства к одной домашней сети** и нажми на ПК «Запустить сервер».
3. **Открой «Подключение».** Перед первым подключением приложение попросит настроить включение ПК по сети. Если найдёт проблему, покажет, что исправить. Этот шаг нельзя пропустить; часть настроек BIOS придётся проверить вручную.
4. **Создай QR подключения и открой его телефоном.** Если камера не открывает ссылку, скопируй её в «Добавить ПК» на телефоне.
5. **Сравни код на двух экранах.** Нажми «Разрешить» на ПК и «Сохранить ПК» на телефоне. Готово — можно пользоваться.

Нужны **Windows 10/11 x64** и **Android 5 или новее**. Для управления телефоном жестами — Android 7+.

**[Подробная инструкция и помощь с подключением](docs/GETTING_STARTED.md)**

## Где что искать

В Windows все разделы находятся слева в одном окне:

- **Подключение** — установить приложение на телефон и связать устройства.
- **Экран телефона** — смотреть телефон и управлять им.
- **Программы** — добавить свои программы для запуска с телефона.
- **Приём файлов** — выбрать, куда сохранять загрузки.
- **Включение ПК** — проверить и настроить пробуждение по сети.
- **Настройки** — видео, звук и оформление.

Чтобы показать телефон на компьютере, оставь окно DroidBridge и сервер включёнными. На телефоне нажми **«Трансляция на ПК»** и разреши показ экрана. Для управления телефоном понадобится ещё разрешение в специальных возможностях Android.

## Обновления

Приложение само проверяет обновления при запуске. Можно установить их сразу или отложить. На Android установку нужно подтвердить в системном окне.

## Что важно знать

- **Используй только в доверенной домашней сети.** Подключение устройств защищено, но сами команды, видео и файлы пока передаются без шифрования. Не открывай порты приложения в интернет.
- **Для показа экрана ПК нужна совместимая видеокарта NVIDIA с NVENC.** На других видеокартах этот режим пока не работает.
- **Файлы — до 50 ГиБ.** Для докачки выбирай папку на NTFS; FAT/exFAT не подходят. Не меняй исходный файл и держи приложение на телефоне открытым во время передачи. Незаконченные загрузки хранятся до семи дней.
- **Пробуждение зависит от компьютера и сети.** Приложение поможет с настройкой, но не сможет включить эту возможность, если её не поддерживает железо. Даже успешная проверка не заменяет пробное включение.
- **Системные ограничения остаются.** Приложение не обходит защиту Android и Windows. Звук телефона доступен на Android 10+ и только там, где само приложение разрешает его захватывать.

## Как выглядит

[Скриншоты с пояснениями](docs/SCREENSHOTS.md). В галерее указано, к каким версиям относятся снимки: оформление может отличаться.

## О проекте

Сделал с помощью ИИ для себя, потом решил поделиться — вдруг кому-то тоже пригодится. Это личный эксперимент, а не коммерческий сервис с круглосуточной поддержкой. Ошибки вполне возможны.

Нашёл баг или придумал улучшение — **[напиши в Issues](https://github.com/alexfduch231-prog/DroidBridge/issues)**. Хочешь помочь кодом — [как участвовать](CONTRIBUTING.md) и [как собрать проект](docs/DEVELOPMENT.md).

[Что нового](CHANGELOG.md) · [Безопасность](SECURITY.md) · [Лицензия MIT](LICENSE)

---

# English

Control your home PC from your phone — or your phone from your PC. Both devices need to be on the same local network. No account or cloud service required.

**[Download for Windows and Android](https://github.com/alexfduch231-prog/DroidBridge/releases/latest)**

## What it does

- Shows your PC screen on your phone, with clicking, scrolling and typing.
- Shows your phone screen on your PC. Grant Android's control permission to use it with a mouse.
- Sends files from your phone to a folder you choose on the PC, with pause and resume.
- Launches your programs, controls media, locks, restarts and shuts down your PC.
- Can wake the PC if your hardware and network support Wake-on-LAN.

## Connect your devices

1. **Install the Windows app and Android APK** from the download page. You don't need the source archives. The PC app also has an Android download QR under Connection.
2. **Connect both devices to your home network** and click Start server on the PC.
3. **Open Connection.** Before the first pairing, the app requires network-wake setup. If something is wrong, it tells you what to fix. This step cannot be skipped; some BIOS settings need to be checked manually.
4. **Create a pairing QR and open it on your phone.** If the camera doesn't open the link, paste it into Add PC in the Android app.
5. **Compare the code on both screens.** Click Allow on the PC, then Save PC on the phone. You're ready to go.

Requires **Windows 10/11 x64** and **Android 5+**. Phone-control gestures require Android 7+.

**[Full setup guide and troubleshooting](docs/GETTING_STARTED.md#english)**

## Finding your way around

The Windows sidebar keeps everything in one window:

- **Connection** — install the Android app and pair your devices.
- **Phone screen** — view and control your phone.
- **Applications** — choose programs to launch from your phone.
- **Received files** — choose where uploads are saved.
- **Wake PC** — check and configure network waking.
- **Settings** — video, audio and appearance.

To cast your phone, keep the DroidBridge window open and its server running. Tap **Cast phone to PC** on Android and approve screen sharing. Phone control also needs Android's Accessibility permission. The Windows sidebar currently uses Russian labels.

## Updates

The app checks for updates at startup. Install now or leave it for later — your choice. Android asks you to confirm installation in its system dialog.

## Before you use it

- **Use a trusted home network only.** Pairing is protected, but commands, video and files are not yet encrypted. Don't expose the app's ports to the internet.
- **PC screen streaming needs a supported NVIDIA GPU with NVENC.** Other GPUs aren't supported by this mode yet.
- **Files can be up to 50 GiB.** Use an NTFS destination for resumable uploads; FAT/exFAT won't work. Keep the source unchanged and the Android app open while transferring. Incomplete uploads are kept for up to seven days.
- **Waking depends on your PC and network.** The app helps with setup, but can't add hardware support. A successful check isn't a substitute for trying an actual wake.
- **OS restrictions still apply.** The app doesn't bypass Android or Windows protections. Phone audio needs Android 10+ and an app that allows audio capture.

## Screenshots

[See the screens and explanations](docs/SCREENSHOTS.md). Each capture is labelled with its version; the current app may look different.

## About

Built with AI for my own home setup, then shared in case someone else finds it useful. It's a personal experiment, not a commercial service with round-the-clock support. Expect some rough edges.

Found a bug or have an idea? **[Open an Issue](https://github.com/alexfduch231-prog/DroidBridge/issues)**. Want to help with the code? See [contributing](CONTRIBUTING.md) and the [build guide](docs/DEVELOPMENT.md).

[What's new](CHANGELOG.md) · [Security](SECURITY.md) · [MIT license](LICENSE)
