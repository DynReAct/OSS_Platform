pipeline {
    agent any

    environment {
        IMAGE_NAME = "dynreact-shortterm"
        IMAGE_TAG = "latest"
        LOCAL_REGISTRY = "192.168.110.176:5000/"

        TOPIC_CALLBACK = "DynReact-TEST-Callback"
        TOPIC_GEN = "DynReact-TEST-Gen"

        SNAPSHOT_VERSION = "2025-01-18T10:00:00Z"
        SCENARIO_5_EQUIPMENT = "9" // One Equipment, One Material
        SCENARIO_6_EQUIPMENT = "9" // One Equipment, Two Material
        SCENARIO_7_EQUIPMENTS = "9 10" // Two Equipments, One Material
        SCENARIO_8_EQUIPMENTS = "9 11" // Two Equipments, shared material
        SCENARIO_8_ORDER_ID = "1199061"
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Build Docker Image') {
            steps {
                script {
                    sh """
                    cd ShortTermPlanning
                    docker build -t ${IMAGE_NAME}:${IMAGE_TAG} .
                    """
                }
            }
        }

        stage('Tag & Push Image') {
            steps {
                script {
                    sh """
                    docker tag ${IMAGE_NAME}:${IMAGE_TAG} ${LOCAL_REGISTRY}${IMAGE_NAME}:${IMAGE_TAG}
                    docker push ${LOCAL_REGISTRY}${IMAGE_NAME}:${IMAGE_TAG}
                    """
                }
            }
        }

        stage('Run Scenario 0') {
            steps {
                script {
                    sh """
                    # Run container to execute tests
                    docker run --rm \\
                      -v /var/run/docker.sock:/var/run/docker.sock:rw \\
                      -v "$WORKSPACE/ShortTermPlanning/pyproject.toml:/app/pyproject.toml:ro" \\
                      -v "$WORKSPACE/ShortTermPlanning/dynreact/shortterm/short_term_planning.py:/app/shortterm/short_term_planning.py:ro" \\
                      -v "$WORKSPACE/ShortTermPlanning/tests/:/app/tests/:rw" \\
                      --user root \\
                      "${LOCAL_REGISTRY}${IMAGE_NAME}:${IMAGE_TAG}" \\
                      bash -c "source .venv/bin/activate && \\
                               pip install poetry && \\
                               poetry install --no-root && \\
                               cd /app/tests/integration_test && \\
                               pytest -s test_auction.py::test_scenario_00"
                    """
                }
            }
        }

        stage('Run Scenario 1') {
            steps {
                script {
                    sh """
                    # Run container to execute tests
                    docker run --rm \\
                      -v /var/run/docker.sock:/var/run/docker.sock:rw \\
                      -v "$WORKSPACE/ShortTermPlanning/pyproject.toml:/app/pyproject.toml:ro" \\
                      -v "$WORKSPACE/ShortTermPlanning/dynreact/shortterm/short_term_planning.py:/app/shortterm/short_term_planning.py:ro" \\
                      -v "$WORKSPACE/ShortTermPlanning/tests/:/app/tests/:rw" \\
                      --user root \\
                      "${LOCAL_REGISTRY}${IMAGE_NAME}:${IMAGE_TAG}" \\
                      bash -c "source .venv/bin/activate && \\
                               pip install poetry && \\
                               poetry install --no-root && \\
                               cd /app/tests/integration_test && \\
                               pytest -s test_auction.py::test_scenario_01"
                    """
                }
            }
        }

        stage('Run Scenario 2') {
            steps {
                script {
                    sh """
                    # Run container to execute tests
                    docker run --rm \\
                      -v /var/run/docker.sock:/var/run/docker.sock:rw \\
                      -v "$WORKSPACE/ShortTermPlanning/pyproject.toml:/app/pyproject.toml:ro" \\
                      -v "$WORKSPACE/ShortTermPlanning/dynreact/shortterm/short_term_planning.py:/app/shortterm/short_term_planning.py:ro" \\
                      -v "$WORKSPACE/ShortTermPlanning/tests/:/app/tests/:rw" \\
                      --user root \\
                      "${LOCAL_REGISTRY}${IMAGE_NAME}:${IMAGE_TAG}" \\
                      bash -c "source .venv/bin/activate && \\
                               pip install poetry && \\
                               poetry install --no-root && \\
                               cd /app/tests/integration_test && \\
                               pytest -s test_auction.py::test_scenario_02"
                    """
                }
            }
        }

        stage('Run Scenario 3') {
            steps {
                script {
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
                               pytest -s test_auction.py::test_scenario_03"
                    """
                }
            }
        }

        stage('Run Scenario 5') {
            steps {
                script {
                    def vars = ['TOPIC_CALLBACK', 'TOPIC_GEN', 'SNAPSHOT_VERSION', 'SCENARIO_5_EQUIPMENT']
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
                               pytest -s test_auction.py::test_scenario_05"
                    """
                }
            }
        }

        stage('Run Scenario 6') {
            steps {
                script {
                    def vars = ['TOPIC_CALLBACK', 'TOPIC_GEN', 'SNAPSHOT_VERSION', 'SCENARIO_6_EQUIPMENT']
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
                               pytest -s test_auction.py::test_scenario_06"
                    """
                }
            }
        }

        stage('Run Scenario 7') {
            steps {
                script {
                    def vars = ['TOPIC_CALLBACK', 'TOPIC_GEN', 'SNAPSHOT_VERSION', 'SCENARIO_7_EQUIPMENT']
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
                               pytest -s test_auction.py::test_scenario_07"
                    """
                }
            }
        }

        stage('Run Scenario 8') {
            steps {
                script {
                    def vars = ['TOPIC_CALLBACK', 'TOPIC_GEN', 'SNAPSHOT_VERSION', 'SCENARIO_8_EQUIPMENT', 'SCENARIO_8_ORDER_ID']
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
                               pytest -s test_auction.py::test_scenario_08"
                    """
                }
            }
        }
    }

    post {
        success {
            sh "docker system prune -f"
            echo "Docker image successfully pushed to ${LOCAL_REGISTRY}${IMAGE_NAME}:${IMAGE_TAG}"
        }
        failure {
            echo "Build failed. Check logs for errors."
        }
    }
}
