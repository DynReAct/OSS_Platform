(function() {

    globalThis.dash_clientside = Object.assign({}, globalThis.dash_clientside, {
        lots2: {}
    });

    const materialsTag = "dynreact-material-grid";

    // TODO handle case that only totalProduction changed... no need to reinitialize the grid from scratch then
    globalThis.dash_clientside.lots2.initMaterialGrid = function(totalProduction, gridId) {
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
        const materialGrid = document.querySelector("div#" + gridId + " " + materialsTag);
        return materialGrid?.getSetpoints() || {};
    }

    globalThis.dash_clientside.lots2.resetMaterialGrid = function(_, setpoints, gridId) {
        document.querySelector("div#" + gridId + " " + materialsTag)?.reset(setpoints);
        return "ltr";
    }

})();