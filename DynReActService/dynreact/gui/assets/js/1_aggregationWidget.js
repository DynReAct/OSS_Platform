/**
 * Displays material categories for a selection of orders
 */
class AggregationWidget extends HTMLElement {

    #grid;
    // { mat category id: { name: str, classes: { mat class id: {name: cl name, weight: aggregated weight} } } }
    #aggregations;
    // dict[str, float]   // <class, weight>
    #targetWeights;
    #mainCategory;  // string

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
                           ".ltp-materials-grid>div { min-width: 8em; max-width: 11em; min-height: 1.5em; }\n" +
                           ".ltp-material-category { background: var(--ltp-portfolio-base); color: white; padding: 0 1em; padding-top: 0.5em; }\n" +
                           ".material-class { display: flex; flex-direction: column; justify-content: space-between; align-items: stretch; }\n" +
                           ".material-class>div:first-child { background: var(--ltp-portfolio-light);color: var(--ltp-portfolio-dark); " +
                                                "flex-grow: 1; padding: 0.125em 1em; font-size: 0.95em; vertical-align: middle;}\n" +
                           ".material-class>div:nth-child(2) { background: var(--ltp-portfolio-light); flex-grow: 1; padding: 0.25em 0;}";


        shadow.append(style);
        const grid = document.createElement("div");
        shadow.append(grid);
        grid.classList.add("ltp-materials-grid");
        this.#grid = grid;
        /*
        const tooltipContainer = document.createElement("div");
        tooltipContainer.classList.add("tooltip-container");
        tooltipContainer.setAttribute("hidden", "true");
        shadow.append(tooltipContainer);
        this.#tooltipContainer = tooltipContainer;
        */
    }

    setAggregation(agg, targetWeights) {
        this.#mainCategory = undefined;
        const isNestedStructure = !!targetWeights && Object.values(targetWeights).find(t => typeof t === "object") !== undefined;
        if (isNestedStructure) {
            this.#mainCategory = AggregationWidget.#determineMainCategory(targetWeights, agg);
            // convert targetWeights to a flat structure... we do not display the nested structure here
            const newTargets = {};
            for (const [main_class, values] of Object.entries(targetWeights)) {
                if (main_class === "_sum")
                    continue;
                newTargets[main_class] = values["_sum"];
                for (const [sub_class, sub_val] of Object.entries(values)) {
                    if (!(sub_class in newTargets))
                        newTargets[sub_class] = 0;
                    newTargets[sub_class] += sub_val;
                }
            }
            targetWeights = newTargets;
        }
        this.#aggregations = agg;
        this.#targetWeights = targetWeights;
        this.#init();
    }

    #init() {
        JsUtils.clear(this.#grid);
        // { mat category id: { name: str, classes: { mat class id: {name: cl name, weight: aggregated weight} } } }
        const materials = this.#aggregations;
        if (!materials)
            return;
        const targets = this.#targetWeights;  // may be none/empty
        const targetsSpecified = !!targets && Object.keys(targets).length > 0;
        const columns = Object.keys(materials).length;
        const frag = document.createDocumentFragment();
        let column = 0;
        let title = "Selected tons in backlog";
        if (targetsSpecified)
            title += " / target tons";
        const cats = Object.entries(materials);
        const main = this.#mainCategory;
        if (main)
            cats.sort((a, b) => a[0] === main ? -1 : b[0] === main ? 1 : 0)
        for (const [cat, material_category] of cats) {
            column++;
            const categoryHeader = JsUtils.createElement("div", {
                parent: frag,
                text: material_category.name,
                classes: "ltp-material-category",
                style: {"grid-column-start": column, "grid-row-start": 1}
            });
            let row = 1;
            for (const [clz, material_class] of Object.entries(material_category.classes)) {
                row = row + 1;
                const data_dict = {"data-category": cat, "data-material": clz};
                // TODO ?
                /*
                if (material_class.is_default)
                    data_dict["data-default"] = true;
                if (material_class.default_share !== undefined)
                    data_dict["data-defaultshare"] = material_class.default_share;
                */
                const material_parent = JsUtils.createElement("div", {
                    parent: frag,
                    style: {"grid-column-start": column, "grid-row-start": row},
                    classes: "material-class",
                    attributes: data_dict,
                    title: title
                });
                JsUtils.createElement("div", {text: material_class.name, parent: material_parent});
                let text = JsUtils.formatNumber(material_class.weight, 5);
                if (targetsSpecified && clz in targets && typeof targets[clz] === "number") {
                    const targetWeight = targets[clz];
                    text +=  " / " + JsUtils.formatNumber(targetWeight, 5)
                }
                const value = JsUtils.createElement("div", {
                    parent: material_parent,
                    text: text,
                });
                /*
                if (material_class.is_default){
                    inp.readOnly = true;
                    inp.style.backgroundColor = "LightSteelBlue";
                }
                */;

            }
        }
        this.#grid.style["grid-template-columns"] = "repeat(" + columns + ", auto)";
        this.#grid.appendChild(frag);
    }

    static #determineMainCategory(targets, categories) {
        const cats = categories ? Object.entries(categories) : undefined;
        if (!(cats?.length > 0))
            return undefined;
        return cats
            .map(([cat, cat_obj]) => [cat, Object.keys(cat_obj.classes).filter(cl => cl in targets).length])
            .sort((arr1, arr2) => arr2[1]-arr1[1])[0][0];
    }

}