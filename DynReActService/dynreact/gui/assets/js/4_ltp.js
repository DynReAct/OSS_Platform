(function() {

    globalThis.dash_clientside = Object.assign({}, globalThis.dash_clientside, {
        ltp: {}
    });

    const materialsTag = "dynreact-material-grid";
    const plantCalendarTag = "dynreact-plant-calendar";

    globalThis.dash_clientside.ltp.initMaterialGrid = function(_, __, totalProduction, existingSetpoints, gridId) {
        if (!globalThis.customElements.get(materialsTag))
            globalThis.customElements.define(materialsTag, MaterialsGridLtp);
        const grid = document.querySelector("#" + gridId);
        JsUtils.clear(grid);
        const el = JsUtils.createElement(materialsTag, {parent: grid});
        const trySetMaterials = (attempt) => {
            attempt = attempt || 0;
            const site = dynreact?.getSite();
            if (site) {
                el.setMaterials(site.material_categories, existingSetpoints, totalProduction);
            } else if (attempt < 20) {
                setTimeout(() => trySetMaterials(attempt + 1), 50)
            } else {
                console.error("Did not find site information, something went wrong...");
            }
        };
        trySetMaterials();
    }

    globalThis.dash_clientside.ltp.getMaterialSetpoints = function(_, gridId) {
        const materialGrid = document.querySelector("div#" + gridId + " " + materialsTag);
        return materialGrid?.getSetpoints();
    }

    globalThis.dash_clientside.ltp.initCalendar = function(plantAvailabilities, plant, startTime, horizonWeeks, divId) {
        if (!globalThis.customElements.get(plantCalendarTag))
            globalThis.customElements.define(plantCalendarTag, PlantCalendar);
        const parent = document.querySelector("div#" + divId);
        JsUtils.clear(parent);
        const el = JsUtils.createElement(plantCalendarTag, {parent: parent});
        plantAvailabilities = plantAvailabilities ? JSON.parse(plantAvailabilities) : undefined;
        el.setAvailabilities(startTime, horizonWeeks, plantAvailabilities, plant);
    }

    globalThis.dash_clientside.ltp.getAvailabilities = function(_, divId) {
        const calendar = document.querySelector("div#" + divId + " " + plantCalendarTag);
        return calendar?.getAvailabilities();
    }

})();