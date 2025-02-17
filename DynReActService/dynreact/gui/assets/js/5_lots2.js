(function() {

    globalThis.dash_clientside = Object.assign({}, globalThis.dash_clientside, {
        lots2: {}
    });

    const materialsTag = "dynreact-material-grid";

    // &&& in work spread elements to grid without init from scratch
    globalThis.dash_clientside.lots2.spreadMaterialGrid = function(_, totalProduction, gridId){
        console.log ('loc 10 here lots2.spreadMaterialGrid ');
        console.log(' totalProduction ', totalProduction)
        const grid = document.querySelector("#" + gridId);
        console.log('loc 12 ', gridId);
        const elements = globalThis.customElements.get(materialsTag);
        console.log (elements);
        //
        const materialGrid = document.querySelector("div#" + gridId + " " + materialsTag);
        // to get the values from the fields_
        mySetpoints = materialGrid?.getSetpoints();
        console.log(' loc 19 ');
        console.log(mySetpoints);

        // set values into fields
        materialGrid?.setSetpoints(totalProduction);
    }


    // TODO handle case that only totalProduction changed... no need to reinitialize the grid from scratch then
    globalThis.dash_clientside.lots2.initMaterialGrid = function(totalProduction, setpoints, gridId) {
        console.log('loc 11 here lots2.initMaterialGrid ');
        console.log(setpoints);  //&&&
        if (Object.keys(setpoints).length === 0) {   //empty
            console.log('setpoints are empty');
            fullinit = true;
        } else {
            console.log('setpoints not empty');
            fullinit = false;
        }

        if (globalThis.customElements.get(materialsTag)) {
            console.log('exist !!');
            const newGrid = false;
        } else {
            console.log('not exist');
            const newGrid = true;
        }

        if (!globalThis.customElements.get(materialsTag))
            globalThis.customElements.define(materialsTag, MaterialsGrid);     //use MaterialGrid from ltp
        const grid = document.querySelector("#" + gridId);
        console.log('loc 16 ', gridId);
        const elements = globalThis.customElements.get(materialsTag);
        console.log('loc 16 ', elements);

        //goon = true;
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
                        //el.initTargetsFromPrev(totalProduction, setpoints)
                } else if (attempt < 20) {
                    setTimeout(() => trySetMaterials(attempt + 1), 50)
                } else {
                    console.error("Did not find site information, something went wrong...");
                }
            };
            trySetMaterials();
        }
    }

    globalThis.dash_clientside.lots2.getMaterialSetpoints = function(_, gridId) {
        console.log('here lots2.getMaterialSetpoints')
        const materialGrid = document.querySelector("div#" + gridId + " " + materialsTag);
        //console.log( gridId)
        //console.log (materialGrid)
        mySetpoints = materialGrid?.getSetpoints();
        console.log('lots2 loc 39 ');
        console.log(mySetpoints);
        return materialGrid?.getSetpoints() || {};
    }

    globalThis.dash_clientside.lots2.resetMaterialGrid = function(_, setpoints, gridId) {
        document.querySelector("div#" + gridId + " " + materialsTag)?.reset(setpoints);
        return "ltr";
    }

})();