import { JsUtils } from "@dynreact/client";
/**
 *  Configuration example:
 *   --spinner-css-background-color: rgb(200, 200, 200, 0.5);
 *   --spinner-css-color: darkblue;
 *   --spinner-css-size: 168px;
 *   --spinner-css-segment-width: 20px;
 */
export class SpinnerCss extends HTMLElement {
    static #DEFAULT_TAG = "spinner-css";
    static #tag;
    /**
     * Call once to register the new tag type "<spinner-css></spinner-css>"
     * @param tag
     */
    static register(tag) {
        tag = tag || SpinnerCss.#DEFAULT_TAG;
        if (tag !== SpinnerCss.#tag) {
            customElements.define(tag, SpinnerCss);
            SpinnerCss.#tag = tag;
        }
        return tag;
    }
    /**
     * Retrieve the registered tag type for this element type, or undefined if not registered yet.
     */
    static tag() {
        return SpinnerCss.#tag;
    }
    // TODO color, size, ...
    static get observedAttributes() {
        return ["top", "bottom", "left", "right", "width", "height", "active", "duration"];
    }
    #backdrop;
    #spinner;
    constructor() {
        super();
        const style = document.createElement("style");
        style.textContent = ":host { display: none; position: absolute; width: 100%; height: 100%; z-index: 1;}\n" +
            ".backdrop {display: inline; position: absolute; top: 0; left: 0; width: 100%; height: 100%; background-color: var(--spinner-css-background-color, rgba(255,255,255,0)); }\n" +
            ".spinner {display: block; position: absolute; top: 40%; left: 40%; width: 100%; height: 100%; color: var(--spinner-css-color, darkblue); box-sizing: border-box; z-index: 1;}\n" +
            ".spinner:after {display: block; content: \" \"; box-sizing: border-box; width: var(--spinner-css-size, 64px); height: var(--spinner-css-size, 64px); " +
            "margin: var(--spinner-css-segment-width, 8px); border-radius: 50%; border: var(--spinner-css-segment-width, 8px) solid currentColor; border-color: currentColor transparent currentColor transparent; animation: spinner 2s linear infinite; }\n" +
            "@keyframes spinner { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }";
        const shadow = this.attachShadow({ mode: "open" });
        shadow.appendChild(style);
        this.#backdrop = JsUtils.createElement("div", { parent: shadow, classes: "backdrop" });
        this.#spinner = JsUtils.createElement("div", { parent: shadow, classes: [ /*"hidden"*/ /*, spinner */] });
    }
    get top() {
        return this.style.top;
    }
    set top(value) {
        if (value)
            this.setAttribute("top", value);
        else
            this.removeAttribute("top");
    }
    get bottom() {
        return this.style.bottom;
    }
    set bottom(value) {
        if (value)
            this.setAttribute("bottom", value);
        else
            this.removeAttribute("bottom");
    }
    get left() {
        return this.style.left;
    }
    set left(value) {
        if (value)
            this.setAttribute("left", value);
        else
            this.removeAttribute("left");
    }
    get right() {
        return this.style.right;
    }
    set right(value) {
        if (value)
            this.setAttribute("right", value);
        else
            this.removeAttribute("right");
    }
    get width() {
        return this.style.width;
    }
    set width(value) {
        if (value)
            this.setAttribute("width", value);
        else
            this.removeAttribute("width");
    }
    get height() {
        return this.style.height;
    }
    set height(value) {
        if (value)
            this.setAttribute("height", value);
        else
            this.removeAttribute("height");
    }
    get active() {
        const attr = this.getAttribute("active")?.toLowerCase();
        return attr !== undefined && attr !== "false";
    }
    set active(active) {
        if (active)
            this.setAttribute("active", "");
        else
            this.removeAttribute("active");
    }
    get duration() {
        let an = this.style.animation;
        if (an) {
            an = an.substring("spinner ".length);
            const firstS = an.indexOf("s");
            if (firstS > 0) {
                an = an.substring(0, firstS);
                const duration = parseFloat(an);
                if (duration > 0)
                    return duration;
            }
        }
        return 2;
    }
    set duration(duration) {
        if (duration > 0)
            this.setAttribute("duration", duration + "");
        else
            this.removeAttribute("duration");
    }
    async attributeChangedCallback(name, oldValue, newValue) {
        const attr = name.toLowerCase();
        switch (attr) {
            case "top":
            case "bottom":
            case "left":
            case "right":
            case "width":
            case "height":
                if (newValue)
                    this.style.setProperty(attr, newValue);
                else
                    this.style.removeProperty(attr);
                break;
            case "active":
                if (newValue !== null && newValue !== "false") {
                    this.style.display = "block";
                    this.#spinner.classList.add("spinner");
                }
                else {
                    this.style.display = "none";
                    this.#spinner.classList.remove("spinner");
                }
                break;
            case "duration":
                const duration = parseInt(newValue);
                if (!(duration > 0))
                    this.#spinner.style.removeProperty("animation");
                else
                    this.#spinner.style.animation = "spinner " + duration + "s linear infinite";
                break;
        }
    }
}
//# sourceMappingURL=spinner-css.js.map