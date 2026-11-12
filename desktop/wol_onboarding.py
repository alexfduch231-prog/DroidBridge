"""Private one-time Wake-on-LAN prerequisite for explicit new pairing only."""
import json
import os
from pathlib import Path
import tempfile

try:
    from desktop import wol_setup as wol
except ModuleNotFoundError:
    import wol_setup as wol


def load_completion(data_dir):
    """Read bounded local state only; never probe Windows on application startup."""
    try:
        with (Path(data_dir) / 'wol_onboarding.json').open('rb') as stream:
            raw = stream.read(4097)
        if len(raw) > 4096:
            return None
        record = json.loads(raw)
        if (not isinstance(record, dict) or type(record.get('schema')) is not int or record['schema'] != 1
                or record.get('completed') is not True or record.get('bios_manual_ack') is not True
                or record.get('network_compatible') is not True):
            return None
        guid = wol._validated_guid(record.get('adapter_guid'))
        if guid != record['adapter_guid']:
            return None
        return {key: record[key] for key in ('schema', 'adapter_guid', 'bios_manual_ack', 'network_compatible', 'completed')}
    except (OSError, ValueError, UnicodeError, RecursionError, wol.WolSetupError):
        return None


def matches_completion(record, report):
    return bool(record and report and report.adapter_name and report.adapter_guid == record['adapter_guid']
                and report.magic_packet == 'enabled')


def complete_onboarding(data_dir, *, adapter_guid, bios_manual_ack, network_compatible, cancelled=None):
    """Fresh check and atomic commit; invoke off Tk's thread. Never a wake proof."""
    guid = wol._validated_guid(adapter_guid)
    if bios_manual_ack is not True or network_compatible is not True:
        raise wol.WolSetupError('Подтверди ручную проверку BIOS/UEFI и совместимость локальной сети.')
    report = wol.check_wol_readiness()
    if cancelled is not None and cancelled.is_set():
        raise wol.WolSetupError('Настройка отменена: страница закрыта. Завершение не сохранено.')
    if not report.adapter_name or report.adapter_guid != guid or report.magic_packet != 'enabled':
        raise wol.WolSetupError('Завершение заблокировано: свежая проверка должна подтвердить Magic Packet '
                                'Enabled на том же физическом адаптере. Проверь Windows и повтори проверку.')
    record = {'schema': 1, 'adapter_guid': guid, 'bios_manual_ack': True,
              'network_compatible': True, 'completed': True}
    temporary = None
    try:
        directory = Path(data_dir)
        directory.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=directory,
                                         prefix='.wol-onboarding-', suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(record, stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        if cancelled is not None and cancelled.is_set():
            raise wol.WolSetupError('Настройка отменена: страница закрыта. Завершение не сохранено.')
        os.replace(temporary, directory / 'wol_onboarding.json')
    except OSError:
        raise wol.WolSetupError('Не удалось сохранить завершение настройки. Сопряжение пока заблокировано.') from None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return record


def build_onboarding_page(parent, data_dir, on_completed):
    """Embedded, disposable prerequisite; workers only exchange queue messages."""
    import queue
    import threading
    import tkinter as tk
    from tkinter import ttk

    saved = load_completion(data_dir)
    state = {'report': None, 'saved': False, 'busy': False, 'disposed': False, 'timer': None,
             'generation': 0, 'save_generation': None}
    results = queue.Queue(maxsize=2)
    cancelled = threading.Event()
    page = wol.build_wol_page(parent, data_dir, on_report=lambda report: report_changed(report), auto_check=False)
    frame = page.content
    explanation = tk.StringVar(page, value='Перед первым сопряжением настрой включение ПК по сети. '
        'Пропустить этот шаг нельзя. BIOS/UEFI приложение проверить не может; реальное пробуждение не проверяется.')
    ttk.Label(frame, textvariable=explanation, wraplength=620, style='DB.Muted.TLabel').pack(anchor='w', pady=12)
    bios = tk.BooleanVar(page, value=False)
    network = tk.BooleanVar(page, value=False)
    ttk.Checkbutton(frame, text='Я вручную проверил BIOS/UEFI по инструкции производителя и разрешил WoL',
                    variable=bios).pack(anchor='w', pady=4)
    ttk.Checkbutton(frame, text='Я проверил совместимость адаптера, питание ПК и локальную сеть телефона',
                    variable=network).pack(anchor='w', pady=4)

    def report_changed(report):
        state['generation'] += 1
        state['report'] = report
        state['saved'] = False
        if report is None:
            continue_button.configure(state='disabled')
            return
        if matches_completion(saved, report):
            state['saved'] = True
            on_completed()
            return
        if not report.adapter_name or report.magic_packet != 'enabled':
            explanation.set('Сопряжение заблокировано. Нужен активный физический адаптер с Magic Packet Enabled. '
                'Если Disabled — настрой Windows с подтверждением UAC или вручную. Если Unknown/Unsupported '
                'или адаптер не найден — проверь драйвер, Ethernet и руководство производителя, затем повтори проверку. '
                'Это не подтверждает BIOS или реальное пробуждение.')
        else:
            explanation.set('Windows: Magic Packet включён. Прочти инструкцию BIOS/UEFI и подтверди оба пункта ниже. '
                'Перед сохранением адаптер будет проверен ещё раз. Это не доказательство работающего пробуждения.')
        continue_button.configure(state='disabled')

    def poll():
        state['timer'] = None
        if state['disposed']:
            return
        try:
            kind, value = results.get_nowait()
        except queue.Empty:
            state['timer'] = page.after(75, poll)
            return
        state['busy'] = False
        save_button.configure(state='normal')
        if kind == 'done' and (state['save_generation'] != state['generation']
                               or not matches_completion(load_completion(data_dir), state['report'])):
            state['saved'] = False
            explanation.set('Результат сохранения устарел: после него началась новая проверка или адаптер изменился. '
                            'Повтори проверку и завершение настройки. Сопряжение заблокировано.')
            continue_button.configure(state='disabled')
        elif kind == 'done':
            state['saved'] = True
            explanation.set('Одноразовая настройка сохранена. BIOS отмечен только по твоему ручному подтверждению; '
                            'пробуждение не проверено. Теперь можно продолжить сопряжение.')
            continue_button.configure(state='normal')
        else:
            explanation.set(value)
            continue_button.configure(state='disabled')

    def save():
        report = state['report']
        if state['disposed'] or state['busy'] or page.is_busy():
            return
        state['saved'] = False
        continue_button.configure(state='disabled')
        if not report or not report.adapter_name or report.magic_packet != 'enabled' or bios.get() is not True or network.get() is not True:
            explanation.set('Нельзя завершить настройку: нужна проверка Magic Packet Enabled и оба ручных подтверждения.')
            return
        state['busy'] = True
        state['save_generation'] = state['generation']
        save_button.configure(state='disabled')
        guid = report.adapter_guid
        def work():
            try:
                complete_onboarding(data_dir, adapter_guid=guid, bios_manual_ack=True,
                                    network_compatible=True, cancelled=cancelled)
                results.put(('done', None))
            except wol.WolSetupError as error:
                results.put(('error', str(error)))
            except Exception:
                results.put(('error', 'Не удалось сохранить настройку. Повтори проверку; сопряжение заблокировано.'))
        threading.Thread(target=work, name='wol-onboarding-save', daemon=True).start()
        state['timer'] = page.after(75, poll)

    def proceed():
        if (not state['disposed'] and state['saved'] and not state['busy'] and not page.is_busy()
                and matches_completion(load_completion(data_dir), state['report'])):
            on_completed()

    save_button = ttk.Button(frame, text='Проверить и завершить настройку', command=save)
    save_button.pack(anchor='w', pady=(12, 6))
    continue_button = ttk.Button(frame, text='Продолжить сопряжение', command=proceed, state='disabled', style='DB.Primary.TButton')
    continue_button.pack(anchor='w', pady=6)
    original_dispose = page.dispose
    def cleanup(event=None):
        if event is not None and event.widget is not page:
            return
        state['disposed'] = True
        cancelled.set()
        if state['timer'] is not None:
            try:
                page.after_cancel(state['timer'])
            except tk.TclError:
                pass
            state['timer'] = None
    def dispose():
        cleanup()
        original_dispose()
    page.dispose = dispose
    page.bind('<Destroy>', cleanup, add='+')
    page.check()
    return page
