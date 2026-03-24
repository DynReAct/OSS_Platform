import { initDynreactState, JsUtils } from "@dynreact/client";
import "toolcool-color-picker";
/**
 * Dispatches "change" events of type CustomEvent<MaterialSelection|undefined>;
 */
export class MaterialSelector extends HTMLElement {
    static #DEFAULT_TAG = "material-selector";
    static #tag;
    static #DEFAULT_COLORS = ["rgb(0, 0, 255)", "rgb(0, 255, 0)", "rgb(255, 0, 0)", "rgb(255, 165, 0)", "rgb(235, 0, 255)"];
    /**
     * Call once to register the new tag type "<material-selector></material-selector>"
     * @param tag
     */
    static register(tag) {
        tag = tag || MaterialSelector.#DEFAULT_TAG;
        if (tag !== MaterialSelector.#tag) {
            customElements.define(tag, MaterialSelector);
            MaterialSelector.#tag = tag;
        }
        return tag;
    }
    /**
     * Retrieve the registered tag type for this element type, or undefined if not registered yet.
     */
    static tag() {
        return MaterialSelector.#tag;
    }
    static get observedAttributes() {
        return ["auto-fetch", "server", "colors", "none-option"];
    }
    #selectCat;
    #subContainer;
    #catChangeListener;
    #colorChangeListener;
    #colors = [...MaterialSelector.#DEFAULT_COLORS];
    #state;
    #connected = false;
    #materialCategories;
    #selectedCat;
    #currentState;
    // keys: class id, value: color
    #colorsCache = {};
    constructor() {
        super();
        const style = document.createElement("style");
        // https://nolanlawson.com/2021/01/03/options-for-styling-web-components/
        style.textContent = ".main-flex {display: flex; column-gap: 1em; align-items: center;}\n" +
            ".sub-flex {display: flex; column-gap: 2em; align-items: center;}\n" +
            ".class-flex {display: flex; column-gap: 1em; align-items: center;}";
        const shadow = this.attachShadow({ mode: "open" });
        shadow.appendChild(style);
        const flex = JsUtils.createElement("div", { parent: shadow, classes: "main-flex" });
        JsUtils.createElement("div", { parent: flex, text: "Structure category:" });
        const selectCat = JsUtils.createElement("select", { parent: flex });
        const subContainer = JsUtils.createElement("div", { parent: flex, classes: "sub-flex" });
        this.#selectCat = selectCat;
        this.#subContainer = subContainer;
        this.#catChangeListener = this.#catChanged.bind(this);
        this.#colorChangeListener = this.#colorChanged.bind(this);
    }
    connectedCallback() {
        this.#connected = true;
        this.#selectCat.addEventListener("change", this.#catChangeListener);
        this.#initState();
    }
    disconnectedCallback() {
        this.#connected = false;
        this.#selectCat.removeEventListener("change", this.#catChangeListener);
    }
    async attributeChangedCallback(name, oldValue, newValue) {
        const attr = name.toLowerCase();
        switch (attr) {
            case "auto-fetch":
            case "server":
                this.#initState();
                break;
            case "none-option":
                this.#init();
                break;
            case "colors":
                if (!newValue) {
                    this.#colors = MaterialSelector.#DEFAULT_COLORS;
                }
                else {
                    this.#colors = newValue.split(",").map(col => col.trim()).filter(c => c);
                }
                const keys = Object.entries(this.#colorsCache)
                    .filter(([key, value]) => this.#colors.indexOf(value) < 0)
                    .map(([key, value]) => key);
                keys.forEach(k => delete this.#colorsCache[k]);
                this.#init();
                break;
            default:
                this.#selectCat.setAttribute(name, newValue);
        }
    }
    async #initState() {
        const server = this.server;
        if (!this.#connected || !this.autoFetch || !server)
            return;
        this.setState(await initDynreactState({ serverUrl: server }));
    }
    /**
     * Use either this method to let the component handle the materials retrieval itself, or setMaterials to set materials externally.
     * Or set the auto-fetch and server attributes.
     * @param state
     */
    setState(state) {
        this.#state = state;
        this.#fetch();
    }
    setMaterials(materials) {
        this.#materialCategories = materials;
        this.#init();
    }
    getMaterials() {
        const materials = this.#materialCategories;
        if (!materials)
            return undefined;
        materials.map(mat => {
            return {
                ...mat,
                classes: mat.classes.map(cl => {
                    return { ...cl, allowed_equipment: cl.allowed_equipment ?
                            Object.fromEntries(Object.entries(cl.allowed_equipment).map(([key, val]) => [key, [...val]])) : undefined };
                }),
                process_steps: mat.process_steps?.map(p => p)
            };
        });
    }
    async #fetch() {
        const state = this.#state;
        if (!state)
            return;
        const site = await state.site();
        this.setMaterials(site.material_categories);
    }
    #init() {
        const select = this.#selectCat;
        const previousSelection = select.value;
        while (select.firstChild)
            select.firstChild.remove();
        const cats = this.#materialCategories;
        if (!cats)
            return;
        const frag = document.createDocumentFragment();
        if (this.noneOption)
            JsUtils.createElement("option", { parent: frag, attributes: { value: "__none__", label: "None" } });
        cats.forEach(cat => JsUtils.createElement("option", { parent: frag, attributes: { value: cat.id, label: cat.name || cat.id } }));
        select.appendChild(frag);
        const preselected = Array.from(select.options).find(o => o.value === previousSelection);
        if (preselected)
            select.value = previousSelection;
        this.#catChanged();
    }
    #catChanged() {
        const cat = this.#selectCat.value;
        const previous = this.#selectedCat;
        while (this.#subContainer.firstChild) // ?
            this.#subContainer.firstChild.remove();
        const selected = this.#materialCategories?.find(c => c.id === cat);
        if (!selected) {
            if (cat === "__none__") {
                this.#selectedCat = undefined;
                this.#dispatchChange();
            }
            return;
        }
        const frag = document.createDocumentFragment();
        const colors = this.#colors;
        const colorActions = [];
        selected.classes.forEach((cl, idx) => {
            const container = JsUtils.createElement("div", { parent: frag, classes: "class-flex" });
            JsUtils.createElement("div", { parent: container, text: (cl.name || cl.id) + ":" });
            const colorContainer = JsUtils.createElement("div", { parent: container });
            const picker = JsUtils.createElement("toolcool-color-picker", { parent: colorContainer, attributes: { "data-clz": cl.id } });
            const color = this.#colorsCache[cl.id] || colors[idx % colors.length];
            // apparently it is not possible to set the color before the element is added to the dom
            //picker.color = color;
            colorActions.push(() => {
                picker.color = color;
                picker.addEventListener("change", this.#colorChangeListener);
            });
            this.#colorsCache[cl.id] = color;
        });
        this.#subContainer.appendChild(frag);
        colorActions.forEach(a => a());
        //
        this.#selectedCat = cat;
        this.#dispatchChange();
    }
    #colorChanged(event) {
        const clz = event.currentTarget.dataset["clz"];
        const rgba = event.detail?.rgba;
        if (clz && rgba)
            this.#colorsCache[clz] = event.detail.rgba;
        this.#dispatchChange();
    }
    #getSelectedColors() {
        const colors = Object.fromEntries(Array.from(this.#subContainer.querySelectorAll("toolcool-color-picker[data-clz]"))
            .map(picker => [picker.dataset["clz"], picker.rgba]));
        return colors;
    }
    #dispatchChange() {
        const oldState = this.#currentState;
        const cat = this.#selectedCat;
        const selected = this.#materialCategories?.find(c => c.id === cat);
        if (!selected) {
            if (oldState) {
                this.dispatchEvent(new CustomEvent("change", { detail: undefined }));
                this.#currentState = undefined;
            }
            return;
        }
        const colors = this.#getSelectedColors();
        const newState = {
            category: cat,
            colors: colors
        };
        const changed = cat !== oldState?.category || !JsUtils.primitiveObjectsEqual(colors, oldState?.colors);
        if (!changed)
            return;
        this.#currentState = { ...newState, colors: { ...colors } };
        this.dispatchEvent(new CustomEvent("change", { detail: newState }));
    }
    get state() {
        if (!this.#currentState)
            return undefined;
        return { ...this.#currentState, colors: this.#currentState.colors };
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
    get colors() {
        return [...this.#colors];
    }
    set colors(colors) {
        if (colors) {
            this.setAttribute("colors", colors.join(","));
        }
        else {
            this.removeAttribute("colors");
        }
    }
    get noneOption() {
        return this.getAttribute("none-option")?.toLowerCase() !== "false";
    }
    set noneOption(include) {
        if (include)
            this.removeAttribute("none-option");
        else
            this.setAttribute("none-option", "false");
    }
}
//# sourceMappingURL=material-selector.js.map