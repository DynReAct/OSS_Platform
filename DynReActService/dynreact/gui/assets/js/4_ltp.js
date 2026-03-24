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

    globalThis.dash_clientside.ltp.initCalendar = function(plantAvailabilities, shifts, plant, startTime, horizonWeeks, divId) {
        if (!globalThis.customElements.get(plantCalendarTag))
            globalThis.customElements.define(plantCalendarTag, PlantCalendar);
        if (!isFinite(plant))
            return;
        const parent = document.querySelector("div#" + divId);
        JsUtils.clear(parent);
        const el = JsUtils.createElement(plantCalendarTag, {parent: parent});
        plantAvailabilities = plantAvailabilities ? JSON.parse(plantAvailabilities) : undefined;
        el.setAvailabilities(startTime, horizonWeeks, plantAvailabilities, shifts, plant);
    }

    globalThis.dash_clientside.ltp.getAvailabilities = function(_, divId) {
        const calendar = document.querySelector("div#" + divId + " " + plantCalendarTag);
        return calendar?.getAvailabilities();
    }

    const storageListener = (event) => {
        const target = event.currentTarget;
        const value = Number.parseFloat(target.value);
        if (!Number.isFinite(value))
            return;
        const isAbsoluteLevel = !!target.parentElement?.dataset?.capacity;
        const capacityEl = isAbsoluteLevel ? target.parentElement : target.parentElement.previousElementSibling;
        const capacity = Number.parseFloat(capacityEl.dataset.capacity);
        const limit = isAbsoluteLevel ? capacity/1000 : 100;
        const level = value / limit;
        if (isAbsoluteLevel)
            target.parentElement.nextElementSibling.querySelector("input").value = level * 100;
        else
            capacityEl.querySelector("input").value = level * capacity / 1000;
    };

    globalThis.dash_clientside.ltp.setStorageListeners = function(dummyTitle, id) {
        const elements = document.querySelector("#" + id)?.children;
        if (!elements)
            return dummyTitle;
        for (const element of elements) {
            const inp = element.querySelector("input");
            inp?.addEventListener("change", storageListener);
        }
        return dummyTitle;
    }

     globalThis.dash_clientside.ltp.create_ltp_animation = async function(solutionId, elId) {
        const el = document.querySelector("#" + elId);
        while (el?.firstChild)
                el.firstChild.remove();
        if (!el || !solutionId)
            return;
        const initDynreactState = await import("../dynreactviz/client/state.js").then(module => module.initDynreactState);
        //const LongTermPlanningSelector = await import("../dynreactviz/components/ltp-selector.js").then(module => module.LongTermPlanningSelector);
        const StorageLevels = await import("../dynreactviz/components/storage-levels.js").then(module => module.StorageLevels);
        const MaterialSelector = await import("../dynreactviz/components/material-selector.js").then(module => module.MaterialSelector);
        const LongTermPlanningAnimation = await import("../dynreactviz/components/ltp-animation.js").then(module => module.LongTermPlanningAnimation);
        const PlaybackControls = await import("../dynreactviz/dependencies/playback-controls/index.js").then(module => module.PlaybackControls);

        //LongTermPlanningSelector.register();
        StorageLevels.register();
        MaterialSelector.register();
        PlaybackControls.register();

        /* Create a fragment of the kind:
            <br>
            <material-selector></material-selector>
            <storage-levels></storage-levels>
            <playback-controls></playback-controls>
            <br><br>
        */
        const fragment = document.createDocumentFragment();
        fragment.appendChild(document.createElement("br"));
        const materialSelector = document.createElement("material-selector");
        fragment.appendChild(materialSelector);
        const storageLevels = document.createElement("storage-levels");
        fragment.appendChild(storageLevels);
        const controls = document.createElement("playback-controls");
        fragment.appendChild(controls);
        fragment.appendChild(document.createElement("br"));
        fragment.appendChild(document.createElement("br"));
        el.appendChild(fragment);

        const state = await initDynreactState({serverUrl: "__dash__"});
        materialSelector.setState(state);
        materialSelector.addEventListener("change", event => {
          const selection = event.detail;
          storageLevels.setColorCodes(selection?.colors);
        });
        const timelineParent = document.createElement("div");
        const ltpAnimation = new LongTermPlanningAnimation(storageLevels, controls, timelineParent, state, await state.site());

        const ltp = await state.longTermPlanningSolution(Date.now(), solutionId);
        ltpAnimation.setResults(ltp.storage_levels, ltp.targets.sub_periods);
     }

})();