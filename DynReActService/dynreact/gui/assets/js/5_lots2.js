(function() {

    globalThis.dash_clientside = Object.assign({}, globalThis.dash_clientside, {
        lots2: {}
    });

    const materialsTag = "dynreact-material-grid2";
    const catAggregationWidgetTag = "dynreact-backlog-aggregation";

    globalThis.dash_clientside.lots2.initMaterialGrid = function(totalProduction, process, setpoints, gridId) {
        if (!globalThis.customElements.get(materialsTag))
            globalThis.customElements.define(materialsTag, MaterialsGrid2);     //use class MaterialGrid
        const gridContainer = document.querySelector("#" + gridId);             //object MaterialGrid
        let grid = gridContainer.querySelector(materialsTag);
        const is_process_changed = grid?.getProcessName() !== process;
        const fullinit = !grid?.materialsSet() || is_process_changed;
        if (fullinit){
            // JsUtils.clear(gridContainer);
            grid = grid || JsUtils.createElement(materialsTag, {parent: gridContainer, attributes: {"columns-selectable": ""}});
            const site = dynreact?.getSite();
            if (site) {
                grid.setMaterials(process, site.material_categories);
                if (totalProduction)
                    grid.initTargets(totalProduction);
            }
        } else {
            // lots2-details-plants changed -> try to add diff to default field
            grid.totalValueChanged(totalProduction);
        }
    }

    globalThis.dash_clientside.lots2.setMaterialSetpoints = function(_, gridId) {
        //triggered by 1. button Accept
        //returns all values from grid, callback fills Store lots2-material-setpoints

        const materialGrid = document.querySelector("div#" + gridId + " " + materialsTag);
        mySetpoints = materialGrid?.getSetpoints();
        return materialGrid?.getSetpoints();
    }

    globalThis.dash_clientside.lots2.resetMaterialGrid = function(_, totalWeight, gridId) {
        // set grid to default
        const gridContainer = document.querySelector("#" + gridId);
        const grid = gridContainer.querySelector(materialsTag);
        grid?.initTargets(totalWeight);
        return "ltr";
    }

    // used by lot creation page and lots planning page
    globalThis.dash_clientside.lots2.setBacklogStructureOverview = function(weightAggregation, targetWeights, parentId) {
        const container = document.querySelector("#" + parentId);
         if (!globalThis.customElements.get(catAggregationWidgetTag))
            globalThis.customElements.define(catAggregationWidgetTag, AggregationWidget);  // TODO
        let widget = container.querySelector(catAggregationWidgetTag);
        if (!widget) {
            widget = JsUtils.createElement(catAggregationWidgetTag, {parent: container});
        }
        widget.setAggregation(weightAggregation, targetWeights);
    }

})();