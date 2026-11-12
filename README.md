# DroidBridge

**Русский ниже · [English](#english)**

## По-честному

Это **AI slop** — приложение, сделанное с помощью ИИ изначально исключительно для себя. Оно выросло из простой кнопки управления домашним ПК в набор функций для телефона и компьютера. Здесь нет команды профессиональной поддержки, независимого аудита безопасности или обещаний коммерческого качества.

Публикую исходники, потому что вдруг кому-то тоже окажется нужно и полезно. Код можно изучать, переделывать и улучшать. Баги, шероховатости интерфейса и спорные архитектурные решения вполне возможны. Пользуйся на свой риск, только на своих устройствах или с явного согласия их владельца.

## Как выглядит

**Это демоиллюстрации интерфейса, не реальные скриншоты.** Они построены по текущим формам и подписям; оформление системных элементов схематичное. Поля подключения пустые, примеры программ вымышленные. Личные экраны, ключи и QR здесь не использованы.

<p>
  <img src="docs/images/android-demo.svg" alt="DroidBridge Android — демоиллюстрация, не скриншот" width="440">
  <img src="docs/images/windows-demo.svg" alt="DroidBridge Windows — демоиллюстрация с тестовым каталогом" width="550">
</p>

## Что умеет

- **Телефон → ПК:** смотреть экран Windows в H.264 и нажимать прямо на изображение. Левый/правый клик, перетаскивание, прокрутка, ввод текста и кнопки вроде «Пуск», Esc и Enter.
- **ПК → телефон:** смотреть экран Android со звуком; при отдельном согласии через AccessibilityService — нажимать, делать свайпы, вводить текст, пользоваться «Назад», «Домой» и «Недавние».
- **Файлы:** отправлять выбранный файл с телефона в выбранную на ПК папку (по умолчанию Downloads). В Windows-приложении открой «Приём файлов / Received files» для локального выбора и сброса папки; изменение применяется к следующим загрузкам без перезапуска. Недоступная выбранная папка вызывает ошибку без скрытого сохранения в другое место. Есть прогресс, отмена и защита от перезаписи одноимённых файлов. Лимит — 50 ГиБ, возобновления передачи нет.
- **Обычные команды:** Wake-on-LAN, выключение с задержкой и отменой, перезагрузка, блокировка, медиаклавиши и мониторинг ресурсов ПК.
- **Автопоиск ПК:** после первоначального сопряжения находит IP, MAC и broadcast в общей локальной сети. Ответ проверяется существующим ключом; сам ключ discovery не рассылает.
- **Русский / English:** переключение языка Android-приложения с сохранением выбора.
- **Свои приложения:** список настраивается локально на ПК через «Программы»: выбери EXE или ярлык, задай имя. Android получает только ID и подписи кнопок; личный список владельца не входит в дистрибутив.
- **Первичное сопряжение:** одноразовая ссылка/QR на ПК, проверка TLS-сертификата по отпечатку и подтверждение одинакового кода на обоих устройствах. Постоянный ключ не помещается в QR.

Это **не полноценная замена Chrome Remote Desktop**: нет подключения через облако, обхода системных ограничений или гарантии работы на любом устройстве.

## Требования и запуск

Windows 10/11. Установщик Windows включает Python и зависимости интерфейса/сопряжения: отдельно ставить Python не требуется. **FFmpeg и FFplay устанавливаются отдельно пользователем** и должны быть в PATH; публичная сборка не включает сторонний FFmpeg-бандл. Без них поток H.264 и звук не заработают. Установщик не скачивает их скрытно. В Windows-панели запусти сервер, выбери «Сопряжение», открой одноразовую ссылку/QR на телефоне, сравни код и явно подтверди подключение на ПК и телефоне. Если камера не понимает `pcmote://`, вставь ссылку в «Добавить ПК» в Android. Разрешай порты TCP 8765/8767 и UDP 8766 только в доверенной локальной сети; 8767 слушает только пока открыто окно сопряжения.

Для запуска **из исходников** нужны Python 3.10+ с Tkinter, Pillow, cryptography, qrcode, FFmpeg и FFplay в PATH. Android 5+ для основных функций; управление телефоном жестами требует Android 7+. Для сборки: JDK 21, Android SDK platform 34 и build-tools 34.0.0, PowerShell.

1. Установи зависимости: `python -m pip install -r requirements.txt`.
2. Запусти `python listener/pc-listener.py`. При первом запуске создаётся локальный `listener/token.txt`. **Не публикуй этот файл.**
3. Введи тот же ключ в Android-приложении. При открытии приложения и подключении Wi-Fi выполняется автопоиск; IP/MAC/broadcast принимаются только из подписанного ответа. При необходимости введи IP вручную.
4. Разреши входящий TCP 8765 и UDP 8766 только для доверенной домашней сети. Wi-Fi client isolation между устройствами должен быть выключен. `start.ps1` запускает сервер и может настроить ограниченные правила Windows Firewall с правами администратора.
5. Для экрана телефона запусти трансляцию в Android и подтверди системное разрешение, затем запусти `python client/pc-viewer.pyw` и укажи адрес телефона и тот же ключ. Для управления отдельно включи службу в специальных возможностях Android и флажок управления в ПК-клиенте.

Автопоиск не выполняет сопряжение с неизвестными ПК. Выключенный компьютер ответить не может: Wake-on-LAN использует последние сохранённые MAC и broadcast. Его нужно отдельно разрешить в BIOS/драйвере.

### Сборка и тесты

Задай `JAVA_HOME` и `ANDROID_HOME`, затем выполни `powershell -ExecutionPolicy Bypass -File build.ps1`. При отсутствии keystore скрипт создаёт собственный debug-ключ. APK с другим ключом не обновит чужую установленную сборку. Храни свой keystore вне Git.

```powershell
python -m unittest discover -s listener -p "test_*.py" -v
python -m unittest discover -s client -p "test_*.py" -v
python -m unittest discover -s desktop -p "test_*.py" -v
python -m unittest discover -s app -p "test_*.py" -v
python -m unittest discover -s packaging -p "test_packaging.py" -v
```

Тесты не заменяют проверку реальных устройств. В процессе разработки проверялись передача файла и клики в обе стороны на одной связке Android/Windows; это не подтверждает совместимость со всеми устройствами. Файл на 50 ГиБ целиком не передавался при проверке — проверена логика лимита.

## Ограничения и безопасность

**Только доверенная локальная сеть.** HTTP, видео и передача файлов не имеют транспортного шифрования. HMAC автопоиска не шифрует остальные соединения. Не пробрасывай порты в Интернет; для удалённого доступа нужен отдельно настроенный защищённый туннель.

Защищённые экраны Android, UAC/secure desktop и права повышенных приложений не обходятся. Управление требует явного включения. Во время загрузки файла не закрывай Android-приложение; после обновления APK трансляцию телефона нужно запускать заново.

### Установщик из исходников

Инструкция и ограничения сборки Windows: [packaging/README.md](packaging/README.md). Установщик и APK публикуются отдельно от истории исходников только после проверки; наличие исходников не означает, что релизные бинарники уже доступны. Установщик не подписан коммерческим сертификатом, поэтому Windows может показать предупреждение SmartScreen. Название DroidBridge новое; совместимые внутренние идентификаторы `ru.alexv.pcmote`, `pcmote://` и каталог данных `VzaimoPult` сохранены, чтобы не потерять существующие настройки.

## Предлагай улучшения

Ошибки и идеи — через **Issues**. Изменения кода — **fork → ветка → Pull Request**. Принимать изменения решает владелец; публичный репозиторий не означает свободный push всем подряд. См. [CONTRIBUTING.md](CONTRIBUTING.md) и [SECURITY.md](SECURITY.md). Не прикладывай ключи, личные IP/MAC, файлы или непроверенные логи.

## Что опубликовано

Новая очищенная история исходников — не копия рабочего каталога. Без рабочих токенов, персональных адресов устройств, конфигурации приложений владельца, логов, снимков экрана, APK и ключей подписи. Namespace Android сохранён для совместимости пакета. MIT относится к оригинальному коду; сторонние названия и иконки принадлежат их владельцам, права на них этой лицензией не предоставляются.

---

# English

## Honestly

This is **AI slop**: an AI-built app originally made purely for personal use. It grew from a simple home-PC control button into a collection of phone/PC features. There is no professional support team, independent security audit or promise of commercial-grade quality.

I am sharing the source because somebody else might find it useful. Feel free to study, adapt and improve it. Expect bugs, rough edges and questionable architectural choices. Use it at your own risk, only on your own devices or with their owner's explicit permission.

## Interface preview

**These are interface illustrations, not real screenshots.** They follow the current forms and labels; system styling is schematic. Connection fields are empty and the sample app catalog is synthetic. No personal screens, keys or pairing QR codes were used.

<p>
  <img src="docs/images/android-demo.svg" alt="DroidBridge Android — interface illustration, not a screenshot" width="440">
  <img src="docs/images/windows-demo.svg" alt="DroidBridge Windows — interface illustration with a synthetic catalog" width="550">
</p>

## Features

- **Phone → PC:** view the Windows desktop over H.264 and interact directly with the image. Left/right click, drag, scroll, text input and shortcuts such as Start, Esc and Enter.
- **PC → phone:** view Android's screen with audio. With separate AccessibilityService consent, tap, swipe, enter text and use Back, Home and Recents.
- **File uploads:** send a selected phone file to a locally selected PC folder (Downloads by default). Open **Received files / Приём файлов** in the Windows app to choose/reset the destination; changes apply to new uploads without restarting. An unavailable selected folder fails explicitly instead of silently falling back elsewhere. Uploads come with progress, cancellation and collision-safe filenames. The limit is 50 GiB; interrupted uploads cannot be resumed.
- **Everyday controls:** Wake-on-LAN, delayed shutdown and cancellation, reboot, lock, media keys and PC resource monitoring.
- **LAN discovery:** after initial pairing, discover the PC's IP, MAC and broadcast address on the same local network. Replies are verified using the existing key; discovery does not transmit that key.
- **Russian / English:** a persistent language selector in the Android app.
- **Your applications:** manage the list locally through the Windows Applications panel: choose an EXE or shortcut and a name. Android receives only IDs and button labels; the original owner's personal list is not distributed.
- **Initial pairing:** a one-time PC link/QR, TLS certificate fingerprint pinning and matching-code approval on both devices. The permanent key is never embedded in the QR.

This is **not a complete Chrome Remote Desktop replacement**. There is no cloud relay, bypass of system restrictions or guarantee of compatibility with every device.

## Requirements and setup

Windows 10/11. The Windows installer includes Python and UI/pairing dependencies; a separate Python installation is not required. **Install FFmpeg and FFplay separately** and put them on PATH; the public installer does not redistribute the third-party FFmpeg bundle. H.264 and audio require these tools. Nothing downloads them silently. Start the server in the Windows panel, choose Pair, open the one-time link/QR on Android, compare the code and explicitly approve on the PC and phone. If the camera does not handle `pcmote://`, paste the link into Add PC in the Android app. Allow TCP 8765/8767 and UDP 8766 only on your trusted LAN; port 8767 listens only while the pairing window is open.

Running **from source** requires Python 3.10+ with Tkinter, Pillow, cryptography, qrcode, FFmpeg and FFplay on PATH. Android 5+ for core features; gesture-based phone control requires Android 7+. Building requires JDK 21, Android SDK platform 34, build-tools 34.0.0 and PowerShell.

1. Install dependencies: `python -m pip install -r requirements.txt`.
2. Run `python listener/pc-listener.py`. Its first run creates a local `listener/token.txt`. **Never publish this file.**
3. Enter the same key in the Android app. Discovery runs when opening the app and connecting to Wi-Fi; only signed IP/MAC/broadcast responses are accepted. Enter the PC IP manually if needed.
4. Allow inbound TCP 8765 and UDP 8766 only on your trusted home network. Disable Wi-Fi client isolation between the devices. `start.ps1` starts the server and can configure limited Windows Firewall rules when run as administrator.
5. For phone mirroring, start the broadcast on Android and approve the system prompt. Run `python client/pc-viewer.pyw` and enter the phone address and the same key. To control the phone, separately enable the app's Accessibility service and the PC viewer's control checkbox.

Discovery does not pair with unknown computers. A powered-off PC cannot reply; Wake-on-LAN uses the last saved MAC/broadcast. Enable it separately in the BIOS and network driver.

### Build and tests

Set `JAVA_HOME` and `ANDROID_HOME`, then run `powershell -ExecutionPolicy Bypass -File build.ps1`. The script generates its own debug keystore if missing. An APK signed with a different key cannot update somebody else's installed build. Keep your signing key out of Git.

```powershell
python -m unittest discover -s listener -p "test_*.py" -v
python -m unittest discover -s client -p "test_*.py" -v
python -m unittest discover -s desktop -p "test_*.py" -v
python -m unittest discover -s app -p "test_*.py" -v
python -m unittest discover -s packaging -p "test_packaging.py" -v
```

Automated tests do not replace real-device checks. File transfer and clicks in both directions were checked on one Android/Windows setup during development, not across all devices. An actual 50 GiB transfer was not performed; the size-limit logic was tested.

## Limitations and security

**Trusted LAN only.** HTTP, video and file transfers do not provide transport encryption. Discovery HMAC does not encrypt other connections. Do not expose the ports to the Internet; remote access requires a separately configured secure tunnel.

Android protected screens, UAC/secure desktop and elevated-app restrictions are not bypassed. Control requires explicit opt-in. Keep the Android app open during uploads. Restart phone mirroring after APK updates.

### Building the installer

See [packaging/README.md](packaging/README.md) for the Windows recipe and limitations. Installer/APK assets are published separately only after validation; source availability does not mean release binaries are already available. No commercial code-signing certificate is supplied, so Windows SmartScreen may warn. DroidBridge is the new name; compatible internal identifiers `ru.alexv.pcmote`, `pcmote://` and the `VzaimoPult` data folder are retained to preserve existing settings.

## Contributions

Use **Issues** for bugs and ideas. For code, **fork → branch → Pull Request**. The owner reviews contributions; public access does not grant direct push permissions. See [CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md). Never attach keys, personal device addresses, private files or unredacted logs.

## Publication scope

This is a fresh, cleaned source history, not a copy of the working directory. It excludes live keys, personal device addresses, the owner's app configuration, logs, screenshots, APKs and signing keys. The Android namespace is retained for package compatibility. MIT covers original code; third-party names and icons belong to their owners and are not licensed by this project.
