class JsUtils {

    static formatNumber(n, numDigits = 3) {
        numDigits = numDigits || 3;
        const abs = Math.abs(n);
        if (abs >= Math.exp(Math.log(10) * numDigits) || (abs < 0.01 && abs !== 0))
            return n.toExponential(numDigits-1);
        return Intl.NumberFormat("en-US", { maximumSignificantDigits: numDigits }).format(n)
    }

    static formatDate(date, options) {
        if (options?.skipTime)
            return date.getFullYear() + "-" + JsUtils._asTwoDigits(date.getMonth()+1) + "-" + JsUtils._asTwoDigits(date.getDate());
        return date.getFullYear() + "-" + JsUtils._asTwoDigits(date.getMonth()+1) + "-" + JsUtils._asTwoDigits(date.getDate()) + "T"
                + JsUtils._asTwoDigits(date.getHours()) + ":" + JsUtils._asTwoDigits(date.getMinutes());
    }

    static format(value, numDigits) {
        if (value === undefined || value === null)
            return "";
        if (value instanceof Date)
            return JsUtils.formatDate(value);
        const tp = typeof value;
        if (tp === "string")
            return value;
        if (tp === "number")
            return JsUtils.formatNumber(value, numDigits);
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
         let parsed = undefined;
         if (duration.startsWith("PT") && duration.endsWith("H")) {  // handle PXXH
             parsed = parseInt(duration.substring(2, duration.length - 1));
         } else if (duration.startsWith("P") && duration.endsWith("D")) {
             parsed = parseInt(duration.substring(1, duration.length - 1)) * 24;
         }
         return Number.isFinite(parsed) ? parsed : defaultHours;
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

}