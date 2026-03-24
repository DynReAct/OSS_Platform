import { PlaybackState } from "playback-controls";
import { JsUtils } from "@dynreact/client";
import { SpinnerCss } from "./spinner-css.js";
// TODO length of storage levels = length of periods + 1 ?
// TODO create timeslider
// TODO create line plot with total material indicator above timeslider
export class LongTermPlanningAnimation {
    storageLevelsComponent;
    controls;
    timelineParent;
    state;
    site;
    #storageLevels;
    #dates; // length = storages length - 1
    #timeRange;
    #times; // length = storages length
    #activeDate;
    #activeTime;
    #activeIndex;
    #spinner;
    #smoothAnimation; // TODO configurable via GUI?
    #storageCapacities;
    /**
     *
     * @param storageLevelsComponent
     * @param controls
     * @param timelineParent:
     */
    constructor(storageLevelsComponent, controls, timelineParent, state, site, options) {
        this.storageLevelsComponent = storageLevelsComponent;
        this.controls = controls;
        this.timelineParent = timelineParent;
        this.state = state;
        this.site = site;
        this.#smoothAnimation = options?.smoothAnimation !== undefined ? options?.smoothAnimation : true;
        controls.setAnimationListener({ move: state => this.#setFraction(state.fraction, state.state === PlaybackState.PLAYING ? "forward" :
                state.state === PlaybackState.PLAYING_BACKWARDS ? "backward" : undefined), step: (fraction, backwards) => this.#step(fraction, backwards) });
        const storageMain = storageLevelsComponent.shadowRoot?.querySelector(".main-container");
        const spinnerTag = SpinnerCss.register();
        this.#spinner = JsUtils.createElement(spinnerTag, { parent: storageMain, attributes: { top: "0", left: "0" } });
        this.#storageCapacities = Object.fromEntries(site.storages.filter(s => s.capacity_weight > 0).map(s => [s.name_short, s.capacity_weight]));
        // FIXME 
        // @ts-ignore
        window.dynreact = window.dynreact || {};
        // @ts-ignore
        window.dynreact.ltp_animation = this;
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
        const newDate = newIdx <= this.#dates.length - 1 ? this.#dates[newIdx][0] : this.#dates[newIdx - 1][1];
        const newFraction = (newDate.getTime() - min) / (max - min);
        const result = this.setActive(newDate);
        if (!result)
            return result;
        if (result === true)
            return newFraction;
        return result.then(() => newFraction).catch(() => false);
    }
    #setFraction(fraction, direction) {
        if (!this.#timeRange || fraction === undefined)
            return false;
        const [min, max] = this.#timeRange;
        const date = new Date(min + fraction * (max - min));
        return this.setActive(date);
    }
    setResults(storageLevels, dates) {
        this.state.abortAll(); // note: this state may be shared with other components, this is dangerous... 
        const applicable = storageLevels?.length > 0 && dates?.length > 0;
        if (!applicable) {
            this.#storageLevels = undefined;
            this.#dates = undefined;
            this.#timeRange = undefined;
            this.#times = undefined;
            this.setActive(undefined);
            this.controls.ticks = undefined;
            return;
        }
        this.#storageLevels = storageLevels;
        this.#dates = dates;
        const range = [dates[0][0].getTime(), dates[dates.length - 1][1].getTime()];
        this.#timeRange = range;
        this.#times = dates.map(d => d[0].getTime());
        this.#times.push(dates[dates.length - 1][1].getTime());
        this.setActive(dates[0][0]);
        this.controls.ticks = this.#times.map(d => { return { fraction: (d - range[0]) / (range[1] - range[0]), tick: new Date(d) }; });
    }
    get storageLevels() {
        return this.#storageLevels;
    }
    setActive(date) {
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
        if (smoothAnimation && time !== bestMatchingSnap && (index > 0 || time > bestMatchingSnap) && (index < this.#times?.length - 1 || time < bestMatchingSnap)) {
            return this.#setActiveSmooth(time, bestMatchingSnap, index);
        }
        else {
            return this.#setActiveDiscrete(index);
        }
    }
    #setActiveSmooth(time, bestMatchingSnap, index) {
        const isLess = time < bestMatchingSnap;
        const otherIndex = isLess ? index - 1 : index + 1;
        const [t1, t2] = [bestMatchingSnap, this.#times[otherIndex]].sort();
        const indices = [index, otherIndex].sort();
        const factor = (time - t1) / (t2 - t1);
        const factorFirst = 1 - factor;
        const firstLevels = this.#storageLevels[indices[0]];
        const secondLevels = this.#storageLevels[indices[1]];
        const merged = { ...firstLevels };
        for (const [storage, levels] of Object.entries(secondLevels)) {
            if (!(storage in merged)) {
                merged[storage] = levels;
            }
            else {
                const l1 = merged[storage];
                const l2 = levels;
                const totalLevel = factorFirst * l1.filling_level + factor * l2.filling_level;
                const mat1 = l1.material_levels || {};
                const mat2 = l2.material_levels || {};
                //const allMaterials = new Set([...Object.keys(mat1), ...Object.keys(mat2)]);
                const allMaterials = Object.keys(mat1).filter(m => m in mat2);
                const matResults = {};
                for (const mat of allMaterials) {
                    matResults[mat] = (mat1[mat] || 0) * factorFirst + (mat2[mat] || 0) * factor;
                }
                merged[storage] = { storage: storage, filling_level: totalLevel, material_levels: Object.keys(matResults).length > 0 ? matResults : undefined };
            }
        }
        this.#setView(merged);
        return true;
    }
    #setActiveDiscrete(index) {
        this.#setView(this.#storageLevels[index]);
        return true;
    }
    #setView(storageLevels) {
        if (!storageLevels) {
            this.storageLevelsComponent.setStorageLevels(undefined);
            return;
        }
        const capacities = this.#storageCapacities;
        storageLevels = Object.fromEntries(Object.entries(storageLevels)
            .filter(([storage, levels]) => storage in capacities)
            .map(([storage, levels]) => [storage, LongTermPlanningAnimation.#relativeLevelToAbsolute(levels, capacities[storage])]));
        const targets = Object.fromEntries(Object.entries(storageLevels).map(([storage, levels]) => [storage, levels.material_levels ? { ...levels.material_levels, __total__: levels.filling_level } : levels.filling_level]));
        this.storageLevelsComponent.setStorageLevels(targets);
    }
    static #relativeLevelToAbsolute(sl, capacity) {
        const absolute = { ...sl, filling_level: sl.filling_level * capacity };
        if (sl.material_levels) {
            absolute.material_levels = Object.fromEntries(Object.entries(sl.material_levels).map(([key, value]) => [key, value * capacity]));
        }
        return absolute;
    }
}
//# sourceMappingURL=ltp-animation.js.map