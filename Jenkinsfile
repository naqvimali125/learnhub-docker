pipeline {
    agent any

    triggers { githubPush() }

    stages {
        stage('Checkout') {
            steps {
                git branch: 'main', url: 'https://github.com/naqvimali125/learnhub-docker.git'
            }
        }

        stage('Syntax check in container') {
            agent {
                docker {
                    image 'python:3.12-slim'
                    reuseNode true
                }
            }
            steps {
                sh '''python -c "import ast,glob; [ast.parse(open(f).read()) for f in glob.glob('**/*.py', recursive=True)]; print('Python syntax OK')"'''
            }
        }

        stage('Prepare environment') {
            steps {
                sh 'cp -n .env.docker.example .env || true'
            }
        }

        stage('Build and Deploy') {
            steps {
                sh 'docker compose -f docker-compose.jenkins.yml down || true'
                sh 'docker compose -f docker-compose.jenkins.yml up -d'
            }
        }

        stage('Verify') {
            steps {
                sh '''
                for i in $(seq 1 30); do
                  code=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8081/ || true)
                  echo "Attempt $i: HTTP $code"
                  if [ "$code" = "200" ]; then exit 0; fi
                  sleep 6
                done
                docker logs --tail 40 learnhub_ci_web
                exit 1
                '''
            }
        }
    }

    post {
        always {
            script {
                def committer = ''
                try {
                    sh "git config --global --add safe.directory ${env.WORKSPACE}"
                    committer = sh(script: "git log -1 --pretty=format:'%ae'", returnStdout: true).trim()
                } catch (e) {
                    echo 'Could not read the committer email'
                }
                def recipients = ['naqvimali125@gmail.com']
                if (committer.endsWith('noreply.github.com')) {
                    recipients << 'qasimalik@gmail.com'
                } else if (committer != '') {
                    recipients << committer
                }
                emailext(
                    to: recipients.join(','),
                    subject: "LearnHub build #${env.BUILD_NUMBER}: ${currentBuild.currentResult}",
                    body: "Build Status: ${currentBuild.currentResult}\nJob: ${env.JOB_NAME}\nBuild: #${env.BUILD_NUMBER}\nCommit author: ${committer}\nDetails: ${env.BUILD_URL}"
                )
            }
        }
    }
}
