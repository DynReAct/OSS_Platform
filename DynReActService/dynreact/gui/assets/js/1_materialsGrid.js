class MaterialsGrid2 extends HTMLElement {

    #grid;
    #materials;
    #tooltipContainer;
    #processName;
    #totalValue = 0; // number

    static get observedAttributes() {
        return ["columns-selectable"];
    }

    constructor() {
        super();
        const shadow = this.attachShadow({mode: "open"});
        const style = document.createElement("style");
        style.textContent = ":root {--ltp-portfolio-base: blue; --ltp-portfolio-light: lightblue; --ltp-portfolio-lighter: lightblue; --ltp-portfolio-dark: darkblue; --ltp-portfolio-readonly: lightsteelblue; }\n" +
                            "@supports (background-color: color-mix(in srgb, red 50%, blue 50%)) {\n" +
                                    ":root { --ltp-portfolio-base: #4169E1;  --ltp-portfolio-light: color-mix(in srgb, var(--ltp-portfolio-base), white); " +
                                            "--ltp-portfolio-lighter: color-mix(in srgb, var(--ltp-portfolio-base), white 75%);" +
                                            "--ltp-portfolio-dark: color-mix(in srgb, var(--ltp-portfolio-base), black); }}\n" +
                            ".ltp-materials-grid { display: grid; column-gap: 0.1em; row-gap: 0.1em; justify-items: stretch; " +
                                        "align-items: stretch; justify-content: start; text-align: center; word-wrap: wrap; }\n" +
                           ".ltp-materials-grid>div {  min-height: 2em; }\n" +
                           ".ltp-material-category { width: 10em; background-color: var(--ltp-portfolio-base); color: white; padding: 0 1em; padding-top: 0.5em; display: flex; column-gap: 1em; }\n" +
                           ".ltp-material-class { display: flex; flex-direction: column; justify-content: space-between; align-items: stretch; width: 12em; }\n" +
                           ".ltp-material-class>div:first-child { background-color: var(--ltp-portfolio-light); color: var(--ltp-portfolio-dark); " +
                                                "flex-grow: 1; padding: 0.25em 1em; min-height: 2em; vertical-align: middle;}\n" +
                           ".ltp-material-class>div:nth-child(2) { background-color: var(--ltp-portfolio-light); flex-grow: 1; padding: 0.5em 0;}\n" +
                           ".ltp-material-class>div>input { max-width: 8em; background-color: var(--ltp-portfolio-lighter);}\n" +
                           ".ltp-material-class>div>input:read-only { background-color: var(--ltp-portfolio-readonly); }\n" +
                           ".active-toggle {}\n " +
                           ".active-toggle:hover { cursor: pointer; }\n " +
                           ".ltp-material-disabled { background-color: darkgrey; } ";


        shadow.append(style);
        const grid = document.createElement("div");
        shadow.append(grid);
        grid.classList.add("ltp-materials-grid");
        this.#grid = grid;
        const tooltipContainer = document.createElement("div");
        tooltipContainer.classList.add("tooltip-container");
        tooltipContainer.setAttribute("hidden", "true");
        shadow.append(tooltipContainer);
        this.#tooltipContainer = tooltipContainer;
    }

    setMaterials(process, materials) {
        JsUtils.clear(this.#grid);
        this.#materials = materials;
        this.#processName = process;
        this.#totalValue = 0;
        const columns = materials.length;
        const columnsSelectable = this.columnsSelectable;
        //const rows = Math.max(...materials.map(cat => cat.classes.length));
        const frag = document.createDocumentFragment();
        let column = 0;
        for (const material_category of materials) {
            if (material_category.process_steps && material_category.process_steps.indexOf(process) < 0)
                continue;
            column++;
            const categoryHeader = JsUtils.createElement("div", {
                parent: frag,
                classes: "ltp-material-category",
                style: {"grid-column-start": column, "grid-row-start": 1}
            });
            const headerText = JsUtils.createElement("div", {text: material_category.name || material_category.id, parent: categoryHeader});
            let row = 1;
            const classes = [];
            for (const material_class of material_category.classes) {
                row = row + 1;
                const data_dict = {"data-category": material_category.id, "data-material": material_class.id};
                if (material_class.is_default)
                    data_dict["data-default"] = true;
                if (material_class.default_share !== undefined)
                    data_dict["data-defaultshare"] = material_class.default_share;
                const material_parent = JsUtils.createElement("div", {
                    parent: frag,
                    style: {"grid-column-start": column, "grid-row-start": row},
                    classes: "ltp-material-class",
                    attributes: data_dict
                });
                JsUtils.createElement("div", {text: material_class.name||material_class.id, parent: material_parent});
                // TODO handle stepMismatch (should be ignored) https://developer.mozilla.org/en-US/docs/Web/API/ValidityState/stepMismatch
                const inp = JsUtils.createElement("input", {
                    parent: JsUtils.createElement("div", {parent: material_parent}),
                    attributes: {min: "0", step: "1000", type: "number"}
                });
                inp.value = 0;
                if (material_class.is_default){
                    inp.readOnly = true;
                } else {
                    inp.addEventListener("change", (event) => this.changeFilling(material_category, material_class.id));
                }
                classes.push(material_parent);
            }
            if (columnsSelectable) {
                const toggle = JsUtils.createElement("div", {parent: categoryHeader, attributes: {"data-active": "true"}, text: "✔",
                                            classes: "active-toggle", title: "Disable structure category"});
                toggle.addEventListener("click", () => {
                    const wasActive = toggle.dataset["active"] === "true";
                    if (wasActive) {
                        delete toggle.dataset["active"];
                        toggle.textContent = "X";
                        toggle.title = "Activate structure category";
                        classes.forEach(cl => {
                            cl.classList.add("ltp-material-disabled");
                            cl.querySelector("input").disabled = true;
                        });
                        categoryHeader.classList.add("ltp-material-disabled");
                    } else {
                        toggle.dataset["active"] = "true";
                        toggle.textContent = "✔";
                        toggle.title = "Disable structure category";
                        classes.forEach(cl => {
                            cl.classList.remove("ltp-material-disabled");
                            cl.querySelector("input").disabled = false;
                        });
                        categoryHeader.classList.remove("ltp-material-disabled");
                    }
                });
            }
        }
        this.#grid.style["grid-template-columns"] = "repeat(" + columns + ", 1fr)";
        this.#grid.appendChild(frag);
        // FIXME
        window.materials = this;
    }

    materialsSet() {
        return !!this.#materials;
    }

    initTargets(totalValue) {
        if (totalValue === undefined || !this.#materials)
            return;
        this.#totalValue = totalValue;
        for (const category of this.#materials) {
            const sharesMissing = category.classes.filter(m => m.default_share === undefined);
            const sharesDefined = sharesMissing.length <= 1;
            const shares = Object.fromEntries(category.classes.filter(cl => cl.default_share !== undefined).map(cl => [cl.id, cl.default_share]));
            if (sharesMissing.length === 1) {
                const aggregated = Object.values(shares).reduce((a,b) => a+b, 0);
                const final = aggregated >= 1 ? 0 : 1 - aggregated;
                shares[sharesMissing[0].id] = final;
            }
            else {
                const defaultClass = category.classes.find(m => m.is_default);
                if (defaultClass) {
                    const aggregated = Object.entries(shares).filter(([k,v]) => k !== defaultClass.id).map(([k,v]) => v).reduce((a,b) => a+b, 0);
                    const final = aggregated >= 1 ? 0 : 1 - aggregated;
                    sharesMissing.forEach(sh => shares[sh.id] = 0);
                    shares[defaultClass.id] = final;
                }
            }
            for (const [clzz, share] of Object.entries(shares)) {
                const amount = totalValue * share;
                const materialParent = this.#grid.querySelector("div[data-category=\"" + category.id + "\"][data-material=\"" + clzz + "\"]");
                if (!materialParent) {
                    console.log("Material cell not found:", clzz, "category: ", category?.id);
                    continue;
                }
                const inp = materialParent.querySelector("input[type=number]");
                inp.value = amount;
                inp.max = totalValue;
            }
        }
    }

    getSetpoints() {
        // get all values from grid
        if (!this.#materials)
            return undefined;
        const results = Object.create(null);
        for (const container of this.#grid.querySelectorAll("div[data-category][data-material]:not(.ltp-material-disabled)")) {
            const inp = container.querySelector("input[type=number]");
            results[container.dataset.material] = parseFloat(inp.value) || 0;
        }
        return results;
    }

    getOneField(cellid){
        return parseFloat(this.#grid.querySelector("div[data-category][data-material=\"" + cellid + "\"]")?.querySelector("input[type=number]")?.value);
    }

    setOneField(cellid, newValue){
        //set value to spec grid cell
        const materialParent = this.#grid.querySelector("div[data-category][data-material=\"" + cellid + "\"]");
        if (materialParent)
            materialParent.querySelector("input[type=number]").value = newValue;
    }

    setSetpointsTest(totalProduction) {
        // just test method loop grid and to set specified value to specified field
        for (const category of this.#materials) {
            let idx = 0;
            for (const item in category.classes) {
                idx = idx + 1;
                const cellid = category.classes[item].id;
                const materialParent = this.#grid.querySelector("div[data-category=\"" + category.id + "\"][data-material=\"" + cellid + "\"]");
                if (!materialParent) {
                    console.log("Material cell not found:", item, "category: ", category?.id);
                    continue;
                }
                materialParent.querySelector("input[type=number]").value = 4712;  //just test
            }
        }
    }

    /*
    reset(setpoints) {
        if (!setpoints)
            return;
        Object.entries(setpoints).forEach(([key, value]) => {
            const el = this.#grid.querySelector("div[data-material=\"" + key + "\"] input[type=\"number\"]");
            if (el)
                el.value = value;
        });
    }
    */

    changeFilling(material_category, changed_class) {
        const lots_weight_total = this.#totalValue;
        const allContainers = Array.from(this.#grid.querySelectorAll("div[data-category=\"" + material_category.id + "\"][data-material]"));
        const defaultContainer = allContainers.find(c => c.dataset["default"] === "true") || allContainers[0];
        const totalSum = allContainers.map(c => parseFloat(c.querySelector("input[type=number]").value) || 0).reduce((a,b) => a+b, 0);
        const diff = totalSum - lots_weight_total;
        if (diff === 0)
            return false;
        const defaultValueField = defaultContainer.querySelector("input[type=number]");
        const defaultValue = parseFloat(defaultValueField.value) || 0;
        if (changed_class !== undefined && defaultValue - diff >= 0) {  // if possible, adapt the default field only
            defaultValueField.value = defaultValue - diff;
            return true;
        }
        // else, try to adapt all others
        const currentChanged = allContainers.find(c => c.dataset["material"] === changed_class);
        const currentValue = currentChanged !== undefined ? parseFloat(currentChanged.querySelector("input[type=number]").value ) || 0 : 0;
        if (currentValue <= lots_weight_total) {
            const totalRemaining = lots_weight_total - currentValue;
            const totalOther = totalSum - currentValue;
            for (const el of allContainers) {
                if (el === currentChanged)
                    continue;
                const inp = el.querySelector("input[type=number]");
                const fraction = parseFloat(inp.value) / totalOther;
                inp.value = fraction * totalRemaining;
            }
            return true;
        }
        // else: the newly set value is greater than the total available amount => TODO show warning to user and disable Accept button
        return false; // FIXME
    }

    totalValueChanged(totalProduction) {
        // called from initMaterialGrid when total production changes
        const oldValue = this.#totalValue;
        if (oldValue === totalProduction)
            return;
        this.#totalValue = totalProduction;
        if (oldValue === 0) {
            this.initTargets(totalProduction);
            return true;
        }
        Array.from(this.#grid.querySelectorAll("[data-category][data-material] input[type=number]")).forEach(inp => inp.max = totalProduction);
        let changed = false;
        //calc sum per category
        for (const category of this.#materials) {
            if (this.changeFilling(category, undefined))
                changed = true;
        }
        return changed;
    }

//    setPrimaryCategory(prim_category, prim_classes){
//       for (const category of this.#materials) {
//            for (const material_class of category.classes) {
//                if ( category == prim_category and material_class in prim_classes):
//                    //style.backgroundColor = "Red"; // not working
//                    continue
//            }
//       }
//    }

    getProcessName(){
        return this.#processName;
    }

    get columnsSelectable() {
        return this.getAttribute("columns-selectable") !== null;
    }

    set columnsSelectable(selectable) {
        if (selectable)
            this.setAttribute("columns-selectable", "");
        else
            this.removeAttribute("columns-selectable");
    }

}