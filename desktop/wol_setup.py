"""Local Wake-on-LAN readiness; importing this module never probes or changes Windows."""
import base64
from dataclasses import dataclass
import json
import os
from pathlib import Path
import queue
import subprocess
import threading
import uuid


class WolSetupError(Exception):
    """A human-readable bounded local diagnostics/setup failure."""


@dataclass(frozen=True)
class WolReport:
    adapter_name: str = ''
    adapter_guid: str = ''
    magic_packet: str = 'unknown'
    wake_verified: bool = False


# Get-PM requires elevation on some drivers/Windows versions. Failure is unknown,
# not proof that hardware lacks support. Default route is a heuristic, not proof
# this adapter serves the paired phone (especially with multiple NICs).
_SELECTION_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$physical = @(Get-NetAdapter -Physical | Where-Object { $_.Status -eq 'Up' })
$routes = @(Get-NetRoute -AddressFamily IPv4 -DestinationPrefix '0.0.0.0/0' | ForEach-Object {
    $route = $_
    $nic = @($physical | Where-Object { $_.ifIndex -eq $route.InterfaceIndex })
    if ($nic.Count -eq 1) {
        $ip = Get-NetIPInterface -AddressFamily IPv4 -InterfaceIndex $route.InterfaceIndex
        [pscustomobject]@{ Adapter = $nic[0]; Score = ([long]$route.RouteMetric + [long]$ip.InterfaceMetric) }
    }
})
$ordered = @($routes | Sort-Object Score)
$selected = $null
if ($ordered.Count -gt 0) {
    $best = @($ordered | Where-Object { $_.Score -eq $ordered[0].Score } | Group-Object { $_.Adapter.InterfaceGuid })
    if ($best.Count -eq 1) { $selected = $ordered[0] }
}
$a = $null
if ($selected) { $a = $selected.Adapter }
"""

DIAGNOSTIC_SCRIPT = _SELECTION_SCRIPT + r"""
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$result = @{ adapter = $null; selection = 'default_route' }
if ($a) {
    $magic = 'Unknown'
    try {
        $pm = @(Get-NetAdapterPowerManagement -Name ([WildcardPattern]::Escape([string]$a.Name)))
        if ($pm.Count -eq 1 -and $pm[0].InterfaceDescription -eq $a.InterfaceDescription) {
            $magic = [string]$pm[0].WakeOnMagicPacket
        }
    } catch { }
    $result.adapter = @{ name = [string]$a.Name; guid = [string]$a.InterfaceGuid; status = [string]$a.Status; magic_packet = $magic }
}
$result | ConvertTo-Json -Depth 4 -Compress
"""

BIOS_GUIDE = (
    'После Windows проверь BIOS/UEFI вручную. В инструкции к своей плате найди Wake on LAN, '
    'Power On by PCI-E / PME Event Wake Up и разреши пробуждение по сети. Названия зависят от платы; '
    'не меняй незнакомые параметры. ErP / Deep Sleep иногда отключают питание сетевой карты в выключенном состоянии: '
    'проверь руководство производителя. DroidBridge не меняет BIOS и не перезагружает ПК.\n\n'
    'Для обычного WOL нужен Ethernet-кабель, питание ПК от розетки и поддержка сетевой карты/платы. '
    'Wi-Fi (WoWLAN), USB-адаптеры и включение после полного выключения поддерживаются не всегда. '
    'Быстрый запуск Windows и состояния сна тоже влияют; здесь они автоматически не меняются. '
    'Без дежурного питания включить ПК по сети невозможно.\n\n'
    'Настоящий тест выполняй вручную: сохрани работу, по своему решению переведи ПК в поддерживаемый режим '
    'и отправь пробуждение с телефона в той же LAN. Эта страница не усыпляет и не выключает ПК. '
    'Через интернет потребуются отдельные безопасные настройки сети; открывать удалённое администрирование не нужно.'
)


def parse_diagnostics(raw):
    if not isinstance(raw, str) or len(raw) > 65536:
        raise WolSetupError('Некорректный ответ проверки Windows.')
    try:
        data = json.loads(raw.lstrip('\ufeff'))
        if not isinstance(data, dict) or 'adapter' not in data:
            raise ValueError()
        adapter = data['adapter']
        if adapter is None:
            return WolReport()
        if not isinstance(adapter, dict) or adapter.get('status') != 'Up':
            raise ValueError()
        name = adapter.get('name')
        if not isinstance(name, str) or not name or len(name) > 256:
            raise ValueError()
        guid = str(uuid.UUID(adapter['guid']))
        magic = str(adapter.get('magic_packet')).lower()
        if magic not in ('enabled', 'disabled', 'unsupported'):
            magic = 'unknown'
        return WolReport(name, guid, magic)
    except (ValueError, TypeError, KeyError, RecursionError, AttributeError):
        raise WolSetupError('Некорректный ответ проверки Windows.') from None


def summary_text(report):
    if not report.adapter_name:
        return 'Активный физический адаптер с IPv4-маршрутом по умолчанию не найден. Пробуждение не проверено.'
    states = {'enabled': 'Magic Packet включён в Windows', 'disabled': 'Magic Packet выключен в Windows',
              'unsupported': 'Драйвер сообщает: Magic Packet не поддерживается',
              'unknown': 'Windows не раскрыла настройку Magic Packet (могут требоваться права администратора)'}
    return (f'{report.adapter_name}: {states[report.magic_packet]}. Пробуждение не проверено. '
            'Адаптер выбран по маршруту по умолчанию; при нескольких сетях сверь его с сетью телефона.')


def _powershell():
    if os.name != 'nt':
        raise WolSetupError('Эта проверка доступна только в Windows.')
    # Use the trusted Windows system directory, not PATH or the current folder.
    import ctypes
    buffer = ctypes.create_unicode_buffer(32768)
    size = ctypes.windll.kernel32.GetWindowsDirectoryW(buffer, len(buffer))
    if not size or size >= len(buffer):
        raise WolSetupError('Не удалось найти системный Windows PowerShell.')
    return str(Path(buffer.value) / 'System32' / 'WindowsPowerShell' / 'v1.0' / 'powershell.exe')


def _encoded(script):
    return base64.b64encode(script.encode('utf-16-le')).decode('ascii')


def _run_script(script, timeout=20):
    try:
        return subprocess.run([_powershell(), '-NoLogo', '-NoProfile', '-NonInteractive', '-EncodedCommand', _encoded(script)],
                              shell=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout,
                              creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except (OSError, subprocess.TimeoutExpired):
        raise WolSetupError('Проверка Windows недоступна или превысила время ожидания. Настройки могли остаться без изменений.') from None


def check_wol_readiness():
    """Read-only synchronous snapshot; callers must run this off the UI thread."""
    result = _run_script(DIAGNOSTIC_SCRIPT)
    if result.returncode != 0:
        raise WolSetupError('Не удалось прочитать сетевые параметры Windows. Проверь адаптер вручную.')
    try:
        return parse_diagnostics(result.stdout.decode('utf-8'))
    except UnicodeError:
        raise WolSetupError('Некорректный ответ проверки Windows.') from None


def _validated_guid(value):
    if not isinstance(value, str):
        raise WolSetupError('Не выбран сетевой адаптер.')
    try:
        return str(uuid.UUID(value))
    except (ValueError, AttributeError):
        raise WolSetupError('Некорректный идентификатор адаптера.') from None


def setup_script(adapter_guid):
    """Only variable input is a canonical UUID, never a script/path/adapter name."""
    guid = _validated_guid(adapter_guid)
    return _SELECTION_SCRIPT + "\n$expected = [guid]'" + guid + "'\n" + r"""
try {
    if (-not $a -or ([guid]$a.InterfaceGuid) -ne $expected) { exit 21 }
    $command = Get-Command Set-NetAdapterPowerManagement -ErrorAction Stop
    if (-not $command.Parameters.ContainsKey('NoRestart') -or -not $command.Parameters.ContainsKey('InputObject')) { exit 22 }
    $pm = @(Get-NetAdapterPowerManagement -Name ([WildcardPattern]::Escape([string]$a.Name)))
    if ($pm.Count -ne 1 -or $pm[0].InterfaceDescription -ne $a.InterfaceDescription) { exit 21 }
    if ([string]$pm[0].WakeOnMagicPacket -eq 'Enabled') { exit 0 }
    if ([string]$pm[0].WakeOnMagicPacket -ne 'Disabled') { exit 22 }
    Set-NetAdapterPowerManagement -InputObject $pm[0] -WakeOnMagicPacket Enabled -NoRestart -ErrorAction Stop
    exit 0
} catch { exit 23 }
"""


_setup_lock = threading.Lock()
_setup_uncertain = threading.Event()


def setup_available():
    """Process-wide fail-closed state survives settings-page disposal/reopening."""
    return not _setup_uncertain.is_set() and not _setup_lock.locked()


def configure_windows(adapter_guid, *, consent=False):
    """One explicit, local UAC action; no persistent elevated helper or network API."""
    if consent is not True:
        raise WolSetupError('Изменения требуют твоего явного подтверждения.')
    if not _setup_lock.acquire(blocking=False):
        raise WolSetupError('Настройка Windows уже выполняется. Дождись завершения.')
    try:
        if _setup_uncertain.is_set():
            raise WolSetupError('После прерванной настройки состояние неизвестно. Автонастройка заблокирована '
                                'до перезапуска DroidBridge. Сначала дождись закрытия окна администратора/UAC '
                                'и проверь адаптер вручную; не перезапускай приложение для повтора, пока окно открыто.')
        return _configure_windows(adapter_guid, consent=consent)
    finally:
        _setup_lock.release()


def _configure_windows(adapter_guid, *, consent=False):
    if consent is not True:
        raise WolSetupError('Изменения требуют твоего явного подтверждения.')
    guid = _validated_guid(adapter_guid)
    encoded = _encoded(setup_script(guid))
    # The elevated program and both script bodies stay in memory. No writable
    # on-disk script/config is later trusted by an administrator process.
    outer = r"""
$ErrorActionPreference = 'Stop'
try {
    $exe = Join-Path ([Environment]::GetFolderPath('Windows')) 'System32\WindowsPowerShell\v1.0\powershell.exe'
    $process = Start-Process -FilePath $exe -Verb RunAs -Wait -PassThru -ArgumentList @('-NoLogo','-NoProfile','-NonInteractive','-EncodedCommand','""" + encoded + r"""')
    exit $process.ExitCode
} catch { exit 20 }
"""
    try:
        result = _run_script(outer, timeout=180)
    except WolSetupError:
        _setup_uncertain.set()
        raise WolSetupError('Ожидание настройки прервано: состояние неизвестно. Окно администратора может '
                            'завершить изменение позднее. Автонастройка заблокирована до перезапуска DroidBridge. '
                            'Сначала дождись закрытия окна UAC/PowerShell и проверь свойства адаптера вручную. '
                            'Не перезапускай приложение для повтора, пока окно администратора открыто.') from None
    messages = {
        20: 'Windows не разрешила запуск администратора или запрос UAC отменён. Автонастройка не выполнена.',
        21: 'Активный адаптер или маршрут изменился. Обнови проверку; изменения не выполнены.',
        22: 'Драйвер не позволяет безопасно включить Magic Packet без перезапуска. Используй инструкцию вручную.',
        23: 'Windows не смогла завершить настройку. Проверь свойства адаптера вручную: изменение могло примениться частично.',
    }
    if result.returncode != 0:
        raise WolSetupError(messages.get(result.returncode, 'Windows не подтвердила завершение настройки. Проверь свойства адаптера вручную.'))
    report = check_wol_readiness()
    if report.adapter_guid != guid:
        raise WolSetupError('Настройка завершилась, но маршрут изменился: повторно проверить выбранный адаптер не удалось.')
    return report


def start_diagnostics(results):
    """Queue progress and one report/error without accessing Tk from a worker."""
    def work():
        results.put(('progress', 1))
        try:
            report = check_wol_readiness()
            results.put(('progress', 2))
            results.put(('progress', 3))
            results.put(('done', report))
        except WolSetupError as error:
            results.put(('error', str(error)))
        except Exception:
            results.put(('error', 'Не удалось проверить параметры Windows.'))
    worker = threading.Thread(target=work, name='wol-diagnostics', daemon=True)
    worker.start()
    return worker


def progress_text(step, label):
    return f'{step}/3 · {round(step * 100 / 3)}% · {label}'


def build_wol_page(parent, data_dir):
    """Build an unpacked local settings page. data_dir is intentionally not written."""
    import tkinter as tk
    from tkinter import messagebox, ttk
    try:
        from desktop.theme import scrollable_card
    except ModuleNotFoundError:
        from theme import scrollable_card
    window = ttk.Frame(parent, style='DB.TFrame')
    frame = scrollable_card(window)
    ttk.Label(frame, text='Включение ПК по сети · Wake-on-LAN', style='DB.Heading.TLabel').pack(anchor='w')
    ttk.Label(frame, text='Сначала проверяем Windows без изменений. Автонастройка запускается только по твоему '
              'подтверждению и с системным запросом прав администратора. Выключенный ПК эта страница настроить не может.',
              style='DB.Muted.TLabel', wraplength=620).pack(anchor='w', pady=10)
    status = tk.StringVar(window, value='Проверка ещё не выполнена.')
    progress_label = tk.StringVar(window, value=progress_text(0, 'Ожидание проверки'))
    ttk.Label(frame, textvariable=status, wraplength=620).pack(anchor='w', pady=6)
    ttk.Label(frame, textvariable=progress_label, style='DB.Muted.TLabel', wraplength=620).pack(anchor='w')
    progress = ttk.Progressbar(frame, maximum=3, mode='determinate')
    progress.pack(fill='x', pady=8)
    ttk.Label(frame, text='100% означает завершение проверок или настройки, а не успешное пробуждение ПК. '
              'После настройки без перезапуска карты драйвер может применить параметр только при следующем '
              'плановом перезапуске. Приложение не перезапускает карту или компьютер.',
              style='DB.Muted.TLabel', wraplength=620).pack(anchor='w', pady=6)
    results = queue.Queue()
    state = {'disposed': False, 'timer': None, 'busy': False, 'report': None, 'setup': False}

    def cleanup(event=None):
        if event is not None and event.widget is not window:
            return
        state['disposed'] = True
        if state['timer'] is not None:
            try:
                window.after_cancel(state['timer'])
            except tk.TclError:
                pass
            state['timer'] = None

    def dispose():
        cleanup()
        if window.winfo_exists():
            window.destroy()

    window.dispose = dispose
    window.bind('<Destroy>', cleanup, add='+')
    window.is_busy = lambda: state['busy']

    def set_busy(value):
        state['busy'] = value
        refresh.configure(state='disabled' if value else 'normal')
        report = state['report']
        configure.configure(state='normal' if not value and setup_available() and report and report.adapter_guid and
                            report.magic_packet in ('disabled', 'unknown') else 'disabled')

    def poll():
        state['timer'] = None
        if state['disposed']:
            return
        try:
            while True:
                kind, value = results.get_nowait()
                if kind == 'progress':
                    progress['value'] = value
                    labels = {1: 'Читаем активный адаптер Windows', 2: 'Разбираем результат', 3: 'Проверки завершены'}
                    progress_label.set(progress_text(value, labels[value]))
                elif kind == 'done':
                    state['report'] = value
                    prefix = ''
                    if state['setup']:
                        prefix = ('Windows завершила настройку; параметр перепроверен. ' if value.magic_packet == 'enabled' else
                                  'Windows завершила команду, но повторная проверка не подтвердила включение; проверь вручную. ')
                    status.set(prefix + summary_text(value))
                    set_busy(False)
                elif kind == 'error':
                    status.set(value)
                    progress_label.set('Проверка/настройка не подтверждена · смотри инструкцию ниже')
                    set_busy(False)
        except queue.Empty:
            if state['busy']:
                state['timer'] = window.after(75, poll)

    def check():
        if state['busy']:
            return
        state['setup'] = False
        state['report'] = None
        progress['value'] = 0
        set_busy(True)
        status.set('Читаем сетевые настройки; изменения не вносятся…')
        start_diagnostics(results)
        state['timer'] = window.after(75, poll)

    def setup():
        report = state['report']
        if state['busy'] or not report or not report.adapter_guid:
            return
        if not messagebox.askyesno('Настроить Windows для Wake-on-LAN?',
                f'Адаптер: {report.adapter_name}\nGUID: {report.adapter_guid}\n\n'
                'Проверь, что телефон использует эту же локальную сеть. Будет запрошено разрешение UAC. '
                'DroidBridge заново проверит адаптер и включит только WakeOnMagicPacket, только если драйвер '
                'явно сообщает Disabled. Если параметр уже включён — ничего не изменит. '
                'Неподдерживаемые и неизвестные драйверу параметры не меняются.\n\n'
                'Сетевая карта не будет перезапущена. BIOS, быстрый запуск, брандмауэр, роутер и другие '
                'параметры питания не меняются. Работающее пробуждение не гарантируется. Продолжить?', parent=window):
            return
        state['setup'] = True
        set_busy(True)
        progress['value'] = 1
        progress_label.set(progress_text(1, 'Подтверди запрос UAC; ждём настройку Windows'))
        status.set('Не закрывай страницу до окончания настройки. Отмена UAC не включает Magic Packet.')
        def work():
            try:
                updated = configure_windows(report.adapter_guid, consent=True)
                results.put(('progress', 2))
                results.put(('progress', 3))
                results.put(('done', updated))
            except WolSetupError as error:
                results.put(('error', str(error)))
            except Exception:
                results.put(('error', 'Не удалось подтвердить настройку. Проверь свойства адаптера вручную.'))
        threading.Thread(target=work, name='wol-local-setup', daemon=True).start()
        state['timer'] = window.after(75, poll)

    row = ttk.Frame(frame, style='DB.Card.TFrame')
    row.pack(fill='x', pady=8)
    refresh = ttk.Button(row, text='Повторить проверку', command=check)
    refresh.pack(side='left')
    configure = ttk.Button(row, text='Настроить Windows…', style='DB.Primary.TButton', command=setup, state='disabled')
    configure.pack(side='left', padx=8)
    ttk.Label(frame, text='Windows вручную', style='DB.Heading.TLabel').pack(anchor='w', pady=(12, 6))
    ttk.Label(frame, text='Открой Диспетчер устройств → Сетевые адаптеры → выбранный адаптер → Свойства. '
              'В «Дополнительно» ищи Wake on Magic Packet; в управлении питанием — разрешение пробуждения '
              'и только Magic Packet, если они доступны. Названия и наличие зависят от драйвера. '
              'Для неизвестного или неподдерживаемого параметра сверяйся с документацией производителя.',
              wraplength=620, style='DB.Muted.TLabel').pack(anchor='w')
    ttk.Label(frame, text='Дальше — BIOS/UEFI и ручной тест', style='DB.Heading.TLabel').pack(anchor='w', pady=(16, 6))
    ttk.Label(frame, text=BIOS_GUIDE, wraplength=620, style='DB.Muted.TLabel').pack(anchor='w')
    check()
    return window
