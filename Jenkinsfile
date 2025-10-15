node {
    def IMAGE_NAME = "dynreact-shortterm"
    def IMAGE_TAG = "latest"

    env.TOPIC_CALLBACK = "DynReact-TEST-Callback"
    env.TOPIC_GEN = "DynReact-TEST-Gen"
    env.CONTAINER_NAME_PREFIX = "JENKINS_TEST"

    env.SNAPSHOT_VERSION = "2025-01-18T08:00:00Z"
    env.SCENARIO_4_5_EQUIPMENT = "9" // One Equipment, One Material
    env.SCENARIO_6_EQUIPMENT = "9" // One Equipment, Two Material
    env.SCENARIO_7_EQUIPMENTS = "9 10" // Two Equipments, One Material
    env.SCENARIO_8_EQUIPMENTS = "9 11" // Two Equipments, shared material
    env.SCENARIO_8_ORDER_ID = "1181267"

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
            docker tag ${IMAGE_NAME}:${IMAGE_TAG} ${REGISTRY}${IMAGE_NAME}:${IMAGE_TAG}
            docker push ${REGISTRY}${IMAGE_NAME}:${IMAGE_TAG}
            """
        }

        runStageWithCleanup('Run Scenario 0') {
            def vars = ['KAFKA_IP', 'LOG_FILE_PATH', 'REST_URL', 'TOPIC_CALLBACK', 'TOPIC_GEN', 'SNAPSHOT_VERSION', 'CONTAINER_NAME_PREFIX']
            def envArgs = vars.collect { varName -> "-e ${varName}=\"${env.getProperty(varName)}\"" }.join(' ')
            sh """
            # Run container to execute tests
            docker run --rm \\
              -v /var/run/docker.sock:/var/run/docker.sock:rw \\
              -v "$WORKSPACE/ShortTermPlanning/pyproject.toml:/app/pyproject.toml:ro" \\
              -v "$WORKSPACE/ShortTermPlanning/dynreact/shortterm/short_term_planning.py:/app/shortterm/dynreact/shortterm/short_term_planning.py:ro" \\
              -v "$WORKSPACE/ShortTermPlanning/tests/:/app/shortterm/dynreact/tests/:rw" \\
              ${envArgs} \\
              --user root \\
              "${REGISTRY}${IMAGE_NAME}:${IMAGE_TAG}" \\
              bash -c "source .venv/bin/activate && \\
                       pip install poetry && \\
                       poetry install --no-root && \\
                       cd /app/shortterm/dynreact/tests/integration_test && \\
                       pytest -s test_auction.py::test_scenario_00"
            """
        }

        runStageWithCleanup('Run Scenario 1') {
            def vars = ['KAFKA_IP', 'LOG_FILE_PATH', 'REST_URL', 'TOPIC_CALLBACK', 'TOPIC_GEN', 'SNAPSHOT_VERSION', 'CONTAINER_NAME_PREFIX']
            def envArgs = vars.collect { varName -> "-e ${varName}=\"${env.getProperty(varName)}\"" }.join(' ')
            sh """
            # Run container to execute tests
            docker run --rm \\
              -v /var/run/docker.sock:/var/run/docker.sock:rw \\
              -v "$WORKSPACE/ShortTermPlanning/pyproject.toml:/app/pyproject.toml:ro" \\
              -v "$WORKSPACE/ShortTermPlanning/dynreact/shortterm/short_term_planning.py:/app/shortterm/dynreact/shortterm/short_term_planning.py:ro" \\
              -v "$WORKSPACE/ShortTermPlanning/tests/:/app/shortterm/dynreact/tests/:rw" \\
              -v "/var/log/dynreact-logs:/var/log/dynreact-logs:rw,rshared" \\
              ${envArgs} \\
              --user root \\
              "${REGISTRY}${IMAGE_NAME}:${IMAGE_TAG}" \\
              bash -c "source .venv/bin/activate && \\
                       pip install poetry && \\
                       poetry install --no-root && \\
                       cd /app/shortterm/dynreact/tests/integration_test && \\
                       pytest -s test_auction.py::test_scenario_01"
            """
        }

        runStageWithCleanup('Run Scenario 2') {
            def vars = ['KAFKA_IP', 'LOG_FILE_PATH', 'REST_URL', 'TOPIC_CALLBACK', 'TOPIC_GEN', 'SNAPSHOT_VERSION', 'CONTAINER_NAME_PREFIX']
            def envArgs = vars.collect { varName -> "-e ${varName}=\"${env.getProperty(varName)}\"" }.join(' ')
            sh """
            # Run container to execute tests
            docker run --rm \\
              -v /var/run/docker.sock:/var/run/docker.sock:rw \\
              -v "$WORKSPACE/ShortTermPlanning/pyproject.toml:/app/pyproject.toml:ro" \\
              -v "$WORKSPACE/ShortTermPlanning/dynreact/shortterm/short_term_planning.py:/app/shortterm/dynreact/shortterm/short_term_planning.py:ro" \\
              -v "$WORKSPACE/ShortTermPlanning/tests/:/app/shortterm/dynreact/tests/:rw" \\
              ${envArgs} \\
              --user root \\
              "${REGISTRY}${IMAGE_NAME}:${IMAGE_TAG}" \\
              bash -c "source .venv/bin/activate && \\
                       pip install poetry && \\
                       poetry install --no-root && \\
                       cd /app/shortterm/dynreact/tests/integration_test && \\
                       pytest -s test_auction.py::test_scenario_02"
            """
        }

        runStageWithCleanup('Run Scenario 3') {
            def vars = ['KAFKA_IP', 'LOG_FILE_PATH', 'REST_URL', 'TOPIC_CALLBACK', 'TOPIC_GEN', 'SNAPSHOT_VERSION', 'CONTAINER_NAME_PREFIX']
            def envArgs = vars.collect { varName -> "-e ${varName}=\"${env.getProperty(varName)}\"" }.join(' ')
            sh """
            # Run container to execute tests
            docker run --rm \\
              -v /var/run/docker.sock:/var/run/docker.sock:rw \\
              -v "$WORKSPACE/ShortTermPlanning/pyproject.toml:/app/pyproject.toml:ro" \\
              -v "$WORKSPACE/ShortTermPlanning/dynreact/shortterm/short_term_planning.py:/app/shortterm/dynreact/shortterm/short_term_planning.py:ro" \\
              -v "$WORKSPACE/ShortTermPlanning/tests/:/app/shortterm/dynreact/tests/:rw" \\
              ${envArgs} \\
              --user root \\
              "${REGISTRY}${IMAGE_NAME}:${IMAGE_TAG}" \\
              bash -c "source .venv/bin/activate && \\
                       pip install poetry && \\
                       poetry install --no-root && \\
                       cd /app/shortterm/dynreact/tests/integration_test && \\
                       pytest -s test_auction.py::test_scenario_03"
            """
        }

        runStageWithCleanup('Run Scenario 4') {
            def vars = ['KAFKA_IP', 'LOG_FILE_PATH', 'REST_URL', 'TOPIC_CALLBACK', 'TOPIC_GEN', 'SNAPSHOT_VERSION', 'SCENARIO_4_5_EQUIPMENT', 'CONTAINER_NAME_PREFIX']
            def envArgs = vars.collect { varName -> "-e ${varName}=\"${env.getProperty(varName)}\"" }.join(' ')
            sh """
            # Run container to execute tests
            docker run --rm \\
              -v /var/run/docker.sock:/var/run/docker.sock:rw \\
              -v "$WORKSPACE/ShortTermPlanning/pyproject.toml:/app/pyproject.toml:ro" \\
              -v "$WORKSPACE/ShortTermPlanning/dynreact/shortterm/short_term_planning.py:/app/shortterm/dynreact/shortterm/short_term_planning.py:ro" \\
              -v "$WORKSPACE/ShortTermPlanning/tests/:/app/shortterm/dynreact/tests/:rw" \\
              ${envArgs} \\
              --user root \\
              "${REGISTRY}${IMAGE_NAME}:${IMAGE_TAG}" \\
              bash -c "source .venv/bin/activate && \\
                       pip install poetry && \\
                       poetry install --no-root && \\
                       cd /app/shortterm/dynreact/tests/integration_test && \\
                       pytest -s test_auction.py::test_scenario_04"
            """
        }

        stage('Replace BASE agents') {
            def vars = ['KAFKA_IP', 'LOG_FILE_PATH', 'REST_URL']
            def envArgs = vars.collect { varName -> "-e ${varName}=\"${env.getProperty(varName)}\"" }.join(' ')
            sh """
            # Run container to execute tests
            docker run --rm \\
              -v /var/run/docker.sock:/var/run/docker.sock:rw \\
              -v "$WORKSPACE/ShortTermPlanning/dynreact/shortterm/replace_base.py:/app/shortterm/__main__.py:ro" \\
              -v "$WORKSPACE/ShortTermPlanning/dynreact/shortterm/short_term_planning.py:/app/shortterm/dynreact/shortterm/short_term_planning.py:ro" \\
              ${envArgs} \\
              --user root \\
              "${REGISTRY}${IMAGE_NAME}:${IMAGE_TAG}" \\
               python -m shortterm -v 3 -g 111
            """
        }

        stage('Run Scenario 5') {
            def vars = ['KAFKA_IP', 'LOG_FILE_PATH', 'REST_URL', 'SNAPSHOT_VERSION', 'SCENARIO_4_5_EQUIPMENT', 'LOCAL_REGISTRY']
            def envArgs = vars.collect { varName -> "-e ${varName}=\"${env.getProperty(varName)}\"" }.join(' ')
            sh """
            # Run container to execute tests
            docker run --rm \\
              -v /var/run/docker.sock:/var/run/docker.sock:rw \\
              -v "$WORKSPACE/ShortTermPlanning/pyproject.toml:/app/pyproject.toml:ro" \\
              -v "$WORKSPACE/ShortTermPlanning/dynreact/shortterm/short_term_planning.py:/app/shortterm/dynreact/shortterm/short_term_planning.py:ro" \\
              -v "$WORKSPACE/ShortTermPlanning/tests/:/app/shortterm/dynreact/tests/:rw" \\
              ${envArgs} \\
              --user root \\
              "${REGISTRY}${IMAGE_NAME}:${IMAGE_TAG}" \\
              bash -c "source .venv/bin/activate && \\
                       pip install poetry && \\
                       poetry install --no-root && \\
                       cd /app/shortterm/dynreact/tests/integration_test && \\
                       pytest -s test_auction.py::test_scenario_05"
            """
        }

        stage('Run Scenario 6') {
            def vars = ['KAFKA_IP', 'LOG_FILE_PATH', 'REST_URL', 'SNAPSHOT_VERSION', 'SCENARIO_6_EQUIPMENT', 'LOCAL_REGISTRY']
            def envArgs = vars.collect { varName -> "-e ${varName}=\"${env.getProperty(varName)}\"" }.join(' ')
            sh """
            # Run container to execute tests
            docker run --rm \\
              -v /var/run/docker.sock:/var/run/docker.sock:rw \\
              -v "$WORKSPACE/ShortTermPlanning/pyproject.toml:/app/pyproject.toml:ro" \\
              -v "$WORKSPACE/ShortTermPlanning/dynreact/shortterm/short_term_planning.py:/app/shortterm/dynreact/shortterm/short_term_planning.py:ro" \\
              -v "$WORKSPACE/ShortTermPlanning/tests/:/app/shortterm/dynreact/tests/:rw" \\
              ${envArgs} \\
              --user root \\
              "${REGISTRY}${IMAGE_NAME}:${IMAGE_TAG}" \\
              bash -c "source .venv/bin/activate && \\
                       pip install poetry && \\
                       poetry install --no-root && \\
                       cd /app/shortterm/dynreact/tests/integration_test && \\
                       pytest -s test_auction.py::test_scenario_06"
            """
        }

        stage('Run Scenario 7') {
            def vars = ['KAFKA_IP', 'LOG_FILE_PATH', 'REST_URL', 'SNAPSHOT_VERSION', 'SCENARIO_7_EQUIPMENTS', 'LOCAL_REGISTRY']
            def envArgs = vars.collect { varName -> "-e ${varName}=\"${env.getProperty(varName)}\"" }.join(' ')
            sh """
            # Run container to execute tests
            docker run --rm \\
              -v /var/run/docker.sock:/var/run/docker.sock:rw \\
              -v "$WORKSPACE/ShortTermPlanning/pyproject.toml:/app/pyproject.toml:ro" \\
              -v "$WORKSPACE/ShortTermPlanning/dynreact/shortterm/short_term_planning.py:/app/shortterm/dynreact/shortterm/short_term_planning.py:ro" \\
              -v "$WORKSPACE/ShortTermPlanning/tests/:/app/shortterm/dynreact/tests/:rw" \\
              ${envArgs} \\
              --user root \\
              "${REGISTRY}${IMAGE_NAME}:${IMAGE_TAG}" \\
              bash -c "source .venv/bin/activate && \\
                       pip install poetry && \\
                       poetry install --no-root && \\
                       cd /app/shortterm/dynreact/tests/integration_test && \\
                       pytest -s test_auction.py::test_scenario_07"
            """
        }

        stage('Run Scenario 8') {
            def vars = ['KAFKA_IP', 'LOG_FILE_PATH', 'REST_URL', 'SNAPSHOT_VERSION', 'SCENARIO_8_EQUIPMENTS', 'SCENARIO_8_ORDER_ID', 'LOCAL_REGISTRY']
            def envArgs = vars.collect { varName -> "-e ${varName}=\"${env.getProperty(varName)}\"" }.join(' ')
            sh """
            # Run container to execute tests
            docker run --rm \\
              -v /var/run/docker.sock:/var/run/docker.sock:rw \\
              -v "$WORKSPACE/ShortTermPlanning/pyproject.toml:/app/pyproject.toml:ro" \\
              -v "$WORKSPACE/ShortTermPlanning/dynreact/shortterm/short_term_planning.py:/app/shortterm/dynreact/shortterm/short_term_planning.py:ro" \\
              -v "$WORKSPACE/ShortTermPlanning/tests/:/app/shortterm/dynreact/tests/:rw" \\
              ${envArgs} \\
              --user root \\
              "${REGISTRY}${IMAGE_NAME}:${IMAGE_TAG}" \\
              bash -c "source .venv/bin/activate && \\
                       python3 -m pip install --retries 5 --timeout 120  poetry==2.1.1 && \\
                       poetry install --no-root --no-ansi && \\
                       cd /app/shortterm/dynreact/tests/integration_test && \\
                       pytest -s test_auction.py::test_scenario_08"
            """
        }
    }
}
