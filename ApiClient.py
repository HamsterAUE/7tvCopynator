import requests
import os
import sys

class ApiClient:
    def __init__(self, project_dir):
        self.url = 'https://7tv.io/v4/gql'
        self._cached_query = {}

        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            self.gql_dir = os.path.join(sys._MEIPASS, "7tv-gql")
        else:
            # Если запускаем из исходников .py
            base_dir = project_dir or os.path.dirname(os.path.abspath(__file__))
            self.gql_dir = os.path.join(base_dir, "7tv-gql")



    # Вспомогательный метод для сборки чистых заголовков
    def _get_headers(self, token: str = None) -> dict:
        headers = {'Content-Type': 'application/json'}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers


    def _load_gql(self, query_name):
        try:
            if not query_name.endswith(".gql"):
                query_name += ".gql"

            if query_name in self._cached_query:
                return self._cached_query[query_name]

            gql_path=os.path.join(self.gql_dir, query_name)
            with open(gql_path) as f:
                content = f.read()
                self._cached_query[query_name] = content
                return content
        except Exception as e:
            print(f"Ошибка загрузки .gql файла [{query_name}]: {e}")
            return None


    def get_me(self, token):
        query = self._load_gql("get-me.gql")

        try:
            headers = self._get_headers(token)
            response = requests.post(self.url, json={"query": query}, headers=headers, timeout=(3.05, 7))
            if response.status_code == 200:
                res_data = response.json()

                if "errors" not in res_data and res_data.get("data", {}).get("users", {}).get("me"):
                    return res_data["data"]["users"]["me"]
        except Exception as e:
            print(f"Не удалось получить данные о вас: {e}")
        return None


    def get_user_esets(self, user_from):
        query = self._load_gql("get-user-esets.gql")
        payload = {"query": query,
                   "variables": {"query": user_from}}

        try:
            response = requests.post(self.url, json=payload, headers=self._get_headers() ,timeout=(3.05, 7))
            if response.status_code == 200:
                data = response.json()
                items = data.get("data", {}).get("users", {}).get("search", {}).get("items", [])
                return items
        except Exception as e:
            print(f"Не удалось получить данные о эмоут сетх пользователя {user_from}: {e}")
        return None


    def add_to_eset(self,token, set_to,alias, emote_id ):
        query = self._load_gql("add-to-eset.gql")
        headers = self._get_headers(token)
        payload = {
            "query": query,
            "variables": {
                "emoteSetId": set_to,
                "emote": {
                    "alias": alias,
                    "emoteId": emote_id
                }
            }
        }

        try:
            response = requests.post(self.url, json=payload, headers=headers, timeout=(3.05, 7))
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            print(f"Не удалось отправить запрос на изменение: {e}")
        return None

