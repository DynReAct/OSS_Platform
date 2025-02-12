(function() {

    globalThis.dash_clientside = Object.assign({}, globalThis.dash_clientside, {
        lots2: {}
    });

    const materialsTag = "dynreact-material-grid";

    // TODO handle case that only totalProduction changed... no need to reinitialize the grid from scratch then
    globalThis.dash_clientside.lots2.initMaterialGrid = function(totalProduction, setpoints, gridId) {
        console.log ('loc 11 here lots2.initMaterialGrid ')
        console.log(setpoints)  //&&&
        if (!globalThis.customElements.get(materialsTag))
            globalThis.customElements.define(materialsTag, MaterialsGrid);     //use MaterialGrid from ltp
        const grid = document.querySelector("#" + gridId);
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

    globalThis.dash_clientside.lots2.getMaterialSetpoints = function(_, gridId) {
        console.log('here lots2.getMaterialSetpoints')
        const materialGrid = document.querySelector("div#" + gridId + " " + materialsTag);
        //console.log( gridId)
        //console.log (materialGrid)
        mySetpoints = materialGrid?.getSetpoints()
        console.log('lots2 loc 39 ')
        console.log(mySetpoints)
        return materialGrid?.getSetpoints() || {};
    }

    globalThis.dash_clientside.lots2.resetMaterialGrid = function(_, setpoints, gridId) {
        document.querySelector("div#" + gridId + " " + materialsTag)?.reset(setpoints);
        return "ltr";
    }

})();