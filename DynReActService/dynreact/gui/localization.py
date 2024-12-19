import requests


class Localization:

    # Keys from outer to inner: language code, page code, item
    _languages: dict[str, dict[str, dict[str, str]]] = {}

    @staticmethod
    def get_translation(lang: str|None, page_code: str) -> dict[str, str]|None:
        if lang is None or lang == "en":  # use defaults
            return None
        if lang not in Localization._languages:
            # FIXME hardcoded path
            dictionary_path = "http://localhost:8050/dash/assets/locale/" + lang + ".json"
            response: requests.Response = requests.get(dictionary_path)
            dictionary = response.json()
            Localization._languages[lang] = dictionary
        all_translations = Localization._languages.get(lang)
        return all_translations.get(page_code) if all_translations is not None else None

    @staticmethod
    def get_value(page_translations: dict[str, str]|None, key: str, default_value: str) -> str:
        if page_translations is None:
            return default_value
        val = page_translations.get(key)
        return val if val is not None else default_value