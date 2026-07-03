class JsUtils {

    static formatNumber(n, numDigits = 3, expThreshold) {
        numDigits = numDigits || 3;
        expThreshold = expThreshold || numDigits;
        const abs = Math.abs(n);
        if (abs >= Math.exp(Math.log(10) * expThreshold) || (abs < 0.01 && abs !== 0))
            return n.toExponential(numDigits-1);
        return Intl.NumberFormat("en-US", { maximumSignificantDigits: numDigits }).format(n)
    }

    static formatDate(date, options) {
        if (options?.skipTime)
            return date.getFullYear() + "-" + JsUtils._asTwoDigits(date.getMonth()+1) + "-" + JsUtils._asTwoDigits(date.getDate());
        return date.getFullYear() + "-" + JsUtils._asTwoDigits(date.getMonth()+1) + "-" + JsUtils._asTwoDigits(date.getDate()) + "T"
                + JsUtils._asTwoDigits(date.getHours()) + ":" + JsUtils._asTwoDigits(date.getMinutes());
    }

    static format(value, numDigits, expThreshold) {
        if (value === undefined || value === null)
            return "";
        if (value instanceof Date)
            return JsUtils.formatDate(value);
        const tp = typeof value;
        if (tp === "string")
            return value;
        if (tp === "number")
            return JsUtils.formatNumber(value, numDigits, expThreshold);
        if (tp === "object")
            return JSON.stringify(value);
        return value.toString();
    }

    static _asTwoDigits(value) {
        if (value < 10)
            return "0" + value;
        return value;
    }

    // https://en.wikipedia.org/wiki/ISO_8601#Durations
    static parseDurationHours(duration, defaultHours=24) {
         if (!duration)
            return defaultHours;
         duration = duration.trim();
         let parsed = undefined;
         const isMinus = duration.startsWith("-");
         if (isMinus)
            duration = duration.substring(1);
         if (duration.startsWith("PT") && duration.endsWith("H")) {  // handle PXXH
             parsed = parseInt(duration.substring(2, duration.length - 1));
         } else if (duration.startsWith("P") && duration.endsWith("D")) {
             parsed = parseInt(duration.substring(1, duration.length - 1)) * 24;
         }
         return Number.isFinite(parsed) ? (isMinus ? -parsed : parsed) : defaultHours;
    }

    // FIXME copied from DynReActViz, targeted for removal
    static parseDuration(duration) {
        let state = -1;
        const dur = {};
        let currentValue = "";
        for (let idx=0; idx<duration.length; idx++) {
            const char = duration.charAt(idx);
            if (char.trim() === "")  // ignore whitespace
                continue;
            if (state === -1) {
                if (char !== "P")
                    throw new Error("Unexpected character at position " + idx + " in duration string " + duration);
                state += 1;
                continue;
            }
            const isNumber = char >= "0" && char <= "9";
            if (!isNumber) {
                if (state <= 0 && char !== "T") {
                    throw new Error("Invalid duration " + duration);
                }
                const newState = char in JsUtils.#DURATION_CODES ? JsUtils.#DURATION_CODES[char] : char === "M" ? (state >= 8 ? 12 : 4) : undefined;
                if (newState === undefined)
                    throw new Error("Invalid duration " + duration + "; unknown code \"" + char + "\"");
                if (newState <= state)
                    throw new Error("Invalid duration " + duration + "; invalid order");
                if (char === "T") { // special character
                    if (currentValue !== "")
                        throw new Error("Invalid duration " + duration);
                    state = newState;
                    continue;
                }
                if (currentValue === "")
                    throw new Error("No duration provided for key " + char + " in " + duration);
                const value = parseInt(currentValue);
                const field = char in JsUtils.#DURATION_FIELDS ? JsUtils.#DURATION_FIELDS[char] : state >= 8 ? "minutes" : "months";  // "M" is duplicate
                dur[field] = value;
                state = newState;
                currentValue = "";
            } else {
                if (currentValue === "")
                    state += 1;
                currentValue += char;

            }
        }
        if (currentValue !== "")
            throw new Error("Invalid duration " + duration + ", missing closing character");
        return dur;
    }

    // FIXME copied from DynReActViz, targeted for removal
    static #DURATION_CODES = Object.freeze({Y: 2, D: 6, T: 8, H: 10, S: 14});
    static #DURATION_FIELDS = Object.freeze({Y: "years", D: "days", H: "hours", S: "seconds"});
    static #DURATION_KEYS = Object.freeze(["years", "months", "days", "hours", "minutes", "seconds"]);
    static toMillis(duration) {
        if (typeof duration === "string")
            duration = JsUtils.parseDuration(duration);
        let days = 0;
        if (duration.years !== undefined)
            days += 365 * duration.years;
        if (duration.months !== undefined)
            days += 30 * duration.months;
        if (duration.weeks !== undefined)
            days += 7 * duration.weeks;
        if (duration.days !== undefined)
            days += duration.days;
        let millis = days * 86400000;
        if (duration.hours !== undefined)
            millis += 3_600_000 * duration.hours;
        if (duration.minutes !== undefined)
            millis += 60_000 * duration.minutes;
        if (duration.seconds !== undefined)
            millis += 1000 * duration.seconds;
        if (duration.millis !== undefined)
            millis += duration.millis;
        return millis;
    }

    static clear(element) {
        while (element?.firstChild)
            element.firstChild.remove();
    }

    static createElement(tagName, options) {
        const el = document.createElement(tagName, options);
        if (options?.text) {
            if (tagName === "input")
                el.value = options.text;
            else
                el.textContent = options?.text;
        }
        if (options?.title)
            el.title = options.title;
        if (options?.classes) {
            if (typeof options.classes === "string")
                el.classList.add(options.classes)
            else
                options.classes.forEach(cl => el.classList.add(cl));
        }
        if (options?.style)
            Object.entries(options.style).forEach(([key, value]) => el.style[key] = value);
        if (options?.role)
            el.role = options?.role;
        if (options?.attributes)
            Object.entries(options.attributes).forEach(([key, value]) => el.setAttribute(key, value));
        if (options?.css)
           Object.entries(options.css).forEach(([key, value]) => el.style.setProperty(key, value));
        options?.parent?.appendChild(el);
        return el;
    }

    static downloadData(data /*: string*/, options /*?: {format?: "json"|"csv"|"txt"; fileName?: string;}|undefined*/) {
        let fileName = options?.fileName || "file";
        const fileLower = fileName.toLowerCase();
        const format = options?.format || (fileLower.endsWith(".json") ? "json" : fileLower.endsWith(".csv") ? "csv" : "txt");
        if (!fileName.toLowerCase().endsWith("." + format))
            fileName = fileName + "." + format;
        const a = document.createElement("a");
        const blob = new Blob([data], {type: format === "json" ? "application/json" : format === "csv" ? "text/csv" : "text/plain"});
        const url = URL.createObjectURL(blob);
        a.href = url;
        a.setAttribute("download", fileName);
        a.click();
        URL.revokeObjectURL(url);
    }

    /**
    * Sets the default_share attribute for material classes, potentially adjusted for excluded material
    */
    static defaultMaterialSharesByCategory(cats /*: Array<MaterialCategory> */, excludedMaterial /*: Array<MaterialClass>|undefined */) /* => Array<MaterialCategory> */ {
        const results /*: Array<MaterialCategory> */ = [];
        for (const cat of catsIncluded) {
            const shareByMat = Object.fromEntries(cat.classes.filter(cl => cl.default_share > 0).map(cl => [cl.id, cl.default_share]));
            const sumShares = Object.values(shareByMat).reduce((a,b) => a+b, 0);
            const defaultClass = cat.classes.find(cl => cl.is_default && !(cl.default_share > 0));
            if (defaultClass)
                shareByMat[defaultClass.id] = Math.max(1-sumShares, 0);
            if (excludedMaterial) {
                missingShare = Object.entries(shareByMat).filter(([mat, share]) => excludedMaterial.indexOf(mat) >= 0).reduce((a,b)=>a+b, 0);
                if (missingShare > 0) {
                    if (missingShare >= 1-1e-4) {
                         allMats = cat.classes.filter(cl => excludedMaterial.indexOf(cl.id) < 0);
                         if (allMats.length === 0) {
                            shareByMat = {};
                         } else {
                            shareByMat = Object.fromEntries(allMats.map(mat => [mat, 1/allMats.length]));
                         }
                    } else {
                        shareByMat = Object.fromEntries(Object.entries(shareByMat)
                            .filter(([mat, value]) => excludedMaterial.indexOf(mat) < 0)
                            .map(([mat, value]) => [mat, value / (1-missingShare)]));
                    }
                }
            }
            const newCat = {...cat, classes: cat.classes.filter(cl => excludedMaterial.indexOf(cl.id) < 0).map(cl => { return {...cl, default_share: shareByMat[cl.id] || 0}; })};
            results.push(newCat);
        }
        return results;
    }

}