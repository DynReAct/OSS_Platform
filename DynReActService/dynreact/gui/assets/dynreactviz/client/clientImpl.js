import { createFetchClient } from "resilient-fetch-client";
import { JsUtils } from "./jsUtils.js";
export async function createImplClient(config) {
    const client = await createFetchClient({
        baseUrl: config.serverUrl,
        timeoutRequest: 30_000 /* milliseconds */,
        parallelRequests: { maxParallelRequests: 4, maxQueuedRequests: 100 },
        retries: 2,
        circuitBreaker: { openAfterFailedAttempts: 5, halfOpenAfter: 15_000 /* milliseconds */ },
        timeoutTotal: 60_000
    });
    return new ClientImpl(config, client);
}
class ClientImpl {
    #config;
    #client;
    constructor(config, client) {
        this.#client = client;
        this.#config = Object.freeze(config);
    }
    config() {
        return this.#config;
    }
    site() {
        return this.#client.fetchJson("site").then(r => r.value);
    }
    snapshots(options) {
        if (options?.start instanceof Date)
            options.start = JsUtils.formatDate(options.start);
        if (options?.end instanceof Date)
            options.end = JsUtils.formatDate(options.end);
        const filtered = Object.entries(options || {}).filter(([key, value]) => value !== undefined && value !== null);
        const params = new URLSearchParams(filtered);
        return this.#client.fetchJson("snapshots?" + params.toString())
            .then(r => r.value.map(v => new Date(v)));
    }
    snapshot(snapshot) {
        if (!snapshot)
            snapshot = "now";
        else if (snapshot instanceof Date)
            snapshot = JsUtils.formatDate(snapshot);
        return this.#client.fetchJson("snapshots/" + snapshot)
            .then(r => r.value)
            .then(snap => {
            snap.timestamp = new Date(snap.timestamp);
            snap.orders.filter(o => o.due_date).forEach(o => o.due_date = new Date(o.due_date));
            return snap;
        });
    }
    snapshotAggregation(snapshot, options) {
        if (!snapshot)
            snapshot = "now";
        else if (snapshot instanceof Date)
            snapshot = JsUtils.formatDate(snapshot);
        const level = ["plant", "storage", "process"].indexOf(options?.level) >= 0 ? options?.level : "plant";
        return this.#client.fetchJson("snapshots/" + snapshot + "/aggregation?level=" + level)
            .then(r => r.value);
    }
    longTermPlanningResults(options) {
        //if (!options?.start || !options.end)
        //    throw new Error("Invalid start or end: " + options.start + " - " + options.end);
        const start = options?.start instanceof Date ? JsUtils.formatDate(options.start) : options?.start;
        const end = options?.end instanceof Date ? JsUtils.formatDate(options.end) : options?.end;
        const sort = options?.sort === "desc" ? "desc" : "asc";
        const queryParams = new URLSearchParams();
        ClientImpl.#setQueryParams(queryParams, "start", start);
        ClientImpl.#setQueryParams(queryParams, "end", end);
        ClientImpl.#setQueryParams(queryParams, "sort", sort);
        if (options?.limit > 0)
            ClientImpl.#setQueryParams(queryParams, "limit", options?.limit + "");
        let url = "longtermplanning";
        if (queryParams.size > 0)
            url = url + "?" + queryParams.toString();
        return this.#client.fetchJson(url).then(r => r.value);
    }
    async longTermPlanningSolution(date, solutionId) {
        const start = typeof date === "string" ? date : JsUtils.formatDate(date, { utc: true });
        const result0 = await this.#client.fetchJson("longtermplanning/" + start + "/" + solutionId).then(r => r.value);
        if (!result0)
            return result0;
        if (result0.storage_levels)
            result0.storage_levels.forEach(levels => Object.values(levels).filter(sl => sl.timestamp).forEach(sl => sl.timestamp = new Date(sl.timestamp)));
        result0.targets.period = result0.targets.period.map(dt => new Date(dt));
        result0.targets.sub_periods = result0.targets.sub_periods.map(([dt1, dt2]) => [new Date(dt1), new Date(dt2)]);
        Object.values(result0.targets.production_sub_targets).forEach(targets => targets.map(target => target.period = target.period.map(dt => new Date(dt))));
        return result0;
    }
    abortAll() {
        this.#client.abortAll();
    }
    static #setQueryParams(params, key, value) {
        if (!value)
            return;
        params.set(key, value);
    }
}
//# sourceMappingURL=clientImpl.js.map