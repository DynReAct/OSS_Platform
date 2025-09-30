#!/bin/bash
docker run -d --rm --name dynreact -p 8050:8050 -e STP_FRONTEND="" -e CONFIG_PROVIDER=default+file:data/site.json -e SNAPSHOT_PROVIDER=default+file:data -e COST_PROVIDER=COST_PROVIDER=sampleuc:costs -v /$(pwd)/DynReActService/data:/usr/src/app/DynReActService/data dynreact.eu/oss/dynreact-service
