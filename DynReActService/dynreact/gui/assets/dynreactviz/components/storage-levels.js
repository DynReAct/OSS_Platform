import { initDynreactState, JsUtils, SiteImpl } from "@dynreact/client";
export class StorageLevels extends HTMLElement {
    static #DEFAULT_TAG = "storage-levels";
    static #DEFAULT_CAPACITY = 10_000; // tons
    static #tag;
    /**
     * Call once to register the new tag type "<storage-levels></storage-levels>"
     * @param tag
     */
    static register(tag) {
        tag = tag || StorageLevels.#DEFAULT_TAG;
        if (tag !== StorageLevels.#tag) {
            customElements.define(tag, StorageLevels);
            StorageLevels.#tag = tag;
        }
        return tag;
    }
    /**
     * Retrieve the registered tag type for this element type, or undefined if not registered yet.
     */
    static tag() {
        return StorageLevels.#tag;
    }
    static get observedAttributes() {
        return ["auto-fetch", "server", "width", "height", "storage-mode", "default-capacity"];
    }
    #connected = false;
    #state;
    #site;
    #plants; // initialized once the canvas has been drawn
    #storages; // initialized once the canvas has been drawn
    #processes;
    /**
     * Keys: storage ids (or plant ids, process ids); values: either a number (absolute filling level, in t) or a map
     * from material class id to filling level
     */
    #storageLevels;
    /**
     * Keys: material class ids, values: color codes
     */
    #colorCodes;
    #canvas;
    #resizeListener;
    #pointermoveHandler;
    #clickHandler;
    /*
    readonly #tooltip: HTMLElement;
    #tooltipAppended: boolean = false;
    #tooltipTarget: HoverData|undefined;
    */
    #tooltip;
    constructor() {
        super();
        const style = document.createElement("style");
        style.textContent = ".main-container {position: relative; }\n" +
            ".tooltip {position: absolute; padding: 1em; background-color:rgba(173,216,230, 0.9); color: darkblue; border-radius: 4px;}\n" +
            ".tooltip-fixed { border: 2px dashed darkblue;}\n" +
            ".tooltip-fixed>.tooltip-header {font-weight: bold; }\n " +
            ".tooltip-grid {display: grid; column-gap: 1em; row-gap: 0.3em; }\n " +
            ".grid-2-cols {grid-template-columns: repeat(2, auto);} .grid-3-cols {grid-template-columns: repeat(3, auto);}\n" +
            ".tt-grid-header {padding-top: 1em; font-weight: bold;}\n" +
            ".capacity-grid {display: grid; grid-template-columns: repeat(2, auto); column-gap: 1em; row-gap: 0.3em; padding-top: 0.5em;}";
        const shadow = this.attachShadow({ mode: "open" });
        shadow.appendChild(style);
        const mainContainer = JsUtils.createElement("div", { parent: shadow, classes: "main-container" });
        const width = (globalThis?.innerWidth || 1368) - 100;
        const canvas = JsUtils.createElement("canvas", { parent: mainContainer, attributes: { width: width, height: 512 } });
        this.#canvas = canvas;
        const tt = JsUtils.createElement("div", { classes: "tooltip" });
        this.#tooltip = new Tooltip(tt, () => shadow.appendChild(tt), () => this.#site);
        this.#resizeListener = this.#resized.bind(this);
        this.#pointermoveHandler = new PointermoveHandler(canvas, () => [this.#plants, this.#storages], this.#tooltip.show.bind(this.#tooltip));
        this.#clickHandler = new CanvasListener(canvas, "click", () => [this.#plants, this.#storages], this.#tooltip.fix.bind(this.#tooltip));
    }
    #resized() {
        let width = globalThis?.innerWidth || 1368;
        const site = this.#site;
        if (site) {
            const numProcesses = site.processes.length;
            const minWidth = numProcesses * 120;
            if (width < minWidth)
                width = minWidth;
            else if (width > 1300)
                width = width - 50;
        }
        this.#canvas.width = width;
        this.#init();
    }
    connectedCallback() {
        this.#connected = true;
        globalThis.addEventListener("resize", this.#resizeListener);
        this.#pointermoveHandler.start();
        this.#clickHandler.start();
    }
    disconnectedCallback() {
        this.#connected = false;
        globalThis.removeEventListener("resize", this.#resizeListener);
        this.#pointermoveHandler.end();
        this.#clickHandler.end();
    }
    async #initState() {
        const server = this.server;
        if (!this.#connected || !this.autoFetch || !server)
            return;
        this.setState(await initDynreactState({ serverUrl: server }));
    }
    /**
     * Use either this method to let the component handle the site retrieval itself, or setSite() to set the site externally.
     * Or set the auto-fetch and server attributes.
     * @param state
     */
    setState(state) {
        this.#state = state;
        this.#fetch();
    }
    async #fetch() {
        const state = this.#state;
        if (!state)
            return;
        const site = await state.site();
        this.setSite(site);
    }
    setSite(site) {
        this.#site = site;
        this.#init();
    }
    setStorageLevels(levels) {
        this.#storageLevels = levels;
        if (this.#site)
            this.#init();
    }
    /**
     *
     * @param colors keys: material class ids, values: colors
     */
    setColorCodes(colors) {
        this.#colorCodes = colors;
        if (this.#site)
            this.#init();
    }
    #init() {
        this.#clear();
        const site = this.#site;
        if (!site)
            return;
        const canvas = this.#canvas;
        const ctx = canvas.getContext("2d");
        const siteImpl = new SiteImpl(site);
        const totalWidth = canvas.width;
        const totalHeight = canvas.height;
        const heightCenter = Math.floor(totalHeight / 2);
        const processes = site.processes;
        const plants = site.equipment;
        const storages = site.storages;
        ctx.strokeStyle = "blue";
        ctx.lineWidth = 3;
        ctx.font = "12px Arial";
        ctx.fillStyle = "darkblue";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        const plantsDrawn = [];
        const storagesDrawn = [];
        const processesDrawn = [];
        let processesByIds = {};
        let lastProcId = 0;
        for (const process of processes) {
            const firstId = process?.process_ids?.length > 0 ? process.process_ids[0] : lastProcId + 1;
            const asStr = firstId + "";
            if (!(asStr in processesByIds))
                processesByIds[asStr] = [process];
            else
                processesByIds[asStr].push(process);
            lastProcId = firstId;
        }
        processesByIds = Object.fromEntries(Object.entries(processesByIds).sort(([id1, _], [id2, __]) => parseInt(id1) - parseInt(id2)));
        const processNamesById = Object.fromEntries(Object.entries(processesByIds).map(([proc_id, processes]) => [proc_id, processes.map(pr => pr.name_short)]));
        const plantsById = Object.fromEntries(Object.keys(processesByIds).map(proc_id => [proc_id, plants.filter(e => processNamesById[proc_id].indexOf(e.process) >= 0)]));
        const maxPlantsPerCol = Math.max(...Object.values(plantsById).map(plants => plants.length));
        const columnByStorage = {};
        const storageMode = this.storageMode;
        const storagesById = storageMode === "storage" ? Object.fromEntries(Object.entries(plantsById).map(([proc_id, plants], colIdx) => {
            const storages = JsUtils.uniquePreserverOrder(plants.map(p => p.storage_in).filter(s => !(s in columnByStorage)));
            storages.forEach(s => columnByStorage[s] = 2 * colIdx + 1);
            return [proc_id, storages];
        })) : storageMode === "plant" ? Object.fromEntries(Object.entries(plantsById).map(([key, plants]) => [key, plants.map(p => p.name_short)])) :
            Object.fromEntries(Object.entries(processNamesById).map(([key, names]) => [key, [names.join(",")]]));
        const maxStoragesPerCol = Math.max(...Object.values(storagesById).map(s => s.length));
        const heightPerStorage = Math.max(Math.floor(totalHeight / Math.max(maxStoragesPerCol, 2)), 60);
        // the total storage space contains the storage circle, the content rectangle and 3*border offset
        const storageBorderOffset = heightPerStorage > 160 ? 15 : 10;
        const storageCircleRadius = Math.max(Math.floor(heightPerStorage / (heightPerStorage > 160 ? 8 : 6)), 5);
        const storageContentHeight = heightPerStorage - 3 * storageBorderOffset - 2 * storageCircleRadius;
        let colIdx = 0;
        const columns = 2 * Object.keys(processesByIds).length + 1; // 1 col per process and 1 per storages for this process, plus final storage (TODO)
        const widthPerCol = Math.max(...[Math.floor(totalWidth / columns), 25]);
        const plantOffset = totalWidth > 1200 ? totalWidth / 40 : 20; // TODO handle very small cases?
        const plantWidth = widthPerCol - plantOffset;
        const storageWidth = plantWidth - plantOffset / 2;
        let colStartX = -widthPerCol;
        for (const [proc_id, procs] of Object.entries(processesByIds)) {
            colStartX += widthPerCol;
            const procPlants = plantsById[proc_id];
            const numPlants = procPlants.length;
            const heightPerPlant = Math.min(...[Math.max(...[Math.floor(totalHeight / numPlants), 25]), 65]);
            const storageIds = storagesById[proc_id];
            const numStorages = storageIds.length;
            let rowIdx = 0;
            //const xStartStorage = xStart - widthPerCol + plantOffset/4;
            const xStartStorage = colStartX + plantOffset / 4;
            const yStartStorage0 = heightCenter + Math.floor(numStorages / 2) * heightPerStorage;
            const yStartStorage = numStorages % 2 === 1 ? yStartStorage0 + storageCircleRadius + storageBorderOffset : yStartStorage0;
            const plantHeight = heightPerPlant - 10;
            ctx.lineWidth = 2;
            ctx.strokeStyle = "darkblue";
            for (const storage of storageIds) {
                //const stg = storages.find(s => s.name_short === storage)!;
                const toggleStorageAndContainer = rowIdx >= numStorages / 2;
                const yBottom = yStartStorage - rowIdx * heightPerStorage;
                const yCenterCircle = toggleStorageAndContainer ? yBottom - 2 * storageBorderOffset - storageContentHeight - storageCircleRadius : yBottom - storageCircleRadius - storageBorderOffset;
                const xStorageLeft = xStartStorage + storageWidth / 2 - storageCircleRadius;
                const yStorageTop = toggleStorageAndContainer ? yBottom - storageBorderOffset - storageContentHeight : yBottom - 2 * storageBorderOffset - 2 * storageCircleRadius - storageContentHeight;
                const storageDrawn = { name_short: storage, circ: { x: xStartStorage + storageWidth / 2, y: yCenterCircle, r: storageCircleRadius },
                    storage: { x: xStorageLeft, y: yStorageTop, width: 2 * storageCircleRadius, height: storageContentHeight } };
                ctx.beginPath();
                ctx.fillStyle = "lightgray";
                ctx.arc(xStartStorage + storageWidth / 2, yCenterCircle, storageCircleRadius, 0, 2 * Math.PI);
                ctx.fill();
                ctx.fillStyle = "black";
                ctx.fillText(storageDrawn.name_short, xStartStorage + storageWidth / 2, yCenterCircle);
                ctx.rect(xStorageLeft, yStorageTop, 2 * storageCircleRadius, storageContentHeight);
                ctx.stroke();
                //StorageLevels.#drawRect(ctx, storageDrawn);
                storagesDrawn.push(storageDrawn);
                rowIdx++;
            }
            ctx.lineWidth = 3;
            //ctx.stroke();
            ctx.beginPath();
            ctx.strokeStyle = "blue";
            ctx.fillStyle = "darkblue";
            rowIdx = 0;
            colStartX += widthPerCol;
            const yOffset = procPlants.length % 2 === 1 ? heightPerPlant / 2 : 0;
            for (const plant of procPlants) {
                const centerY = heightCenter - 50 + Math.floor(numPlants / 2) * heightPerPlant + yOffset - rowIdx * heightPerPlant;
                const plantDrawn = { ...plant, rect: { x: colStartX + 10, y: centerY, width: plantWidth, height: plantHeight } };
                plantsDrawn.push(plantDrawn);
                StorageLevels.#drawRect(ctx, plantDrawn);
                //ctx.fillText(plant.name_short, xStart + plantWidth/2, centerY + plantHeight/2);
                rowIdx++;
            }
            ctx.stroke();
            colIdx++;
        }
        this.#plants = plantsDrawn;
        this.#storages = storagesDrawn;
        this.#processes = processesDrawn;
        if (this.#storageLevels) {
            this.#initStorageLevels();
        }
        const canvasRect = canvas.getClientRects()[0];
        this.#tooltip.update(canvasRect.x, canvasRect.y, plantsDrawn, storagesDrawn);
    }
    static #validateLevel(level) {
        if (level < 0)
            level = 0;
        else if (level > 1)
            level = 1;
        return level;
    }
    #initStorageLevels() {
        const levels = this.#storageLevels;
        if (!levels)
            return;
        const colorCodes = this.#colorCodes || {};
        const canvas = this.#canvas;
        const ctx = canvas.getContext("2d");
        const capacities = this.#getCapacities();
        for (const storage of this.#storages) {
            const storageId = storage.name_short;
            // TODO case of merged process names // TODO show only selected categories
            const currentLevels = levels[storageId];
            if (!currentLevels)
                continue;
            const capacity = capacities[storageId] || StorageLevels.#DEFAULT_CAPACITY;
            storage.capacity = capacity;
            storage.filled = 0;
            const totalHeightAvailable = storage.storage.height - 2;
            const x = storage.storage.x + 1;
            const width = storage.storage.width - 2;
            if (typeof currentLevels === "number" || (Object.keys(colorCodes).find(c => c in currentLevels) === undefined && "__total__" in currentLevels)) {
                const level0 = typeof currentLevels === "number" ? currentLevels : currentLevels.__total__;
                const level = StorageLevels.#validateLevel(level0 / capacity);
                const y = storage.storage.y + (1 - level) * totalHeightAvailable;
                const height = level * totalHeightAvailable;
                storage.filled = level0;
                ctx.fillStyle = "gray";
                ctx.fillRect(x, y, width, height);
            }
            else {
                const yTop = storage.storage.y + 1;
                let yBottom = yTop + totalHeightAvailable;
                storage.materialContainers = [];
                for (const [key, absoluteLevel] of Object.entries(currentLevels)) {
                    if (!(key in colorCodes))
                        continue;
                    storage.filled += absoluteLevel;
                    const color = colorCodes[key];
                    const level = absoluteLevel / capacity;
                    const height = StorageLevels.#validateLevel(level) * totalHeightAvailable;
                    yBottom = yBottom - height;
                    ctx.fillStyle = color;
                    ctx.fillRect(x, yBottom, width, height);
                    storage.materialContainers.push({ x: x, y: yBottom, width: width, height: height, materialId: key, weight: absoluteLevel });
                }
            }
        }
    }
    static #drawRect(ctx, element) {
        const rect = element.rect;
        ctx.rect(rect.x, rect.y, rect.width, rect.height);
        ctx.fillText(element.name_short, rect.x + rect.width / 2, rect.y + rect.height / 2);
    }
    #clear() {
        const canvas = this.#canvas;
        const ctx = canvas.getContext("2d");
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        this.#plants = undefined;
        this.#storages = undefined;
        this.#processes = undefined;
    }
    #getCapacities() {
        const site = this.#site;
        const mode = this.storageMode;
        const defaultCapacity = this.defaultCapacity;
        if (!site || !mode)
            return {};
        if (mode === "storage")
            return Object.fromEntries(site.storages.map(s => [s.name_short, s.capacity_weight || defaultCapacity]));
        const plantsByStorage = JsUtils.groupBy(site.equipment, eq => eq.storage_in, eq => eq.name_short);
        const capByPlant = {};
        site.storages.forEach(s => {
            const plants = plantsByStorage[s.name_short];
            if (plants) {
                const numPlants = plants.length;
                const cap = s.capacity_weight || defaultCapacity;
                plants.forEach(p => capByPlant[p] = cap / numPlants);
            }
        });
        if (mode === "plant")
            return capByPlant;
        const plantsByProcess = JsUtils.groupBy(site.equipment, (eq) => eq.process, (eq) => eq.name_short);
        const capByProcess = Object.fromEntries(Object.entries(plantsByProcess).map(([proc, plants]) => [proc, plants.map(p => capByPlant[p] || 0).reduce((a, b) => a + b, 0)]));
        return capByProcess;
    }
    async attributeChangedCallback(name, oldValue, newValue) {
        const attr = name.toLowerCase();
        switch (attr) {
            case "auto-fetch":
            case "server":
                this.#initState();
                break;
        }
    }
    // boilerplate below
    get autoFetch() {
        return this.getAttribute("auto-fetch")?.toLowerCase() === "true";
    }
    set autoFetch(doFetch) {
        if (doFetch)
            this.setAttribute("auto-fetch", "true");
        else
            this.removeAttribute("auto-fetch");
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
    get storageMode() {
        const mode = this.getAttribute("storage-mode")?.toLowerCase();
        if (mode === "plant" || mode === "storage" || mode === "process")
            return mode;
        return "storage"; // default
    }
    set storageMode(mode) {
        mode = mode?.toLowerCase();
        if (["storage", "plant", "process"].indexOf(mode) >= 0)
            this.setAttribute("storage-mode", mode);
    }
    get defaultCapacity() {
        const cap = parseFloat(this.getAttribute("default-capacity"));
        if (cap > 0)
            return cap;
        return StorageLevels.#DEFAULT_CAPACITY;
    }
    set defaultCapacity(capacity) {
        if (capacity > 0)
            this.setAttribute("default-capacity", capacity + "");
    }
}
class CanvasListener {
    _canvas;
    _eventType;
    _data;
    _listener;
    #moveListener;
    start() {
        this._canvas.addEventListener(this._eventType, this.#moveListener, { passive: true });
    }
    end() {
        this._canvas.removeEventListener(this._eventType, this.#moveListener);
    }
    constructor(_canvas, _eventType, _data, _listener) {
        this._canvas = _canvas;
        this._eventType = _eventType;
        this._data = _data;
        this._listener = _listener;
        this.#moveListener = this.getListener();
    }
    getListener() {
        return this.call.bind(this);
    }
    call(evt) {
        if (!evt) {
            this._listener();
            return;
        }
        const [plants, storages] = this._data();
        const canvas = this._canvas.getClientRects()[0];
        const hoveredElement = CanvasListener.getHoveredElement({ x: evt.x - canvas.x, y: evt.y - canvas.y }, plants, storages);
        if (hoveredElement)
            this._listener({ ...hoveredElement, x: evt.x, y: evt.y });
        else
            this._listener();
    }
    static getHoveredElement(point, plants, storages) {
        const storage = storages?.find(s => CanvasListener.#circContainsPoint(s.circ, point) || CanvasListener.#rectContainsPoint(s.storage, point));
        0;
        if (storage) {
            return { x: point.x, y: point.y, storage: { ...storage, isMaterialContainer: CanvasListener.#rectContainsPoint(storage.storage, point) } };
        }
        const plant = plants?.find(p => CanvasListener.#rectContainsPoint(p.rect, point));
        if (plant)
            return { x: point.x, y: point.y, plant: plant };
        return undefined;
    }
    static #rectContainsPoint(rect, point) {
        return rect.x <= point.x && rect.x + rect.width >= point.x && rect.y <= point.y && rect.y + rect.height >= point.y;
    }
    static #circContainsPoint(circ, point) {
        const dist = Math.pow(circ.x - point.x, 2) + Math.pow(circ.y - point.y, 2);
        return dist <= Math.pow(circ.r, 2);
    }
}
// like a regular pointermove handler, but it throttles the callbacks to a certain max frequency.
class PointermoveHandler extends CanvasListener {
    _canvas;
    _data;
    _listener;
    #timer;
    #lastEvent;
    #execListener;
    constructor(_canvas, _data, _listener) {
        super(_canvas, "pointermove", _data, _listener);
        this._canvas = _canvas;
        this._data = _data;
        this._listener = _listener;
        this.#execListener = this.#callDelayed.bind(this);
    }
    getListener() {
        return (event) => this.#execute(event);
    }
    end() {
        super.end();
        globalThis.clearTimeout(this.#timer);
        this.#timer = undefined;
        this.#lastEvent = undefined;
    }
    #execute(event) {
        this.#lastEvent = event;
        if (this.#timer !== undefined)
            return;
        this.#timer = window.setTimeout(this.#execListener, 100);
    }
    #callDelayed() {
        this.#timer = undefined;
        super.call(this.#lastEvent);
    }
}
class Tooltip {
    _element;
    _connect;
    _siteAccess;
    #header;
    #body;
    #tooltipTarget;
    #tooltipAppended = false;
    #fixed = false;
    constructor(_element, _connect, _siteAccess) {
        this._element = _element;
        this._connect = _connect;
        this._siteAccess = _siteAccess;
        const header = JsUtils.createElement("div", { parent: _element, classes: "tooltip-header" });
        const body = JsUtils.createElement("div", { parent: _element });
        this.#header = header;
        this.#body = body;
    }
    show(data, options) {
        if (this.#fixed)
            return;
        const tooltip = this._element;
        const lastTarget = this.#tooltipTarget;
        this.#tooltipTarget = data;
        if (!data) {
            tooltip.remove();
            this.#tooltipAppended = false;
            return;
        }
        const header = this.#header;
        const body = this.#body;
        tooltip.style.left = (data.x + 25) + "px";
        tooltip.style.top = (data.y - 10) + "px";
        if (data.plant !== lastTarget?.plant || data.storage !== lastTarget?.storage) {
            header.textContent = data.plant ? "Equipment " + data.plant.name_short : "Storage " + data.storage?.name_short || "";
        }
        while (body.firstChild)
            body.firstChild.remove();
        if (options?.showDetails && data.storage) {
            const site = this._siteAccess();
            const capacity = data.storage.capacity;
            const hasCapacity = !!capacity;
            const capacityGrid = JsUtils.createElement("div", { parent: body, classes: "capacity-grid" });
            if (hasCapacity) {
                JsUtils.createElement("div", { parent: capacityGrid, text: "Capacity:" });
                JsUtils.createElement("div", { parent: capacityGrid, text: JsUtils.formatNumber(capacity, { upperExpoLimitDigits: 5 }) + " t" });
            }
            if (data.storage.materialContainers && site) { // TODO in separate method
                const matCats = Object.fromEntries(site.material_categories.map(c => [c.id, c]));
                const classesByCats = Object.fromEntries(site.material_categories.map(cat => [cat.id, cat.classes
                        .map(cl => data.storage.materialContainers.find(c => c.materialId === cl.id)).filter(cl => cl)])
                    .filter(([cat, classes]) => classes.length > 0));
                if (Object.keys(classesByCats).length > 0) {
                    const totalWeight = Object.values(classesByCats)[0].map(cl => cl.weight).reduce((a, b) => a + b, 0);
                    JsUtils.createElement("div", { parent: capacityGrid, text: "Content:" });
                    let weight = JsUtils.formatNumber(totalWeight, { upperExpoLimitDigits: 5 }) + " t";
                    if (capacity)
                        weight += "  (" + Math.round(totalWeight / capacity * 1000) / 10 + "%)";
                    JsUtils.createElement("div", { parent: capacityGrid, text: weight });
                }
                const grid = JsUtils.createElement("div", { parent: body, classes: ["tooltip-grid", hasCapacity ? "grid-3-cols" : "grid-2-cols"] });
                const frag = document.createDocumentFragment();
                for (const [cat, classes] of Object.entries(classesByCats)) {
                    JsUtils.createElement("div", { parent: frag, classes: "tt-grid-header", text: matCats[cat]?.name || cat });
                    JsUtils.createElement("div", { parent: frag, classes: "tt-grid-header", text: "Weight/t" });
                    if (hasCapacity)
                        JsUtils.createElement("div", { parent: frag, classes: "tt-grid-header", text: "Level" });
                    for (const clazz of classes) {
                        JsUtils.createElement("div", { parent: frag, classes: "tt-grid-cell", text: matCats[cat]?.classes?.find(cl => cl.id === clazz.materialId)?.name || clazz.materialId });
                        JsUtils.createElement("div", { parent: frag, classes: "tt-grid-cell", text: JsUtils.formatNumber(clazz.weight, { upperExpoLimitDigits: 5 }) });
                        if (hasCapacity)
                            JsUtils.createElement("div", { parent: frag, classes: "tt-grid-cell", text: (Math.round(clazz.weight / capacity * 1000) / 10) + "%" });
                    }
                    break; // this assumes there is only a single entry in classesByCats, which should always be the case
                }
                grid.appendChild(frag);
            }
            // TODO show storage content
        }
        if (data.body)
            body.appendChild(data.body);
        if (!this.#tooltipAppended) {
            this._connect();
            this.#tooltipAppended = true;
        }
    }
    fix(data) {
        const tooltip = this._element;
        const wasFixed = this.#fixed;
        if (wasFixed) {
            tooltip.classList.remove("tooltip-fixed");
            this.#fixed = false;
        }
        if (!data) {
            tooltip.remove();
            this.#tooltipAppended = false;
            return;
        }
        this.show(data, { showDetails: !wasFixed });
        if (!wasFixed) {
            tooltip.classList.add("tooltip-fixed");
            this.#fixed = true;
        }
    }
    update(offsetX, offsetY, plants, storages) {
        if (!this.#fixed)
            return;
        const data = CanvasListener.getHoveredElement({ x: this.#tooltipTarget.x - offsetX, y: this.#tooltipTarget.y - offsetY }, plants, storages);
        const tooltip = this._element;
        this.#fixed = false;
        if (!data) {
            tooltip.remove();
            this.#tooltipAppended = false;
            tooltip.classList.remove("tooltip-fixed");
            this.#tooltipTarget = data;
            return;
        }
        data.x = data.x + offsetX;
        data.y = data.y + offsetY;
        this.show(data, { showDetails: true });
        this.#fixed = true;
    }
}
//# sourceMappingURL=storage-levels.js.map