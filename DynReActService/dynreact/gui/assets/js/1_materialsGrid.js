class MaterialsGrid extends HTMLElement {

    #grid;
    #materials;
    #tooltipContainer;

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
                // TODO &&& action diff amount in default field, check if <
                inp.addEventListener("change", (event) => {
                    console.log('loc 76 ', ' field has changed' )
                });

            }
        }
        this.#grid.style["grid-template-columns"] = "repeat(" + columns + ", 1fr)";
        this.#grid.appendChild(frag);
        // FIXME
        window.materials = this;
    }

    initTargets(totalValue) {
        console.log(this.#materials)
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
                console.log('here materialsGrid.initTargets')
                //materialParent.querySelector("input[type=number]").value = 4712;
            }
        }
    }

    initTargetsFromPrev(totalValue, setpoints) {
        console.log('loc 119 materialsGrid.initTargetsFromPrev');
        console.log(this.#materials);
        console.log(setpoints);    //dict { rtype1: 1, rtype2: 2, rtype3: 3, rtype4: 4712, ftype1: 4712, ftype2: 4712 }
        if (!totalValue || !this.#materials)
            return;
        for (const category of this.#materials) {
            console.log( category);
//            for (const types in category){
//                console.log('loc127 ')
//                console.log(types)
//            //const XXX = category.classes.filter(m=> m.default_share === undefined)
//            }

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
                //materialParent.querySelector("input[type=number]").value = amount;
                console.log('loc 158 set amount');
                //materialParent.querySelector("input[type=number]").value = 4712;
            }
        }
    }

    getSetpoints() {
        console.log(' here getSetpoints ')
        if (!this.#materials)
            return undefined;
        const results = Object.create(null);
        for (const container of this.#grid.querySelectorAll("div[data-category][data-material]")) {
            const inp = container.querySelector("input");
            results[container.dataset.material] = parseFloat(inp.value) || 0;
        }
        return results;
    }

    //&&
    setOneField(cellid, newValue){
        console.log ('loc 182 ', 'setOneField ');
        for (const category of this.#materials) {
            for (const item in category.classes) {
                const materialParent = this.#grid.querySelector("div[data-category=\"" + category.id + "\"][data-material=\"" + cellid + "\"]");
                if (!materialParent) {
                    console.log("Material cell not found:", item, "category: ", category?.id);
                    continue;
                }
                materialParent.querySelector("input[type=number]").value = newValue;
            }
        }
    }


    setSetpoints(totalProduction) {
        // just method to set specified value to specified field
        console.log('loc 177 setSetpoints ', totalProduction);
        for (const category of this.#materials) {
            console.log ('loc 178 ', category);
            //const amount = 777; //totalValue * share;
            let idx = 0;
            for (const item in category.classes) {
                idx = idx + 1;
                console.log ('loc 181 ', item, category.classes[item].id);
                const cellid = category.classes[item].id;

                const materialParent = this.#grid.querySelector("div[data-category=\"" + category.id + "\"][data-material=\"" + cellid + "\"]");
                if (!materialParent) {
                    console.log("Material cell not found:", item, "category: ", category?.id);
                    continue;
                }
                materialParent.querySelector("input[type=number]").value = totalProduction / 4; //amount +idx;
                //console.log('here materialsGrid.setSetpoints');
                //materialParent.querySelector("input[type=number]").value = 4712;
            }
        }
        // just test one grid element
        console.log('loc 219 before OneField');
        setOneField("surface_tin", 777777);     // not working
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

}