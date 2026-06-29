import { PlaybackState } from "playback-controls";
import { JsUtils } from "@dynreact/client";
import { SpinnerCss } from "./spinner-css.js";
// TODO create timeslider
// TODO create line plot with total material indicator above timeslider
export class StorageAnimation {
    storageLevels;
    controls;
    timelineParent;
    state;
    static #DEFAULT_MAX_NUMBER_SNAPSHOTS = 20;
    static #DEFAULT_PRELOAD_COUNT = 10;
    // 
    static #DEFAULT_PRELOAD_WAIT_COUNT = 5;
    #hasTimeOfDay;
    #snapshotTimes;
    #maxNumberSnapshots;
    #snapshots;
    #times;
    #dateRange;
    #timeRange;
    #activeDate;
    #activeTime;
    #activeIndex;
    // note: we need not cache aggressively, since those get requests should be cached by the browser
    // keys: snapshot timestamps; material aggregation outer key: storage
    #aggregationCache = {};
    // snapshot timestamps which are currently being preloaded
    #activeLoadRequests = [];
    #spinner;
    #preloadCount;
    #preloadWaitCount;
    #smoothAnimation; // TODO configurable via GUI?
    /**
     *
     * @param storageLevels
     * @param controls
     * @param timelineParent:
     */
    constructor(storageLevels, controls, timelineParent, state, options) {
        this.storageLevels = storageLevels;
        this.controls = controls;
        this.timelineParent = timelineParent;
        this.state = state;
        this.#hasTimeOfDay = !!options?.snapshotTimes;
        this.#snapshotTimes = options?.snapshotTimes;
        this.#maxNumberSnapshots = options?.maxNumberSnapshots > 0 ? options?.maxNumberSnapshots : StorageAnimation.#DEFAULT_MAX_NUMBER_SNAPSHOTS;
        this.#smoothAnimation = options?.smoothAnimation !== undefined ? options?.smoothAnimation : true;
        controls.setAnimationListener({ move: state => this.#setFraction(state.fraction, state.state === PlaybackState.PLAYING ? "forward" :
                state.state === PlaybackState.PLAYING_BACKWARDS ? "backward" : undefined), step: (fraction, backwards) => this.#step(fraction, backwards) });
        const storageMain = storageLevels.shadowRoot?.querySelector(".main-container");
        const spinnerTag = SpinnerCss.register();
        this.#spinner = JsUtils.createElement(spinnerTag, { parent: storageMain, attributes: { top: options?.spinnerTop || "0", left: options?.spinnerLeft || "0" } });
        this.#preloadCount = options?.preloadCount > 0 ? options?.preloadCount : StorageAnimation.#DEFAULT_PRELOAD_COUNT;
        this.#preloadWaitCount = options?.preloadWaitCount > 0 ? options?.preloadWaitCount : StorageAnimation.#DEFAULT_PRELOAD_WAIT_COUNT;
        // FIXME 
        // @ts-ignore
        window.dynreact = window.dynreact || {};
        // @ts-ignore
        window.dynreact.storage_animation = this;
    }
    #step(fraction, backwards) {
        if (!(this.#times?.length > 1))
            return false;
        const [min, max] = this.#timeRange;
        const date = new Date(min + fraction * (max - min));
        const time = date.getTime();
        const [bestMatchingSnap, index, exactMatch] = JsUtils.binarySearch(time, this.#times);
        const epsilon = 1e-3;
        let newIdx;
        if (backwards) {
            if (index === 0 && exactMatch)
                return false;
            newIdx = index === 0 || time > bestMatchingSnap + epsilon ? index : index - 1;
        }
        else {
            if (index === this.#times?.length - 1 && exactMatch)
                return false;
            newIdx = index === this.#times?.length - 1 || time < bestMatchingSnap - epsilon ? index : index + 1;
        }
        const snap = this.#snapshots[newIdx];
        const newFraction = (snap.getTime() - min) / (max - min);
        const result = this.setActive(snap, undefined /* FIXME not known*/, { skipWaitForPreload: true });
        if (result === true)
            return newFraction;
        if (result === false)
            return false;
        return result.then(() => newFraction);
    }
    #setFraction(fraction, direction) {
        if (!this.#timeRange || fraction === undefined)
            return false;
        const [min, max] = this.#timeRange;
        const date = new Date(min + fraction * (max - min));
        const result = this.setActive(date, direction);
        return result;
    }
    set snapshots(snaps) {
        this.state.abortAll(); // note: this state may be shared with other components, this is dangerous... 
        if (this.#hasTimeOfDay && snaps?.length > 2) {
            const start = snaps[0];
            const startDay = new Date(start);
            startDay.setHours(0, 0, 0, 0);
            const end = snaps[snaps.length - 1];
            const newSnaps = [];
            while (startDay <= end) {
                for (const time of this.#snapshotTimes) {
                    const dt = new Date(startDay);
                    dt.setHours(time[0]);
                    dt.setMinutes(time[1]);
                    if (dt < start)
                        continue;
                    if (dt >= end)
                        break;
                    newSnaps.push(dt);
                }
                startDay.setDate(startDay.getDate() + 1);
            }
            snaps = newSnaps;
        }
        else if (snaps?.length > this.#maxNumberSnapshots) {
            const snaps1 = snaps;
            const diff = (snaps1[snaps1.length - 1].getTime() - snaps1[0].getTime()) / (this.#maxNumberSnapshots - 1);
            const first = snaps1[0];
            let lastTime = first.getTime();
            const newSnaps = [first];
            for (const snap of snaps1) {
                if (snap.getTime() - lastTime >= diff) {
                    newSnaps.push(snap);
                    lastTime = snap.getTime();
                }
            }
            if (newSnaps.indexOf(snaps1[snaps1.length - 1]) < 0)
                newSnaps.push(snaps1[snaps1.length - 1]);
            snaps = newSnaps;
        }
        this.#snapshots = snaps ? [...snaps] : undefined;
        this.#times = snaps ? snaps.map(d => d.getTime()) : undefined;
        this.#dateRange = snaps ? [snaps[0], snaps[snaps.length - 1]] : undefined;
        this.#timeRange = snaps ? this.#dateRange.map(d => d.getTime()) : undefined;
        const removeFromCache = Object.keys(this.#aggregationCache).filter(snap => !snaps || this.#times.indexOf(parseInt(snap)) < 0);
        for (const old of removeFromCache) {
            delete this.#aggregationCache[parseInt(old)];
        }
        if (!(snaps?.length > 0)) {
            this.setActive(undefined, undefined);
            this.controls.ticks = undefined;
        }
        else {
            const first = isFinite(this.#activeDate?.getTime()) ? this.#activeDate : snaps[0];
            this.setActive(first, "forward", { skipWaitForPreload: true });
            const range = this.#timeRange;
            this.controls.ticks = this.#times.map(d => { return { fraction: (d - range[0]) / (range[1] - range[0]), tick: new Date(d) }; });
        }
    }
    get snapshots() {
        return this.#snapshots ? [...this.#snapshots] : undefined;
    }
    set maxNumberSnapshots(max) {
        if (max > 0)
            this.#maxNumberSnapshots = max;
    }
    get maxNumberSnapshots() {
        return this.#maxNumberSnapshots;
    }
    setActive(date, direction, options) {
        if (!date) {
            this.#activeDate = undefined;
            this.#activeTime = undefined;
            this.#activeIndex = undefined;
            // ?
            return false;
        }
        if (!(this.#timeRange?.length > 0))
            return false;
        const time = date.getTime();
        const [bestMatchingSnap, index, exactMatch] = JsUtils.binarySearch(time, this.#times);
        const smoothAnimation = this.#smoothAnimation;
        const matchChanged = bestMatchingSnap !== this.#activeTime;
        if (!matchChanged && (!smoothAnimation || time === bestMatchingSnap))
            return true;
        // console.log("New active date", new Date(bestMatchingSnap!));
        this.#activeDate = new Date(bestMatchingSnap);
        this.#activeTime = bestMatchingSnap;
        this.#activeIndex = index;
        const numberPreloadItems = !!direction ? this.#preloadCount : 3;
        const preloadOptions = { numberItems: numberPreloadItems, forwardOnly: direction === "forward", backwardOnly: direction === "backward" };
        if (smoothAnimation && time !== bestMatchingSnap && (index > 0 || time > bestMatchingSnap) && (index < this.#times?.length - 1 || time < bestMatchingSnap)) {
            return this.#setActiveSmooth(time, bestMatchingSnap, index, matchChanged, preloadOptions, direction, options?.skipWaitForPreload);
        }
        else {
            return this.#setActiveDiscrete(bestMatchingSnap, index, matchChanged, preloadOptions, direction, options?.skipWaitForPreload);
        }
    }
    #setActiveSmooth(time, bestMatchingSnap, index, matchChanged, preloadOptions, direction, skipWaitForPreload) {
        const isLess = time < bestMatchingSnap;
        const otherIndex = isLess ? index - 1 : index + 1;
        const [t1, t2] = [bestMatchingSnap, this.#times[otherIndex]].sort();
        const factor = (time - t1) / (t2 - t1);
        if (t1 in this.#aggregationCache && t1 in this.#aggregationCache) {
            this.#setViewInterpolated(t1, t2, factor);
            if (matchChanged) { // then preload some more
                this.#triggerPreload(index, preloadOptions).catch(e => console.log("Preload failed", e));
            }
            return true;
        }
        this.#spinner.active = true;
        const promise = Promise.all([this.#getSnapshotAggregation(t1), this.#getSnapshotAggregation(t2)]).then(() => this.#setViewInterpolated(t1, t2, factor)); // TODO handle errors
        const preloadPromise = promise.then(() => this.#triggerPreload(index, preloadOptions)).catch(e => console.log("Preload failed", e));
        const waitForPreload = !!direction && !skipWaitForPreload;
        const numberPreloadItems = !!direction ? this.#preloadCount : 3;
        const preloadWaitPromise = waitForPreload && numberPreloadItems > this.#preloadWaitCount ? this.#triggerPreload(index, { ...preloadOptions, numberItems: this.#preloadWaitCount }) : preloadPromise;
        const basePromise = waitForPreload ? preloadWaitPromise : promise;
        basePromise.finally(() => this.#spinner.active = false);
        return basePromise.then(() => true);
    }
    #setActiveDiscrete(bestMatchingSnap, index, matchChanged, preloadOptions, direction, skipWaitForPreload) {
        if (bestMatchingSnap in this.#aggregationCache) {
            this.#setView(bestMatchingSnap);
            if (matchChanged) { // then preload some more
                this.#triggerPreload(index, preloadOptions).catch(e => console.log("Preload failed", e));
            }
            return true;
        }
        this.#spinner.active = true;
        const promise = this.#getSnapshotAggregation(bestMatchingSnap);
        promise.then(() => this.#setView(bestMatchingSnap)); // TODO handle errors
        const preloadPromise = promise.then(() => this.#triggerPreload(index, preloadOptions)).catch(e => console.log("Preload failed", e));
        const waitForPreload = !!direction && !skipWaitForPreload;
        const numberPreloadItems = !!direction ? this.#preloadCount : 3;
        const preloadWaitPromise = waitForPreload && numberPreloadItems > this.#preloadWaitCount ? this.#triggerPreload(index, { ...preloadOptions, numberItems: this.#preloadWaitCount }) : preloadPromise;
        const basePromise = waitForPreload ? preloadWaitPromise : promise;
        basePromise.finally(() => this.#spinner.active = false);
        return basePromise.then(() => true);
    }
    #triggerPreload(idx0, options) {
        const snapshots = this.#times;
        if (!snapshots || snapshots.length < idx0 + 1)
            return Promise.resolve();
        const allIndices = snapshots.map((_, idx) => idx);
        const count = options?.numberItems || 2;
        const cache = this.#aggregationCache;
        const loadRequests = Object.keys(this.#activeLoadRequests).map(k => parseInt(k));
        const indicesToPreload = [];
        if (!options?.backwardOnly)
            indicesToPreload.push(...allIndices.slice(idx0 + 1, idx0 + 1 + count));
        if (!options?.forwardOnly)
            indicesToPreload.push(...allIndices.slice(Math.max(idx0 - count, 0), idx0));
        const snapshotsTimestamps = indicesToPreload.map(idx => snapshots[idx]);
        const existingRequests = indicesToPreload.filter(t => loadRequests.indexOf(t) >= 0).map(t => this.#activeLoadRequests[t]);
        const timestamps = snapshotsTimestamps.filter(t => !(t in cache) && loadRequests.indexOf(t) < 0);
        return Promise.all([...existingRequests, ...timestamps.map(t => this.#triggerPreloadSnapshot(t))]);
    }
    #getSnapshotAggregation(snap) {
        return snap in this.#aggregationCache ? Promise.resolve(this.#aggregationCache[snap]) :
            snap in this.#activeLoadRequests ? this.#activeLoadRequests[snap] : this.#triggerPreloadSnapshot(snap);
    }
    /** do not call this directly, call #getSnapshotAggregation instead */
    async #triggerPreloadSnapshot(snap) {
        for (let idx = 0; idx < 6; idx++) {
            if (Object.keys(this.#activeLoadRequests).length < 3)
                break;
            if (idx === 6)
                throw new Error("Too many requests");
            await new Promise(resolve => setTimeout(resolve, 100 * (idx + 1)));
        }
        const promise = this.state.snapshotAggregation(new Date(snap), { level: "storage" }).then(result => { this.#aggregationCache[snap] = result; return result; });
        this.#activeLoadRequests[snap] = promise;
        // remove from loading list
        promise.finally(() => delete this.#activeLoadRequests[snap]);
        return promise;
    }
    #setView(snap) {
        const material = this.#aggregationCache[snap];
        if (!material) {
            this.storageLevels.setStorageLevels(undefined);
            return;
        }
        // here we get rid of the intermediate category keys
        const flatAggregation = StorageAnimation.#toFlatAggregation(material);
        this.storageLevels.setStorageLevels(flatAggregation);
    }
    #setViewInterpolated(snap1, snap2, factor) {
        if (factor <= 0) {
            this.#setView(snap1);
            return;
        }
        else if (factor >= 1) {
            this.#setView(snap2);
            return;
        }
        const material1 = this.#aggregationCache[snap1];
        const material2 = this.#aggregationCache[snap2];
        if (!material1 || !material2) {
            this.storageLevels.setStorageLevels(undefined);
            return;
        }
        const flatAggregation1 = StorageAnimation.#toFlatAggregation(material1);
        const flatAggregation2 = StorageAnimation.#toFlatAggregation(material2);
        const allStorages = new Set([...Object.keys(flatAggregation1), ...Object.keys(flatAggregation2)]);
        const mergedAggregation = Object.fromEntries([...allStorages].map(storage => {
            const firstIsPrimary = storage in flatAggregation1;
            const primary = firstIsPrimary ? flatAggregation1 : flatAggregation2;
            const values1 = primary[storage];
            const factor1 = firstIsPrimary ? 1 - factor : factor;
            const scaledValues1 = Object.fromEntries(Object.entries(values1).map(([key, value]) => [key, value * factor1]));
            const result = scaledValues1;
            if (primary !== flatAggregation2 && storage in flatAggregation2) {
                const values2 = flatAggregation2[storage];
                Object.entries(values2).map(([key, value]) => [key, value * factor]).forEach(([key, value]) => result[key] = key in result ? result[key] + value : value);
            }
            return [storage, result];
        }));
        this.storageLevels.setStorageLevels(mergedAggregation);
    }
    /**
     * Get rid of the intermediate category keys
     * @param material
     * @returns
     */
    static #toFlatAggregation(material) {
        /*return Object.fromEntries(Object.entries(material).map(
            ([storage, aggregation]) => [storage, Object.fromEntries(Object.values(aggregation).map(entry => Object.entries(entry)).flatMap(entry => entry))]));*/
        return Object.fromEntries(Object.entries(material).map(([storage, agg]) => [storage, StorageAnimation.#aggregationToRecord(agg)]));
    }
    static #aggregationToRecord(agg) {
        const result = agg.material_weights ? { ...agg.material_weights } : {};
        result["__total__"] = agg.total_weight;
        return result;
    }
}
//# sourceMappingURL=storage-animation.js.map