import { JsUtils } from "./jsUtils.js";
export function fixSnapshot(snap, options) {
    // copy only what is necessary for not changing the original
    const snap2 = options?.skipCopy ? snap :
        { ...snap, orders: snap.orders.map(o => { return { ...o }; }), lots: Object.fromEntries(Object.entries(snap.lots).map(([eqId, eqLots]) => [eqId, eqLots.map(lt => { return { ...lt }; })])) };
    snap2.timestamp = new Date(snap2.timestamp);
    snap2.orders.filter(o => o.due_date).forEach(o => o.due_date = new Date(o.due_date));
    Object.values(snap2.lots).forEach(lots => lots.forEach(lot => {
        lot.start_time = lot.start_time ? new Date(lot.start_time) : undefined;
        lot.end_time = lot.end_time ? new Date(lot.end_time) : undefined;
    }));
    return snap2;
}
function _fixShifts(shifts) {
    const shifts2 = shifts.map(shift => { return { ...shift, period: shift.period.map(p => new Date(p)), worktime: JsUtils.toMillis(shift.worktime) }; });
    Object.freeze(shifts2);
    return shifts2;
}
export function fixShifts(shifts) {
    return Object.fromEntries(Object.entries(shifts).map(([eq, eqShifts]) => [eq, _fixShifts(eqShifts)]));
}
//# sourceMappingURL=clientUtils.js.map