(function() {

    globalThis.dash_clientside = Object.assign({}, globalThis.dash_clientside, {
        lots2: {}
    });

    const materialsTag = "dynreact-material-grid2";

    // TODO handle case that only totalProduction changed... no need to reinitialize the grid from scratch then
    globalThis.dash_clientside.lots2.initMaterialGrid = function(totalProduction, process, setpoints, gridId) {
        let is_process_changed;
        let prevProcess;

        if (!globalThis.customElements.get(materialsTag))
            globalThis.customElements.define(materialsTag, MaterialsGrid2);     //use class MaterialGrid
        const gridContainer = document.querySelector("#" + gridId);             //object MaterialGrid
        let grid = gridContainer.querySelector(materialsTag);
        const fullinit = !grid?.materialsSet();

        if (fullinit){
            JsUtils.clear(gridContainer);
            grid = JsUtils.createElement(materialsTag, {parent: gridContainer});
            const site = dynreact?.getSite();
            if (site) {
                grid.setMaterials(site.material_categories);
                if (totalProduction)
                    grid.initTargets(totalProduction);
            }
        }

        //check if process changed
        prevProcess = grid.getProcessName();
        if (prevProcess){
            if (process == prevProcess)
                is_process_changed = false;
            else
                is_process_changed = true;
        } else
            is_process_changed = true;

        // process changed -> grid default vals
        if (is_process_changed)
            grid.resetGrid(totalProduction);


        // lots2-details-plants changed -> add diff to default field
        const sumsChanged = grid.checkSums();

        grid.setProcessName(process);
    }

    globalThis.dash_clientside.lots2.setMaterialSetpoints = function(_, __, gridId) {
        //triggered by button Accept or by lots2-weight-total changed
        //returns all values from grid, callback fills Store lots2-material-setpoints
        const materialGrid = document.querySelector("div#" + gridId + " " + materialsTag);
        mySetpoints = materialGrid?.getSetpoints();
        return materialGrid?.getSetpoints() || {};
    }

    globalThis.dash_clientside.lots2.resetMaterialGrid = function(_, gridId) {
        // set grid to default
        let lotsWeightTotal = Number(document.getElementById("lots2-weight-total").value);
        const gridContainer = document.querySelector("#" + gridId);
        let grid = gridContainer.querySelector(materialsTag) || null;
        if (grid)
            grid.resetGrid(lotsWeightTotal);
        //document.querySelector("div#" + gridId + " " + materialsTag)?.reset(setpoints);
        return "lots2";
    }

})();