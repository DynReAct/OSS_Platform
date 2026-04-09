import { loadClient } from "./client.js";
import { JsUtils } from "./jsUtils.js";
export async function initDynreactState(config) {
    const client = await loadClient(config);
    return new StateImpl(client);
}
class StateImpl {
    _client;
    static #MONTH = 31 * 24 * 3_600_000;
    static #YEAR = 12 * StateImpl.#MONTH;
    #sitePromise;
    constructor(_client) {
        this._client = _client;
    }
    site() {
        if (!this.#sitePromise)
            this.#sitePromise = this._client.site();
        return this.#sitePromise;
    }
    snapshot(snapshot) {
        return this._client.snapshot(snapshot);
    }
    snapshots(options) {
        const state = this;
        options = options || {};
        const isReverse = options.sort === "desc";
        const batchSize = options?.batchSize > 0 ? options.batchSize : 1000;
        let lastTimestamp = undefined;
        let closed = false;
        const source = {
            cancel(reason) {
                closed = true;
            },
            async pull(controller) {
                if (closed)
                    return;
                const newOptions = { limit: batchSize, sort: options?.sort };
                if (isReverse) {
                    newOptions.start = options?.start;
                }
                else {
                    newOptions.end = options?.end;
                }
                if (lastTimestamp) {
                    lastTimestamp.setSeconds(lastTimestamp.getSeconds() + (isReverse ? -10 : 10));
                    if (isReverse)
                        newOptions.end = JsUtils.formatDate(lastTimestamp);
                    else
                        newOptions.start = JsUtils.formatDate(lastTimestamp);
                }
                else {
                    if (isReverse)
                        newOptions.end = options?.end;
                    else
                        newOptions.start = options?.start;
                }
                let snaps = await state._client.snapshots(newOptions);
                // catch case that the last snapshot is reported again here... this probably should not happen, but does => remove from snaps
                if (snaps.length > 0 && lastTimestamp && (isReverse ? snaps[0] >= lastTimestamp : snaps[0] <= lastTimestamp))
                    snaps = snaps.slice(1);
                if (snaps.length === 0) {
                    closed = true;
                    controller.close();
                }
                lastTimestamp = new Date(snaps[snaps.length - 1]);
                controller.enqueue(snaps);
            }
        };
        return new ReadableStream(source);
    }
    snapshotAggregation(snapshot, options) {
        return this._client.snapshotAggregation(snapshot, options);
    }
    longTermPlanningResults(options) {
        const state = this;
        const hasFixedEnd = !!options?.end;
        const hasFixedStart = !!options?.start;
        const asc = options?.sort !== "desc";
        let start = options?.start;
        let end = options?.end;
        const clientLimit = options?.limit > 0 && options?.limit < 10 ? options?.limit : 10;
        const clientOptions = { ...(options || {}), limit: clientLimit };
        //let lastTimestamp: Date|undefined = undefined;
        let closed = false;
        let first = true;
        const source = {
            cancel(reason) {
                closed = true;
            },
            async pull(controller) {
                if (closed)
                    return;
                while (true) {
                    const newOptions = { ...clientOptions, start: start, end: end };
                    const results = await state._client.longTermPlanningResults(newOptions);
                    if (Object.keys(results).length > 0) {
                        controller.enqueue(results);
                        const timestamps = Object.keys(results);
                        const last = new Date(timestamps[asc ? timestamps.length - 1 : 0]);
                        if (asc) {
                            start = last;
                            if (options?.end && start >= options?.end) {
                                closed = true;
                                controller.close();
                            }
                        }
                        else {
                            end = last;
                            if (options?.start && end <= options?.start) {
                                closed = true;
                                controller.close();
                            }
                        }
                        break;
                    }
                    closed = true;
                    controller.close();
                }
            }
        };
        return new ReadableStream(source);
    }
    longTermPlanningSolution(date, solutionId) {
        return this._client.longTermPlanningSolution(date, solutionId);
    }
    abortAll() {
        this._client.abortAll();
    }
}
//# sourceMappingURL=state.js.map