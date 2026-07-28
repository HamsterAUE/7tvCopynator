import ApiClient
import TokenModule

import json
import sys
import os

import time

if getattr(sys, 'frozen', False):
    project_dir = os.path.dirname(sys.executable)
else:
    project_dir = os.path.dirname(os.path.abspath(__file__))

GQLHelper = ApiClient.ApiClient(project_dir)

proxies = {
    'http': 'socks5h://127.0.0.1:40000',
    'https': 'socks5h://127.0.0.1:40000'
}


def input_set(eset, show_total=False):
    print("\nВыберите какой эмоутсет копировать (0 для отмены):")
    for i, s in enumerate(eset, start=1):
        if show_total:
            total_emotes = s.get("emotes", {}).get("totalCount", 0)
            print(f"[{i}] {s['name']} - {total_emotes} емоутов")
        else:
            print(f"[{i}] {s['name']}")

    user_input = int(input("Введите номер: "))
    if user_input == 0:
        sys.exit(0)

    selected_set = eset[user_input - 1]
    print(f"Выбран сет: '{selected_set['name']}' (ID: {selected_set['id']})")
    return selected_set["id"], user_input - 1



token = None
cfg_dir = os.path.join(project_dir, "cfg.json")
user_from=None
set_from = None
set_to = None

if os.path.exists(cfg_dir):
    try:
        with open(cfg_dir, "r", encoding="utf-8") as f:
            token = json.loads(f.read()).get("7tv-token")  # Сразу пишем в token
    except Exception as e:
        print(f"Ошибка чтения конфига: {e}")

user_data = GQLHelper.get_me(token)

if user_data is None:
    print("Токен не найден или устарел. Запуск браузера для авторизации...")
    browser_path, user_data_dir = TokenModule.get_default_browser_info(project_dir)
    token = TokenModule.get_7tv_token(project_dir, browser_path, user_data_dir)

    if token:
        user_data = GQLHelper.get_me(token)
        if user_data:
            with open(cfg_dir, "w", encoding="utf-8") as f:
                f.write(json.dumps({"7tv-token": token}, indent=4))
            print("Новый токен успешно получен и сохранен")
        else:
            print("Браузер вернул токен, но не удалось определить вас.")
            input("\nНажмите Enter для выхода...")
    else:
        print("Не удалось получить токен из браузера.")
        input("\nНажмите Enter для выхода...")

if user_data:
    user_to = user_data['mainConnection']['platformUsername']
    print(f"Успешная авторизация как {user_to}")
    sets = user_data["emoteSets"]
    set_to, _ = input_set(sets)

    user_from = input("Введите ник владельца эмоутсета для копирования: ")

    total=0
    try:
        items = GQLHelper.get_user_esets(user_from)
        if not items:
            print("Пользователь не найден.")
            input("\nНажмите Enter для выхода...")
            exit()

        esets = items[0].get("emoteSets", [])
        if not esets:
            print("У этого пользователя нет эмоутсетов.")
            input("\nНажмите Enter для выхода...")
            exit()

        set_from, eseti = input_set(esets, True)
        total = esets[eseti].get("emotes", {}).get("totalCount", 0)
        source_emotes = esets[eseti].get("emotes", {}).get("items", [])
        print(f"Выбран целевой сет ID: {set_from}")

    except Exception as e:
        print(f"При попытке получить эмоут сет произошла ошибка: {e}")
        input("\nНажмите Enter для выхода...")
        exit()

    print("\nНачинаем копирование (нажмите Ctrl + C в любой момент для отмены)...")

    count = 1
    trouble_emotes = []
    user_cancelled = False
    try:
        for count, item in enumerate(source_emotes, start=1):

            emote_id = item["emote"]["id"]
            alias = item.get("alias") or item["emote"]["defaultName"]

            max_retries = 3
            success = False
            for attempt in range(1, max_retries + 1):
                try:
                    res_data = GQLHelper.add_to_eset(token, set_to, alias, emote_id)
                    if not res_data:
                        raise Exception("Пустой ответ от сервера")

                    # Проверяем не смертельные ошибки самого 7TV
                    if "errors" in res_data:
                        err_msg = res_data["errors"][0].get("message", "Неизвестная ошибка")

                        if "rate limit" in err_msg.lower() or "too many requests" in err_msg.lower():
                            print(
                                f"!! Превышен лимит запросов на [{alias}]. Пауза 2 сек (попытка {attempt}/{max_retries})...")
                            time.sleep(2)
                            continue
                        print(f"!! Пропуск [{alias}] ({count} из {total}): {err_msg}")
                        success = True
                        break
                    else:
                        print(f"[{count}/{total}] {alias} добавлен")
                        success = True
                        break

                except Exception as e:
                    if attempt < max_retries:
                        print(f"!! Сбой сети при добавлении [{alias}]: {e}. Повтор ({attempt}/{max_retries})...")
                        time.sleep(1.5)  # Пауза перед повторной попыткой
                    else:
                        print(f"!! Не удалось добавить [{alias}] ({count} из {total}) после {max_retries} попыток.")
            if not success:
                trouble_emotes.append({"alias": alias, "id": emote_id})

            # Защита от 429 Too Many Requests (Rate limit)
            time.sleep(0.4)
    except KeyboardInterrupt as e:
        print(f"Процесс отменен пользователем")
        user_cancelled = True
    if not user_cancelled:
        print("\nПроцесс копирования завершен!")

    if trouble_emotes:
        print(f"\nНе удалось скопировать ({len(trouble_emotes)} шт.):")
        for err_item in trouble_emotes:
            print(f" - {err_item['alias']}")

    input()
else:
    print("Работа скрипта не может быть продолжена без авторизации.")
    input("\nНажмите Enter для выхода...")

