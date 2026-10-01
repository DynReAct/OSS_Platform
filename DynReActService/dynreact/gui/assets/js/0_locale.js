(function() {

    if (!globalThis.dynreact)
        globalThis.dynreact = {};
    Object.assign(globalThis.dynreact, { _translations: {}, _lang: "en" });
    const dynreact = globalThis.dynreact;

    const loadLanguage = async (lang) => {
        if (dynreact[lang])
            return dynreact[lang];
        const resp = await fetch("/dash/assets/locale/" + lang.toLowerCase() + ".json");
        if (!resp.ok)
            throw new Error("Failed to load translation for " + lang + ": " + resp.status + ": " + resp.statusText);
        const translation = await resp.json();
        dynreact._translations[lang] = translation;
        return translation;
    };

    const storeAttribute = (element, key) => {
        const datasetKey = "dynreact_" + key;
        if (element.dataset[datasetKey])
            return;
        let value = "";
        switch(key) {
        case "text":
            value = element.textContent;
            break;
        case "value":
            value = element.value;
            break;
        case "title":
            value = element.title;
            break;
        case "placeholder":
            value = element.placeholder;
            break;
        }
        if (value)
            element.dataset[datasetKey] = value;
    }

    const applyTranslation = (lang, translation) => {
        if (!translation)
            return;
        Object.entries(translation).forEach(([key, translationRecord]) => {
            const mainContainer = document.querySelector("#" + key);
            if (!mainContainer)
                return;
            const currentLang = mainContainer.dataset.lang || "en";
            if (currentLang === lang)
                return;
            const isEnglish = currentLang.startsWith("en");
            mainContainer.dataset.lang = lang;
            Object.entries(translationRecord).forEach(([subKey, value]) => {
                const sub = mainContainer.querySelector("#" + key + "-" + subKey);
                if (sub) {
                    try {
                        const text = value instanceof Object ? value.text : value;
                        if (text) {
                            if (isEnglish)
                                storeAttribute(sub, "text");
                            sub.textContent = text;
                        }
                        if (value?.value) {
                            if (isEnglish)
                                storeAttribute(sub, "value");
                            sub.value = value.value;
                        }
                        if (value?.title) {
                            if (isEnglish)
                                storeAttribute(sub, "title");
                            sub.title = value.title;
                        }
                        if (value?.placeholder) {
                            if (isEnglish)
                                storeAttribute(sub, "placeholder");
                            sub.placeholder = value.placeholder;
                        }
                    } catch (e) {
                        console.error("Failed to apply translation", lang, "to element", sub, ":", e)
                    }
                }
            });
        });
    }

    /**
    * Set back to english
    */
    const restoreLanguage = () => {
        document.querySelectorAll("[data-dynreact_text]").forEach(el => el.textContent = el.dataset.dynreact_text);
        document.querySelectorAll("[data-dynreact_title]").forEach(el => el.title = el.dataset.dynreact_title);
        document.querySelectorAll("[data-dynreact_value]").forEach(el => el.value = el.dataset.dynreact_value);
        Array.from(document.querySelectorAll("[data-lang]")).forEach(el => el.dataset.lang = "en");
    };

    const setLocale = (lang, _, lang2) => {
        lang = lang || lang2;
        if (!lang) {
            const params = new URLSearchParams(globalThis.location.search);
            lang = params.get("lang");
            if (!lang)
                lang = globalThis.navigator?.language;
            if (!lang)
                lang = "en";
        }
        if (lang?.indexOf("-") > 0)
            lang = lang.substring(0, lang.indexOf("-"));
        if (lang === "en") {
            dynreact._lang = "en";
            restoreLanguage();
        } else {
            loadLanguage(lang).then(translation => {
                dynreact._lang = lang;
                applyTranslation(lang, translation);
            });
        }
        return lang;
    };

    dynreact.setLocale = setLocale;

    /**
    *  Note: setLocale does not work reliably on page load
    */
    const setLocaleTwice = (...args) => {
        const result = setLocale(...args);
        setTimeout(() => setLocale(...args), 100);
        return [result, result];
    };

    /**
    * Referenced in dynreact/gui/dash_app.py
    */
    globalThis.dash_clientside = Object.assign({}, globalThis.dash_clientside, {
        locale: {
            setLocale: setLocaleTwice
        }
    });

})();