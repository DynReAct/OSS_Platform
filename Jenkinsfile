node {
    def IMAGE_NAME = "dynreact-shortterm"
    def IMAGE_TAG = "latest"
    def LOCAL_REGISTRY = "192.168.110.176:5000/"

    env.LOCAL_REGISTRY = LOCAL_REGISTRY
    env.TOPIC_CALLBACK = "DynReact-TEST-Callback"
    env.TOPIC_GEN = "DynReact-TEST-Gen"
    env.CONTAINER_NAME_PREFIX = "JENKINS_TEST"

    env.SNAPSHOT_VERSION = "2025-01-18T08:00:00Z"
    env.SCENARIO_4_5_EQUIPMENT = "7" // One Equipment, One Material
    env.SCENARIO_6_EQUIPMENT = "7" // One Equipment, Two Material
    env.SCENARIO_7_EQUIPMENTS = "6 7" // Two Equipments, One Material
    env.SCENARIO_8_EQUIPMENTS = "6 7" // Two Equipments, shared material
    env.SCENARIO_8_ORDER_ID = "1193611" 

     // Wrap all secret text credentials at once
    withCredentials([
        string(credentialsId: 'LOCAL_REGISTRY', variable: 'REGISTRY'),
        string(credentialsId: 'KAFKA_IP', variable: 'KAFKA_IP_SECRET'),
        string(credentialsId: 'LOG_FILE_PATH', variable: 'LOG_FILE_PATH_SECRET'),
        string(credentialsId: 'REST_URL', variable: 'REST_URL_SECRET')
    ]) {

        env.KAFKA_IP = KAFKA_IP_SECRET
        env.LOG_FILE_PATH = LOG_FILE_PATH_SECRET
        env.REST_URL = REST_URL_SECRET
        env.LOCAL_REGISTRY = REGISTRY


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
        docker build \\
            --build-arg DOCKER_REGISTRY="$REGISTRY" \\
            --build-arg BUILD_DATE="\$(date -u +'%Y-%m-%dT%H:%M:%SZ')" \\
            --build-arg JENKINS_BUILD_ID="$BUILD_ID" \\
            -t ${IMAGE_NAME}:${IMAGE_TAG} .
    """
    }

    stage('Tag & Push Image') {
        sh """
        docker tag ${IMAGE_NAME}:${IMAGE_TAG} ${LOCAL_REGISTRY}${IMAGE_NAME}:${IMAGE_TAG}
        docker push ${LOCAL_REGISTRY}${IMAGE_NAME}:${IMAGE_TAG}
        """
    }

runStageWithCleanup('Run Scenario 0') {
    def vars = ['KAFKA_IP', 'LOG_FILE_PATH', 'REST_URL', 'TOPIC_CALLBACK', 'TOPIC_GEN', 'SNAPSHOT_VERSION', 'CONTAINER_NAME_PREFIX']
    def envArgs = vars.collect { varName -> "-e ${varName}=\"${env.getProperty(varName)}\"" }.join(' ')

    sh """
        docker run --rm \\
          --network host \\
          -v /var/run/docker.sock:/var/run/docker.sock:rw \\
          -v ${WORKSPACE}:/repo:ro \\
          -v ${WORKSPACE}/ShortTermPlanning/dynreact/shortterm/short_term_planning.py:/app/shortterm/dynreact/shortterm/short_term_planning.py:ro \\
          -v ${WORKSPACE}/ShortTermPlanning/tests/:/app/shortterm/dynreact/tests/:rw \\
          -e PYTHONDONTWRITEBYTECODE=1 \\
          -e PYTHONPYCACHEPREFIX=/tmp/pycache \\
          -e PIP_CACHE_DIR=/tmp/pip-cache \\
          --user "0:0" \\
          ${envArgs} \\
          192.168.110.176:5000/dynreact-shortterm:latest \\
          bash -lc 'set -euo pipefail
                source .venv/bin/activate
                COMP=DynReActService

                python -m venv /tmp/venv
                . /tmp/venv/bin/activate

                python -m pip install -U pip setuptools wheel
                python -m pip install -r "/repo/DynReActBase/requirements.txt"
                python -m pip install -r "/repo/\$COMP/requirements.txt"
                [ -f "/repo/\$COMP/requirements_local.txt" ] && python -m pip install -r "/repo/\$COMP/requirements_local.txt" || true
                [ -f "/repo/\$COMP/requirements-dev.txt" ] && python -m pip install -r "/repo/\$COMP/requirements-dev.txt" || true
                python -m pip install -r "/repo/ShortTermPlanning/requirements.txt"

                command -v pytest >/dev/null 2>&1 || python -m pip install pytest
                cd /app/shortterm/dynreact/tests/integration_test
                pytest -s -p no:cacheprovider test_auction.py::test_scenario_00
      '
    """
    }


    runStageWithCleanup('Run Scenario 1') {
        def vars = ['KAFKA_IP', 'LOG_FILE_PATH', 'REST_URL', 'TOPIC_CALLBACK', 'TOPIC_GEN', 'SNAPSHOT_VERSION', 'CONTAINER_NAME_PREFIX']
        def envArgs = vars.collect { varName -> "-e ${varName}=\"${env.getProperty(varName)}\"" }.join(' ')
        sh """
        # Run container to execute tests
        docker run --rm \\
          --network host \\
          -v /var/run/docker.sock:/var/run/docker.sock:rw \\
          -v "$WORKSPACE:/repo:ro" \\
          -v "$WORKSPACE/ShortTermPlanning/dynreact/shortterm/short_term_planning.py:/app/shortterm/dynreact/shortterm/short_term_planning.py:ro" \\
          -v "$WORKSPACE/ShortTermPlanning/tests/:/app/shortterm/dynreact/tests/:rw" \\
          -v "/var/log/dynreact-logs:/var/log/dynreact-logs:rw,rshared" \\
          -e PYTHONDONTWRITEBYTECODE=1 \\
          -e PYTHONPYCACHEPREFIX=/tmp/pycache \\
          --user "0:0" \\
          ${envArgs} \\
          "${LOCAL_REGISTRY}${IMAGE_NAME}:${IMAGE_TAG}" \\
          bash -lc 'set -euo pipefail
                   python -m venv /tmp/venv
                   source .venv/bin/activate 
                   COMP='ShortTermPlanning' 
                   pip install -r /repo/\$COMP/requirements.txt
                   [ -f /repo/\$COMP/requirements_local.txt ] && pip install -r /repo/\$COMP/requirements_local.txt || true 
                   [ -f /repo/\$COMP/requirements-dev.txt ] && pip install -r /repo/\$COMP/requirements-dev.txt || true 

                   command -v pytest >/dev/null 2>&1 || python -m pip install pytest
                   cd /app/shortterm/dynreact/tests/integration_test 
                   pytest -s  -p no:cacheprovider test_auction.py::test_scenario_01
         '
        """
    }

    runStageWithCleanup('Run Scenario 2') {
        def vars = ['KAFKA_IP', 'LOG_FILE_PATH', 'REST_URL', 'TOPIC_CALLBACK', 'TOPIC_GEN', 'SNAPSHOT_VERSION', 'CONTAINER_NAME_PREFIX']
        def envArgs = vars.collect { varName -> "-e ${varName}=\"${env.getProperty(varName)}\"" }.join(' ')
        sh """
        # Run container to execute tests
        docker run --rm \\
          --network host \\
          -v /var/run/docker.sock:/var/run/docker.sock:rw \\
          -v "$WORKSPACE:/repo:ro" \\
          -v "$WORKSPACE/ShortTermPlanning/dynreact/shortterm/short_term_planning.py:/app/shortterm/dynreact/shortterm/short_term_planning.py:ro" \\
          -v "$WORKSPACE/ShortTermPlanning/tests/:/app/shortterm/dynreact/tests/:rw" \\
          -e PYTHONDONTWRITEBYTECODE=1 \\
          -e PYTHONPYCACHEPREFIX=/tmp/pycache \\
          --user "0:0" \\
          ${envArgs} \\
          "${LOCAL_REGISTRY}${IMAGE_NAME}:${IMAGE_TAG}" \\
          bash -lc 'set -euo pipefail
                   python -m venv /tmp/venv
                   source .venv/bin/activate 
                   COMP='ShortTermPlanning' 
                   pip install -r /repo/\$COMP/requirements.txt 
                   [ -f /repo/\$COMP/requirements_local.txt ] && pip install -r /repo/\$COMP/requirements_local.txt || true 
                   [ -f /repo/\$COMP/requirements-dev.txt ] && pip install -r /repo/\$COMP/requirements-dev.txt || true 

                   command -v pytest >/dev/null 2>&1 || python -m pip install pytest
                   cd /app/shortterm/dynreact/tests/integration_test 
                   pytest -s -p no:cacheprovider test_auction.py::test_scenario_02
         '
        """
    }

    runStageWithCleanup('Run Scenario 3') {
        def vars = ['KAFKA_IP', 'LOG_FILE_PATH', 'REST_URL', 'TOPIC_CALLBACK', 'TOPIC_GEN', 'SNAPSHOT_VERSION', 'CONTAINER_NAME_PREFIX']
        def envArgs = vars.collect { varName -> "-e ${varName}=\"${env.getProperty(varName)}\"" }.join(' ')
        sh """
        # Run container to execute tests
        docker run --rm \\
          --network host \\
          -v /var/run/docker.sock:/var/run/docker.sock:rw \\
          -v "$WORKSPACE:/repo:ro" \\
          -v "$WORKSPACE/ShortTermPlanning/pyproject.toml:/app/pyproject.toml:ro" \\
          -v "$WORKSPACE/ShortTermPlanning/dynreact/shortterm/short_term_planning.py:/app/shortterm/dynreact/shortterm/short_term_planning.py:ro" \\
          -v "$WORKSPACE/ShortTermPlanning/tests/:/app/shortterm/dynreact/tests/:rw" \\
          -e PYTHONDONTWRITEBYTECODE=1 \\
          -e PYTHONPYCACHEPREFIX=/tmp/pycache \\
          ${envArgs} \\
          --user "0:0" \\
          "${LOCAL_REGISTRY}${IMAGE_NAME}:${IMAGE_TAG}" \\
          bash -lc 'set -euo pipefail
                   python -m venv /tmp/venv
                   source .venv/bin/activate 
                   COMP='ShortTermPlanning' 
                   pip install -r /repo/\$COMP/requirements.txt 
                   [ -f /repo/\$COMP/requirements_local.txt ] && pip install -r /repo/\$COMP/requirements_local.txt || true 
                   [ -f /repo/\$COMP/requirements-dev.txt ] && pip install -r /repo/\$COMP/requirements-dev.txt || true 

                   command -v pytest >/dev/null 2>&1 || python -m pip install pytest
                   cd /app/shortterm/dynreact/tests/integration_test 
                   pytest -s -p no:cacheprovider test_auction.py::test_scenario_03
         '
        """
    }

    runStageWithCleanup('Run Scenario 4') {
        def vars = ['KAFKA_IP', 'LOG_FILE_PATH', 'REST_URL', 'TOPIC_CALLBACK', 'TOPIC_GEN', 'SNAPSHOT_VERSION', 'CONTAINER_NAME_PREFIX']
        def envArgs = vars.collect { varName -> "-e ${varName}=\"${env.getProperty(varName)}\"" }.join(' ')
        sh """
        # Run container to execute tests
        docker run --rm \\
          --network host \\
          -v /var/run/docker.sock:/var/run/docker.sock:rw \\
          -v "$WORKSPACE:/repo:ro" \\
          -v "$WORKSPACE/ShortTermPlanning/pyproject.toml:/app/pyproject.toml:ro" \\
          -v "$WORKSPACE/ShortTermPlanning/dynreact/shortterm/short_term_planning.py:/app/shortterm/dynreact/shortterm/short_term_planning.py:ro" \\
          -v "$WORKSPACE/ShortTermPlanning/tests/:/app/shortterm/dynreact/tests/:rw" \\
          -e PYTHONDONTWRITEBYTECODE=1 \\
          -e PYTHONPYCACHEPREFIX=/tmp/pycache \\
          ${envArgs} \\
          --user "0:0" \\
          "${LOCAL_REGISTRY}${IMAGE_NAME}:${IMAGE_TAG}" \\
          bash -lc 'set -euo pipefail
                   python -m venv /tmp/venv
                   source .venv/bin/activate 
                   COMP='ShortTermPlanning' 
                   pip install -r /repo/\$COMP/requirements.txt 
                   [ -f /repo/\$COMP/requirements_local.txt ] && pip install -r /repo/\$COMP/requirements_local.txt || true 
                   [ -f /repo/\$COMP/requirements-dev.txt ] && pip install -r /repo/\$COMP/requirements-dev.txt || true 

                   command -v pytest >/dev/null 2>&1 || python -m pip install pytest
                   cd /app/shortterm/dynreact/tests/integration_test 
                   pytest -s -p no:cacheprovider test_auction.py::test_scenario_04
         '
        """
    }

    stage('Replace BASE agents') {
        sh """
        # Run container to execute tests
        docker run --rm \\
          --network host \\
          -v /var/run/docker.sock:/var/run/docker.sock:rw \\
          -v "$WORKSPACE:/repo:ro" \\
          -v "$WORKSPACE/ShortTermPlanning/dynreact/shortterm/replace_base.py:/app/shortterm/__main__.py:ro" \\
          -v "$WORKSPACE/ShortTermPlanning/dynreact/shortterm/short_term_planning.py:/app/shortterm/dynreact/shortterm/short_term_planning.py:ro" \\
          -e PYTHONDONTWRITEBYTECODE=1 \\
          -e PYTHONPYCACHEPREFIX=/tmp/pycache \\
          --user "0:0" \\
          "${LOCAL_REGISTRY}${IMAGE_NAME}:${IMAGE_TAG}" \\
           python -m shortterm -v 3 -g 111
        """
    }

    stage('Run Scenario 5') {
        def vars = ['KAFKA_IP', 'LOG_FILE_PATH', 'REST_URL', 'TOPIC_CALLBACK', 'TOPIC_GEN', 'SNAPSHOT_VERSION', 'CONTAINER_NAME_PREFIX']
        def envArgs = vars.collect { varName -> "-e ${varName}=\"${env.getProperty(varName)}\"" }.join(' ')
        sh """
        # Run container to execute tests
        docker run --rm \\
          --network host \\
          -v /var/run/docker.sock:/var/run/docker.sock:rw \\
          -v "$WORKSPACE:/repo:ro" \\
          -v "$WORKSPACE/ShortTermPlanning/pyproject.toml:/app/pyproject.toml:ro" \\
          -v "$WORKSPACE/ShortTermPlanning/dynreact/shortterm/short_term_planning.py:/app/shortterm/dynreact/shortterm/short_term_planning.py:ro" \\
          -v "$WORKSPACE/ShortTermPlanning/tests/:/app/shortterm/dynreact/tests/:rw" \\
          -e PYTHONDONTWRITEBYTECODE=1 \\
          -e PYTHONPYCACHEPREFIX=/tmp/pycache \\
          ${envArgs} \\
          --user "0:0" \\
          "${LOCAL_REGISTRY}${IMAGE_NAME}:${IMAGE_TAG}" \\
          bash -lc 'set -euo pipefail
                   source .venv/bin/activate 
                   COMP='ShortTermPlanning' 
                   pip install -r /repo/\$COMP/requirements.txt 
                   [ -f /repo/\$COMP/requirements_local.txt ] && pip install -r /repo/\$COMP/requirements_local.txt || true 
                   [ -f /repo/\$COMP/requirements-dev.txt ] && pip install -r /repo/\$COMP/requirements-dev.txt || true

                   command -v pytest >/dev/null 2>&1 || python -m pip install pytest
                   cd /app/shortterm/dynreact/tests/integration_test 
                   pytest -s -p no:cacheprovider test_auction.py::test_scenario_05
         '
        """
    }

    stage('Run Scenario 6') {
        def vars = ['KAFKA_IP', 'LOG_FILE_PATH', 'REST_URL', 'TOPIC_CALLBACK', 'TOPIC_GEN', 'SNAPSHOT_VERSION', 'CONTAINER_NAME_PREFIX']
        def envArgs = vars.collect { varName -> "-e ${varName}=\"${env.getProperty(varName)}\"" }.join(' ')
        sh """
        # Run container to execute tests
        docker run --rm \\
          --network host \\
          -v /var/run/docker.sock:/var/run/docker.sock:rw \\
          -v "$WORKSPACE:/repo:ro" \\
          -v "$WORKSPACE/ShortTermPlanning/pyproject.toml:/app/pyproject.toml:ro" \\
          -v "$WORKSPACE/ShortTermPlanning/dynreact/shortterm/short_term_planning.py:/app/shortterm/dynreact/shortterm/short_term_planning.py:ro" \\
          -v "$WORKSPACE/ShortTermPlanning/tests/:/app/shortterm/dynreact/tests/:rw" \\
          -e PYTHONDONTWRITEBYTECODE=1 \\
          -e PYTHONPYCACHEPREFIX=/tmp/pycache \\
          ${envArgs} \\
          --user "0:0" \\
          "${LOCAL_REGISTRY}${IMAGE_NAME}:${IMAGE_TAG}" \\
          bash -lc 'set -euo pipefail
                   source .venv/bin/activate 
                   COMP='ShortTermPlanning' 
                   pip install -r /repo/\$COMP/requirements.txt 
                   [ -f /repo/\$COMP/requirements_local.txt ] && pip install -r /repo/\$COMP/requirements_local.txt || true 
                   [ -f /repo/\$COMP/requirements-dev.txt ] && pip install -r /repo/\$COMP/requirements-dev.txt || true 

                   command -v pytest >/dev/null 2>&1 || python -m pip install pytest
                   cd /app/shortterm/dynreact/tests/integration_test 
                   pytest -s -p no:cacheprovider test_auction.py::test_scenario_06
         '
        """
    }

    stage('Run Scenario 7') {
        def vars = ['KAFKA_IP', 'LOG_FILE_PATH', 'REST_URL', 'TOPIC_CALLBACK', 'TOPIC_GEN', 'SNAPSHOT_VERSION', 'CONTAINER_NAME_PREFIX']
        def envArgs = vars.collect { varName -> "-e ${varName}=\"${env.getProperty(varName)}\"" }.join(' ')
        sh """
        # Run container to execute tests
        docker run --rm \\
          --network host \\
          -v /var/run/docker.sock:/var/run/docker.sock:rw \\
          -v "$WORKSPACE:/repo:ro" \\
          -v "$WORKSPACE/ShortTermPlanning/pyproject.toml:/app/pyproject.toml:ro" \\
          -v "$WORKSPACE/ShortTermPlanning/dynreact/shortterm/short_term_planning.py:/app/shortterm/dynreact/shortterm/short_term_planning.py:ro" \\
          -v "$WORKSPACE/ShortTermPlanning/tests/:/app/shortterm/dynreact/tests/:rw" \\
          -e PYTHONDONTWRITEBYTECODE=1 \\
          -e PYTHONPYCACHEPREFIX=/tmp/pycache \\
          ${envArgs} \\
          --user "0:0" \\
          "${LOCAL_REGISTRY}${IMAGE_NAME}:${IMAGE_TAG}" \\
          bash -lc 'set -euo pipefail
                   source .venv/bin/activate 
                   COMP='ShortTermPlanning' 
                   pip install -r /repo/\$COMP/requirements.txt 
                   [ -f /repo/\$COMP/requirements_local.txt ] && pip install -r /repo/\$COMP/requirements_local.txt || true 
                   [ -f /repo/\$COMP/requirements-dev.txt ] && pip install -r /repo/\$COMP/requirements-dev.txt || true 

                   command -v pytest >/dev/null 2>&1 || python -m pip install pytest
                   cd /app/shortterm/dynreact/tests/integration_test 
                   pytest -s -p no:cacheprovider test_auction.py::test_scenario_07
         '
        """
    }

    stage('Run Scenario 8') {
        def vars = ['KAFKA_IP', 'LOG_FILE_PATH', 'REST_URL', 'TOPIC_CALLBACK', 'TOPIC_GEN', 'SNAPSHOT_VERSION', 'CONTAINER_NAME_PREFIX']
        def envArgs = vars.collect { varName -> "-e ${varName}=\"${env.getProperty(varName)}\"" }.join(' ')
        sh """
        # Run container to execute tests
        docker run --rm \\
          --network host \\
          -v /var/run/docker.sock:/var/run/docker.sock:rw \\
          -v "$WORKSPACE:/repo:ro" \\
          -v "$WORKSPACE/ShortTermPlanning/pyproject.toml:/app/pyproject.toml:ro" \\
          -v "$WORKSPACE/ShortTermPlanning/dynreact/shortterm/short_term_planning.py:/app/shortterm/dynreact/shortterm/short_term_planning.py:ro" \\
          -v "$WORKSPACE/ShortTermPlanning/tests/:/app/shortterm/dynreact/tests/:rw" \\
          -e PYTHONDONTWRITEBYTECODE=1 \\
          -e PYTHONPYCACHEPREFIX=/tmp/pycache \\
          ${envArgs} \\
          --user "0:0" \\
          "${LOCAL_REGISTRY}${IMAGE_NAME}:${IMAGE_TAG}" \\
          bash -lc 'set -euo pipefail
                   source .venv/bin/activate 
                   COMP='ShortTermPlanning' 
                   pip install -r /repo/\$COMP/requirements.txt 
                   [ -f /repo/\$COMP/requirements_local.txt ] && pip install -r /repo/\$COMP/requirements_local.txt || true 
                   [ -f /repo/\$COMP/requirements-dev.txt ] && pip install -r /repo/\$COMP/requirements-dev.txt || true 

                   command -v pytest >/dev/null 2>&1 || python -m pip install pytest
                   cd /app/shortterm/dynreact/tests/integration_test 
                   pytest -s -p no:cacheprovider test_auction.py::test_scenario_08
         '
        """
    }
  }
}

