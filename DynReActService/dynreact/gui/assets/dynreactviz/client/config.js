const defaultConfig = {
    serverUrl: "http://localhost:8050"
};
export function toConfig(config) {
    return { ...defaultConfig, ...(config || {}) };
}
//# sourceMappingURL=config.js.map