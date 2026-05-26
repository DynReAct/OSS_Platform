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
                grid.setMaterials(process, site.material_categories, site.lot_creation);
                if (totalProduction)  // TODO consider setpoints
                    grid.initTargets(totalProduction, setpoints);
            }
        } else {
            // lots2-details-plants changed -> try to add diff to default field
            // TODO consider setpoints
            grid.totalValueChanged(totalProduction);
        }

    }

    globalThis.dash_clientside.lots2.initMaterialGrid2 = function(_, process, totalProduction, setpoints, gridId) {
        if (!process)
            return;
        if (!globalThis.customElements.get(materialsTag))
            globalThis.customElements.define(materialsTag, MaterialsGrid2);     //use class MaterialGrid
        const gridContainer = document.querySelector("#" + gridId);             //object MaterialGrid
        let grid = gridContainer.querySelector(materialsTag);
        // const changed = dash_clientside.callback_context.triggered_id;
        grid = grid || JsUtils.createElement(materialsTag, {parent: gridContainer, attributes: {"columns-selectable": ""}});
        const site = dynreact?.getSite();
        if (totalProduction === undefined)
            totalProduction = setpoints?._sum;
        if (site) {
            grid.setMaterials(process, site.material_categories, site.lot_creation);
            if (totalProduction)
                grid.initTargets(totalProduction, setpoints);
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

    // extra function to use buttons Clear and SetDefault
    globalThis.dash_clientside.lots2.clearMaterialGrid = function(_, totalWeight, gridId) {
        // set grid to default
        const gridContainer = document.querySelector("#" + gridId);
        const grid = gridContainer.querySelector(materialsTag);
        grid?.initTargets(totalWeight);
        return "ltr";
    }

    // used by lot creation page, lots planning page and ltp results page
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

    // used by lot planning page to download scenarios
    globalThis.dash_clientside.lots2.downloadScenario = function(json, snapshot, solution_id) {
        if (!json || !snapshot || !solution_id)
            return;
        const fileName = "snap_" + snapshot + "_" + solution_id;
        const data = typeof(json) === "string" ? json : JSON.stringify(json, undefined, 4);
        JsUtils.downloadData(data, {format: "json", fileName: fileName});
        return "";
    }

})();