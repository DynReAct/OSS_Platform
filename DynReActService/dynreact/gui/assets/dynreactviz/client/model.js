export class SiteImpl {
    _site;
    constructor(_site) {
        this._site = _site;
    }
    get site() {
        return this._site;
    }
    get_process(process, options) {
        const proc = this._site.processes.find(p => p.name_short === process);
        if (!proc && options?.do_raise)
            throw new Error("Process not found: " + process);
        return proc;
    }
    get_process_by_id(process, options) {
        const proc = this._site.processes.find(p => p.process_ids.indexOf(process) >= 0);
        if (!proc && options?.do_raise)
            throw new Error("Process not found: " + process);
        return proc;
    }
    get_equipment(equipment_id, options) {
        const plant = this._site.equipment.find(p => p.id === equipment_id);
        if (!plant && options?.do_raise)
            throw new Error("Equipment not found: " + equipment_id);
        return plant;
    }
    get_equipment_by_name(equipment, options) {
        const plant = this._site.equipment.find(p => p.name_short === equipment);
        if (!plant && options?.do_raise)
            throw new Error("Equipment not found: " + equipment);
        return plant;
    }
}
export class SnapshotImpl {
    _snapshot;
    constructor(_snapshot) {
        this._snapshot = _snapshot;
    }
    get snapshot() {
        return this._snapshot;
    }
    get_order(order_id, options) {
        const order = this._snapshot.orders.find(o => o.id === order_id);
        if (!order && options?.do_raise)
            throw new Error("Order not found: " + order_id);
        return order;
    }
    get_material(mat_id, options) {
        const mat = this._snapshot.material.find(o => o.id === mat_id);
        if (!mat && options?.do_raise)
            throw new Error("Material not found: " + mat_id);
        return mat;
    }
}
//# sourceMappingURL=model.js.map