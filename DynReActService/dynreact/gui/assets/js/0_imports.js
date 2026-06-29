(function() {
    const importmap = document.createElement("script");
    importmap.type = "importmap";
    importmap.textContent = "{" +
"    \"imports\": {\n" +
"        \"playback-controls/\": \"/dash/assets/dynreactviz/dependencies/playback-controls/\",\n" +
"        \"playback-controls\": \"/dash/assets/dynreactviz/dependencies/playback-controls/index.js\",\n" +
"        \"toolcool-color-picker\": \"/dash/assets/dynreactviz/dependencies/toolcool-color-picker.min.js\",\n" +
"        \"@dynreact/client\": \"/dash/assets/dynreactviz/client/index.js\",\n" +
"        \"@dynreact/client/\": \"/dash/assets/dynreactviz/client/\"\n" +
"    }\n" +
"}";
    /*

"        \"resilient-fetch-client/\": \"/dash/assets/dynreactviz/dependencies/resilient-fetch-client/\",\n" +
"        \"resilient-fetch-client\": \"/dash/assets/dynreactviz/dependencies/resilient-fetch-client/client.js\",\n" +
    */
    document.head.appendChild(importmap);

})();