import json
import sys

import os
import subprocess
import shutil
import requests
import time
import winreg
from shlex import split

if getattr(sys, 'frozen', False):
    project_dir = os.path.dirname(sys.executable)
else:
    project_dir = os.path.dirname(os.path.abspath(__file__))

os.environ["PLAYWRIGHT_BROWSERS_PATH"] = os.path.join(project_dir, "pw-browsers")
api = "https://7tv.io/v4/gql"


proxies = {
    'http': 'socks5h://127.0.0.1:40000',
    'https': 'socks5h://127.0.0.1:40000'
}

#----------------- Поиск браузера по умолчанию в реестре -----
def get_default_browser_info():

    # Будем создавать изолированную сессию в локальном AppData пользователя
    # local_appdata = os.environ.get("LOCALAPPDATA", "")

    # Дефолтные настройки, если реестр не ответит
    browser_path = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

    try:
        #Читаем из реестра Windows, какая программа отвечает за HTTP ссылки
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                        r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\http\UserChoice") as key:
            prog_id, _ = winreg.QueryValueEx(key, "ProgId")

        #По полученному ProgId находим команду запуска .exe
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, f"{prog_id}\\shell\\open\\command") as key:
            command, _ = winreg.QueryValueEx(key, "")

        # Очищаем путь от кавычек и лишних флагов (например, "%1")
        split_cmd = split(command)
        if split_cmd:
            browser_path = split_cmd[0]

    except Exception:
        print("Не удалось определить браузер по умолчанию через реестр, используем Edge.")

    lowered_path = browser_path.lower()
    if "chrome" in lowered_path: browser_name = "Chrome"
    elif "yandex" in lowered_path or "browser.exe" in lowered_path:
        browser_name = "Yandex"
    else: browser_name = "Edge"


    user_data_dir = os.path.join(project_dir, f"browser_session_{browser_name}")

    return browser_path, user_data_dir



# ---------------------- Получение токена авторизации через локальное хранилище браузера -------------------
def get_7tv_token():
    browser_path, user_data_dir = get_default_browser_info()

    print(f"Используем браузер: {browser_path}")
    args = [
        browser_path,
        f"--user-data-dir={user_data_dir}",
        "https://api.7tv.app/v4/auth/login?platform=twitch",
        "--no-first-run"
    ]
    browser_process = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print("Ожидание авторизации в окне браузера...")

    # Путь к файлу Local Storage, куда 7TV запишет токен после успешного входа
    leveldb_dir = os.path.join(user_data_dir, "Default", "Local Storage", "leveldb")

    token = None
    timeout = 150
    start_time = time.time()

    while not token and (time.time() - start_time) < timeout:
        time.sleep(2)

        # Проверяем, создалась ли папка с хранилищем
        if not os.path.exists(leveldb_dir):
            continue

        try:
            # Делаем копию так как файлы leveldb могут быть заблокированы открытым браузером
            tmp_leveldb = os.path.join(project_dir, "tmp_leveldb")
            if os.path.exists(tmp_leveldb):
                shutil.rmtree(tmp_leveldb)
            shutil.copytree(leveldb_dir, tmp_leveldb, ignore=shutil.ignore_patterns('LOCK'))

            # Сканируем файлы leveldb (.log и .ldb) на наличие строки токена
            for filename in os.listdir(tmp_leveldb):
                if filename.endswith(('.log', '.ldb')):
                    file_path = os.path.join(tmp_leveldb, filename)
                    try:
                        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                            content = f.read()
                            # Ищем упоминание ключа '7tv-token' в бинарном файле
                            if "7tv-token" in content:

                                idx = content.find("7tv-token")
                                raw_sub = content[idx:idx + 500]
                                # JWT токен начинается с 'eyJ...'
                                jwt_idx = raw_sub.find("eyJ")
                                if jwt_idx != -1:
                                    # Вычленяем сам токен (он идет до конца строки или спецсимвола)
                                    potential_token = ""
                                    for char in raw_sub[jwt_idx:]:
                                        if char.isalnum() or char in "._-":
                                            potential_token += char
                                        else:
                                            break
                                    if len(potential_token) > 42:
                                        token = potential_token
                                        break
                    except Exception:
                        pass

            # Чистим за собой временную папку
            if os.path.exists(tmp_leveldb):
                shutil.rmtree(tmp_leveldb)

        except Exception as e:
            pass
    # Надежный способ закончить процесс браузера
    try:
        browser_process.terminate()
        browser_process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        try:
            subprocess.run(
                f"taskkill /F /T /PID {browser_process.pid}",
                shell=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        except Exception:
            pass
    except Exception:
        pass
    return token


# -------------- Проверка валидности токена авторизации ----------------
def check_auth(auth_token):
    if not auth_token:
        return False, None

    query = """
        query {
          users {
            me {
              id
              mainConnection {
                platform
                platformUsername
              }
              emoteSets {
                name
                id
              }
            }
          }
        }
    """
    headers = {
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(api, json={"query": query}, headers=headers, timeout=(3.05, 7))
        if response.status_code == 200:
            res_data = response.json()

            if "errors" not in res_data and res_data.get("data", {}).get("users", {}).get("me"):
                return True, res_data["data"]["users"]["me"]
    except Exception as e:
        print(f"Ошибка запроса: {e}")

    return False, None


def input_set(eset, total=None):
    print("\nВыберите какой эмоутсет копировать (0 для отмены):")
    for i, s in enumerate(eset, start=1):
        if total:
            total = s["emotes"]["totalCount"]
            print(f"[{i}] {s['name']} - {total} емоутов")
        else:
            print(f"[{i}] {s['name']}")
    user_input = int(input("Введите номер: "))
    if user_input == 0:
        exit()

    eid = eset[user_input - 1]["id"]
    print(f"Выбран целевой сет ID: {eid}")
    return eid, user_input-1



token = None
cfg_dir = os.path.join(project_dir, "cfg.json")
user_from=None
user_to = None
set_from = None
set_to = None

if os.path.exists(cfg_dir):
    try:
        with open(cfg_dir, "r", encoding="utf-8") as f:
            token = json.loads(f.read()).get("7tv-token")  # Сразу пишем в token
    except Exception as e:
        print(f"Ошибка чтения конфига: {e}")

is_correct, user_data = check_auth(token)

if not is_correct:
    print("Токен не найден или устарел. Запуск браузера для авторизации...")
    token = get_7tv_token()
    if token:
        is_correct, user_data = check_auth(token)
        if is_correct:
            with open(cfg_dir, "w", encoding="utf-8") as f:
                f.write(json.dumps({"7tv-token": token}, indent=4))
            print("Новый токен успешно получен и сохранен")
        else:
            print("Браузер вернул токен, но GQL-запрос отклонен.")
    else:
        print("Не удалось получить токен из браузера.")

if is_correct and user_data:
    user_to = user_data['mainConnection']['platformUsername']
    print(f"Успешная авторизация как {user_to}")
    sets = user_data["emoteSets"]

    set_to, _ = input_set(sets)

    user_from = input("Введите имя владельца эмоутсета для копирования: ")


    query =  """
        query Users( $query: String!) {
          users {
            search(query: $query) {
              items {
                id
                emoteSets {
                  id
                  name
                  emotes {
                    totalCount
                    items {
                      emote {
                        id
                        defaultName
                      }
                      alias
                    }
                  }
                }
              }
            }
          }
        }
    """
    try:
        payload = {
            "query": query,
            "variables": {"query": user_from, "limit": 1}
        }
        response = requests.post(api, json=payload, timeout=(3.05, 7))

        source_emotes = None
        if response.status_code == 200:
            data = response.json()
            items = data.get("data", {}).get("users", {}).get("search", {}).get("items", [])

            if not items:
                print("Пользователь не найден.")
                exit()

            esets = items[0].get("emoteSets", [])
            if not esets:
                print("У этого пользователя нет эмоутсетов.")
                exit()

            set_from, eseti = input_set(esets, 1)
            source_emotes = esets[eseti].get("emotes", {}).get("items", [])

            print(f"Выбран целевой сет ID: {set_from}")
    except Exception as e:
        print(f"При попытке получить эмоут сет произошла ошибка: {e}")
        exit()

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    mutation = """
            mutation EmoteSet($emote: EmoteSetEmoteId!, $emoteSetId: Id!) {
              emoteSets {
                emoteSet(id: $emoteSetId) {
                  addEmote(id: $emote) {
                    id
                    name
                  }
                }
              }
            }
        """
    print("\nНачинаем копирование...")
    try:
        for item in source_emotes:
            emote_id = item["emote"]["id"]
            alias = item.get("alias") or item["emote"]["defaultName"]

            payload = {
                "query": mutation,
                "variables": {
                    "emoteSetId": set_to,
                    "emote": {
                        "alias": alias,
                        "emoteId": emote_id
                    }
                }
            }
            try:
                res = requests.post(api, json=payload, headers=headers, timeout=5)
                res_data = res.json()

                # Проверяем "не смертельные" ошибки самого 7TV
                if "errors" in res_data:
                    err_msg = res_data["errors"][0].get("message", "Неизвестная ошибка")
                    print(f"!!Пропуск [{alias}]: {err_msg}")
                else:
                    print(f"{alias} added")

            except Exception as e:
                print(f"!!Ошибка сети при добавлении {alias}: {e}")

                # Защита от 429 Too Many Requests (Rate limit)
            time.sleep(0.4)
        print("\nПроцесс копирования завершен!")
    except KeyboardInterrupt as e:
        print("Копирование остановлено пользователем.")


else:
    print("Работа скрипта не может быть продолжена без авторизации.")

