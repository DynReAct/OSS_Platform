class MaterialsGrid2 extends HTMLElement {

    #grid;
    #materials;
    #tooltipContainer;
    #processName;

    constructor() {
        super();
        const shadow = this.attachShadow({mode: "open"});
        const style = document.createElement("style");
        style.textContent = ":root {--ltp-portfolio-base: blue; --ltp-portfolio-light: lightblue; --ltp-portfolio-lighter: lightblue; --ltp-portfolio-dark: darkblue;}\n" +
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
                           ".ltp-material-class>div>input { max-width: 10em; background: var(--ltp-portfolio-lighter);}";


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

    setMaterials(materials) {
        JsUtils.clear(this.#grid);
        this.#materials = materials;
        const columns = materials.length;
        const rows = Math.max(materials.map(cat => cat.classes.length));
        const frag = document.createDocumentFragment();
        let column = 0;
        for (const material_category of materials) {
            column++;
            const categoryHeader = JsUtils.createElement("div", {
                parent: frag,
                text: material_category.name || material_category.id,
                classes: "ltp-material-category",
                style: {"grid-column-start": column, "grid-row-start": 1}
            });
            let row = 1;
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
                    attributes: {min: "0", step: "1000", type: "number"}   // TODO test
                });
                if (material_class.is_default){
                    inp.readOnly = true;
                    inp.style.backgroundColor = "LightSteelBlue";
                }
                inp.addEventListener("change", (event) => {
                     this.changeFilling(material_category, inp.value);
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
        if (!totalValue || !this.#materials)
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
                    const aggregated = Object.values(shares).reduce((a,b) => a+b, 0);
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
                materialParent.querySelector("input[type=number]").value = amount;
            }
        }
    }

    getSetpoints() {
        // get all values from grid
        if (!this.#materials)
            return undefined;
        const results = Object.create(null);
        for (const container of this.#grid.querySelectorAll("div[data-category][data-material]")) {
            const inp = container.querySelector("input");
            results[container.dataset.material] = parseFloat(inp.value) || 0;
        }
        return results;
    }

    getOneField(cellid){
        //get value from spec grid cell
        let result;
        for (const category of this.#materials) {
            for (const item in category.classes) {
                const materialParent = this.#grid.querySelector("div[data-category=\"" + category.id + "\"][data-material=\"" + cellid + "\"]");
                if (!materialParent)
                    continue;
                result = Number(materialParent.querySelector("input[type=number]").value);
            }
        }
        return result;
    }

    setOneField(cellid, newValue){
        //set value to spec grid cell
        for (const category of this.#materials) {
            for (const item in category.classes) {
                const materialParent = this.#grid.querySelector("div[data-category=\"" + category.id + "\"][data-material=\"" + cellid + "\"]");
                if (!materialParent)
                    continue;
                materialParent.querySelector("input[type=number]").value = newValue;
            }
        }
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

    reset(setpoints) {
        if (!setpoints)
            return;
        Object.entries(setpoints).forEach(([key, value]) => {
            const el = this.#grid.querySelector("div[data-material=\"" + key + "\"] input[type=\"number\"]");
            if (el)
                el.value = value;
        });
    }

    changeFilling(material_category,  new_value){
        // triggerd by input change, recalc one col of grid
        let new_value_default_field;
        //find field in cur col with default entry
        let default_field_id;
        let sum_other_fields = 0;
        // get value from field with id lots2-weight-total
        let lots_weight_total = Number(document.getElementById("lots2-weight-total").value);
        for (const material_class of material_category.classes) {
            if (material_class.is_default){
                //get id of default field
                default_field_id = material_class.id; }
            else
                sum_other_fields = sum_other_fields + this.getOneField(material_class.id);
        }
        sum_other_fields = sum_other_fields - new_value;
        // calc diff to total
        new_value_default_field = lots_weight_total - sum_other_fields - new_value;
        //set new value to default field
        this.setOneField(default_field_id, new_value_default_field);
        //check new entry < value default entry, else ?? todo
    }

    resetGrid(lots_weight_total){
       // reset to default filling
       for (const category of this.#materials) {
            for (const material_class of category.classes) {
                if (material_class.is_default)
                    this.setOneField(material_class.id, lots_weight_total);
                else
                    this.setOneField(material_class.id, 0);
            }
        }
    }

    checkSums(){
        //called from initMaterialGrid
        //compare lots2-weight-total with sum of cols
        // ->add diff to default-field
        let lots_weight_total = Number(document.getElementById("lots2-weight-total").value);
        let lots_weight_sum;
        let weight_diff = 0;
        let changed = false;
        //calc sum per category
        for (const category of this.#materials) {
            lots_weight_sum = 0;
            for (const material_class of category.classes) {
                lots_weight_sum = lots_weight_sum + this.getOneField(material_class.id);
                }
            if (lots_weight_sum != lots_weight_total){
                weight_diff = lots_weight_total - lots_weight_sum;
                changed = true;
                for (const material_class of category.classes) {
                    if (material_class.is_default){
                        this.setOneField(material_class.id, this.getOneField(material_class.id) + weight_diff);
                    }
                 }
            }
        } return changed;
    }

    setProcessName(process){
        this.processName = process;
    }

    getProcessName(){
        return this.processName;
    }

}