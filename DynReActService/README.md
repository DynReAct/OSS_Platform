# DynReActSrv2

DynReAct service and GUI.

## Prerequisites

### Virtual environment

Tested with Python 3.11 and 3.12. It is strongly recommended to setup a virtual environment for the project:

```commandline
python -m venv --upgrade-deps venv
```

Activate this environment, e.g. via the IDE, or on Windows in the Anaconda Prompt: `.\venv\Scripts\activate.bat`.

### Install dependencies

This project depends on [DynReActBase](https://github.com/DynReAct/DynReActBase), [LotCreation](https://github.com/DynReAct/LotCreation) and [LotCreationRas](https://github.com/DynReAct/LotCreationRas),
although the latter should be thought of as a plugin that could be replaced by another use-case specific implementation.

1) build the dependencies; either creating a virtual environment for each of them and installing the respective dependencies, or creating a common environment (TODO test). Then execute
  
  ```commandline
  pip wheel . --no-cache-dir --disable-pip-version-check --no-deps --wheel-dir dist
  ```

2) install dependencies using the [requirements.txt](./requirements.txt) and [requirements_local.txt](./requirements_local.txt) files:

  ```commandline
  pip install -r requirements.txt -r requirements_local.txt
  ```
  or

  ```commandline
  python -m pip install -r requirements.txt -r requirements_local.txt
  ```

### Update dependencies

If any of the dependencies `dynreact_base`, `dynreact_lotcreation_core` or one of the plugins, such as `dynreact_plugin_ras` have changed, uninstall them:

```commandline
pip uninstall dynreact_base dynreact_lotcreation_core dynreact_plugin_ras
```

rebuild the dependencies, and reinstall:

```commandline
python -m pip install -r requirements.txt -r requirements_local.txt
```

### Configuration

Create a *.env* file in this folder with content:

```
SNAPSHOT_PROVIDER=ras+file:./data
```

Furthermore, create a subfolder *data* and copy the files [site.json](https://github.com/DynReAct/data/blob/main/config/site.json)
and [snapshot.csv](https://github.com/DynReAct/data/blob/main/snapshots/snapshot_N6179_5_20240919141253.csv) to this folder. 

## Run

```commandline
python -m uvicorn run:fastapi_app --reload --port 8050 --log-level debug
```

The service documentation (Swagger UI) is then available at http://localhost:8050/docs/, and the user interface at http://localhost:8050/dash/. 
The OpenAPI documentation can be downloaded from http://localhost:8050/openapi.json.

### Run with dummy authentication

For testing the operation with authentication enabled, there is a dummy auth mode. 
In order to enable it, create a file *.env* in the root folder, with content

```
AUTH_METHOD=dummy
DUMMY_USER=test
DUMMY_PW=test
```

Then start the server; you can login into the frontend at http://localhost:8050/dash/login or use the service
with basic auth and the configured user/pw.

### Run with LDAP authentication

#### Configure simple LDAP authentication

Create a *.env* file in the base folder of this project, with content (adapt domain if not using the test server)

```
AUTH_METHOD=ldap_simple
LDAP_ADDRESS=localhost:1389
LDAP_USER_EXTENSION=ou=users,dc=example,dc=org
```

#### Configure LDAP authentication with query user

Create a *.env* file in the base folder of this project, with content (adapt domain if not using the test server)

```
AUTH_METHOD=ldap
LDAP_ADDRESS=localhost:1389
LDAP_QUERY_USER=cn=user01,ou=users,dc=example,dc=org
LDAP_QUERY_PW=bitnami1
LDAP_SEARCH_BASE=ou=users,dc=example,dc=org
#LDAP_QUERY=(sAMAccountName={user})
LDAP_QUERY=(cn={user})
```


#### Set up an LDAP dev server

Run an LDAP test server with docker:

```
docker run -d --rm --name openldap -p 1389:1389 bitnami/openldap:latest
```
See https://hub.docker.com/r/bitnami/openldap/ for configuration options. In the default configuration it comes with two users preconfigured: 
* DN: *cn=user01,ou=users,dc=example,dc=org*, password: *bitnami1*
* DN: *cn=user02,ou=users,dc=example,dc=org*, password: *bitnami2*

OpenLDAP comes with a command line client too. To use it once the container is running, connect to the container:

```
docker exec -it openldap bash
```

and in the container shell, execute
``` 
ldapsearch -H ldap://localhost:1389 -x -b dc=example,dc=org objectclass=*
```



