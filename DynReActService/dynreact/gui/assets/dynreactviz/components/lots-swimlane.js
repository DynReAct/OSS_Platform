import { initDynreactState, JsUtils, SnapshotImpl } from "@dynreact/client";
/**
 * Gantt chart for lots
 */
export class LotsSwimlane extends HTMLElement {
    static #DEFAULT_TAG = "lots-swimlane";
    static #tag;
    /**
     * Call once to register the new tag type <lots-swimlane></lots-swimlane>
     * @param tag
     */
    static register(tag) {
        tag = tag || LotsSwimlane.#DEFAULT_TAG;
        if (tag !== LotsSwimlane.#tag) {
            customElements.define(tag, LotsSwimlane);
            LotsSwimlane.#tag = tag;
        }
        return tag;
    }
    /**
     * Retrieve the registered tag type for this element type, or undefined if not registered yet.
     */
    static tag() {
        return LotsSwimlane.#tag;
    }
    static get observedAttributes() {
        return ["auto-fetch", "row-size", "lot-height", "lot-color", "lot-sizing", "process", "server", "skip-shifts", "complete-lots-only", "min-status"];
    }
    #lanesContainer;
    #tooltipContainer;
    #svgParent;
    #connected = false;
    #rowSize = 50;
    #lotHeight = 20;
    #missingShiftHeight = 30;
    #lotColor = "rgba(139,0,0,0.9)";
    #lotSizing = "constant";
    #site = undefined;
    #snapshot = undefined;
    #state = undefined;
    #lots = undefined; // keys: plant id
    #lotsOriginal;
    #lotsSetExplicitly = false;
    #shifts;
    #coils = undefined; // keys: lot id, order id
    // all: Record<string, number>
    #numOrdersByLot = undefined;
    #numCoilsByLot = undefined;
    #numOrdersByPlant = undefined;
    #numCoilsByPlant = undefined;
    #weightByLot = undefined;
    #durationByLot = undefined; // in millis
    #endTimeByPlant = undefined;
    //#durationByPlant: Record<number, number>|undefined = undefined;  // in millis   // tbd
    #weightByPlant = undefined;
    #plants = undefined;
    // information about created elements
    #lanes = undefined;
    set rowSize(size) {
        if (size > 0) {
            this.#rowSize = size;
            this.#init();
        }
    }
    get rowSize() {
        return this.#rowSize;
    }
    set lotHeight(height) {
        if (height > 0) {
            this.#lotHeight = height;
            this.#init();
        }
    }
    get lotHeight() {
        return this.#lotHeight;
    }
    set lotColor(color) {
        if (color) {
            this.#lotColor = color;
            this.#init();
        }
    }
    get lotColor() {
        return this.#lotColor;
    }
    set lotSizing(value) {
        const previous = this.#lotSizing;
        const lower = value?.toLowerCase();
        switch (lower) {
            case "constant":
            case "weight":
            case "orders":
            case "coils":
            case "time":
                this.#lotSizing = lower;
                if (lower !== previous)
                    this.#init();
        }
    }
    get lotSizing() {
        return this.#lotSizing;
    }
    get lots() {
        return this.#lots ? { ...this.#lots } : undefined;
    }
    get site() {
        return this.#site ? { ...this.#site } : undefined;
    }
    get snapshot() {
        return this.#snapshot ? { ...this.#snapshot } : undefined;
    }
    get plants() {
        return this.#plants ? [...this.#plants] : undefined;
    }
    get coils() {
        return this.#coils ? { ...this.#coils } : undefined;
    }
    get numOrdersByLot() {
        return this.#numOrdersByLot ? { ...this.#numOrdersByLot } : undefined;
    }
    get numCoilsByLot() {
        return this.#numCoilsByLot ? { ...this.#numCoilsByLot } : undefined;
    }
    get weightByLot() {
        return this.#weightByLot ? { ...this.#weightByLot } : undefined;
    }
    get numOrdersByPlant() {
        return this.#numOrdersByPlant ? { ...this.#numOrdersByPlant } : undefined;
    }
    get numCoilsByPlant() {
        return this.#numCoilsByPlant ? { ...this.#numCoilsByPlant } : undefined;
    }
    get weightByPlant() {
        return this.#weightByPlant ? { ...this.#weightByPlant } : undefined;
    }
    get process() {
        return this.getAttribute("process") || undefined;
    }
    set process(process) {
        if (process)
            this.setAttribute("process", process);
        else
            this.removeAttribute("process");
    }
    get server() {
        return this.getAttribute("server");
    }
    set server(server) {
        if (server)
            this.setAttribute("server", server);
        else
            this.removeAttribute("server");
    }
    get autoFetch() {
        return this.getAttribute("auto-fetch")?.toLowerCase() === "true";
    }
    set autoFetch(doFetch) {
        if (doFetch)
            this.setAttribute("auto-fetch", "true");
        else
            this.removeAttribute("auto-fetch");
    }
    get completeLotsOnly() {
        return this.getAttribute("complete-lots-only") !== null;
    }
    set completeLotsOnly(completeOnly) {
        if (completeOnly)
            this.setAttribute("complete-lots-only", "true");
        else
            this.removeAttribute("complete-lots-only");
    }
    get minStatus() {
        const status = Number.parseInt(this.getAttribute("min-status"));
        return status >= 0 ? status : undefined;
    }
    set minStatus(status) {
        if (Number.isInteger(status) && status > 0)
            this.setAttribute("min-status", status.toString());
        else
            this.removeAttribute("min-status");
    }
    get skipShifts() {
        return this.getAttribute("skip-shifts") !== null;
    }
    set skipShifts(skip) {
        if (skip)
            this.setAttribute("skip-shifts", "true");
        else
            this.removeAttribute("skip-shifts");
    }
    constructor() {
        super();
        const shadow = this.attachShadow({ mode: "open" });
        const style = document.createElement("style");
        style.textContent = ".hidden { display: none; } " +
            ".plant-header { dominant-baseline: middle; color: darkgreen; } " +
            ".tooltip-container { position: absolute; pointer-events: none; background: white; padding: 0.5em; z-index: 5; border-radius: 2px; } " +
            ".tooltip-container[hidden] { display: none; } " +
            ".plant-header:hover { cursor: pointer;} " +
            ".lot-rect:hover { cursor: pointer;} ";
        /*
        ".lanes-container {display: grid; grid-template-columns: auto 1fr; } " +
        ".plant-title {padding: 1em; border: 2px solid darkgreen;} " +
        ".plant-lane {padding: 1em; border: 2px solid darkgreen;} "
        ;
        */
        shadow.append(style);
        const lanesContainer = document.createElement("div");
        shadow.append(lanesContainer);
        lanesContainer.classList.add("lanes-container");
        this.#lanesContainer = lanesContainer;
        const tooltipContainer = document.createElement("div");
        tooltipContainer.classList.add("tooltip-container");
        tooltipContainer.setAttribute("hidden", "true");
        shadow.append(tooltipContainer);
        this.#tooltipContainer = tooltipContainer;
        // FIXME
        // @ts-ignore
        window.lane = this;
    }
    #previousHoverTarget = undefined;
    #hover(evt) {
        const target = evt.target;
        const container = this.#tooltipContainer;
        if (target === this.#previousHoverTarget) {
            if (!container.getAttribute("hidden")) {
                container.style.setProperty("top", (evt.pageY - 5) + "px");
                container.style.setProperty("left", (evt.pageX + 15) + "px");
            }
            return;
        }
        this.#previousHoverTarget = target;
        const lot = target.dataset.lot;
        const plant = parseInt(target.dataset.plant);
        if (Number.isFinite(plant)) {
            const type = target.dataset.type;
            const isLot = !!lot;
            if (isLot) {
                const numOrders = this.#numOrdersByLot[lot] || 0;
                const numCoils = this.#numCoilsByLot[lot] || 0;
                const weight = this.#weightByLot[lot] || 0;
                let tooltip = "Lot " + target.dataset.lot + " (orders: " + numOrders + ", coils: " + numCoils + ", weight: " + JsUtils.formatNumber(weight) + "t";
                const lotObj = this.#lotsOriginal?.find(lt => lt.id === lot);
                if (lotObj?.status !== undefined)
                    tooltip += ", status = " + lotObj.status;
                if (lotObj?.start_time || lotObj?.end_time) {
                    if (lotObj.start_time)
                        tooltip += ", start: " + JsUtils.formatDate(lotObj.start_time);
                    if (lotObj.end_time)
                        tooltip += ", end: " + JsUtils.formatDate(lotObj.end_time);
                }
                tooltip += ")";
                container.textContent = tooltip;
            }
            else if (type === "downtime") {
                const start = target.dataset.start;
                const end = target.dataset.end;
                container.textContent = "Downtime, start: " + start + ", end: " + end + ".";
            }
            else {
                const numOrders = this.#numOrdersByPlant[plant] || 0;
                const numCoils = this.#numCoilsByPlant[plant] || 0;
                const weight = this.#weightByPlant[plant] || 0;
                const plantName = this.#plants.find(p => p.id === plant)?.name_short || plant;
                container.textContent = "Plant " + plantName + " (id: " + plant + ", orders: " + numOrders + ", coils: " + numCoils + ", weight: " + JsUtils.formatNumber(weight, { numDigits: 4 }) + "t)";
                ;
            }
            container.style.setProperty("top", (evt.pageY - 5) + "px");
            container.style.setProperty("left", (evt.pageX + 15) + "px");
            container.removeAttribute("hidden");
        }
        else { // if tooltip visible
            container.setAttribute("hidden", "true");
        }
    }
    connectedCallback() {
        this.#connected = true;
        this.#initState();
    }
    disconnectedCallback() {
        this.#connected = false;
    }
    // FIXME currently this does not expect Lot objects, but something similar...
    setPlanning(site, snapshot0, process, lots, shifts, skipProcess) {
        // console.log("New planning", lots);
        const snapshot = snapshot0 instanceof SnapshotImpl ? snapshot0 : new SnapshotImpl(snapshot0);
        const lotsByPlant = {};
        this.#lotsSetExplicitly = !!lots;
        if (!lots)
            lots = Object.values(snapshot.snapshot.lots).flatMap(lotsArr => lotsArr);
        lots = lots.map(lot => {
            if (lot.equipment && lot.orders)
                return lot;
            // legacy: support table dict lot entries
            return {
                // @ts-ignore
                equipment: lot.plant_id, orders: lot.order_ids,
                ...lot
            };
        });
        this.#lotsOriginal = lots;
        this.#shifts = shifts;
        const completeOnly = this.completeLotsOnly;
        if (completeOnly)
            lots = lots.filter(lot => lot.lot_complete);
        const minStatus = this.minStatus;
        if (minStatus >= 0)
            lots = lots.filter(lot => lot.status >= minStatus);
        if (!this.#lotsSetExplicitly) {
            lots = lots.sort((l1, l2) => {
                if (l1.equipment !== l2.equipment) // irrelevant
                    return 0;
                const bothDates1 = l1.start_time && l1.end_time;
                const bothDates2 = l2.start_time && l2.end_time;
                if (bothDates1 && !bothDates2)
                    return -1;
                if (bothDates2 && !bothDates1)
                    return 1;
                if (bothDates1)
                    return l1.end_time < l2.end_time ? -1 : l1.end_time > l2.end_time ? 1 : 0;
                if (l1.status > l2.status)
                    return -1;
                if (l2.status > l1.status)
                    return 1;
                if (l1.active && !l2.active)
                    return -1;
                if (l2.active && !l1.active)
                    return 1;
                // @ts-ignore
                if (l1["priority"] !== undefined || l2["priority"] !== undefined) {
                    // @ts-ignore
                    if (l1["priority"] === undefined)
                        return 1;
                    // @ts-ignore
                    if (l2["priority"] === undefined)
                        return -1;
                    // @ts-ignore;
                    return Number.parseInt(l1["priority"]) - Number.parseInt(l2["priority"]);
                }
                return l1.id.localeCompare(l2.id);
            });
        }
        lots.forEach(lot => {
            const plant = lot.equipment;
            if (!(plant in lotsByPlant))
                lotsByPlant[plant] = [];
            lotsByPlant[plant].push(lot);
        });

        this.#lots = lots ? lotsByPlant : undefined;
        this.#site = site;
        this.#snapshot = snapshot;
        const plantIds = [...Object.keys(lotsByPlant)].map(v => parseInt(v));
        this.#plants = site?.equipment?.filter(plant => plantIds.indexOf(plant.id) >= 0);
        const snapTime = snapshot.snapshot.timestamp.getTime();
        if (snapshot && lots) {
            const coilsByOrder = snapshot.get_coils_by_order();
            // Record<string, Record<string, Array<Coil>>>  // keys: lot id, order id
            const coils = Object.fromEntries(lots.map(lot => [lot.id, Object.fromEntries(lot.orders.map(order => [order, order in coilsByOrder ? coilsByOrder[order] : []]))]));
            this.#coils = coils;
            // Record<string, number>
            const numOrdersByLot = Object.fromEntries(lots.map(lot => [lot.id, lot.id in coils ? Object.keys(coils[lot.id]).length : 0]));
            // Record<string, number>
            const numCoilsByLot = Object.fromEntries(lots.map(lot => [lot.id, lot.id in coils ? Object.values(coils[lot.id]).flatMap(coils0 => coils0).length : 0]));
            const weightByLot = Object.fromEntries(lots.map(lot => [lot.id, lot.id in coils ?
                    Object.values(coils[lot.id]).map(coils0 => coils0.map(c => c.weight).filter(weight => Number.isFinite(weight)).reduce((a, b) => a + b, 0)).reduce((a, b) => a + b, 0) : 0]));
            const numOrdersByPlant = Object.fromEntries(Object.entries(lotsByPlant).map(([plantId, lots]) => [plantId, lots.map(lot => numOrdersByLot[lot.id]).reduce((a, b) => a + b, 0)]));
            const numCoilsByPlant = Object.fromEntries(Object.entries(lotsByPlant).map(([plantId, lots]) => [plantId, lots.map(lot => numCoilsByLot[lot.id]).reduce((a, b) => a + b, 0)]));
            const weightByPlant = Object.fromEntries(Object.entries(lotsByPlant).map(([plantId, lots]) => [plantId, lots.map(lot => weightByLot[lot.id]).reduce((a, b) => a + b, 0)]));
            const durationByLot = Object.fromEntries(lots.filter(lot => lot.end_time && lot.start_time).map(lot => [lot.id, lot.end_time.getTime() - Math.max(lot.start_time.getTime(), snapTime)]));
            const endTimeByPlant = Object.fromEntries(Object.entries(lotsByPlant).map(([plantId, lots]) => [plantId, new Date(Math.max(...lots.filter(lt => lt.end_time).map(lt => lt.end_time.getTime()), snapTime))]));
            this.#numOrdersByLot = numOrdersByLot;
            this.#numCoilsByLot = numCoilsByLot;
            this.#weightByLot = weightByLot;
            this.#numOrdersByPlant = numOrdersByPlant;
            this.#numCoilsByPlant = numCoilsByPlant;
            this.#weightByPlant = weightByPlant;
            this.#durationByLot = durationByLot;
            this.#endTimeByPlant = endTimeByPlant;
        }
        else {
            this.#coils = undefined;
            this.#numOrdersByLot = undefined;
            this.#numCoilsByLot = undefined;
            this.#numOrdersByPlant = undefined;
            this.#numCoilsByPlant = undefined;
            this.#weightByLot = undefined;
            this.#weightByPlant = undefined;
            this.#durationByLot = undefined;
            this.#endTimeByPlant = undefined;
        }
        if (!skipProcess)
            this.process = process; // will lead to reinitialization
        // this.#init();
    }
    async #initState() {
        const server = this.server;
        if (!this.#connected || !this.autoFetch || !server)
            return;
        this.setState(await initDynreactState({ serverUrl: server }));
    }
    /**
     * Use either this method to let the component handle the snapshot retrieval itself, or setPlanning()
     * Or set the auto-fetch and server attributes.
     * @param state
     */
    setState(state) {
        this.#state = state;
        const process = this.process;
        this.#initProcess(process);
    }
    #queryShifts(snapshot) {
        const end = new Date(snapshot);
        end.setDate(end.getDate() + 10); // ?
        return this.#state.shifts({ start: snapshot, end: end, limit: 1000 });
    }
    #initProcess(process) {
        if (!this.#snapshot && this.#state) {
            const sitePromise = this.#state.site();
            const snapshotPromise = this.#state.snapshot(); // TODO date configurable?
            const shiftsPromise = this.skipShifts ? Promise.resolve(undefined) : snapshotPromise.then(snap => this.#queryShifts(snap.timestamp));
            Promise.all([sitePromise, snapshotPromise, shiftsPromise]).then(([site, snap, shifts]) => {
                this.setPlanning(site, snap, process, undefined, shifts, true); // avoid retriggering this method
                this.#init();
            });
            return;
        }
        if (this.#snapshot && !this.#lotsSetExplicitly) // determine process lots from snapshot
            this.setPlanning(this.#site, this.#snapshot, process, undefined, this.#shifts, true);
        this.#init();
    }
    #init() {
        this.clear();
        if (!this.#plants)
            return;
        const rowSize = this.#rowSize;
        const lotHeight = this.#lotHeight;
        const missingShiftHeight = this.#missingShiftHeight;
        const lotColor = this.#lotColor;
        const width = Math.max(document.body.clientWidth - 100, 200);
        const svgParent = LotsSwimlane.#create("svg", { attributes: {
                viewbox: "0 0 " + width + " " + (rowSize * this.#plants.length + 1),
                /*
                width: "90vw", // FIXME this leads to the disappearance of some content
                */
                width: width + "px",
                height: (rowSize * this.#plants.length + 75) + "px"
            } });
        this.#svgParent = svgParent;
        const sizing = this.#lotSizing;
        const startTime = this.#snapshot.snapshot.timestamp;
        const endTime = new Date(Math.max(...Object.values(this.#endTimeByPlant).map(dt => dt.getTime())));
        const sizeFactor = sizing === "constant" ? Math.max(...Array.from(Object.values(this.#lots)).map(plantLots => plantLots.length)) :
            sizing === "weight" ? Math.max(...Object.values(this.#weightByPlant)) :
                sizing === "orders" ? Math.max(...Object.values(this.#numOrdersByPlant)) :
                    sizing === "time" ? endTime.getTime() - startTime.getTime() :
                        Math.max(...Object.values(this.#numCoilsByPlant));
        const xStartGantt = 100;
        // draw x-axis
        const y = this.#plants.length * rowSize;
        LotsSwimlane.#create("line", { parent: svgParent, attributes: { x1: "0", y1: y + "", x2: width + "", y2: y + "", stroke: "darkgreen" } });
        const legendY = y + 20;
        // axis
        LotsSwimlane.#create("line", { parent: svgParent, attributes: { x1: xStartGantt + "", y1: legendY + "", x2: width + "", y2: legendY + "", stroke: "black" } });
        const isNumeric = sizing === "coils" || sizing === "orders" || sizing === "weight" || sizing === "constant";
        if (isNumeric) {
            const items = JsUtils.findTicks([0, sizeFactor], width - xStartGantt, 100, 250);
            const factor = (width - xStartGantt) / sizeFactor;
            const positions = items.map(item => Math.floor(xStartGantt + item * factor));
            const useKt = sizing === "weight" && items[items.length - 1] > 2000;
            positions.forEach((pos, idx) => {
                const textAnchor = pos - xStartGantt < 50 ? "start" : width - pos < 50 ? "end" : "middle";
                LotsSwimlane.#create("line", { parent: svgParent, attributes: { x1: pos + "", y1: legendY + "", x2: pos + "", y2: (legendY + 10) + "", stroke: "black" } });
                const text = useKt && idx !== 0 ? (items[idx] / 1000).toFixed(2) : items[idx].toString();
                //const x = pos < 30 ? pos + 2 : pos - (Math.min(text.length, 20)*5 / 2)
                const label = LotsSwimlane.#create("text", { attributes: { x: pos + "", y: (legendY + 30) + "", "text-anchor": textAnchor }, /*classes: "plant-header",*/ parent: svgParent });
                label.textContent = text;
                const verticalLine = LotsSwimlane.#create("line", { attributes: { x1: pos + "", x2: pos + "", y1: "0", y2: (legendY + 30) + "", stroke: "lightgrey" }, parent: svgParent });
            });
            if (sizing === "weight") {
                const label = LotsSwimlane.#create("text", { attributes: { x: (width - 1) + "", y: (legendY + 45) + "", "text-anchor": "end" }, /*classes: "plant-header",*/ parent: svgParent });
                label.textContent = useKt ? "kt" : "t";
            }
        }
        else if (sizing === "time") {
            const startMillis = startTime.getTime();
            const [items, unit] = JsUtils.findDateTicks([startTime, endTime], width - xStartGantt, 200, 400);
            const factor = (width - xStartGantt) / sizeFactor;
            const positions = items.map(item => Math.floor(xStartGantt + (item.getTime() - startMillis) * factor));
            positions.forEach((pos, idx) => {
                const textAnchor = pos - xStartGantt < 50 ? "start" : width - pos < 50 ? "end" : "middle";
                LotsSwimlane.#create("line", { parent: svgParent, attributes: { x1: pos + "", y1: legendY + "", x2: pos + "", y2: (legendY + 10) + "", stroke: "black" } });
                const item = items[idx];
                const text = JsUtils.formatDateByUnit(item, unit);
                const label = LotsSwimlane.#create("text", { attributes: { x: pos + "", y: (legendY + 30) + "", "text-anchor": textAnchor }, /*classes: "plant-header",*/ parent: svgParent });
                label.textContent = text;
                const verticalLine = LotsSwimlane.#create("line", { attributes: { x1: pos + "", x2: pos + "", y1: "0", y2: (legendY + 30) + "", stroke: "lightgrey" }, parent: svgParent });
            });
        }
        // draw shift gaps
        if (sizing === "time" && this.#shifts) {
            const defs = LotsSwimlane.#create("defs", { parent: svgParent });
            const shiftH = missingShiftHeight + "";
            const shiftColor = "green";
            const pattern = LotsSwimlane.#create("pattern", { parent: defs, attributes: { id: "downtime", x: "0", y: "0", width: shiftH, height: shiftH, patternUnits: "userSpaceOnUse" } });
            const line1 = LotsSwimlane.#create("line", { parent: pattern, attributes: { x1: "0", y1: "0", x2: shiftH, y2: shiftH, stroke: shiftColor, "stroke-width": "2" } });
            const line2 = LotsSwimlane.#create("line", { parent: pattern, attributes: { x1: "0", y1: shiftH, x2: shiftH, y2: "0", stroke: shiftColor, "stroke-width": "2" } });
        }
        // draw lots
        this.#lanes = this.#plants.map((plant, idx) => this.#createPlantLane(idx, plant, svgParent, rowSize, width, lotHeight, missingShiftHeight, lotColor, sizing, sizeFactor, xStartGantt, [startTime, endTime]));
        this.#lanesContainer.appendChild(svgParent);
        // @ts-ignore
        svgParent.addEventListener("mousemove", this.#hover.bind(this));
    }
    // using event.target property instead
    /*
    _findField(x, y) {
        const lanes = this.#lanes;  // Array<{plant: number; title: DOMRect, lots: Array<{lot: string; field: DOMRect}>}>
        if (!lanes)
            return undefined;
        // check for vertical match first
        const match = lanes.find(lane => lane.title.y < y && (lane.title.y + lane.title.height) > y);
        if (!match)
            return undefined;
        const isTitle = match.title.x < x && (match.title.x + match.title.width) > x;
        const lot = isTitle ? undefined :
            match.lots.find(lot => lot.field.x < x && (lot.field.x + lot.field.width) > x && lot.field.y < y && (lot.field.y + lot.field.height) > y);
        return {
            plant: match.plant,
            isTitle: isTitle,
            lot: lot?.lot
        };
    }
    */
    /**
    * before calling this function, we need to determine the available space and the algorithm used to calculate the item length
    */
    #createPlantLane(idx, plant, svg, rowSize, rowWidth, lotHeight, missingShiftHeight, lotColor, sizing, sizeFactor, start0, startEndTime) {
        const title = LotsSwimlane.#create("text", { attributes: { x: "15", y: ((idx + 0.5) * rowSize) + "" }, dataset: { plant: plant.id + "" }, classes: "plant-header", parent: svg });
        title.textContent = LotsSwimlane.#plantName(plant);
        const yFieldStart = idx * rowSize;
        const titleField = new DOMRect(0, yFieldStart, start0, rowSize);
        const lotFields = [];
        const lots = this.#lots[plant.id];
        const isTime = sizing === "time";
        const effectiveRowWidth = rowWidth - start0;
        const gapFields = [];
        // draw shift gaps
        if (sizing === "time" && this.#shifts) {
            const shifts = this.#shifts[plant.id];
            if (!shifts) {
                // TODO ?
            }
            else {
                let lastShiftEnd = this.#snapshot.snapshot.timestamp;
                let gapStart = undefined;
                for (const shift of shifts) {
                    const isGap = shift.worktime <= 0;
                    if (isGap) {
                        if (gapStart === undefined)
                            gapStart = shift.period[0];
                        continue;
                    }
                    if (gapStart !== undefined || shift.period[0] > lastShiftEnd) {
                        const gap = [gapStart !== undefined ? gapStart : lastShiftEnd, shift.period[0]]; // TODO what if the current shift has only partial worktime?
                        const xStart = Math.round(start0 + (Math.max(gap[0].getTime(), startEndTime[0].getTime()) - startEndTime[0].getTime()) / sizeFactor * effectiveRowWidth);
                        const width = Math.round(Math.max(effectiveRowWidth * (gap[1].getTime() - gap[0].getTime()) / sizeFactor - 10, 3));
                        const lotYStart = (idx + 0.5) * rowSize - (missingShiftHeight / 2);
                        // TODO fill color
                        const rect = LotsSwimlane.#create("rect", { attributes: { x: xStart + "", width: width + "", y: lotYStart + "", height: missingShiftHeight + "",
                                rx: "3", "stroke": "green", "stroke-width": "2", "fill": "url(#downtime)" },
                            dataset: { "type": "downtime", plant: plant.id + "", start: JsUtils.formatDate(gap[0]), end: JsUtils.formatDate(gap[1]) }, parent: svg });
                        gapStart = undefined;
                    }
                    lastShiftEnd = shift.period[1];
                    if (shift.period[0] >= startEndTime[1])
                        break;
                }
            }
        }
        let xStart = start0;
        for (const lot of lots) {
            //x="120" width="100" height="100" rx="15"
            const size = sizing === "constant" ? 1 :
                sizing === "weight" ? this.#weightByLot[lot.id] :
                    sizing === "orders" ? this.#numOrdersByLot[lot.id] :
                        sizing === "time" ? this.#durationByLot[lot.id] || 3_600_000 : // 1h if unknown => ?
                            this.#numCoilsByLot[lot.id];
            if (isTime && lot.start_time) {
                xStart = start0 + (Math.max(lot.start_time.getTime(), startEndTime[0].getTime()) - startEndTime[0].getTime()) / sizeFactor * effectiveRowWidth;
            }
            const width = Math.max(effectiveRowWidth * (size / sizeFactor) - 10, 3);
            const lotYStart = (idx + 0.5) * rowSize - (lotHeight / 2);
            const rect = LotsSwimlane.#create("rect", { attributes: { x: xStart + "", width: width + "",
                    y: lotYStart + "", height: lotHeight + "", rx: "3", fill: lotColor }, dataset: { lot: lot.id, plant: plant.id + "" },
                classes: "lot-rect", parent: svg });
            xStart += width + 10;
            const field = new DOMRect(xStart, lotYStart, width, lotHeight);
            lotFields.push({
                lot: lot.id,
                field: field
            });
        }
        const y = (idx * rowSize) + "";
        LotsSwimlane.#create("line", { parent: svg, attributes: {
                x1: "0", y1: y, x2: rowWidth + "", y2: y, stroke: "darkgreen"
            } });
        return {
            plant: plant.id,
            title: titleField,
            lots: lotFields
        };
    }
    clear() {
        while (this.#lanesContainer.firstChild)
            this.#lanesContainer.firstChild.remove();
        this.#svgParent = undefined;
        this.#lanes = undefined;
    }
    attributeChangedCallback(name, oldValue, newValue) {
        const attr = name.toLowerCase();
        switch (attr) {
            case "row-size":
                this.rowSize = parseFloat(newValue);
                break;
            case "lot-height":
                this.lotHeight = parseFloat(newValue);
                break;
            case "lot-color":
                this.lotColor = newValue;
                break;
            case "lot-sizing":
                this.lotSizing = newValue;
                break;
            case "process":
                this.#initProcess(newValue || undefined);
                break;
            case "complete-lots-only":
            case "min-status":
                if (this.#lotsOriginal) {
                    // TODO new mthod for this
                    this.setPlanning(this.#site, this.#snapshot, this.process, this.#lotsOriginal, this.#shifts, true);
                    this.#init();
                }
                break;
            case "server":
            case "auto-fetch":
                this.#initState();
                break;
        }
    }
    static #plantName(plant) {
        return plant.name_short || plant.name || plant.id + "";
    }
    static #plantTooltip(plant) {
        if (plant.name)
            return plant.name + "(id: " + plant.id + ")";
        return "Id: " + plant.id;
    }
    static #create(svgTag, options) {
        const el = document.createElementNS("http://www.w3.org/2000/svg", svgTag);
        if (options?.attributes)
            Object.entries(options.attributes).forEach(([key, value]) => el.setAttribute(key, value));
        if (options?.dataset)
            Object.entries(options.dataset).forEach(([key, value]) => el.dataset[key] = value);
        if (options?.classes) {
            const classes = !Array.isArray(options.classes) ? [options.classes] : options.classes;
            classes.forEach(cl => el.classList.add(cl));
        }
        if (options?.parent)
            options?.parent.appendChild(el);
        return el;
    }
}
//globalThis.customElements.define("lots-swimlane", LotsSwimlane);
/* row data (TODO: need snapshot in addition, also site maybe)

{
    "id": lot.id,
    "plant": plants[lot.plant].name_short if lot.plant in plants and plants[lot.plant].name_short is not None else str(lot.plant),
    "num_orders": len(lot.orders),
    "num_coils": num_coils[lot.id],
    "order_ids": ", ".join(lot.orders),
    "first_due_date": first_due_dates[lot.id],
    "all_due_dates": all_due_dates[lot.id],
    "total_weight": total_weights[lot.id]
}

*/
//# sourceMappingURL=lots-swimlane.js.map