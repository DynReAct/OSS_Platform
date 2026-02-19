node {
    def IMAGE_NAME = "dynreact-shortterm"
    def IMAGE_TAG = "latest"
    def LOCAL_REGISTRY = "192.168.110.176:5000/"

    env.LOCAL_REGISTRY = LOCAL_REGISTRY
    env.TOPIC_CALLBACK = "DynReact-TEST-Callback"
    env.TOPIC_GEN = "DynReact-TEST-Gen"

    env.SNAPSHOT_VERSION = "2025-01-18T08:00:00Z"
    env.SCENARIO_4_5_EQUIPMENT = "9" // One Equipment, One Material
    env.SCENARIO_6_EQUIPMENT = "9" // One Equipment, Two Material
    env.SCENARIO_7_EQUIPMENTS = "9 10" // Two Equipments, One Material
    env.SCENARIO_8_EQUIPMENTS = "9 11" // Two Equipments, shared material
    env.SCENARIO_8_ORDER_ID = "1193611" 

    def runStageWithCleanup = { stageName, body ->
        stage(stageName) {
            sh '''
                echo "[PRE] Cleaning up dynreact-shortterm containers..."
                docker ps -a --filter ancestor=dynreact-shortterm -q | xargs -r docker stop
                docker ps -a --filter ancestor=dynreact-shortterm -q | xargs -r docker rm
                docker system prune -f
            '''
            body()
        }
    }

    stage('Checkout') {
        checkout scm
    }

    stage('Build Docker Image') {
        sh """
        cd ShortTermPlanning
        docker build --build-arg DOCKER_REGISTRY=${LOCAL_REGISTRY} -t ${IMAGE_NAME}:${IMAGE_TAG} .
        """
    }

    stage('Tag & Push Image') {
        sh """
        docker tag ${IMAGE_NAME}:${IMAGE_TAG} ${LOCAL_REGISTRY}${IMAGE_NAME}:${IMAGE_TAG}
        docker push ${LOCAL_REGISTRY}${IMAGE_NAME}:${IMAGE_TAG}
        """
    }

runStageWithCleanup('Run Scenario 0') {
    def vars = ['TOPIC_CALLBACK', 'TOPIC_GEN', 'SNAPSHOT_VERSION']
    def envArgs = vars.collect { varName -> "-e ${varName}=\"${env.getProperty(varName)}\"" }.join(' ')
    def kafka = env.KAFKA_BOOTSTRAP_SERVERS ?: '138.100.82.173:9092'
    sh """
        echo "[INFO] KAFKA_BOOTSTRAP_SERVERS=${kafka}"

        docker run --rm \\
          --network host \\
          -v /var/run/docker.sock:/var/run/docker.sock:rw \\
          -v ${WORKSPACE}:/repo:ro \\
          -v ${WORKSPACE}/ShortTermPlanning/dynreact/shortterm/short_term_planning.py:/app/shortterm/dynreact/shortterm/short_term_planning.py:ro \\
          -v ${WORKSPACE}/ShortTermPlanning/tests/:/app/shortterm/dynreact/tests/:rw \\
          -e PYTHONDONTWRITEBYTECODE=1 \\
          -e PYTHONPYCACHEPREFIX=/tmp/pycache \\
          -e PIP_CACHE_DIR=/tmp/pip-cache \\
          -e KAFKA_BOOTSTRAP_SERVERS="${kafka}" \\
          -e BOOTSTRAP_SERVERS="${kafka}" \\
          ${envArgs} \\
          --user \$(id -u):\$(id -g) \\
          192.168.110.176:5000/dynreact-shortterm:latest \\
          bash -lc 'set -euo pipefail
                source .venv/bin/activate
                COMP=ShortTermPlanning

                python -m venv /tmp/venv
                . /tmp/venv/bin/activate

                python -m pip install -U pip setuptools wheel
                python -m pip install -r "/repo/DynReActBase/requirements.txt"
                python -m pip install -r "/repo/\$COMP/requirements.txt"
                [ -f "/repo/\$COMP/requirements_local.txt" ] && python -m pip install -r "/repo/\$COMP/requirements_local.txt" || true
                [ -f "/repo/\$COMP/requirements-dev.txt" ] && python -m pip install -r "/repo/\$COMP/requirements-dev.txt" || true
                command -v pytest >/dev/null 2>&1 || python -m pip install pytest

                cd /app/shortterm/dynreact/tests/integration_test

                # Debug: variables de entorno (OJO: comillas correctas)
                python -c '"'"'import os; print("KAFKA_BOOTSTRAP_SERVERS=", os.getenv("KAFKA_BOOTSTRAP_SERVERS")); print("BOOTSTRAP_SERVERS=", os.getenv("BOOTSTRAP_SERVERS"))'"'"'

                # Debug: conectividad TCP al broker
                python - <<'"'"'PY'"'"'
                    import os, socket
                    bs = os.getenv("KAFKA_BOOTSTRAP_SERVERS") or os.getenv("BOOTSTRAP_SERVERS","")
                    print("bootstrap:", bs)
                    host, port = bs.split(":")
                    socket.create_connection((host, int(port)), timeout=3).close()
                    print("TCP connectivity OK")
PY

                pytest -s -p no:cacheprovider test_auction.py::test_scenario_00
      '
    """
    }


    runStageWithCleanup('Run Scenario 1') {
        def vars = ['TOPIC_CALLBACK', 'TOPIC_GEN', 'SNAPSHOT_VERSION']
        def envArgs = vars.collect { varName -> "-e ${varName}=\"${env.getProperty(varName)}\"" }.join(' ')
        sh """
        # Run container to execute tests
        docker run --rm \\
          -v /var/run/docker.sock:/var/run/docker.sock:rw \\
          -v "$WORKSPACE:/repo:ro" \\
          -v "$WORKSPACE/ShortTermPlanning/pyproject.toml:/app/pyproject.toml:ro" \\
          -v "$WORKSPACE/ShortTermPlanning/dynreact/shortterm/short_term_planning.py:/app/shortterm/dynreact/shortterm/short_term_planning.py:ro" \\
          -v "$WORKSPACE/ShortTermPlanning/tests/:/app/shortterm/dynreact/tests/:rw" \\
          -v "/var/log/dynreact-logs:/var/log/dynreact-logs:rw,rshared" \\
          -e PYTHONDONTWRITEBYTECODE=1 \\
          -e PYTHONPYCACHEPREFIX=/tmp/pycache \\
          ${envArgs} \\
          --user "\$(id -u):\$(id -g)" \\
          "${LOCAL_REGISTRY}${IMAGE_NAME}:${IMAGE_TAG}" \\
          bash -c "source .venv/bin/activate && \\
                   COMP='ShortTermPlanning' && \\
                   pip install -r /repo/\$COMP/requirements.txt && \\
                   [ -f /repo/\$COMP/requirements_local.txt ] && pip install -r /repo/\$COMP/requirements_local.txt || true && \\
                   [ -f /repo/\$COMP/requirements-dev.txt ] && pip install -r /repo/\$COMP/requirements-dev.txt || true && \\
                   cd /app/shortterm/dynreact/tests/integration_test && \\
                   pytest -s  -p no:cacheprovider test_auction.py::test_scenario_01"
        """
    }

    runStageWithCleanup('Run Scenario 2') {
        def vars = ['TOPIC_CALLBACK', 'TOPIC_GEN', 'SNAPSHOT_VERSION']
        def envArgs = vars.collect { varName -> "-e ${varName}=\"${env.getProperty(varName)}\"" }.join(' ')
        sh """
        # Run container to execute tests
        docker run --rm \\
          -v /var/run/docker.sock:/var/run/docker.sock:rw \\
          -v "$WORKSPACE:/repo:ro" \\
          -v "$WORKSPACE/ShortTermPlanning/pyproject.toml:/app/pyproject.toml:ro" \\
          -v "$WORKSPACE/ShortTermPlanning/dynreact/shortterm/short_term_planning.py:/app/shortterm/dynreact/shortterm/short_term_planning.py:ro" \\
          -v "$WORKSPACE/ShortTermPlanning/tests/:/app/shortterm/dynreact/tests/:rw" \\
          -e PYTHONDONTWRITEBYTECODE=1 \\
          -e PYTHONPYCACHEPREFIX=/tmp/pycache \\
          ${envArgs} \\
          --user "\$(id -u):\$(id -g)" \\
          "${LOCAL_REGISTRY}${IMAGE_NAME}:${IMAGE_TAG}" \\
          bash -c "source .venv/bin/activate && \\
                   COMP='ShortTermPlanning' && \\
                   pip install -r /repo/\$COMP/requirements.txt && \\
                   [ -f /repo/\$COMP/requirements_local.txt ] && pip install -r /repo/\$COMP/requirements_local.txt || true && \\
                   [ -f /repo/\$COMP/requirements-dev.txt ] && pip install -r /repo/\$COMP/requirements-dev.txt || true && \\
                   cd /app/shortterm/dynreact/tests/integration_test && \\
                   pytest -s -p no:cacheprovider test_auction.py::test_scenario_02"
        """
    }

    runStageWithCleanup('Run Scenario 3') {
        def vars = ['TOPIC_CALLBACK', 'TOPIC_GEN', 'SNAPSHOT_VERSION']
        def envArgs = vars.collect { varName -> "-e ${varName}=\"${env.getProperty(varName)}\"" }.join(' ')
        sh """
        # Run container to execute tests
        docker run --rm \\
          -v /var/run/docker.sock:/var/run/docker.sock:rw \\
          -v "$WORKSPACE:/repo:ro" \\
          -v "$WORKSPACE/ShortTermPlanning/pyproject.toml:/app/pyproject.toml:ro" \\
          -v "$WORKSPACE/ShortTermPlanning/dynreact/shortterm/short_term_planning.py:/app/shortterm/dynreact/shortterm/short_term_planning.py:ro" \\
          -v "$WORKSPACE/ShortTermPlanning/tests/:/app/shortterm/dynreact/tests/:rw" \\
          -e PYTHONDONTWRITEBYTECODE=1 \\
          -e PYTHONPYCACHEPREFIX=/tmp/pycache \\
          ${envArgs} \\
          --user "\$(id -u):\$(id -g)" \\
          "${LOCAL_REGISTRY}${IMAGE_NAME}:${IMAGE_TAG}" \\
          bash -c "source .venv/bin/activate && \\
                   COMP='ShortTermPlanning' && \\
                   pip install -r /repo/\$COMP/requirements.txt && \\
                   [ -f /repo/\$COMP/requirements_local.txt ] && pip install -r /repo/\$COMP/requirements_local.txt || true && \\
                   [ -f /repo/\$COMP/requirements-dev.txt ] && pip install -r /repo/\$COMP/requirements-dev.txt || true && \\
                   cd /app/shortterm/dynreact/tests/integration_test && \\
                   pytest -s -p no:cacheprovider test_auction.py::test_scenario_03"
        """
    }

    runStageWithCleanup('Run Scenario 4') {
        def vars = ['TOPIC_CALLBACK', 'TOPIC_GEN', 'SNAPSHOT_VERSION', 'SCENARIO_4_5_EQUIPMENT']
        def envArgs = vars.collect { varName -> "-e ${varName}=\"${env.getProperty(varName)}\"" }.join(' ')
        sh """
        # Run container to execute tests
        docker run --rm \\
          -v /var/run/docker.sock:/var/run/docker.sock:rw \\
          -v "$WORKSPACE:/repo:ro" \\
          -v "$WORKSPACE/ShortTermPlanning/pyproject.toml:/app/pyproject.toml:ro" \\
          -v "$WORKSPACE/ShortTermPlanning/dynreact/shortterm/short_term_planning.py:/app/shortterm/dynreact/shortterm/short_term_planning.py:ro" \\
          -v "$WORKSPACE/ShortTermPlanning/tests/:/app/shortterm/dynreact/tests/:rw" \\
          -e PYTHONDONTWRITEBYTECODE=1 \\
          -e PYTHONPYCACHEPREFIX=/tmp/pycache \\
          ${envArgs} \\
          --user "\$(id -u):\$(id -g)" \\
          "${LOCAL_REGISTRY}${IMAGE_NAME}:${IMAGE_TAG}" \\
          bash -c "source .venv/bin/activate && \\
                   COMP='ShortTermPlanning' && \\
                   pip install -r /repo/\$COMP/requirements.txt && \\
                   [ -f /repo/\$COMP/requirements_local.txt ] && pip install -r /repo/\$COMP/requirements_local.txt || true && \\
                   [ -f /repo/\$COMP/requirements-dev.txt ] && pip install -r /repo/\$COMP/requirements-dev.txt || true && \\
                   cd /app/shortterm/dynreact/tests/integration_test && \\
                   pytest -s -p no:cacheprovider test_auction.py::test_scenario_04"
        """
    }

    stage('Replace BASE agents') {
        sh """
        # Run container to execute tests
        docker run --rm \\
          -v /var/run/docker.sock:/var/run/docker.sock:rw \\
          -v "$WORKSPACE:/repo:ro" \\
          -v "$WORKSPACE/ShortTermPlanning/dynreact/shortterm/replace_base.py:/app/shortterm/__main__.py:ro" \\
          -v "$WORKSPACE/ShortTermPlanning/dynreact/shortterm/short_term_planning.py:/app/shortterm/dynreact/shortterm/short_term_planning.py:ro" \\
          -e PYTHONDONTWRITEBYTECODE=1 \\
          -e PYTHONPYCACHEPREFIX=/tmp/pycache \\
          --user "\$(id -u):\$(id -g)" \\
          "${LOCAL_REGISTRY}${IMAGE_NAME}:${IMAGE_TAG}" \\
           python -m shortterm -v 3 -g 111
        """
    }

    stage('Run Scenario 5') {
        def vars = ['SNAPSHOT_VERSION', 'SCENARIO_4_5_EQUIPMENT', 'LOCAL_REGISTRY']
        def envArgs = vars.collect { varName -> "-e ${varName}=\"${env.getProperty(varName)}\"" }.join(' ')
        sh """
        # Run container to execute tests
        docker run --rm \\
          -v /var/run/docker.sock:/var/run/docker.sock:rw \\
          -v "$WORKSPACE:/repo:ro" \\
          -v "$WORKSPACE/ShortTermPlanning/pyproject.toml:/app/pyproject.toml:ro" \\
          -v "$WORKSPACE/ShortTermPlanning/dynreact/shortterm/short_term_planning.py:/app/shortterm/dynreact/shortterm/short_term_planning.py:ro" \\
          -v "$WORKSPACE/ShortTermPlanning/tests/:/app/shortterm/dynreact/tests/:rw" \\
          -e PYTHONDONTWRITEBYTECODE=1 \\
          -e PYTHONPYCACHEPREFIX=/tmp/pycache \\
          ${envArgs} \\
          --user "\$(id -u):\$(id -g)" \\
          "${LOCAL_REGISTRY}${IMAGE_NAME}:${IMAGE_TAG}" \\
          bash -c "source .venv/bin/activate && \\
                   COMP='ShortTermPlanning' && \\
                   pip install -r /repo/\$COMP/requirements.txt && \\
                   [ -f /repo/\$COMP/requirements_local.txt ] && pip install -r /repo/\$COMP/requirements_local.txt || true && \\
                   [ -f /repo/\$COMP/requirements-dev.txt ] && pip install -r /repo/\$COMP/requirements-dev.txt || true && \\
                   cd /app/shortterm/dynreact/tests/integration_test && \\
                   pytest -s -p no:cacheprovider test_auction.py::test_scenario_05"
        """
    }

    stage('Run Scenario 6') {
        def vars = ['SNAPSHOT_VERSION', 'SCENARIO_6_EQUIPMENT', 'LOCAL_REGISTRY']
        def envArgs = vars.collect { varName -> "-e ${varName}=\"${env.getProperty(varName)}\"" }.join(' ')
        sh """
        # Run container to execute tests
        docker run --rm \\
          -v /var/run/docker.sock:/var/run/docker.sock:rw \\
          -v "$WORKSPACE:/repo:ro" \\
          -v "$WORKSPACE/ShortTermPlanning/pyproject.toml:/app/pyproject.toml:ro" \\
          -v "$WORKSPACE/ShortTermPlanning/dynreact/shortterm/short_term_planning.py:/app/shortterm/dynreact/shortterm/short_term_planning.py:ro" \\
          -v "$WORKSPACE/ShortTermPlanning/tests/:/app/shortterm/dynreact/tests/:rw" \\
          -e PYTHONDONTWRITEBYTECODE=1 \\
          -e PYTHONPYCACHEPREFIX=/tmp/pycache \\
          ${envArgs} \\
          --user "\$(id -u):\$(id -g)" \\
          "${LOCAL_REGISTRY}${IMAGE_NAME}:${IMAGE_TAG}" \\
          bash -c "source .venv/bin/activate && \\
                   COMP='ShortTermPlanning' && \\
                   pip install -r /repo/\$COMP/requirements.txt && \\
                   [ -f /repo/\$COMP/requirements_local.txt ] && pip install -r /repo/\$COMP/requirements_local.txt || true && \\
                   [ -f /repo/\$COMP/requirements-dev.txt ] && pip install -r /repo/\$COMP/requirements-dev.txt || true && \\
                   cd /app/shortterm/dynreact/tests/integration_test && \\
                   pytest -s -p no:cacheprovider test_auction.py::test_scenario_06"
        """
    }

    stage('Run Scenario 7') {
        def vars = ['SNAPSHOT_VERSION', 'SCENARIO_7_EQUIPMENTS', 'LOCAL_REGISTRY']
        def envArgs = vars.collect { varName -> "-e ${varName}=\"${env.getProperty(varName)}\"" }.join(' ')
        sh """
        # Run container to execute tests
        docker run --rm \\
          -v /var/run/docker.sock:/var/run/docker.sock:rw \\
          -v "$WORKSPACE:/repo:ro" \\
          -v "$WORKSPACE/ShortTermPlanning/pyproject.toml:/app/pyproject.toml:ro" \\
          -v "$WORKSPACE/ShortTermPlanning/dynreact/shortterm/short_term_planning.py:/app/shortterm/dynreact/shortterm/short_term_planning.py:ro" \\
          -v "$WORKSPACE/ShortTermPlanning/tests/:/app/shortterm/dynreact/tests/:rw" \\
          -e PYTHONDONTWRITEBYTECODE=1 \\
          -e PYTHONPYCACHEPREFIX=/tmp/pycache \\
          ${envArgs} \\
          --user "\$(id -u):\$(id -g)" \\
          "${LOCAL_REGISTRY}${IMAGE_NAME}:${IMAGE_TAG}" \\
          bash -c "source .venv/bin/activate && \\
                   COMP='ShortTermPlanning' && \\
                   pip install -r /repo/\$COMP/requirements.txt && \\
                   [ -f /repo/\$COMP/requirements_local.txt ] && pip install -r /repo/\$COMP/requirements_local.txt || true && \\
                   [ -f /repo/\$COMP/requirements-dev.txt ] && pip install -r /repo/\$COMP/requirements-dev.txt || true && \\
                   cd /app/shortterm/dynreact/tests/integration_test && \\
                   pytest -s -p no:cacheprovider test_auction.py::test_scenario_07"
        """
    }

    stage('Run Scenario 8') {
        def vars = ['SNAPSHOT_VERSION', 'SCENARIO_8_EQUIPMENTS', 'SCENARIO_8_ORDER_ID', 'LOCAL_REGISTRY']
        def envArgs = vars.collect { varName -> "-e ${varName}=\"${env.getProperty(varName)}\"" }.join(' ')
        sh """
        # Run container to execute tests
        docker run --rm \\
          -v /var/run/docker.sock:/var/run/docker.sock:rw \\
          -v "$WORKSPACE:/repo:ro" \\
          -v "$WORKSPACE/ShortTermPlanning/pyproject.toml:/app/pyproject.toml:ro" \\
          -v "$WORKSPACE/ShortTermPlanning/dynreact/shortterm/short_term_planning.py:/app/shortterm/dynreact/shortterm/short_term_planning.py:ro" \\
          -v "$WORKSPACE/ShortTermPlanning/tests/:/app/shortterm/dynreact/tests/:rw" \\
          -e PYTHONDONTWRITEBYTECODE=1 \\
          -e PYTHONPYCACHEPREFIX=/tmp/pycache \\
          ${envArgs} \\
          --user "\$(id -u):\$(id -g)" \\
          "${LOCAL_REGISTRY}${IMAGE_NAME}:${IMAGE_TAG}" \\
          bash -c "source .venv/bin/activate && \\
                   COMP='ShortTermPlanning' && \\
                   pip install -r /repo/\$COMP/requirements.txt && \\
                   [ -f /repo/\$COMP/requirements_local.txt ] && pip install -r /repo/\$COMP/requirements_local.txt || true && \\
                   [ -f /repo/\$COMP/requirements-dev.txt ] && pip install -r /repo/\$COMP/requirements-dev.txt || true && \\
                   cd /app/shortterm/dynreact/tests/integration_test && \\
                   pytest -s -p no:cacheprovider test_auction.py::test_scenario_08"
        """
    }
}
