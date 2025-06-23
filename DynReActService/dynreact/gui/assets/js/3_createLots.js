(function() {

    /*
    *=================================
    * Section 1: modal opener
    *=================================
    */

    const dialogId = "create-details-modal";

    const closeListener = (event) => {
        // Note: this relies on the target being a subelement of the actual dialog, if one clicks within the dialog,
        //  but the dialog itself, if one clicks outside (the backdrop).
        if (event.target.id === dialogId)
            close();
    };

    const close = () => {
        const dialog = document.querySelector("#" + dialogId);
        dialog?.close();
        dialog?.removeEventListener("click", closeListener);
    };

    const show = () => {
        const dialog = document.querySelector("#" + dialogId);
        dialog?.showModal();
        dialog?.addEventListener("click", closeListener);
    }

    globalThis.dash_clientside = Object.assign({}, globalThis.dash_clientside, {
        createlots: {
            showDetailsModal: function(clicks) {
                if (clicks)  // prevent initial callback
                    show();
                return "Click to close settings menu";
            }
        }
    });

    /*
    *======================================================
    * Section 2: Ag grid orders table custom coils tooltip
    *======================================================
    */

    // see https://dash.plotly.com/dash-ag-grid/component-tooltip
    const dagcomponentfuncs = (window.dashAgGridComponentFunctions = window.dashAgGridComponentFunctions || {});

    const elementsForCoil = (coil, site, isInline) => {
        const currentProcessId = coil.current_process;
        const currentProcess = site.processes.find(p => p.process_ids.indexOf(currentProcessId) >= 0);
        const procFound = !!currentProcess;
        // TODO localization => (name, name_de, name_short)
        const processForDisplay = procFound ? currentProcess?.name + " (" + currentProcessId + ": " + currentProcess?.name_short + ")" : currentProcessId?.toString();
        const plantId = coil.current_equipment;
        const plant = site.equipment.find(p => p.id === plantId);
        const plantFound = !!plant;
        const plantForDisplay = plantFound ? plant.name_short + " (" + plantId + ")" : plantId?.toString();

        return React.createElement(React.Fragment, {}, [
            React.createElement("div", undefined, coil.id),
            React.createElement("div", {title: currentProcessId?.toString()}, processForDisplay),
            React.createElement("div", {title: plantId?.toString()}, plantForDisplay),
            React.createElement("div", undefined, coil.order_position),
            React.createElement("div", undefined, JsUtils.formatNumber(coil.weight)),
            React.createElement("div", undefined, isInline ? "x" : ""),

        ]);
    };

    const coilsComparator = (c1, c2) => {
        if (c1?.id === c2?.id)
            return 0;
        const proc = c1.current_process - c2.current_process;
        if (Number.isFinite(proc) && proc !== 0)
            return proc;
        const plant = c1.current_equipment - c2.current_equipment;
        if (Number.isFinite(plant) && plant !== 0)
            return plant;
        if (c1?.order_position !== undefined && c2?.order_position !== undefined)
            return c1.order_position - c2.order_position;
        return 0;
    };

    dagcomponentfuncs.CoilsTooltip = function(props) {
        // can we move the snapshot data clientside once only to make the retrieval of coil data more efficient?
        // maybe to have a Store in the main layout which will be filled by the snapshot selector?
        const dynreact = globalThis.dynreact;
        const currentOrder = props.data.id;
        const snap = dynreact.getSnapshot();
        if (!currentOrder || !snap)
            return undefined;
        let inlineCoils = undefined;  // TODO display inline coils
        if (snap.inline_material) {
            inlineCoils = Object.entries(snap.inline_material)
                .flatMap(([key, values]) => values)
                .filter(val => val.order === currentOrder)
                .map(val => val.coil)
            if (inlineCoils.length === 0)
                inlineCoils = undefined;
        }
        const coils = snap.material.filter(c => c.order === currentOrder).sort(coilsComparator);
        const site = dynreact.getSite();
        const gridEntries = coils.map(coil => /*React.createElement("div", {}, coil.id)*/ elementsForCoil(coil, site, inlineCoils?.indexOf(coil.id) >= 0));
        gridEntries.unshift(...[
            React.createElement("div", {className: "create-order-coil-header"}, "Coil id"),
            React.createElement("div", {className: "create-order-coil-header"}, "Current process"),
            React.createElement("div", {className: "create-order-coil-header"}, "Current plant"),
            React.createElement("div", {className: "create-order-coil-header"}, "Order position"),
            React.createElement("div", {className: "create-order-coil-header"}, "Weight/t"),
            React.createElement("div", {className: "create-order-coil-header"}, "In line?"),
        ]);

        return React.createElement("div", {className: "create-order-popup-parent"}, [
            React.createElement("div", {className: "create-order-popup-filler"}),
            React.createElement("div", {className: "create-order-backlog-popup"}, [
                React.createElement("h3", {className: "header"}, "Coils for order " + currentOrder),
                React.createElement("div", {className: "grid"}, gridEntries)
            ])
        ])
    };

    /*
    *======================================================
    * Section 3: Set grid tooltip parent element: https://dash.plotly.com/dash-ag-grid/tooltips#popup-parent
    *======================================================
    */

    const dagfuncs = (window.dashAgGridFunctions = window.dashAgGridFunctions || {});
    dagfuncs.setCoilPopupParent = () => document.querySelector("dialog#create-details-modal");

    /*
    *=================================
    * Section 4: lots swimlane
    *=================================
    */
    globalThis.dash_clientside.createlots.showLotsSwimlane = function(data, elementId, process, mode) {
        let swimlane = document.querySelector("div#" + elementId + ">lots-swimlane");
        if (!swimlane && data) {
            swimlane = document.createElement("lots-swimlane");
            const element = document.querySelector("div#" + elementId);
            element.appendChild(swimlane);
        }
        if (!data) {
            swimlane?.setPlanning(undefined, undefined, undefined, undefined);
            return "";
        }
        const site = globalThis.dynreact?.getSite();
        const snapshot = globalThis.dynreact?.getSnapshot();
        swimlane.setPlanning(site, snapshot, process, data);
        swimlane.lotSizing = mode;
        return "";
    };

    globalThis.dash_clientside.createlots.setLotsSwimlaneMode = function(mode) {
         Array.from(document.querySelectorAll("lots-swimlane"))
            .forEach(el => el.lotSizing = mode);
    }

})();


