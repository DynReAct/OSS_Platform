import { initDynreactState, JsUtils } from "@dynreact/client";
/**
 * Dispatches CustomEvent<LtpSolution|undefined>
 */
export class LongTermPlanningSelector extends HTMLElement {
    static DEFAULT_TAG = "ltp-selector";
    static _tag;
    /**
     * Call once to register the new tag type "<ltp-selector></ltp-selector>"
     * @param tag
     */
    static register(tag) {
        tag = tag || LongTermPlanningSelector.DEFAULT_TAG;
        if (tag !== LongTermPlanningSelector._tag) {
            customElements.define(tag, LongTermPlanningSelector);
            LongTermPlanningSelector._tag = tag;
        }
        return tag;
    }
    /**
     * Retrieve the registered tag type for this element type, or undefined if not registered yet.
     */
    static tag() {
        return LongTermPlanningSelector._tag;
    }
    static get observedAttributes() {
        return ["auto-fetch", "server"];
    }
    #dateSelect;
    #solutionSelect;
    #changeListener;
    #solutionListener;
    #state;
    #connected = false;
    #dates;
    constructor() {
        super();
        const style = document.createElement("style");
        style.textContent = ":host { position: relative; display: block; }\n " +
            ".container {display: flex; column-gap: 0.5em;}\n" +
            ".hidden {display: none; }";
        const shadow = this.attachShadow({ mode: "open", delegatesFocus: true });
        shadow.appendChild(style);
        const container = JsUtils.createElement("div", { parent: shadow, classes: "container" });
        JsUtils.createElement("div", { parent: container, text: "Start date:" });
        const datesSelect = JsUtils.createElement("select", { parent: container });
        JsUtils.createElement("div", { parent: container, text: "Planning id:" });
        const solutionSelect = JsUtils.createElement("select", { parent: container, classes: "hidden" });
        this.#changeListener = (() => this.#dateChanged());
        this.#solutionListener = (() => this.#solutionChanged());
        this.#dateSelect = datesSelect;
        this.#solutionSelect = solutionSelect;
    }
    connectedCallback() {
        this.#connected = true;
        this.#dateSelect.addEventListener("change", this.#changeListener);
        this.#solutionSelect.addEventListener("change", this.#solutionListener);
        this.#initState();
    }
    disconnectedCallback() {
        this.#connected = false;
        this.#dateSelect.removeEventListener("change", this.#changeListener);
        this.#solutionSelect.removeEventListener("change", this.#solutionListener);
    }
    async attributeChangedCallback(name, oldValue, newValue) {
        const attr = name.toLowerCase();
        switch (attr) {
            case "auto-fetch":
            case "server":
                this.#initState();
                break;
            default:
                this.#dateSelect.setAttribute(name, newValue);
        }
    }
    #dateChanged() {
        const selectedDate = this.#dateSelect.value;
        const solutions = this.#dates ? this.#dates[selectedDate] : undefined;
        const solSelector = this.#solutionSelect;
        const hasMultipleSolutions = !!(solutions?.length > 1);
        if (!hasMultipleSolutions)
            solSelector.classList.add("hidden");
        if (!(solutions?.length > 0)) {
            this.dispatchEvent(new CustomEvent("change"));
            return;
        }
        //if (hasMultipleSolutions) {
        while (solSelector.firstChild)
            solSelector.firstChild.remove();
        const frag = document.createDocumentFragment();
        solutions?.forEach(s => JsUtils.createElement("option", { parent: frag, attributes: { value: s, label: s } }));
        solSelector.appendChild(frag);
        if (hasMultipleSolutions) {
            solSelector.classList.remove("hidden");
        }
        solSelector.dispatchEvent(new Event("change"));
        //this.dispatchEvent(new CustomEvent<LtpSolution>("change", {detail: {date: new Date(selectedDate), solutionId: selectedSolution}}));
    }
    #solutionChanged() {
        const selectedDate = this.#dateSelect.value;
        const selectedSolution = this.#solutionSelect.value;
        if (!selectedDate || !selectedSolution)
            this.dispatchEvent(new CustomEvent("change"));
        else
            this.dispatchEvent(new CustomEvent("change", { detail: { date: new Date(selectedDate), solutionId: selectedSolution } }));
    }
    async #initState() {
        const server = this.server;
        if (!this.#connected || !this.autoFetch || !server)
            return;
        this.setState(await initDynreactState({ serverUrl: server }));
    }
    /**
     * Use either this method to let the component handle the snapshot retrieval itself, or setSnapshots to set snapshots externally.
     * Or set the auto-fetch and server attributes.
     * @param state
     */
    setState(state) {
        this.#state = state;
        this.#init();
    }
    /**
     * Use either this method to set startDates explicity, or setState to let the component handle the dates retrieval itself.
     * @param dates
     */
    // TODO retain selected date if still present
    setStartDates(dates) {
        const select = this.#dateSelect;
        while (select.firstChild)
            select.firstChild.remove();
        const frag = document.createDocumentFragment();
        this.#dates = dates;
        if (dates) {
            Object.keys(dates)
                .map(dt => [dt, new Date(dt)])
                .forEach(([dateStr, date]) => JsUtils.createElement("option", { parent: frag, attributes: { value: dateStr, label: JsUtils.formatDate(date) } }));
        }
        select.appendChild(frag);
        select.dispatchEvent(new Event("change")); // FIXME detail missing
        // TODO trigger callback manually?
    }
    async #init() {
        const state = this.#state;
        if (!state)
            return;
        const select = this.#dateSelect;
        const snapStream = state.longTermPlanningResults({ sort: "desc", end: "now+31d" });
        const reader = snapStream.getReader();
        try {
            const solutions = (await reader.read()).value;
            this.setStartDates(solutions);
        }
        finally {
            reader.releaseLock();
        }
    }
    // boilerplate below
    get autoFetch() {
        return this.getAttribute("auto-fetch")?.toLowerCase() === "true";
    }
    set autoFetch(doFetch) {
        if (doFetch)
            this.setAttribute("auto-fetch", "true");
        else
            this.removeAttribute("auto-fetch");
    }
    get server() {
        return this.getAttribute("server");
    }
    set server(server) {
        if (server)
            this.setAttribute("server", server);
        else
            this.removeAttribute("server");
    }
}
//# sourceMappingURL=ltp-selector.js.map