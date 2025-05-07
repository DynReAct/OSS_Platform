node {
    def IMAGE_NAME = "dynreact-shortterm"
    def IMAGE_TAG = "latest"
    def LOCAL_REGISTRY = "192.168.110.176:5000/"

    env.TOPIC_CALLBACK = "DynReact-TEST-Callback"
    env.TOPIC_GEN = "DynReact-TEST-Gen"

    env.SNAPSHOT_VERSION = "2025-01-18T08:00:00Z"
    env.SCENARIO_5_EQUIPMENT = "9" // One Equipment, One Material
    env.SCENARIO_6_EQUIPMENT = "9" // One Equipment, Two Material
    env.SCENARIO_7_EQUIPMENTS = "9 10" // Two Equipments, One Material
    env.SCENARIO_8_EQUIPMENTS = "9 11" // Two Equipments, shared material
    env.SCENARIO_8_ORDER_ID = "1199061"

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
        docker build -t ${IMAGE_NAME}:${IMAGE_TAG} .
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
        def envArgs = vars.collect { varName -> "-e ${varName}=${env.getProperty(varName)}" }.join(' ')
        sh """
        # Run container to execute tests
        docker run --rm \\
          -v /var/run/docker.sock:/var/run/docker.sock:rw \\
          -v "$WORKSPACE/ShortTermPlanning/pyproject.toml:/app/pyproject.toml:ro" \\
          -v "$WORKSPACE/ShortTermPlanning/dynreact/shortterm/short_term_planning.py:/app/shortterm/short_term_planning.py:ro" \\
          -v "$WORKSPACE/ShortTermPlanning/tests/:/app/tests/:rw" \\
          ${envArgs} \\
          --user root \\
          "${LOCAL_REGISTRY}${IMAGE_NAME}:${IMAGE_TAG}" \\
          bash -c "source .venv/bin/activate && \\
                   pip install poetry && \\
                   poetry install --no-root && \\
                   cd /app/tests/integration_test && \\
                   pytest -s test_auction.py::test_scenario_00"
        """
    }

    stage('Final Cleanup') {
        sh "docker system prune -f"
    }
}
