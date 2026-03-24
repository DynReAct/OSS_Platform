import { JsUtils } from "@dynreact/client";
// TODO
export class Timeslider extends HTMLElement {
    static #DEFAULT_TAG = "time-slider";
    static #DEFAULT_WIDTH = 512;
    static #tag;
    /**
     * Call once to register the new tag type "<time-slider></time-slider>"
     * @param tag
     */
    static register(tag) {
        tag = tag || Timeslider.#DEFAULT_TAG;
        if (tag !== Timeslider.#tag) {
            customElements.define(tag, Timeslider);
            Timeslider.#tag = tag;
        }
    }
    /**
     * Retrieve the registered tag type for this element type, or undefined if not registered yet.
     */
    static tag() {
        return Timeslider.#tag;
    }
    static get observedAttributes() {
        return ["width"];
    }
    #canvas;
    constructor() {
        super();
        const style = document.createElement("style");
        style.textContent = "";
        ;
        const shadow = this.attachShadow({ mode: "open" });
        shadow.appendChild(style);
        const mainContainer = JsUtils.createElement("div", { parent: shadow });
        const canvas = JsUtils.createElement("canvas", { parent: mainContainer, attributes: { width: Timeslider.#DEFAULT_WIDTH, height: 256 } });
        this.#canvas = canvas;
    }
}
//# sourceMappingURL=timeslider.js.map