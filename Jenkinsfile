// ─────────────────────────────────────────────────────────────────────────────
// Jenkins CI Pipeline for Analytical Data Products
// Validates, lints, tests, and packages data product artifacts.
// ─────────────────────────────────────────────────────────────────────────────

pipeline {
    agent { label 'glue-builder' }

    parameters {
        string(
            name: 'PRODUCT_NAME',
            description: 'Analytical Data Product name (e.g., monthly_revenue_by_category)',
            trim: true
        )
        choice(
            name: 'ENV',
            choices: ['dev', 'staging', 'prod'],
            description: 'Target environment'
        )
    }

    environment {
        AWS_REGION      = 'us-east-1'
        ARTIFACT_BUCKET = "adp-artifacts-${params.ENV}"
        PRODUCT_NAME    = "${params.PRODUCT_NAME}"
        AWS_CREDENTIALS = credentials('aws-adp-credentials')
    }

    options {
        buildDiscarder(logRotator(numToKeepStr: '20'))
        timestamps()
        timeout(time: 30, unit: 'MINUTES')
        disableConcurrentBuilds()
    }

    stages {
        // ── Checkout ────────────────────────────────────────────────────────
        stage('Checkout') {
            steps {
                checkout scm
                echo "Building ${PRODUCT_NAME} for ${params.ENV} (build #${BUILD_NUMBER})"
            }
        }

        // ── Validate Config ─────────────────────────────────────────────────
        stage('Validate Config') {
            steps {
                sh '''
                    python -m pip install --quiet pyyaml jsonschema
                    python scripts/validate_config.py \
                        configs/${PRODUCT_NAME}.yaml \
                        schemas/pipeline_config_schema.json
                '''
            }
        }

        // ── Lint ────────────────────────────────────────────────────────────
        stage('Lint') {
            parallel {
                stage('Flake8') {
                    steps {
                        sh '''
                            python -m pip install --quiet flake8
                            flake8 pipelines/${PRODUCT_NAME}/ \
                                --max-line-length=120 \
                                --statistics \
                                --count
                        '''
                    }
                }
                stage('Bandit') {
                    steps {
                        sh '''
                            python -m pip install --quiet bandit
                            bandit -r pipelines/${PRODUCT_NAME}/ \
                                -ll \
                                -f json \
                                -o bandit-report.json || true
                            bandit -r pipelines/${PRODUCT_NAME}/ -ll
                        '''
                    }
                }
            }
        }

        // ── Unit Test ───────────────────────────────────────────────────────
        stage('Unit Test') {
            steps {
                sh '''
                    python -m pip install --quiet pytest pyspark
                    pytest tests/${PRODUCT_NAME}/ \
                        -v \
                        --junitxml=test-results.xml \
                        --tb=short
                '''
            }
            post {
                always {
                    junit allowEmptyResults: true, testResults: 'test-results.xml'
                }
            }
        }

        // ── Terraform Validate ──────────────────────────────────────────────
        stage('Terraform Validate') {
            steps {
                dir("terraform/environments/${params.ENV}") {
                    sh '''
                        terraform init -backend=false -input=false
                        terraform validate
                        terraform fmt -check -recursive
                    '''
                }
            }
        }

        // ── Package Artifacts ───────────────────────────────────────────────
        stage('Package Artifacts') {
            steps {
                sh '''
                    mkdir -p dist/scripts dist/step_functions dist/lambdas dist/config

                    # Copy pipeline code
                    cp -v pipelines/${PRODUCT_NAME}/glue_jobs/*.py dist/scripts/ 2>/dev/null || true
                    cp -v pipelines/${PRODUCT_NAME}/emr_jobs/*.py dist/scripts/ 2>/dev/null || true
                    cp -v pipelines/${PRODUCT_NAME}/ecs_tasks/*.py dist/scripts/ 2>/dev/null || true
                    cp -v pipelines/${PRODUCT_NAME}/step_functions/*.json dist/step_functions/ 2>/dev/null || true
                    cp -v pipelines/${PRODUCT_NAME}/lambdas/*.py dist/lambdas/ 2>/dev/null || true
                    cp -v configs/${PRODUCT_NAME}.yaml dist/config/

                    # Upload to S3
                    aws s3 sync dist/ \
                        s3://${ARTIFACT_BUCKET}/artifacts/${PRODUCT_NAME}/${BUILD_NUMBER}/ \
                        --region ${AWS_REGION}
                '''
                stash includes: 'dist/**', name: 'build-artifacts'
            }
        }

        // ── Terraform Plan ──────────────────────────────────────────────────
        stage('Terraform Plan') {
            steps {
                dir("terraform/environments/${params.ENV}") {
                    sh """
                        terraform init \
                            -backend-config=backend-${params.ENV}.hcl \
                            -input=false \
                            -reconfigure

                        terraform plan \
                            -var="product_name=${PRODUCT_NAME}" \
                            -out=tfplan \
                            -input=false
                    """
                }
                archiveArtifacts artifacts: "terraform/environments/${params.ENV}/tfplan", fingerprint: true
            }
        }
    }

    post {
        success {
            echo "CI Build #${BUILD_NUMBER} SUCCEEDED for ${PRODUCT_NAME} (${params.ENV})"
        }
        failure {
            echo "CI Build #${BUILD_NUMBER} FAILED for ${PRODUCT_NAME} (${params.ENV})"
        }
        always {
            cleanWs()
        }
    }
}
