import subprocess
import winreg
import shutil
import time
import os
from shlex import split

# ---------------------- Получение токена авторизации через локальное хранилище браузера -------------------

api = "https://7tv.io/v4/gql"

def get_7tv_token(project_dir, browser_path, user_data_dir):

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

#----------------- Поиск браузера по умолчанию в реестре -----
def get_default_browser_info(project_dir):

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



# def check_auth(auth_token):
#     if not auth_token:
#         return False, None
#
#     query = """
#         query {
#           users {
#             me {
#               id
#               mainConnection {
#                 platform
#                 platformUsername
#               }
#               emoteSets {
#                 name
#                 id
#               }
#             }
#           }
#         }
#     """
#     headers = {
#         "Authorization": f"Bearer {auth_token}",
#         "Content-Type": "application/json"
#     }
#
#     try:
#         response = requests.post(api, json={"query": query}, headers=headers, timeout=(3.05, 7))
#         if response.status_code == 200:
#             res_data = response.json()
#
#             if "errors" not in res_data and res_data.get("data", {}).get("users", {}).get("me"):
#                 return True, res_data["data"]["users"]["me"]
#     except Exception as e:
#         print(f"Ошибка запроса: {e}")
#
#     return False, None