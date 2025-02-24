(function() {

    globalThis.dash_clientside = Object.assign({}, globalThis.dash_clientside, {
        lots2: {}
    });

    const materialsTag = "dynreact-material-grid";

//    globalThis.dash_clientside.lots2.spreadMaterialGrid = function(_, totalProduction, gridId){
//        // just test spread elements to grid without init from scratch, not in use
//        const grid = document.querySelector("#" + gridId);
//        const elements = globalThis.customElements.get(materialsTag);
//        const materialGrid = document.querySelector("div#" + gridId + " " + materialsTag);
//        // to get the values from the fields
//        mySetpoints = materialGrid?.getSetpoints();
//        // set values into fields
//        const test_val = 4711
//        materialGrid?.setSetpoints(test_val);
//    }

    // TODO handle case that only totalProduction changed... no need to reinitialize the grid from scratch then
    globalThis.dash_clientside.lots2.initMaterialGrid = function(totalProduction, setpoints, gridId) {
        let fullinit;
        if (Object.keys(setpoints).length == 0)    //empty
            fullinit = true;
        else
            fullinit = false;
        let newGrid;
        if (globalThis.customElements.get(materialsTag))
            newGrid = false;
        else
            newGrid = true;

        if (!globalThis.customElements.get(materialsTag))
            globalThis.customElements.define(materialsTag, MaterialsGrid);     //use MaterialGrid from ltp
        const grid = document.querySelector("#" + gridId);
        const elements = globalThis.customElements.get(materialsTag);

        if (fullinit){
            JsUtils.clear(grid);
            const el = JsUtils.createElement(materialsTag, {parent: grid});
            const trySetMaterials = (attempt) => {
                attempt = attempt || 0;
                const site = dynreact?.getSite();
                if (site) {
                    el.setMaterials(site.material_categories);
                    if (totalProduction)
                        el.initTargets(totalProduction);
                 } else if (attempt < 20) {
                    setTimeout(() => trySetMaterials(attempt + 1), 50)
                } else {
                    console.error("Did not find site information, something went wrong...");
                }
            };
            trySetMaterials();
        }
    }

    globalThis.dash_clientside.lots2.setMaterialSetpoints = function(_, gridId) {
        //returns all values from grid, callback fills Store lots2-material-setpoints
        const materialGrid = document.querySelector("div#" + gridId + " " + materialsTag);
        mySetpoints = materialGrid?.getSetpoints();
        return materialGrid?.getSetpoints() || {};
    }

    globalThis.dash_clientside.lots2.resetMaterialGrid = function(_, setpoints, gridId) {
        document.querySelector("div#" + gridId + " " + materialsTag)?.reset(setpoints);
        return "ltr";
    }

})();