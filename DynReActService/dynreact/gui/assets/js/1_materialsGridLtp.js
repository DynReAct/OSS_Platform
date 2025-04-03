class MaterialsGridLtp extends HTMLElement {

    #grid;
    #materials;
    #tooltipContainer;
    #totalValue = 0;

    constructor() {
        super();
        const shadow = this.attachShadow({mode: "open"});
        const style = document.createElement("style");
        style.textContent = ":root {--ltp-portfolio-base: blue; --ltp-portfolio-light: lightblue; --ltp-portfolio-lighter: lightblue; --ltp-portfolio-dark: darkblue; --ltp-portfolio-readonly: lightsteelblue;}\n" +
                            "@supports (background-color: color-mix(in srgb, red 50%, blue 50%)) {\n" +
                                    ":root { --ltp-portfolio-base: #4169E1;  --ltp-portfolio-light: color-mix(in srgb, var(--ltp-portfolio-base), white); " +
                                            "--ltp-portfolio-lighter: color-mix(in srgb, var(--ltp-portfolio-base), white 75%);" +
                                            "--ltp-portfolio-dark: color-mix(in srgb, var(--ltp-portfolio-base), black); }}\n" +
                            ".ltp-materials-grid { display: grid; column-gap: 0.1em; row-gap: 0.1em; justify-items: stretch; " +
                                        "align-items: stretch; justify-content: start; text-align: center; word-wrap: wrap; }\n" +
                           ".ltp-materials-grid>div { min-width: 8em; max-width: 10em; min-height: 2em; }\n" +
                           ".ltp-material-category { background: var(--ltp-portfolio-base); color: white; padding: 0 1em; padding-top: 0.5em; }\n" +
                           ".ltp-material-class { display: flex; flex-direction: column; justify-content: space-between; align-items: stretch; }\n" +
                           ".ltp-material-class>div:first-child { background: var(--ltp-portfolio-light);color: var(--ltp-portfolio-dark); " +
                                                "flex-grow: 1; padding: 0.25em 1em; min-height: 2em; vertical-align: middle;}\n" +
                           ".ltp-material-class>div:nth-child(2) { background: var(--ltp-portfolio-light); flex-grow: 1; padding: 0.5em 0;}\n" +
                           ".ltp-material-class>div>input { max-width: 10em; background: var(--ltp-portfolio-lighter);}\n" +
                           ".ltp-material-class>div>input:read-only { background-color: var(--ltp-portfolio-readonly); }\n";


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

    setMaterials(materials, setpoints, totalValue) {
        JsUtils.clear(this.#grid);
        this.#materials = materials;
        this.#totalValue = totalValue;
        if (totalValue === 0)
            setpoints = undefined;
        const columns = materials.length;
        const rows = Math.max(materials.map(cat => cat.classes.length));
        const frag = document.createDocumentFragment();
        let column = 0;
        const updatesRequired = []; // list of category ids
        let fullInitRequired = false;
        for (const material_category of materials) {
            column++;
            const categoryHeader = JsUtils.createElement("div", {
                parent: frag,
                text: material_category.name || material_category.id,
                classes: "ltp-material-category",
                style: {"grid-column-start": column, "grid-row-start": 1}
            });
            let row = 1;
            let sum = 0;
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
                    attributes: {min: "0", max: totalValue, step: "1000", type: "number"}
                });
                const value = setpoints ? setpoints[material_class.id] || 0 : 0;
                inp.value = value;
                sum += value;
                if (material_class.is_default) {
                    inp.readOnly = true;
                } else {
                    inp.addEventListener("change", (event) => this.changeFilling(material_category, material_class.id));
                }
            }
            const mismatch = Math.abs(sum - totalValue)/Math.abs(sum + totalValue) > 0.01;
            if (mismatch) {
                if (sum > 0 && totalValue > 0) {
                    updatesRequired.push(material_category.id)
                } else if (totalValue > 0) {
                    fullInitRequired = true;
                }
            }


        }
        this.#grid.style["grid-template-columns"] = "repeat(" + columns + ", 1fr)";
        this.#grid.appendChild(frag);
        if (fullInitRequired) {
            this.initTargets(totalValue);
        } else {
            updatesRequired.map(cat => this.changeFilling(materials.find(catObj => catObj.id === cat), undefined));
        }
        // FIXME
        window.materialsltp = this;
    }

    initTargets(totalValue) {
        if (totalValue === undefined || !this.#materials)
            return;
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
        if (!this.#materials)
            return undefined;
        const results = Object.create(null);
        for (const container of this.#grid.querySelectorAll("div[data-category][data-material]")) {
            const inp = container.querySelector("input");
            results[container.dataset.material] = parseFloat(inp.value) || 0;
        }
        return results;
    }

    changeFilling(material_category, changed_class) {
        const target = this.#totalValue;
        const allContainers = Array.from(this.#grid.querySelectorAll("div[data-category=\"" + material_category.id + "\"][data-material]"));
        const defaultContainer = allContainers.find(c => c.dataset["default"] === "true") || allContainers[0];
        const totalSum = allContainers.map(c => parseFloat(c.querySelector("input[type=number]").value) || 0).reduce((a,b) => a+b, 0);
        const diff = totalSum - target;
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
        if (currentValue <= target) {
            const totalRemaining = target - currentValue;
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


}
