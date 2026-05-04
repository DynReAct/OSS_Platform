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
    static formatDateByUnit(date, unit, options) {
        const utc = !!options?.utc;
        unit = unit?.toLowerCase();
        switch (unit) {
            case "y":
            //  @ts-ignore
            case "a":
                return (utc ? date.getUTCFullYear() : date.getFullYear()).toString();
            case "mon":
                return utc ? JsUtils._asTwoDigits(date.getUTCMonth() + 1) + "/" + date.getUTCFullYear() :
                    JsUtils._asTwoDigits(date.getMonth() + 1) + "/" + date.getFullYear();
            default:
                let formatted = utc ? date.getUTCFullYear() + "-" + JsUtils._asTwoDigits(date.getUTCMonth() + 1) + "-" + JsUtils._asTwoDigits(date.getUTCDate()) :
                    date.getFullYear() + "-" + JsUtils._asTwoDigits(date.getMonth() + 1) + "-" + JsUtils._asTwoDigits(date.getDate());
                if (unit === "d")
                    return formatted;
                formatted += "T" + (utc ? JsUtils._asTwoDigits(date.getUTCHours()) : JsUtils._asTwoDigits(date.getHours()))
                    + ":" + (utc ? JsUtils._asTwoDigits(date.getUTCMinutes()) : JsUtils._asTwoDigits(date.getMinutes()));
                if (unit === "h" || unit === "min")
                    return formatted;
                formatted += ":" + (utc ? JsUtils._asTwoDigits(date.getUTCSeconds()) : JsUtils._asTwoDigits(date.getSeconds()));
                return formatted;
        }
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
    static startOfMonth(d, options) {
        const copy = new Date(d);
        if (options?.useUtc) {
            copy.setUTCHours(0, 0, 0, 0);
            copy.setUTCDate(1);
        }
        else {
            copy.setHours(0, 0, 0, 0);
            copy.setDate(1);
        }
        return copy;
    }
    static isSameDay(d1, d2) {
        return d1.getDate() === d2.getDate() && d1.getMonth() === d2.getMonth() && d1.getFullYear() === d2.getFullYear();
    }
    static daysDiff(d1, d2) {
        return Math.round((d2.getTime() - d1.getTime()) / 86400000);
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
    static findTicks(range, width, minTickDistance, maxTickDistance) {
        const diff = range[1] - range[0];
        let cand = JsUtils.find10Multiple(diff);
        let count = Math.max(Math.floor(diff / cand), 1);
        let tickDistance = width / count;
        if (tickDistance > maxTickDistance) {
            const cand2 = cand / 10;
            const count2 = Math.max(Math.floor(diff / cand2), 1);
            const tickDistance2 = width / count2;
            if (tickDistance2 >= minTickDistance / 2) {
                cand = cand2;
                count = count2;
                tickDistance = tickDistance2;
            }
        }
        while (tickDistance < minTickDistance) {
            cand = cand * 2;
            count = Math.max(Math.floor(diff / cand), 1);
            tickDistance = width / count;
        }
        while (tickDistance > maxTickDistance) {
            cand = cand / 2;
            count = Math.max(Math.floor(diff / cand), 1);
            tickDistance = width / count;
        }
        let lastTick = range[0];
        const ticks = [lastTick];
        while (true) {
            const next = lastTick + cand;
            if (next > range[1])
                break;
            ticks.push(next);
            lastTick = next;
        }
        return ticks;
    }
    static findDateTicks(range, width, minTickDistance, maxTickDistance) {
        const diffMillis = range[1].getTime() - range[0].getTime();
        const yr = 31536000000; // 1 year in millis  // up to leap seconds => maybe not a good idea...
        if (diffMillis > yr) { // 1 year
            const yrTicks = JsUtils.findTicks([range[0].getTime() / yr, range[1].getTime() / yr], width, minTickDistance, maxTickDistance);
            // check if these are full year. If yes => use them
            const allIntegers = yrTicks.find(tick => !Number.isInteger(tick)) === undefined;
            if (allIntegers)
                return [yrTicks.map(tick => new Date(tick * yr)), "y"];
        }
        // check if months are suitable
        let monthStart = JsUtils.startOfMonth(range[0]);
        if (monthStart < range[0])
            monthStart.setMonth(monthStart.getMonth() + 1);
        const allMonths = [];
        while (monthStart <= range[1]) {
            allMonths.push(monthStart);
            monthStart = new Date(monthStart);
            monthStart.setMonth(monthStart.getMonth() + 1);
        }
        const monthCount = allMonths.length;
        if (monthCount > 1 && width / (monthCount - 1) <= maxTickDistance) {
            if (width / (monthCount - 1) < minTickDistance) {
                const divisors = [2, 3, 4, 6]; // drop 4? => Jan, May, Sep
                for (const divisor of divisors) {
                    const applicableMonths = allMonths.filter(month => month.getMonth() % divisor === 0);
                    const count = applicableMonths.length;
                    if (count <= 1)
                        continue;
                    const tickDistance = width / (count - 1);
                    if (tickDistance >= minTickDistance)
                        return [applicableMonths, "mon"];
                }
                return [allMonths.filter((_, idx) => idx % divisors[divisors.length - 1] === 0), "mon"];
            }
            return [allMonths, "mon"];
        }
        const allDays = [];
        let dayStart = JsUtils.startOfDay(range[0]);
        if (dayStart < range[0])
            dayStart.setDate(dayStart.getDate() + 1);
        while (dayStart <= range[1]) {
            allDays.push(dayStart);
            dayStart = new Date(dayStart);
            dayStart.setDate(dayStart.getDate() + 1);
        }
        const daysCount = allDays.length;
        if (daysCount > 1 && width / (daysCount - 1) <= maxTickDistance) {
            if (width / (daysCount - 1) < minTickDistance) {
                const divisors = [2, 3, 4, 5, 6, 8, 10, 14, 15];
                for (const divisor of divisors) {
                    const days = allDays.filter((day, idx) => idx % divisor === 0);
                    const daysCount = days.length;
                    if (daysCount <= 1)
                        continue;
                    const tickDistance = width / (daysCount - 1);
                    if (tickDistance >= minTickDistance)
                        return [days, "d"];
                }
                return [allDays.filter((_, idx) => idx % divisors[divisors.length - 1] === 0), "d"];
            }
            return [allDays, "d"];
        }
        const allHours = [];
        let hourStart = new Date(range[0]);
        hourStart.setMinutes(0, 0, 0);
        if (hourStart < range[0])
            hourStart.setHours(hourStart.getHours() + 1);
        while (hourStart <= range[1]) {
            allHours.push(hourStart);
            hourStart = new Date(hourStart);
            hourStart.setHours(hourStart.getHours() + 1);
        }
        const hoursCount = allHours.length;
        if (hoursCount > 1 && width / (hoursCount - 1) <= maxTickDistance) {
            if (width / (hoursCount - 1) < minTickDistance) {
                const divisors = [2, 3, 4, 6, 8, 12];
                for (const divisor of divisors) {
                    const hours = allHours.filter((hour, idx) => idx % divisor === 0);
                    const hoursCount = hours.length;
                    if (hoursCount <= 1)
                        continue;
                    const tickDistance = width / (hoursCount - 1);
                    if (tickDistance >= minTickDistance)
                        return [hours, "h"];
                }
                return [allHours.filter((hour, idx) => idx % divisors[divisors.length - 1] === 0), "h"];
            }
            return [allHours, "h"];
        }
        const allMinutes = [];
        let minuteStart = new Date(range[0]);
        minuteStart.setSeconds(0, 0);
        if (minuteStart < range[0])
            minuteStart.setMinutes(minuteStart.getMinutes() + 1);
        while (minuteStart <= range[1]) {
            allMinutes.push(minuteStart);
            minuteStart = new Date(minuteStart);
            minuteStart.setMinutes(minuteStart.getMinutes() + 1);
        }
        const minutesCount = allMinutes.length;
        if (minutesCount > 1 && width / (minutesCount - 1) <= maxTickDistance) {
            if (width / (minutesCount - 1) < minTickDistance) {
                const divisors = [2, 3, 4, 5, 6, 10, 15, 20, 30];
                for (const divisor of divisors) {
                    const minutes = allMinutes.filter((min, idx) => idx % divisor === 0);
                    const minCount = minutes.length;
                    if (minCount <= 1)
                        continue;
                    const tickDistance = width / (minCount - 1);
                    if (tickDistance >= minTickDistance)
                        return [minutes, "min"];
                }
                return [allMinutes.filter((_, idx) => idx % divisors[divisors.length - 1] === 0), "min"];
            }
            return [allMinutes, "min"];
        }
        return [range.map(dt => new Date(dt)), ""];
    }
    static find10Multiple(num) {
        let cand = 1;
        while (num / cand > 10) {
            cand = cand * 10;
        }
        while (cand / num > 1) {
            cand = cand / 10;
        }
        return cand;
    }
}
//# sourceMappingURL=jsUtils.js.map