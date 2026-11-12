# DroidBridge

Телефон как пульт для домашнего Windows-ПК — и экран телефона на компьютере. Работает в общей локальной сети, без облачного сервиса.

**[Windows и Android — скачать](https://github.com/alexfduch231-prog/DroidBridge/releases/latest)** · [English](#english)

Windows **1.0.7** — одно основное окно с разделами слева. Android **1.16** (сборка **26**): вместе с Windows **1.0.7** он показывает значки программ из настроенных на ПК EXE и ярлыков LNK. Если значок получить не удалось или одна из сторон старой версии, останется обычный значок программы. Android **1.15** остаётся совместимым для прежних функций.

## Что можно делать

- Смотреть экран ПК с телефона, нажимать, прокручивать и вводить текст.
- Смотреть экран Android на ПК; отдельно разрешить управление телефоном. Звук доступен на Android 10+ там, где приложение разрешает захват.
- Отправлять файлы с телефона в выбранную папку на ПК.
- Блокировать, выключать и перезагружать ПК, управлять музыкой, запускать выбранные тобой программы. Wake-on-LAN может разбудить ПК, если настроен на самом компьютере.

## Начать

1. Скачай установщик Windows и Android APK со страницы релиза. Архивы **Source code** для установки не нужны. В Windows 1.0.7 QR скачивания APK находится в разделе **«Подключение» → «Установить на телефон»**. Если приложение уже есть, выбери **«Уже установлено → подключить к ПК»**.
2. Установи приложения и подключи устройства к одной доверенной домашней сети. Нужны Windows 10/11 x64 и Android 5+; жесты управления телефоном — Android 7+.
3. На ПК нажми **«Запустить сервер»** вверху окна. В разделе **«Подключение»** перед новым сопряжением заверши одноразовую настройку включения ПК и нажми **«Продолжить сопряжение»**; [условия настройки](docs/GETTING_STARTED.md#одноразовая-настройка-перед-новым-сопряжением). Затем выбери домашний сетевой адаптер и нажми **«Создать новый QR»**. Пока подключаешь телефон, оставайся в этом разделе.
4. Открой QR телефоном или вставь скопированную ссылку в **«Добавить ПК»**. Сравни код на двух устройствах, нажми **«Разрешить»** на ПК и **«Сохранить ПК»** на телефоне.
5. Попробуй **«Заблокировать»** или **«Смотреть экран ПК»** на телефоне. Для обратной трансляции используй раздел Windows **«Экран телефона»**. Программы и папка приёма файлов настраиваются в своих разделах, медиакомплект — в **«Настройки»**.

Обычный Windows-установщик содержит **FFmpeg и ffplay** и выбирает их автоматически. Отдельно скачивать их, менять PATH или устанавливать Python не нужно. Ручной выбор другой сборки нужен только при восстановлении или осознанной замене инструментов.

**[Подробная инструкция и помощь с подключением](docs/GETTING_STARTED.md)** · [Что нового](CHANGELOG.md)

## Одно основное окно

В 1.0.7 разделы **«Подключение»**, **«Экран телефона»**, **«Программы»**, **«Приём файлов»**, **«Включение ПК»** и **«Настройки»** открываются внутри одного окна. Скачивание Android-приложения и сопряжение находятся в подключении; просмотр телефона — в своём разделе. Для просмотра телефона оставь главное окно DroidBridge открытым и запусти сервер. На сопряжённом телефоне нажми **«Трансляция на ПК»** и подтверди системный запрос Android: экран откроется здесь без ручного ввода IP. Управление включится автоматически только при уже разрешённой службе специальных возможностей Android; приложение не выдаёт это разрешение за тебя. Ручное подключение по IP остаётся доступным. Один сервер без основного окна может обслуживать команды, но не встроенный просмотр телефона. Системные запросы разрешений, выбор файлов и подтверждения по-прежнему могут открывать диалоги.

При уходе со страницы сопряжения временный QR перестаёт действовать: вернись в **«Подключение»** и создай новый. При уходе с просмотра телефона подключение просмотра закрывается. Сервер запускается только по твоей команде; его статус не доказывает доступность ПК с телефона.

**Перед новым сопряжением обязательна одноразовая настройка Wake-on-LAN внутри «Подключение».** Свежая проверка Windows должна подтвердить Magic Packet **«включено»** у той же физической карты; также нужны твои явные подтверждения ручной проверки BIOS/UEFI и совместимости локальной сети. «Выключено», «не поддерживается», «неизвестно» и ошибки проверки завершить шаг не позволяют. При запуске автоматической проверки нет; сохранённое завершение проверяется заново только при явном новом сопряжении и используется повторно для той же карты с включённым Magic Packet. Существующая рабочая пара не отключается. Обычный раздел **«Включение ПК»** остаётся для диагностики и настройки; проверка только читает настройки. **«Настроить Windows»** требует твоего согласия и UAC и включает только поддерживаемый Magic Packet выбранной физической карты. BIOS/UEFI настраивается вручную по инструкции производителя. Даже **100%** означает завершённую проверку или настройку, а не гарантированное пробуждение. [Как настроить и проверить](docs/GETTING_STARTED.md#включение-и-выключение-пк).

## Обновления

Начиная с 1.0.4 Windows- и Android-приложение проверяют обновления при запуске и предлагают **«Позже» / «Обновить»**. Первую версию с этой функцией нужно установить вручную. Windows скачивает и проверяет установщик перед закрытием собственных компонентов и повторно открывает приложение только после успешной установки. На Android обязательно системное подтверждение установки APK; повторное открытие или уведомление зависит от ограничений системы. [Подробности](docs/GETTING_STARTED.md#обновления).

## Важно знать

**Только доверенная локальная сеть.** Сопряжение защищено TLS, но основной транспорт команд, видео и файлов **не зашифрован**. Не открывай порты роутера в Интернет. Подключения через облако нет.

Защищённые экраны Android и UAC Windows не обходятся. Передача файлов — до 50 ГиБ. Для паузы и продолжения исходный файл должен остаться доступным и неизменным. Нужна папка приёма на NTFS или другом диске с поддержкой жёстких ссылок; FAT/exFAT не поддерживаются. Незавершённые передачи хранятся до 7 дней и не считаются готовыми файлами. Подготовка большого файла может занять время; во время подготовки и передачи держи Android-приложение на экране. Совместимость с каждым устройством не гарантируется. Текущий режим H.264 экрана ПК использует NVIDIA NVENC: нужна поддерживаемая видеокарта NVIDIA и подходящий драйвер. Наличие FFmpeg само по себе не гарантирует работу этого режима на любом Windows-ПК.

## Как выглядит / Screenshot

Android **1.16** — реальный скриншот фрагмента кнопок управления. Настройки подключения и системная панель обрезаны. / Actual Android **1.16** screenshot, cropped to the control buttons; connection settings and the system bar are excluded.

<img src="docs/images/android-current.png" alt="Реальный скриншот Android 1.16 — фрагмент кнопок управления / Actual Android 1.16 screenshot — control buttons" width="320">

## О проекте

DroidBridge сделан с помощью ИИ изначально для себя — чтобы управлять домашним компьютером с телефона. Это экспериментальный личный проект, которым автор делится с другими. ИИ участвовал в написании кода; это не обещание безошибочной работы или профессиональной поддержки. Пользуйся только на своих устройствах или с разрешения их владельца.

Нашёл ошибку или есть идея — [создай Issue](https://github.com/alexfduch231-prog/DroidBridge/issues). Для разработки: [инструкция](docs/DEVELOPMENT.md), [участие](CONTRIBUTING.md), [безопасность](SECURITY.md). Оригинальный код — [MIT](LICENSE).

---

# English

Use your phone as a remote for your Windows PC, or view your phone on the computer. DroidBridge works on the same local network, without a cloud service.

**[Windows and Android — download](https://github.com/alexfduch231-prog/DroidBridge/releases/latest)**

Windows **1.0.7** has one main window with sidebar sections. Android **1.16** (build **26**), together with Windows **1.0.7**, shows program icons from the EXE files and LNK shortcuts configured on the PC. If an icon cannot be obtained or either side is older, a generic program icon remains. Android **1.15** remains compatible with existing features.

## What you can do

- View and control the PC screen from your phone: click, scroll and enter text.
- View Android on your PC, with optional phone control. Audio requires Android 10+ and an app that allows playback capture.
- Send files from your phone to a folder you choose on the PC.
- Lock, shut down or restart the PC, control media and launch programs you select. Wake-on-LAN can wake the PC if enabled in its hardware settings.

## Get started

1. Download the Windows installer and Android APK from the release page. You do not need the **Source code** archives. In Windows 1.0.7, the APK download QR is under **«Подключение» → «Установить на телефон»** (Connection → Install on phone). If already installed, choose **«Уже установлено → подключить к ПК»** (Already installed → connect to PC).
2. Install both apps and connect them to the same trusted home network. Requires Windows 10/11 x64 and Android 5+; phone-control gestures require Android 7+.
3. Click **«Запустить сервер»** (Start server) at the top of the Windows window. Inside **«Подключение»** (Connection), complete the one-time waking setup before new pairing and choose **«Продолжить сопряжение»** (Continue pairing); see the [setup requirements](docs/GETTING_STARTED.md#one-time-setup-before-new-pairing). Then select your home network adapter and choose **Create new QR**. Stay in this section while pairing.
4. Open the QR link on Android, or paste the copied link into **Add PC**. Compare the code on both devices, click **Allow** on the PC, then **Save PC** on the phone.
5. Try **Lock** or **View PC screen** on Android. For phone-to-PC mirroring, use **«Экран телефона»** (Phone screen) on Windows. Programs and received-file destinations have their own sections; media tools are under **«Настройки»** (Settings).

The standard Windows installer **includes FFmpeg and ffplay and selects them automatically**. No separate download, PATH editing or Python installation is needed. Manual selection is for recovery or a deliberate tool replacement.

**[Full setup guide and troubleshooting](docs/GETTING_STARTED.md#english)** · [What's new](CHANGELOG.md)

## One main window

Windows 1.0.7 has **«Подключение»** (Connection), **«Экран телефона»** (Phone screen), **«Программы»** (Applications), **«Приём файлов»** (Received files), **«Включение ПК»** (Wake PC) and **«Настройки»** (Settings) inside one main window. Android download and pairing belong to Connection; phone viewing has its own section. Keep the DroidBridge main window open and its server running. On the paired phone, tap **Cast phone to PC** and approve Android's system capture prompt: the screen opens here without typing an IP. Control enables automatically only if you have already enabled the Android Accessibility service; the app does not grant that permission for you. Manual IP connection remains available. A server running alone can handle commands, but not embedded phone viewing. System permission prompts, file pickers and confirmations can still open dialogs. The sidebar currently uses Russian labels.

Leaving pairing invalidates its temporary QR: return to Connection and create a new one. Leaving phone viewing closes the viewer connection. The server starts only when you request it; its status does not establish network reachability.

**One-time Wake-on-LAN setup inside Connection is required before new pairing.** A fresh Windows check must confirm Magic Packet **enabled** on the same physical adapter, with your explicit acknowledgements of a manual BIOS/UEFI check and local-network compatibility. Disabled, unsupported or unknown status and check errors cannot complete the step. Startup runs no automatic check; saved completion is checked again only for explicit new pairing and reused for the same adapter with Magic Packet enabled. An existing working pair is not disconnected. The regular **«Включение ПК»** (Wake PC) section remains for diagnostics and configuration; checking only reads settings. **«Настроить Windows»** (Configure Windows) requires your consent and UAC approval and enables only the selected physical adapter's supported Magic Packet setting. Configure BIOS/UEFI manually using the manufacturer's instructions. Even **100%** means completed checks or configuration, not guaranteed waking. [Setup and testing](docs/GETTING_STARTED.md#waking-and-shutting-down-the-pc).

## Updates

Since 1.0.4, Windows and Android check for updates at startup and offer **Later / Update**. Install the first updater-capable version manually. Windows downloads and verifies the installer before closing its own components and reopens the app only after successful installation. Android requires system APK-installation approval; reopening or a notification depends on system restrictions. [Details](docs/GETTING_STARTED.md#updates).

## Limitations

**Trusted LAN only.** TLS protects pairing, but the main command, video and file transport is **not encrypted**. Do not forward router ports to the Internet. There is no cloud connection.

Android protected screens and Windows UAC restrictions are not bypassed. Uploads are limited to 50 GiB. For pause and resume, the source file must remain accessible and unchanged. The destination must use NTFS or another hard-link-capable disk; FAT/exFAT is unsupported. Incomplete transfers are kept for up to 7 days and are not finished files. Large-file preparation may take time; keep Android in the foreground during preparation and transfer. Compatibility with every device is not guaranteed. Current PC-screen H.264 encoding uses NVIDIA NVENC and requires a supported NVIDIA GPU and driver; bundling FFmpeg does not make this mode work on every Windows PC.

## About

DroidBridge was built with AI, originally for the author's own home setup, and is shared as an experimental personal project. AI helped write the code; that is not a promise of bug-free operation or professional support. Use it only on your own devices or with their owner's permission.

Bugs and ideas: [Issues](https://github.com/alexfduch231-prog/DroidBridge/issues). For developers: [development guide](docs/DEVELOPMENT.md), [contributing](CONTRIBUTING.md), [security](SECURITY.md). Original code: [MIT](LICENSE).
