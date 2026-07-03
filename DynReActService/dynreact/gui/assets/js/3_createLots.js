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
        const currentOrder = props.data?.id;
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
    globalThis.dash_clientside.createlots.showLotsSwimlane = async function(data, shifts, elementId, process, mode, showIds) {

        const site = globalThis.dynreact?.getSite();
        let snap = globalThis.dynreact?.getSnapshot();
        if (!site || !snap || !elementId)
            return;
        snap = {...snap, orders: snap.orders.map(o => {return {...o};}), lots: Object.fromEntries(Object.entries(snap.lots).map(([eqId, eqLots]) => [eqId, eqLots.map(lt => {return {...lt};})])) };
        snap.timestamp = new Date(snap.timestamp);
        snap.orders.filter(o => o.due_date).forEach(o => o.due_date = new Date(o.due_date));
        Object.values(snap.lots).forEach(lots => {
            lots.forEach(lot => {
                lot.start_time = lot.start_time ? new Date(lot.start_time) : undefined;
                lot.end_time = lot.end_time ? new Date(lot.end_time) : undefined;
            })
        });
        //const initDynreactState = await import("../dynreactviz/client/state.js").then(module => module.initDynreactState);
        const LotsSwimlane = await import("../dynreactviz/components/lots-swimlane.js").then(module => module.LotsSwimlane);
        LotsSwimlane.register();
        let swimlane = document.querySelector("div#" + elementId + ">lots-swimlane");
        let snapLots = false;
        if (!data || data < 0) {
            data = Object.values(snap.lots).flatMap(lots => lots);
            snapLots = true;
        } else {
            data.forEach(lot => {
                lot.start_time = lot.start_time ? new Date(lot.start_time) : undefined;
                lot.end_time = lot.end_time ? new Date(lot.end_time) : undefined;
            });
        }
        if (!swimlane) {
            swimlane = document.createElement("lots-swimlane");
            const element = document.querySelector("div#" + elementId);
            element.appendChild(swimlane);
        }
        if (showIds?.length > 0)
            swimlane.showLotLabels = true;
        if (!data) {
            swimlane?.setPlanning(undefined, undefined, undefined, undefined);
            return "";
        }
        /*
        const completeLotsOnly = snapLots && data.find(lot => lot.lot_complete) !== undefined;
        swimlane.completeLotsOnly = completeLotsOnly;
        */
        const activeLotsOnly = snapLots && data.find(lot => lot.active) !== undefined;
        swimlane.activeLotsOnly = activeLotsOnly;
        swimlane.shiftHorizon = snapLots ? "P1D" : undefined;
        if (shifts) {  // XXX copied from DynReActViz
            const _fixShifts = (shifts) => {
                const shifts2 = shifts.map(shift => {return {...shift, period: shift.period.map(p => new Date(p)), worktime: JsUtils.toMillis(shift.worktime)}});
                Object.freeze(shifts2);
                return shifts2;
            };
            shifts = Object.fromEntries(Object.entries(shifts).map(([eq, eqShifts]) => [eq, _fixShifts(eqShifts)]));
        }
        /*
        swimlane.setState(await initDynreactState({serverUrl: "__dash__"}));
        */
        // TODO shifts // FIXME migrate to setState
        swimlane.setPlanning(site, snap, process, data, shifts);
        swimlane.lotSizing = mode;
        return "";
    };

    globalThis.dash_clientside.createlots.setLotsSwimlaneMode = function(mode, elementId) {
         const el = document.querySelector("#" + elementId + " > lots-swimlane");
         if (el)
            el.lotSizing = mode;
    }

    globalThis.dash_clientside.createlots.showLotsSwimlaneIds = function(active, elementId) {
         const isActive = active && active.length > 0;
         const el = document.querySelector("#" + elementId + " > lots-swimlane");
         if (el)
            el.showLotLabels = isActive;
    }

    let tableParent = undefined;
    const pieChartTooltip = document.createElement("div");
    pieChartTooltip.classList.add("lots-gantt-pie-tooltip");
    pieChartTooltip.classList.add("hidden");
    let ttHideTimer = undefined;
    let targetHighlighted = undefined;

    const clearHideTimer = () => {
        if (ttHideTimer !== undefined)
            globalThis.clearTimeout(ttHideTimer);
        ttHideTimer = undefined;
    };

    const startHideTimer = (timeout=1000) => {
        clearHideTimer();
        ttHideTimer = globalThis.setTimeout(() => {
            pieChartTooltip.classList.add("hidden");
            targetHighlighted?.classList?.remove("lots-gantt-pie-highlighted");
            ttHideTimer = undefined;
            targetHighlighted = undefined;
        }, timeout);
    };

    const pointerLeave = () => startHideTimer();

    const pieChartLotsTableListener = (event) => {
        const target = event.target;
        const data = target?.dataset;
        const material = data?.material;
        const matLabel = data?.matLabel || material;
        if (!material || (targetHighlighted && targetHighlighted !== target)) {
            targetHighlighted?.classList?.remove("lots-gantt-pie-highlighted");
            targetHighlighted = undefined;
        }
        if (!material) {
            pieChartTooltip.classList.add("hidden");
            clearHideTimer();
            return;
        }
        const weight = JsUtils.formatNumber(data.weight, 4, 4);
        const fraction = JsUtils.formatNumber(data.fraction, 2, 3);
        pieChartTooltip.classList.remove("hidden");
        const textContent = `${matLabel}: ${weight}t (${fraction*100}%).`;
        pieChartTooltip.textContent = textContent;
        let x = event.clientX;
        let y = event.clientY;
        let parentRect = undefined;
        if (tableParent)
            parentRect = tableParent.getClientRects()[0];
        y = y - (parentRect?.y || 0);
        const clientWidth = document.body.clientWidth;
        pieChartTooltip.style.top = Math.round(y) + "px";
        if (x > 2 * clientWidth/3) {
            x = parentRect.x + parentRect.width - x + 25;
            pieChartTooltip.style.removeProperty("left");
            pieChartTooltip.style.right = Math.round(x) + "px";
        } else {
            x = x - (parentRect?.x || 0) + 25;
            pieChartTooltip.style.removeProperty("right");
            pieChartTooltip.style.left = Math.round(x) + "px";
        }
        if (target !== targetHighlighted)
            target.classList.add("lots-gantt-pie-highlighted");
        targetHighlighted = target;
        startHideTimer(30_000);  // as long as we do not move out, use a large timeout
        //console.log(" HOVERED ", x, y, material, weight, fraction);
    };

    globalThis.dash_clientside.createlots.attachPieChartEventListener = function(rows, elementId) {
        if (!(rows?.length > 0))
            return;
        const el = document.querySelector("#" + elementId);
        if (!el)
            return;
        tableParent = document.querySelector(".lots-gantt-table-parent"); // relative positioned
        tableParent?.appendChild(pieChartTooltip);
        el.querySelectorAll("svg").forEach(svg => svg.addEventListener("pointermove", pieChartLotsTableListener));
        el.querySelectorAll("svg").forEach(svg => svg.addEventListener("pointerleave", pointerLeave));
    }
})();



