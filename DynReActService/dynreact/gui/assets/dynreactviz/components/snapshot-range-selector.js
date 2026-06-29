import { initDynreactState, JsUtils } from "@dynreact/client";
/**
 * Dispatches "change" events of type CustomEvent<SnapshotRange|undefined>;
 */
export class SnapshotRangeSelector extends HTMLElement {
    static DEFAULT_TAG = "snapshot-range-selector";
    static #DEFAULT_BATCH_SIZE = 100;
    static _tag;
    /**
     * Call once to register the new tag type "<snapshot-range-selector></snapshot-range-selector>"
     * @param tag
     */
    static register(tag) {
        tag = tag || SnapshotRangeSelector.DEFAULT_TAG;
        if (tag !== SnapshotRangeSelector._tag) {
            customElements.define(tag, SnapshotRangeSelector);
            SnapshotRangeSelector._tag = tag;
        }
        return tag;
    }
    /**
     * Retrieve the registered tag type for this element type, or undefined if not registered yet.
     */
    static tag() {
        return SnapshotRangeSelector._tag;
    }
    static get observedAttributes() {
        return ["auto-fetch", "server", "same-value-allowed", "show-count", "batch-size", "start-time", "interval", "tolerance", "limit"];
    }
    #selectStart;
    #selectEnd;
    #showCount;
    #rangeContainer;
    // TODO change listener
    #rangeSelection;
    #endChangeListener;
    #startChangeListener;
    #endDateListener;
    #state;
    #connected = false;
    // assumed to be ordered in reverse direction
    #snaps = undefined;
    #snapTimes = undefined; // snaps getTime()
    #currentState = undefined;
    constructor() {
        super();
        const style = document.createElement("style");
        // https://nolanlawson.com/2021/01/03/options-for-styling-web-components/
        style.textContent = ":host { position: relative; display: block; }\n " +
            ".form-container {display: flex; column-gap: 1em; align-items: center; }\n " +
            ".range-container {display: flex; column-gap: 1em; }\n" +
            ".hidden {display: none;}";
        const shadow = this.attachShadow({ mode: "open" });
        shadow.appendChild(style);
        const flex = JsUtils.createElement("div", { parent: shadow, classes: "form-container" });
        JsUtils.createElement("div", { parent: flex, text: "Start:" });
        const selectStart = JsUtils.createElement("select", { parent: flex });
        JsUtils.createElement("div", { parent: flex, text: "End:" });
        const selectEnd = JsUtils.createElement("select", { parent: flex });
        const showCount = JsUtils.createElement("div", { parent: flex, classes: "hidden" });
        const rangeContainer = JsUtils.createElement("div", { parent: flex, classes: ["range-container", "hidden"] });
        JsUtils.createElement("div", { parent: rangeContainer, text: "Selection end date:" });
        this.#rangeSelection = JsUtils.createElement("input", { parent: rangeContainer, attributes: { type: "datetime-local" } });
        this.#rangeContainer = rangeContainer;
        // would not be required if change event had the composed property: https://javascript.info/shadow-dom-events, https://github.com/whatwg/html/issues/5453
        this.#endChangeListener = this.#endChanged.bind(this);
        this.#startChangeListener = this.#dispatchChange.bind(this);
        this.#endDateListener = this.#endDateChanged.bind(this);
        this.#selectStart = selectStart;
        this.#selectEnd = selectEnd;
        this.#showCount = showCount;
    }
    connectedCallback() {
        this.#connected = true;
        this.#selectEnd.addEventListener("change", this.#endChangeListener);
        this.#selectStart.addEventListener("change", this.#startChangeListener);
        this.#rangeSelection.addEventListener("change", this.#endDateListener);
        this.#initState();
    }
    disconnectedCallback() {
        this.#connected = false;
        this.#selectEnd.removeEventListener("change", this.#endChangeListener);
        this.#selectStart.removeEventListener("change", this.#startChangeListener);
        this.#rangeSelection.removeEventListener("change", this.#endDateListener);
    }
    async attributeChangedCallback(name, oldValue, newValue) {
        const attr = name.toLowerCase();
        switch (attr) {
            case "auto-fetch":
            case "server":
                this.#initState();
                break;
            case "same-value-allowed":
                this.#initStart();
                break;
            case "show-count":
                this.#initCount(newValue !== null);
                break;
            default:
                this.#selectEnd.setAttribute(name, newValue);
                this.#selectStart.setAttribute(name, newValue);
        }
    }
    #endChanged() {
        this.#initStart();
    }
    #dispatchChange() {
        const start = new Date(parseInt(this.#selectStart.value));
        const end = new Date(parseInt(this.#selectEnd.value));
        let result = undefined;
        if (isFinite(start.getTime()) && isFinite(end.getTime()) && (end > start || (this.sameValueAllowed && end.getTime() === start.getTime()))) {
            const count = this.#snaps?.filter(snap => snap >= start && snap <= end)?.length || 0;
            result = {
                start: start,
                end: end,
                snapshotCount: count
            };
        }
        if (JsUtils.primitiveObjectsEqual(result, this.#currentState, { checkForDates: true }))
            return;
        this.#currentState = result;
        if (isFinite(result?.snapshotCount)) {
            this.#showCount.textContent = "Snapshots selected: " + (result?.snapshotCount) + ".";
        }
        else
            this.#showCount.textContent = "";
        const evt = new CustomEvent("change", { detail: result });
        this.dispatchEvent(evt);
    }
    async #initState() {
        const server = this.server;
        if (!this.#connected || !this.autoFetch || !server)
            return;
        this.setState(await initDynreactState({ serverUrl: server }));
    }
    /**
     * Use either this method to let the component handle the snapshot retrieval itself, or setSnapshots to set snapshots externally.
     * Or set the auto-fetch and server attributes.
     * @param state
     */
    setState(state) {
        this.#state = state;
        this.#fetch();
    }
    /**
     * Use either this method to set snapshots explicity, or setState to let the component handle the snapshot retrieval itself.
     * @param snaps
     */
    setSnapshots(snaps, options) {
        const times = snaps?.map(snap => snap.getTime());
        if (JsUtils.primitiveArraysEqual(times, this.#snapTimes))
            return;
        this.#snaps = snaps;
        this.#snapTimes = times;
        this.#init();
        if (options?.showDateSelector !== undefined) {
            if (options.showDateSelector) {
                this.#showDateSelector();
                this.#initDateSelector();
            }
            else {
                this.#hideDateSelector();
            }
        }
    }
    async #fetch(options) {
        const state = this.#state;
        if (!state)
            return;
        const batchSize = this.batchSize;
        const snapOptions = { sort: "desc", end: "now", batchSize: batchSize };
        const endDate = new Date(this.#rangeSelection.value);
        if (isFinite(endDate.getTime()))
            snapOptions.end = endDate;
        const snapStream = state.snapshots(snapOptions);
        const snaps = await SnapshotRangeSelector.#extractSnapshots(snapStream, this.limit, this.startTime, this.interval, this.tolerance);
        const newOptions = options?.skipDateSelectorInit ? undefined : { showDateSelector: snaps?.length >= batchSize };
        this.setSnapshots(snaps, newOptions);
        /*
        const reader = snapStream.getReader();
        try {
            const snaps: Array<Date> = (await reader.read()).value!;
            const newOptions = options?.skipDateSelectorInit ? undefined : {showDateSelector: snaps?.length >= batchSize};
            this.setSnapshots(snaps, newOptions);
        } finally {
            reader.releaseLock();
        }
        */
    }
    static async #extractSnapshots(stream, limit, startTime, interval, tolerance) {
        const results = [];
        //const allValues: Array<Date> = [];
        let lastDate = new Date(0);
        let matches = [];
        for await (const values of stream) { // ?
            //allValues.push(...values);
            if (startTime === undefined || interval === undefined) {
                results.push(...values);
            }
            else {
                for (const date of values) {
                    if (!JsUtils.isSameDay(date, lastDate)) {
                        const newMatches = SnapshotRangeSelector.#getDailyTimestamps(date, startTime, interval);
                        lastDate = date;
                        matches = newMatches;
                    }
                    if (matches.findIndex(m => JsUtils.isClose(date, m, tolerance)) >= 0 || results.length === 0) { // always add the last?
                        results.push(date);
                    }
                }
            }
            if (results.length >= limit)
                break;
        }
        return results;
    }
    static #getDailyTimestamps(d, startTime, interval) {
        const start = JsUtils.startOfDay(d);
        const first = new Date(start);
        first.setHours(startTime);
        const results = [];
        let t = first;
        while (JsUtils.isSameDay(t, first)) {
            results.push(t);
            t = JsUtils.addDuration(t, interval);
        }
        t = JsUtils.addDuration(first, interval, { minus: true });
        while (JsUtils.isSameDay(t, first)) {
            results.push(t);
            t = JsUtils.addDuration(t, interval, { minus: true });
        }
        results.sort();
        return results;
    }
    #init() {
        const snaps = this.#snaps;
        const snapTimes = this.#snapTimes;
        const selectEnd = this.#selectEnd;
        const oldEnd = new Date(parseInt(selectEnd.value));
        while (selectEnd.firstChild)
            selectEnd.firstChild.remove();
        if (!(snaps?.length > 0))
            return;
        const fragEnd = document.createDocumentFragment();
        const oldEndTime = oldEnd.getTime();
        const selected = isFinite(oldEndTime) && snapTimes.indexOf(oldEndTime) >= 0 ? oldEndTime : snapTimes[0];
        snaps
            .map(date => [date, JsUtils.formatDate(date)])
            .forEach(([date, formatted]) => JsUtils.createElement("option", { parent: fragEnd, attributes: { value: date.getTime() + "", label: formatted } }));
        selectEnd.appendChild(fragEnd);
        selectEnd.value = selected + "";
        this.#initStart();
    }
    #initStart() {
        const sameValueAllowed = this.sameValueAllowed;
        let snaps = this.#snaps || [];
        let snapTimes = this.#snapTimes || [];
        const selectStart = this.#selectStart;
        const oldStart = new Date(parseInt(selectStart.value));
        while (selectStart.firstChild)
            selectStart.firstChild.remove();
        const selectEnd = this.#selectEnd;
        const endSelected = new Date(parseInt(selectEnd.value));
        const fragStart = document.createDocumentFragment();
        if (isFinite(endSelected.getTime())) {
            const indexIn = snaps.findIndex(snap => sameValueAllowed ? snap <= endSelected : snap < endSelected);
            if (indexIn >= 0) {
                snaps = snaps.slice(indexIn);
                snapTimes = snapTimes.slice(indexIn);
            }
        }
        const oldStartTime = oldStart.getTime();
        const startSelected = isFinite(oldStartTime) && snapTimes?.indexOf(oldStartTime) >= 0 ? oldStartTime : snaps?.length > 0 ? snaps[snaps.length - 1].getTime() : undefined;
        snaps
            .map(date => [date, JsUtils.formatDate(date)])
            .forEach(([date, formatted]) => JsUtils.createElement("option", { parent: fragStart, attributes: { value: date.getTime() + "", label: formatted } }));
        selectStart.appendChild(fragStart);
        selectStart.value = startSelected + "";
        this.#dispatchChange();
    }
    #initDateSelector() {
        const select = this.#rangeSelection;
        const selected = this.#snaps?.length > 0 ? this.#snaps[0] : new Date();
        select.value = JsUtils.formatDate(selected);
    }
    #showDateSelector() {
        this.#rangeContainer.classList.remove("hidden");
    }
    #hideDateSelector() {
        this.#rangeContainer.classList.add("hidden");
    }
    #initCount(doShow) {
        if (!doShow)
            this.#showCount.classList.add("hidden");
        else
            this.#showCount.classList.remove("hidden");
    }
    #endDateChanged() {
        if (this.#state)
            this.#fetch({ skipDateSelectorInit: true });
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
    get sameValueAllowed() {
        return this.getAttribute("same-value-allowed") !== null;
    }
    set sameValueAllowed(allowed) {
        if (allowed)
            this.setAttribute("same-value-allowed", "");
        else
            this.removeAttribute("same-value-allowed");
    }
    get showCount() {
        return this.getAttribute("show-count") !== null;
    }
    set showCount(show) {
        if (show)
            this.setAttribute("show-count", "");
        else
            this.removeAttribute("show-count");
    }
    get batchSize() {
        let bz = parseInt(this.getAttribute("batch-size"));
        if (!(bz > 0))
            bz = SnapshotRangeSelector.#DEFAULT_BATCH_SIZE;
        return bz;
    }
    set batchSize(size) {
        if (!(size > 0) || parseInt(size) !== size)
            throw new Error("Invalid batch size " + size + ", must be a positive integer");
        this.setAttribute("batch-size", size + "");
    }
    get interval() {
        const itv = this.getAttribute("interval");
        if (!itv)
            return undefined;
        try {
            return JsUtils.parseDuration(itv);
        }
        catch (e) {
            return undefined;
        }
    }
    set interval(interval) {
        if (!interval) {
            this.removeAttribute("interval");
            return;
        }
        if (typeof interval === "string")
            JsUtils.parseDuration(interval); // throws if invalid
        else
            interval = JsUtils.serializeDuration(interval);
        this.setAttribute("interval", interval);
    }
    get startTime() {
        const start0 = this.getAttribute("start-time");
        if (start0 === null || start0 === "")
            return undefined;
        const start1 = parseInt(start0);
        if (!isFinite(start1) || start1 < 0 || start1 > 23)
            return undefined;
        return start1;
    }
    set startTime(startTime) {
        if (startTime === undefined) {
            this.removeAttribute("start-time");
            return;
        }
        if (!isFinite(startTime) || startTime < 0 || startTime > 23 || !Number.isInteger(startTime))
            throw new Error("Invalid start time " + startTime + ", must be an integer in the range [0, 23].");
        this.setAttribute("start-time", startTime + "");
    }
    get tolerance() {
        const itv = this.getAttribute("tolerance");
        if (!itv)
            return undefined;
        try {
            return JsUtils.parseDuration(itv);
        }
        catch (e) {
            return undefined;
        }
    }
    set tolerance(tolerance) {
        if (!tolerance) {
            this.removeAttribute("tolerance");
            return;
        }
        if (typeof tolerance === "string")
            JsUtils.parseDuration(tolerance); // throws if invalid
        else
            tolerance = JsUtils.serializeDuration(tolerance);
        this.setAttribute("tolerance", tolerance);
    }
    get limit() {
        let l = parseInt(this.getAttribute("limit"));
        if (!(l > 0))
            l = SnapshotRangeSelector.#DEFAULT_BATCH_SIZE;
        return l;
    }
    set limit(limit) {
        if (!(limit > 0) || !Number.isInteger(limit))
            throw new Error("Invalid limit " + limit + ", must be a positive integer");
        this.setAttribute("limit", limit + "");
    }
}
//# sourceMappingURL=snapshot-range-selector.js.map