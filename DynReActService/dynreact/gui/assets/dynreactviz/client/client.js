import { toConfig } from "./config.js";
import { JsUtils } from "./jsUtils.js";
import { fixShifts, fixSnapshot } from "./clientUtils.js";
export function loadClient(config) {
    config = toConfig(config);
    if (config.serverUrl === "__dash__")
        return Promise.resolve(new DashClient(config));
    return import("./clientImpl.js").then(module => module.createImplClient(config));
}
class DashClient {
    #config;
    #globalAccess;
    constructor(config, options) {
        this.#config = Object.freeze(config);
        this.#globalAccess = options?.clientAccess || globalThis.dynreact;
    }
    config() {
        return this.#config;
    }
    site() {
        const site = this.#globalAccess.getSite();
        if (!site)
            return Promise.reject(new Error("Site not initialized yet"));
        return Promise.resolve(site);
    }
    snapshots(options) {
        const snap = this.#globalAccess.getSnapshot();
        if (!snap)
            return Promise.reject(new Error("Snapshot not initialized yet"));
        return Promise.resolve([snap.timestamp]);
    }
    snapshot(snapshot) {
        const snap = this.#globalAccess.getSnapshot();
        if (!snap)
            return Promise.reject(new Error("Snapshot not initialized yet"));
        return Promise.resolve(fixSnapshot(snap));
    }
    // TODO
    snapshotAggregation(snapshot, options) {
        throw new Error("Method not implemented.");
    }
    longTermPlanningResults(options) {
        const ltp = this.#globalAccess.getLongTermPlanningSolution();
        if (!ltp)
            return Promise.reject(new Error("LongTermPlanning not initialized yet"));
        const start = ltp.targets.period[0];
        return Promise.resolve({ [JsUtils.formatDate(start)]: [ltp.id] });
    }
    longTermPlanningSolution(date, solutionId) {
        const ltp = this.#globalAccess.getLongTermPlanningSolution();
        if (!ltp)
            return Promise.reject(new Error("LongTermPlanning not initialized yet"));
        return Promise.resolve(ltp);
    }
    shifts(options) {
        const shifts = this.#globalAccess.getShifts();
        if (!shifts)
            return Promise.reject(new Error("Shifts not initialized yet"));
        return Promise.resolve(fixShifts(shifts));
    }
    abortAll() { }
}
//# sourceMappingURL=client.js.map