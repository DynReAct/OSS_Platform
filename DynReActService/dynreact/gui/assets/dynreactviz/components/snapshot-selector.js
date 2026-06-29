import { initDynreactState, JsUtils } from "@dynreact/client";
export class SnapshotSelector extends HTMLElement {
    static DEFAULT_TAG = "snapshot-selector";
    static _tag;
    /**
     * Call once to register the new tag type "<snapshot-selector></snapshot-selector>"
     * @param tag
     */
    static register(tag) {
        tag = tag || SnapshotSelector.DEFAULT_TAG;
        if (tag !== SnapshotSelector._tag) {
            customElements.define(tag, SnapshotSelector);
            SnapshotSelector._tag = tag;
        }
        return tag;
    }
    /**
     * Retrieve the registered tag type for this element type, or undefined if not registered yet.
     */
    static tag() {
        return SnapshotSelector._tag;
    }
    static get observedAttributes() {
        return ["auto-fetch", "server"];
    }
    #select;
    #changeListener;
    #state;
    #connected = false;
    constructor() {
        super();
        const select = JsUtils.createElement("select");
        const style = document.createElement("style");
        // https://nolanlawson.com/2021/01/03/options-for-styling-web-components/
        style.textContent = ":host { position: relative; display: block; }";
        const shadow = this.attachShadow({ mode: "open", delegatesFocus: true });
        shadow.appendChild(style);
        shadow.appendChild(select);
        // would not be required if change event had the composed property: https://javascript.info/shadow-dom-events, https://github.com/whatwg/html/issues/5453
        this.#changeListener = ((evt) => this.dispatchEvent(evt));
        this.#select = select;
    }
    connectedCallback() {
        this.#connected = true;
        this.#select.addEventListener("change", this.#changeListener);
        this.#initState();
    }
    disconnectedCallback() {
        this.#connected = false;
        this.#select.removeEventListener("change", this.#changeListener);
    }
    async attributeChangedCallback(name, oldValue, newValue) {
        const attr = name.toLowerCase();
        switch (attr) {
            case "auto-fetch":
            case "server":
                this.#initState();
                break;
            default:
                this.#select.setAttribute(name, newValue);
        }
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
     * Use either this method to set snapshots explicity, or setState to let the component handle the snapshot retrieval itself.
     * @param snaps
     */
    setSnapshots(snaps) {
        const select = this.#select;
        while (select.firstChild)
            select.firstChild.remove();
        const frag = document.createDocumentFragment();
        snaps
            ?.map(date => JsUtils.formatDate(date))
            ?.forEach(date => JsUtils.createElement("option", { parent: frag, attributes: { value: date, label: date } }));
        select.appendChild(frag);
    }
    async #init() {
        const state = this.#state;
        if (!state)
            return;
        const select = this.#select;
        const snapStream = state.snapshots({ sort: "desc", end: "now", batchSize: 100 });
        const reader = snapStream.getReader();
        try {
            const snaps = (await reader.read()).value;
            this.setSnapshots(snaps);
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
//# sourceMappingURL=snapshot-selector.js.map