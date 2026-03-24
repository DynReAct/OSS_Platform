export class JsUtils {
    static formatDate(date, options) {
        const utc = !!options?.utc;
        if (utc) {
            return date.getUTCFullYear() + "-" + JsUtils._asTwoDigits(date.getUTCMonth() + 1) + "-" + JsUtils._asTwoDigits(date.getUTCDate()) + "T"
                + JsUtils._asTwoDigits(date.getUTCHours()) + ":" + JsUtils._asTwoDigits(date.getUTCMinutes());
        }
        return date.getFullYear() + "-" + JsUtils._asTwoDigits(date.getMonth() + 1) + "-" + JsUtils._asTwoDigits(date.getDate()) + "T"
            + JsUtils._asTwoDigits(date.getHours()) + ":" + JsUtils._asTwoDigits(date.getMinutes());
    }
    static _asTwoDigits(value) {
        if (value < 10)
            return "0" + value;
        return value;
    }
    static formatNumber(n, options) {
        if (options?.nanAsWhitespace && isNaN(n))
            return "";
        const numDigits = isFinite(options?.numDigits) ? options?.numDigits : 4;
        const abs = Math.abs(n);
        const upperExpoLimitDigits = options?.upperExpoLimitDigits ?? numDigits;
        if (abs >= Math.exp(Math.log(10) * upperExpoLimitDigits)) {
            const upperExpoNumDigits = options?.upperExpoNumDigits ?? 3;
            return JsUtils._removeTrailingZeros(n.toExponential(upperExpoNumDigits));
        }
        const lowerLimitExpoDigits = options?.lowerLimitExpoDigits ?? 2;
        if (abs != 0 && abs < Math.exp(-Math.LN10 * lowerLimitExpoDigits)) {
            const lowerExpoNumDigits = options?.lowerExpoNumDigits ?? 2;
            return JsUtils._removeTrailingZeros(n.toExponential(lowerExpoNumDigits));
        }
        return Intl.NumberFormat("en-US", { maximumSignificantDigits: numDigits, useGrouping: options?.useGrouping }).format(n);
    }
    static parseRelativeDate(dt) {
        dt = dt.toLowerCase();
        const start = dt.indexOf("now");
        if (start < 0)
            return undefined;
        dt = dt.substring(start + 3).trim();
        const isPlus = dt.charAt(0) === "+";
        const isMinus = !isPlus && dt.charAt(0) === "-";
        if (!isMinus && !isPlus)
            return undefined;
        //dt = dt.substring(1).trim();
        const value = parseInt(dt.substring(0, dt.length - 1));
        if (!isFinite(value))
            return undefined;
        const now = new Date();
        switch (dt.charAt(dt.length - 1)) {
            case "d":
                now.setDate(now.getDate() + value);
                return now;
            case "h":
                now.setHours(now.getHours() + value);
                return now;
            default:
                break;
        }
        return undefined;
    }
    static parseDate(formatted) {
        if (!formatted)
            return undefined;
        const dt = new Date(formatted);
        if (isFinite(dt.getTime()))
            return dt;
        return JsUtils.parseRelativeDate(formatted); // supports date specifiers in the form "now + 1d"
    }
    static startOfDay(d, options) {
        const copy = new Date(d);
        if (options?.useUtc)
            copy.setUTCHours(0, 0, 0, 0);
        else
            copy.setHours(0, 0, 0, 0);
        return copy;
    }
    static isSameDay(d1, d2) {
        return d1.getDate() === d2.getDate() && d1.getMonth() === d2.getMonth() && d1.getFullYear() === d2.getFullYear();
    }
    static isClose(d1, d2, tolerance) {
        if (d1.getTime() === d2.getTime())
            return true;
        if (tolerance === undefined)
            return false;
        const lower = d1 < d2 ? d1 : d2;
        const upper = d1 < d2 ? d2 : d1;
        return JsUtils.addDuration(lower, tolerance) >= upper;
    }
    static #DURATION_CODES = Object.freeze({ Y: 2, D: 6, T: 8, H: 10, S: 14 });
    static #DURATION_FIELDS = Object.freeze({ Y: "years", D: "days", H: "hours", S: "seconds" });
    static #DURATION_KEYS = Object.freeze(["years", "months", "days", "hours", "minutes", "seconds"]);
    /**
     * @param duration a string following the ISO 8601 duration notation P(n)Y(n)M(n)DT(n)H(n)M(n)S. An exception is thrown for invalid input arguments.
     * @returns
     */
    static parseDuration(duration) {
        let state = -1;
        const dur = {};
        let currentValue = "";
        for (let idx = 0; idx < duration.length; idx++) {
            const char = duration.charAt(idx);
            if (char.trim() === "") // ignore whitespace
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
                const field = char in JsUtils.#DURATION_FIELDS ? JsUtils.#DURATION_FIELDS[char] : state >= 8 ? "minutes" : "months"; // "M" is duplicate
                dur[field] = value;
                state = newState;
                currentValue = "";
            }
            else {
                if (currentValue === "")
                    state += 1;
                currentValue += char;
            }
        }
        if (currentValue !== "")
            throw new Error("Invalid duration " + duration + ", missing closing character");
        return dur;
    }
    /**
     * Convert duration object to ISO 8601 duration notation
     * @param duration
     * @returns
     */
    static serializeDuration(duration) {
        let result = "P";
        let tAdded = false;
        for (let idx = 0; idx < JsUtils.#DURATION_KEYS.length; idx++) {
            const key = JsUtils.#DURATION_KEYS[idx];
            const value = duration[key];
            if (value === undefined)
                continue;
            if (idx > 2 && !tAdded) {
                result += "T";
                tAdded = true;
            }
            result += value;
            result += key[0].toUpperCase();
        }
        return result;
    }
    /**
     *
     * @param start
     * @param duration may be either a duration object or a duration string following the ISO 8601 duration notation P(n)Y(n)M(n)DT(n)H(n)M(n)S
     * @param options
     * @returns
     */
    static addDuration(start, duration, options) {
        const result = new Date(start);
        if (!duration)
            result;
        if (typeof duration === "string")
            duration = JsUtils.parseDuration(duration);
        let factor0 = options?.factor !== undefined ? options.factor : 1;
        const factor = options?.minus ? -factor0 : factor0;
        if (duration.years !== undefined)
            result.setFullYear(result.getFullYear() + factor * duration.years);
        if (duration.months !== undefined)
            result.setMonth(result.getMonth() + factor * duration.months);
        if (duration.weeks !== undefined)
            result.setDate(result.getDate() + 7 * factor * duration.weeks);
        if (duration.days !== undefined)
            result.setDate(result.getDate() + factor * duration.days);
        if (duration.hours !== undefined)
            result.setHours(result.getHours() + factor * duration.hours);
        if (duration.minutes !== undefined)
            result.setMinutes(result.getMinutes() + factor * duration.minutes);
        if (duration.seconds !== undefined)
            result.setSeconds(result.getSeconds() + factor * duration.seconds);
        if (duration.millis !== undefined)
            result.setMilliseconds(result.getMilliseconds() + factor * duration.millis);
        return result;
    }
    static _removeTrailingZeros(num) {
        const eIdx = num.indexOf("e");
        const startIdx = eIdx >= 0 ? eIdx - 1 : num.length - 1;
        for (let idx = startIdx; idx > 0; idx--) {
            const char = num.charAt(idx);
            if (char !== "0") {
                let result = num.substring(0, char === "." ? idx : idx + 1);
                if (eIdx >= 0)
                    result += num.substring(eIdx);
                return result;
            }
        }
        return num;
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
                el.classList.add(options.classes);
            else
                options.classes.forEach(cl => el.classList.add(cl));
        }
        if (options?.role)
            el.role = options?.role;
        if (options?.attributes)
            Object.entries(options.attributes).forEach(([key, value]) => el.setAttribute(key, value));
        if (options?.css)
            Object.entries(options.css).forEach(([key, value]) => el.style.setProperty(key, value));
        options?.parent?.appendChild(el);
        return el;
    }
    static primitiveArraysEqual(a1, a2, options) {
        if (a1 === undefined && a2 === undefined)
            return true;
        if (a1 === undefined || a2 === undefined)
            return false;
        if (a1.length !== a2.length)
            return false;
        if (options?.requireSameOrder)
            return a1.find((value, idx) => a2[idx] !== value) === undefined;
        return a1.find(entry => a2.indexOf(entry) < 0) === undefined;
    }
    static primitiveObjectsEqual(a1, a2, options) {
        if (a1 === undefined && a2 === undefined)
            return true;
        if (a1 === undefined || a2 === undefined)
            return false;
        const k1 = Object.keys(a1);
        const k2 = Object.keys(a2);
        if (!JsUtils.primitiveArraysEqual(k1, k2, options))
            return false;
        if (!options?.checkForDates)
            return k2.findIndex(key => a1[key] !== a2[key]) === undefined;
        return k2.findIndex(key => {
            const v1 = a1[key];
            const v2 = a2[key];
            if (v1 === v2)
                return false;
            if (v1 instanceof Date && v2 instanceof Date)
                return v1.getTime() !== v2.getTime();
            return true;
        }) === undefined;
    }
    static uniquePreserverOrder(a) {
        return a.filter((el, idx) => a.indexOf(el) === idx);
    }
    static groupBy(elements, keyMap, valueMap) {
        const result = {};
        for (const el of elements) {
            const value = valueMap(el);
            if (value === undefined)
                continue;
            const key = keyMap(el);
            if (!(key in result))
                result[key] = [];
            result[key].push(value);
        }
        return result;
    }
    /**
     *
     * @param target the element we look for
     * @param array the array we search in; this is assumed ordered
     * @returns the element, the index in the array, and whether the exact element has been found (true) or its closes match.
     *      In the special case that the array is empty (or undefined), [undefined, -1, false] is returned, otherwise the first element is never undefined.
     */
    static binarySearch(target, array, options) {
        if (!array || !(array?.length > 0))
            return [undefined, -1, false];
        const first = array[0];
        if (target <= first)
            return [first, 0, target === first];
        let l = array.length;
        const last = array[l - 1];
        if (target >= last)
            return [last, l - 1, target === last];
        let idx = Math.floor(l / 2);
        const distance = options?.distance ? options.distance : (t1, t2) => Math.abs(t1 - t2);
        let idxBase = 0;
        while (true) {
            const center = array[idx];
            if (target === center)
                return [center, idxBase + idx, true];
            if (l <= 2) {
                const dist1 = distance(target, array[0]);
                const dist2 = distance(target, array[array.length - 1]);
                const idxMatch = dist1 <= dist2 ? 0 : array.length - 1;
                return [array[idxMatch], idxBase + idxMatch, false];
            }
            const isLower = target < center;
            array = isLower ? array.slice(0, idx + 1) : array?.slice(idx);
            idxBase = isLower ? idxBase : idxBase + idx;
            l = array.length;
            idx = Math.floor(l / 2);
        }
    }
}
//# sourceMappingURL=jsUtils.js.map